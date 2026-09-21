// Package snooze 实现 FR-007「一小时后再次提醒」的应用用例：
// 校验调用合法性、复核归属与任务/偏好/频控，并在通过后创建一小时后的 Push 排程与 reminder_snoozed 事件。
package snooze

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

// ErrInvalidRequest 表示调用错误（IDL：400 + INVALID_REQUEST）：入参缺失或超长、
// 该 decision_id 下没有可延后的 INITIAL 排程，或对同一 decision 的第二次 snooze（换 request_id）。
// 技术方案 4.3.2.3 规定这类情况不以 200 业务拒绝返回，避免把非法调用伪装成业务结论；
// 与之相对，业务规则拒绝（完成、过期、免打扰、频控等）返回 200 + REJECTED + reason_code。
var ErrInvalidRequest = errors.New("invalid snooze request")

// maxFieldLength 是 decision_id、request_id、user_id 三个标识的最大长度（IDL：1–64 字符）。
const maxFieldLength = 64

// Request 是延后提醒用例入参，对应路径参数 decision_id 与请求体字段（技术方案 4.3.2.3）。
type Request struct {
	UserID     string
	DecisionID string
	RequestID  string
}

// Result 是延后提醒用例结果，字段与 IDL 的 SnoozeReminderResponse 一一对应：
// REJECTED 时只填 status 与 reason_code（schedule_id 为空串），成功与幂等命中时补齐排程字段。
type Result struct {
	ScheduleID   string                `json:"schedule_id"`
	Status       reminder.SnoozeStatus `json:"status"`
	ReasonCode   reminder.ReasonCode   `json:"reason_code"`
	SnoozeUntil  *time.Time            `json:"snooze_until,omitempty"`
	Channel      reminder.Channel      `json:"channel,omitempty"`
	ScheduleType reminder.ScheduleType `json:"schedule_type,omitempty"`
}

// Service 是延后提醒用例：依赖任务、偏好与延后专用仓储端口，时间由 Clock 注入（本地不做固定时钟开关）。
type Service struct {
	Reminders   port.SnoozeRequestRepository
	Preferences port.PreferenceRepository
	Tasks       port.TaskRepository
	Clock       port.Clock
}

