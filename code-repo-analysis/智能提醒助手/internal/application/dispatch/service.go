package dispatch

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

const (
	// todayTaskDeepLink 是 Push 的落地页标识，与技术方案「落到今日任务页」和 IDL 示例一致。
	todayTaskDeepLink = "today_task_page"
	// defaultBatchSize 与 maxBatchSize 对应技术方案 4.7 的 dispatch_batch_size=50。
	defaultBatchSize = 50
	maxBatchSize     = 50
	// defaultMaxSendAttempts 对应 4.7 的 max_send_attempts=2，即明确失败最多重试一次。
	defaultMaxSendAttempts = 2
)

// Request 是到期发送批次入参；BatchSize 为 0 时取配置默认值。
type Request struct {
	BatchSize int
}

// Result 是按 DispatchDueResponse 口径统计的批次结果，只含计数，不含用户级明细。
type Result struct {
	Scanned   int
	Claimed   int
	Sent      int
	Cancelled int
	Failed    int
	Unknown   int
	Retried   int
	Finished  bool
}

// Service 组织到期发送：抢占、频控与 Push 可用性判定、发送与重试、状态回写和投递事件。
// 发送前的任务状态二次校验属于 FR-004，不在本轮实现。
type Service struct {
	Reminders   port.ReminderRepository
	Preferences port.PreferenceRepository
	Renderer    port.ContentRenderer
	Push        port.PushSender
	Clock       port.Clock
	// MaxPushPerDay 是系统主动 Push 每日上限的默认值，用户设置优先。
	MaxPushPerDay int
	// MaxSendAttempts 是单条排程的最大发送尝试次数，默认 2。
	MaxSendAttempts int
	// BatchSize 是每批次处理的到期排程上限，硬上限 50。
	BatchSize int
}

// DispatchDue 处理一批到期排程。业务性结束（取消、失败终态、未知状态）计入计数并继续；
// 依赖或数据库错误返回 error，由调用方重放同一批次。
func (s Service) DispatchDue(ctx context.Context, request Request) (Result, error) {
	batchSize := request.BatchSize
	if batchSize == 0 {
		batchSize = s.batchSize()
	}
	if batchSize < 1 || batchSize > maxBatchSize {
		return Result{}, fmt.Errorf("batch_size must be between 1 and %d", maxBatchSize)
	}
	now := s.Clock.Now()
	due, err := s.Reminders.ListDueSchedules(ctx, now, batchSize)
	if err != nil {
		return Result{}, fmt.Errorf("list due schedules: %w", err)
	}
	counts := Result{Scanned: len(due)}
	for index := range due {
		if err := s.process(ctx, due[index], now, &counts); err != nil {
			return counts, err
		}
	}
	counts.Finished = true
	return counts, nil
}

// process 处理单条到期排程。抢占失败表示排程已被其他 worker 处理或状态已变化，
// 当前 worker 直接结束，不重复调用渠道。
func (s Service) process(ctx context.Context, candidate reminder.Schedule, now time.Time, counts *Result) error {
	claimed, err := s.Reminders.ClaimSchedule(ctx, candidate.ID, now)
	if err != nil {
		if errors.Is(err, port.ErrConditionFailed) {
			return nil
		}
		return fmt.Errorf("claim schedule: %w", err)
	}
	counts.Claimed++
	if err := s.handle(ctx, claimed, now, counts); err != nil {
		// 依赖或数据库错误：释放抢占让排程回到 SCHEDULED，等下一次调度重试，避免 CLAIMED 记录无人回收。
		if releaseErr := s.release(ctx, claimed, now); releaseErr != nil {
			return releaseErr
		}
		return err
	}
	return nil
}

// handle 返回非 nil 表示依赖或数据库错误；业务性结束（取消、失败终态、未知状态）返回 nil。
func (s Service) handle(ctx context.Context, schedule reminder.Schedule, now time.Time, counts *Result) error {
	decision, err := s.Reminders.GetDecision(ctx, schedule.DecisionID)
	if err != nil {
		return fmt.Errorf("read decision: %w", err)
	}
	// 设置是发送前强依赖：读取失败按失败关闭，不发送、不取消，也不沿用旧设置。
	preference, err := s.Preferences.Get(ctx, schedule.UserID)
	if err != nil {
		return fmt.Errorf("read reminder preference: %w", err)
	}
	if !reminder.PushChannelAvailable(preference) {
		// Push 未授权时跳过本次提醒并记录未触达原因，不做渠道降级（站内承接属 P1）。
		return s.cancel(ctx, schedule, decision, preference, reminder.ReasonNoAvailableChannel, now, counts)
	}
	usage, err := s.Reminders.GetDailyUsage(ctx, schedule.UserID, schedule.TaskDate)
	if err != nil {
		return fmt.Errorf("read daily usage: %w", err)
	}
	// 频控在发送前复核：当日系统主动 Push 已达上限时不再发送（AC-005）。
	if verdict := s.guard().Check(usage, preference, schedule.ScheduleType); !verdict.Allowed {
		return s.cancel(ctx, schedule, decision, preference, verdict.Reason, now, counts)
	}
	return s.send(ctx, schedule, decision, preference, now, counts)
}

// send 发送 Push 并按「明确失败最多重试一次」推进：重试复用同一 idempotency_key，
// 不新增排程、不产生第二条业务提醒。
func (s Service) send(ctx context.Context, schedule reminder.Schedule, decision reminder.Decision, preference reminder.ReminderPreference, now time.Time, counts *Result) error {
	content, err := s.Renderer.Render(ctx, reminder.RenderInput{
		UserID:       schedule.UserID,
		DecisionID:   schedule.DecisionID,
		ScheduleID:   schedule.ID,
		ScheduleType: schedule.ScheduleType,
		DeepLink:     todayTaskDeepLink,
	})
	if err != nil {
		return fmt.Errorf("render push content: %w", err)
	}
	delivery := reminder.Delivery{
		ID:             stableID("delivery", reminder.DeliveryIdempotencyKey(schedule)),
		DecisionID:     schedule.DecisionID,
		ScheduleID:     schedule.ID,
		Channel:        schedule.Channel,
		IdempotencyKey: reminder.DeliveryIdempotencyKey(schedule),
	}
	request := reminder.PushRequest{
		IdempotencyKey: delivery.IdempotencyKey,
		UserID:         schedule.UserID,
		DecisionID:     schedule.DecisionID,
		Title:          content.Title,
		Body:           content.Body,
		DeepLink:       content.DeepLink,
		ExpireAt:       reminder.DeliveryExpireAt(schedule.TaskDate, preference.Timezone),
	}
	for attempt := 1; ; attempt++ {
		if err := s.advance(ctx, schedule, reminder.ScheduleSending, attempt, now); err != nil {
			return err
		}
		schedule.Status = reminder.ScheduleSending
		delivery.AttemptNo = attempt
		delivery.Status = reminder.DeliverySending
		if err := s.Reminders.UpdateDeliveryStatus(ctx, delivery); err != nil {
			return fmt.Errorf("record delivery attempt: %w", err)
		}
		request.AttemptNo = attempt
		outcome, err := s.Push.Send(ctx, request)
		if err != nil {
			// 渠道调用异常按未知状态处理：先查询收敛，不立即重发。
			return s.resolveUnknown(ctx, schedule, decision, preference, delivery, now, counts)
		}
		retryAllowed := reminder.RetryAllowed(attempt, s.maxSendAttempts())
		switch reminder.DeliveryStatusOf(outcome) {
		case reminder.DeliverySent:
			return s.markSent(ctx, schedule, decision, preference, delivery, outcome, attempt, now, counts)
		case reminder.DeliveryFailed:
			delivery.ProviderCode = outcome.ProviderCode
			delivery.ErrorCode = outcome.ErrorCode
			if retryAllowed {
				// 明确失败且仍有重试额度：记录 will_retry=true，同一幂等键再试一次。
				counts.Retried++
				if err := s.publish(ctx, decision, preference, schedule, "reminder_failed", attempt, now, map[string]any{
					"attempt_no": attempt,
					"error_code": outcome.ErrorCode,
					"will_retry": true,
				}); err != nil {
					return err
				}
				if err := s.advance(ctx, schedule, reminder.ScheduleRetryWait, attempt, now); err != nil {
					return err
				}
				schedule.Status = reminder.ScheduleRetryWait
				continue
			}
			return s.markFailed(ctx, schedule, decision, preference, delivery, attempt, now, counts)
		default:
			return s.resolveUnknown(ctx, schedule, decision, preference, delivery, now, counts)
		}
	}
}