// Snooze 执行一次延后提醒，按技术方案 4.1.3 固定的校验顺序短路：
// ①入参与 decision_id 归属 → 幂等命中 → ②是否存在可延后的 INITIAL 排程 → ③–⑨业务规则 → 创建排程与事件。
func (s Service) Snooze(ctx context.Context, request Request) (Result, error) {
	if err := validate(request); err != nil {
		return Result{}, err
	}
	now := s.Clock.Now()
	// ① 归属先行：decision_id 不存在或不属于该 user_id 时返回完全一致的拒绝体，
	// 不泄露资源是否存在（4.3.1 统一口径），也保证越权调用拿不到任何业务信息。
	decision, err := s.Reminders.GetDecision(ctx, request.DecisionID)
	if errors.Is(err, port.ErrNotFound) {
		return rejected(reminder.ReasonDecisionNotFound), nil
	}
	if err != nil {
		return Result{}, fmt.Errorf("read decision: %w", err)
	}
	if decision.UserID != request.UserID {
		return rejected(reminder.ReasonDecisionNotFound), nil
	}
	// 幂等命中：同一 (request_id, decision_id) 已经处理过时直接复用原排程，
	// 不创建新版本、不重复写事件（AC-013「重复点击返回原排程，不产生第三次 Push」）。
	if _, err := s.Reminders.GetSnoozeRequest(ctx, request.RequestID, request.DecisionID); err == nil {
		return s.reused(ctx, request.DecisionID)
	} else if !errors.Is(err, port.ErrNotFound) {
		return Result{}, fmt.Errorf("read snooze request: %w", err)
	}
	// ② 只接受 INITIAL 排程发起 snooze：决策没有排程说明它本就没有可延后的提醒；
	// 最新排程已是 SNOOZE 说明这是第二次入口，两者都属非法调用（4.1.3 校验顺序第 ② 步）。
	original, err := s.Reminders.GetLatestScheduleByDecision(ctx, request.DecisionID)
	if errors.Is(err, port.ErrNotFound) {
		return Result{}, fmt.Errorf("decision %s has no schedule to snooze: %w", request.DecisionID, ErrInvalidRequest)
	}
	if err != nil {
		return Result{}, fmt.Errorf("read latest schedule: %w", err)
	}
	if original.ScheduleType != reminder.ScheduleInitial {
		return Result{}, fmt.Errorf("decision %s already snoozed: %w", request.DecisionID, ErrInvalidRequest)
	}
	// ③–⑨ 业务规则判定交给领域层，用例只负责把持久化事实读齐（任务、偏好、当日用量）。
	task, err := s.Tasks.GetDailyTask(ctx, decision.UserID, decision.TaskDate)
	if err != nil {
		return Result{}, fmt.Errorf("read daily task: %w", err)
	}
	preference, err := s.Preferences.Get(ctx, decision.UserID)
	if err != nil {
		return Result{}, fmt.Errorf("read reminder preference: %w", err)
	}
	usage, err := s.Reminders.GetDailyUsage(ctx, decision.UserID, decision.TaskDate)
	if err != nil {
		return Result{}, fmt.Errorf("read daily usage: %w", err)
	}
	plan := reminder.PlanSnooze(reminder.SnoozeInput{Now: now, Preference: preference, Task: task, Usage: usage})
	if !plan.Allowed {
		return rejected(plan.Reason), nil
	}
	schedule := reminder.Schedule{
		// 排程 ID 沿用既有确定性约定 stableID("schedule", decision_id+"|version")，
		// 使同一决策下的 INITIAL（1）与 SNOOZE（2）各有一条稳定 ID，重放时不会产生新 ID。
		ID:              stableID("schedule", request.DecisionID+"|"+strconv.Itoa(snoozeScheduleVersion)),
		DecisionID:      decision.ID,
		UserID:          decision.UserID,
		TaskDate:        decision.TaskDate,
		ScheduleVersion: snoozeScheduleVersion,
		Channel:         reminder.ChannelPush,
		ScheduleType:    reminder.ScheduleSnooze,
		ScheduledAt:     plan.SnoozeUntil,
		Status:          reminder.ScheduleScheduled,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	created, err := s.Reminders.CreateSnoozeSchedule(ctx, reminder.SnoozeRequest{
		RequestID:  request.RequestID,
		DecisionID: decision.ID,
		ScheduleID: schedule.ID,
		UserID:     decision.UserID,
		TaskDate:   decision.TaskDate,
		CreatedAt:  now,
	}, schedule)
	if err != nil {
		return Result{}, fmt.Errorf("persist snooze schedule: %w", err)
	}
	// 并发下另一个请求抢先创建时按幂等命中返回既有排程，不重复写事件。
	if created.Reused {
		return resultFor(reminder.SnoozeReused, created.Schedule), nil
	}
	if err := s.publishSnoozed(ctx, decision, preference, created.Schedule, original, now); err != nil {
		return Result{}, err
	}
	return resultFor(reminder.SnoozeScheduled, created.Schedule), nil
}

// reused 读取幂等命中时的既有 SNOOZE 排程，保证重复请求返回与首次完全一致的 schedule_id。
func (s Service) reused(ctx context.Context, decisionID string) (Result, error) {
	schedule, err := s.Reminders.GetLatestScheduleByDecision(ctx, decisionID)
	if err != nil {
		return Result{}, fmt.Errorf("read existing snooze schedule: %w", err)
	}
	return resultFor(reminder.SnoozeReused, schedule), nil
}

// publishSnoozed 写入 reminder_snoozed 事件（技术方案 4.3.2.4）：
// snooze_until 为延后到的计划时间，snooze_duration_minutes 固定 60，original_scheduled_at 为延后前的计划时间。
// event_id 由排程 ID 推导，重复执行按唯一键幂等，不会产生第二条业务事件。
func (s Service) publishSnoozed(ctx context.Context, decision reminder.Decision, preference reminder.ReminderPreference, schedule reminder.Schedule, original reminder.Schedule, now time.Time) error {
	event := reminder.ReminderEvent{
		EventID:         stableID("event", schedule.ID+"|reminder_snoozed|0"),
		EventName:       "reminder_snoozed",
		SchemaVersion:   "v1",
		Source:          "reminder-service",
		UserID:          schedule.UserID,
		TaskDate:        schedule.TaskDate,
		Timezone:        preference.Timezone,
		EventTime:       now,
		DecisionID:      decision.ID,
		StrategyVersion: decision.StrategyVersion,
		Channel:         schedule.Channel,
		Payload: map[string]any{
			"snooze_until":            schedule.ScheduledAt,
			"snooze_duration_minutes": reminder.SnoozeDurationMinutes,
			"original_scheduled_at":   original.ScheduledAt,
		},
	}
	if err := s.Reminders.AppendEvent(ctx, event); err != nil {
		return fmt.Errorf("append snoozed event: %w", err)
	}
	return nil
}

// snoozeScheduleVersion 是 SNOOZE 排程固定使用的版本号：INITIAL 为 1、SNOOZE 为 2（技术方案 4.1.3、4.5.1），
// 延后链条最多一段，因此不会出现版本 3。
const snoozeScheduleVersion = 2

// validate 校验调用入参；缺失或超长都属调用错误（4.3.2.3 请求字段校验表）。
// user_id 与鉴权上下文的一致性由 transport/鉴权层保证，本地交付不实现该层。
func validate(request Request) error {
	if request.UserID == "" || request.DecisionID == "" || request.RequestID == "" {
		return fmt.Errorf("user_id, decision_id and request_id are required: %w", ErrInvalidRequest)
	}
	if len(request.UserID) > maxFieldLength || len(request.DecisionID) > maxFieldLength || len(request.RequestID) > maxFieldLength {
		return fmt.Errorf("identifier must not exceed %d characters: %w", maxFieldLength, ErrInvalidRequest)
	}
	return nil
}

// rejected 组装业务拒绝结果：REJECTED 时不返回排程字段，schedule_id 为空串（IDL）。
func rejected(reason reminder.ReasonCode) Result {
	return Result{Status: reminder.SnoozeRejected, ReasonCode: reason}
}

// resultFor 组装成功或幂等命中的结果：成功一律为 ELIGIBLE，并按 IDL 返回排程字段。
func resultFor(status reminder.SnoozeStatus, schedule reminder.Schedule) Result {
	until := schedule.ScheduledAt
	return Result{
		ScheduleID:   schedule.ID,
		Status:       status,
		ReasonCode:   reminder.ReasonEligible,
		SnoozeUntil:  &until,
		Channel:      schedule.Channel,
		ScheduleType: schedule.ScheduleType,
	}
}

// stableID 与 evaluate、dispatch 使用同一 ID 约定（前缀 + sha256 前 16 字节十六进制），
// 保证同一业务事实在不同切片生成的 ID 可复现且不随进程变化。
func stableID(prefix, value string) string {
	sum := sha256.Sum256([]byte(value))
	return prefix + "-" + hex.EncodeToString(sum[:16])
}