// markSent 落库明确成功：投递记录置 SENT、排程置终态，并产生 reminder_sent 事件。
func (s Service) markSent(ctx context.Context, schedule reminder.Schedule, decision reminder.Decision, preference reminder.ReminderPreference, delivery reminder.Delivery, outcome reminder.PushResult, attempt int, now time.Time, counts *Result) error {
	sentAt := outcome.SentAt
	if sentAt.IsZero() {
		sentAt = now
	}
	delivery.Status = reminder.DeliverySent
	delivery.ProviderCode = outcome.ProviderCode
	delivery.ErrorCode = ""
	delivery.SentAt = &sentAt
	if err := s.Reminders.UpdateDeliveryStatus(ctx, delivery); err != nil {
		return fmt.Errorf("record delivery status: %w", err)
	}
	if err := s.advance(ctx, schedule, reminder.ScheduleSent, attempt, now); err != nil {
		return err
	}
	counts.Sent++
	return s.publish(ctx, decision, preference, schedule, "reminder_sent", attempt, now, map[string]any{
		"attempt_no":      attempt,
		"delivery_status": string(reminder.DeliverySent),
	})
}

// markFailed 落库重试耗尽的明确失败：投递记录与排程置 FAILED，产生 will_retry=false 事件。
func (s Service) markFailed(ctx context.Context, schedule reminder.Schedule, decision reminder.Decision, preference reminder.ReminderPreference, delivery reminder.Delivery, attempt int, now time.Time, counts *Result) error {
	delivery.Status = reminder.DeliveryFailed
	if err := s.Reminders.UpdateDeliveryStatus(ctx, delivery); err != nil {
		return fmt.Errorf("record delivery status: %w", err)
	}
	if err := s.advance(ctx, schedule, reminder.ScheduleFailed, attempt, now); err != nil {
		return err
	}
	counts.Failed++
	return s.publish(ctx, decision, preference, schedule, "reminder_failed", attempt, now, map[string]any{
		"attempt_no": attempt,
		"error_code": delivery.ErrorCode,
		"will_retry": false,
	})
}

// resolveUnknown 处理渠道未知状态或调用异常：标记 UNKNOWN、调用一次查询接口收敛，
// 查询前禁止再次发送；无法确认时保留 UNKNOWN 交给 reconcile，不产生第二次业务提醒。
func (s Service) resolveUnknown(ctx context.Context, schedule reminder.Schedule, decision reminder.Decision, preference reminder.ReminderPreference, delivery reminder.Delivery, now time.Time, counts *Result) error {
	delivery.Status = reminder.DeliveryUnknown
	if err := s.Reminders.UpdateDeliveryStatus(ctx, delivery); err != nil {
		return fmt.Errorf("record delivery status: %w", err)
	}
	queried, err := s.Push.Query(ctx, reminder.DeliveryQuery{
		IdempotencyKey: delivery.IdempotencyKey,
		DecisionID:     delivery.DecisionID,
		AttemptNo:      delivery.AttemptNo,
	})
	if err != nil {
		return s.markUnknown(ctx, schedule, decision, preference, delivery, now, counts)
	}
	switch queried {
	case reminder.DeliverySent:
		outcome := reminder.PushResult{Status: string(reminder.DeliverySent), ProviderCode: delivery.ProviderCode}
		return s.markSent(ctx, schedule, decision, preference, delivery, outcome, delivery.AttemptNo, now, counts)
	case reminder.DeliveryFailed:
		return s.markFailed(ctx, schedule, decision, preference, delivery, delivery.AttemptNo, now, counts)
	default:
		return s.markUnknown(ctx, schedule, decision, preference, delivery, now, counts)
	}
}

// markUnknown 保留 UNKNOWN 状态交给 reconcile，并按投递口径补一条 reminder_sent 事件。
func (s Service) markUnknown(ctx context.Context, schedule reminder.Schedule, decision reminder.Decision, preference reminder.ReminderPreference, delivery reminder.Delivery, now time.Time, counts *Result) error {
	if err := s.advance(ctx, schedule, reminder.ScheduleUnknown, delivery.AttemptNo, now); err != nil {
		return err
	}
	counts.Unknown++
	return s.publish(ctx, decision, preference, schedule, "reminder_sent", delivery.AttemptNo, now, map[string]any{
		"attempt_no":      delivery.AttemptNo,
		"delivery_status": string(reminder.DeliveryUnknown),
		"error_code":      delivery.ErrorCode,
	})
}

// cancel 取消本次发送：写排程取消终态、记录未触达或拦截原因，并产生 reminder_cancelled 事件。
func (s Service) cancel(ctx context.Context, schedule reminder.Schedule, decision reminder.Decision, preference reminder.ReminderPreference, reason reminder.ReasonCode, now time.Time, counts *Result) error {
	previous := string(schedule.Status)
	if err := s.Reminders.UpdateSchedule(ctx, reminder.ScheduleUpdate{
		ScheduleID:   schedule.ID,
		FromStatus:   schedule.Status,
		ToStatus:     reminder.ScheduleCancelled,
		AttemptNo:    schedule.AttemptNo,
		CancelReason: reason,
		UpdatedAt:    now,
	}); err != nil && !errors.Is(err, port.ErrConditionFailed) {
		return fmt.Errorf("cancel schedule: %w", err)
	}
	counts.Cancelled++
	return s.publish(ctx, decision, preference, schedule, "reminder_cancelled", 0, now, map[string]any{
		"cancel_reason":   string(reason),
		"previous_status": previous,
		"cancelled_at":    now.UTC().Format(time.RFC3339),
	})
}

// release 把抢占中的排程释放回 SCHEDULED，等待下一次调度重试；已写入的投递记录保留。
func (s Service) release(ctx context.Context, schedule reminder.Schedule, now time.Time) error {
	err := s.Reminders.UpdateSchedule(ctx, reminder.ScheduleUpdate{
		ScheduleID: schedule.ID,
		FromStatus: reminder.ScheduleClaimed,
		ToStatus:   reminder.ScheduleScheduled,
		AttemptNo:  schedule.AttemptNo,
		UpdatedAt:  now,
	})
	if err != nil && !errors.Is(err, port.ErrConditionFailed) {
		return fmt.Errorf("release schedule: %w", err)
	}
	return nil
}

// advance 以条件更新推进排程状态；状态已被其他执行者推进时放弃本次动作，不重复调用渠道。
func (s Service) advance(ctx context.Context, schedule reminder.Schedule, to reminder.ScheduleStatus, attemptNo int, now time.Time) error {
	err := s.Reminders.UpdateSchedule(ctx, reminder.ScheduleUpdate{
		ScheduleID: schedule.ID,
		FromStatus: schedule.Status,
		ToStatus:   to,
		AttemptNo:  attemptNo,
		UpdatedAt:  now,
	})
	if err != nil && !errors.Is(err, port.ErrConditionFailed) {
		return fmt.Errorf("update schedule: %w", err)
	}
	return nil
}

// publish 组装事件信封并落库；event_id 由决策、排程、事件名和尝试序号推导，重复执行按唯一键幂等。
func (s Service) publish(ctx context.Context, decision reminder.Decision, preference reminder.ReminderPreference, schedule reminder.Schedule, name string, attemptNo int, now time.Time, payload map[string]any) error {
	event := reminder.ReminderEvent{
		EventID:         stableID("event", schedule.ID+"|"+name+"|"+strconv.Itoa(attemptNo)),
		EventName:       name,
		SchemaVersion:   "v1",
		Source:          "reminder-service",
		UserID:          schedule.UserID,
		TaskDate:        schedule.TaskDate,
		Timezone:        preference.Timezone,
		EventTime:       now,
		DecisionID:      decision.ID,
		StrategyVersion: decision.StrategyVersion,
		Channel:         schedule.Channel,
		Payload:         payload,
	}
	if err := s.Reminders.AppendEvent(ctx, event); err != nil {
		return fmt.Errorf("append delivery event: %w", err)
	}
	return nil
}

func (s Service) guard() reminder.FrequencyGuard {
	return reminder.FrequencyGuard{MaxPushPerDay: s.MaxPushPerDay}
}

func (s Service) maxSendAttempts() int {
	if s.MaxSendAttempts > 0 {
		return s.MaxSendAttempts
	}
	return defaultMaxSendAttempts
}

func (s Service) batchSize() int {
	if s.BatchSize > 0 {
		return s.BatchSize
	}
	return defaultBatchSize
}

func stableID(prefix, value string) string {
	sum := sha256.Sum256([]byte(value))
	return prefix + "-" + hex.EncodeToString(sum[:16])
}
