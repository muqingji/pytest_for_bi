package evaluate

import (
	"context"
	"fmt"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

// cancelPendingSchedules 取消同名决策下所有未发送排程，返回取消前的排程列表。
// 同时被评估拒绝（FR-004）与用户关闭提醒（FR-003）两条路径复用：两条路径都以决策的
// reason_code 作为 cancel_reason，因此取消原因码在同一处收敛。
func cancelPendingSchedules(ctx context.Context, repository port.ReminderRepository, userID, taskDate string, reason reminder.ReasonCode, now time.Time) ([]reminder.Schedule, error) {
	schedules, ok := repository.(port.PendingScheduleRepository)
	if !ok {
		return nil, fmt.Errorf("reminder repository does not support pending schedule cancellation")
	}
	cancelled, err := schedules.CancelPendingSchedules(ctx, userID, taskDate, reason, now)
	if err != nil {
		return nil, fmt.Errorf("cancel pending schedules: %w", err)
	}
	return cancelled, nil
}

// publishCancellations 为每条被取消的排程发布一条 reminder_cancelled 事件。
// previous_status 取取消前的真实状态；事件信封的 decision_id、strategy_version 与 channel
// 取自排程自身的决策行，保证生命周期事件可由 decision_id 关联（技术方案 4.3.2.4）。
// 事件按 event_id 幂等：重复执行同一取消动作不会产生第二条事件。
func publishCancellations(ctx context.Context, repository port.ReminderRepository, cancelled []reminder.Schedule, timezone string, reason reminder.ReasonCode, now time.Time) error {
	for _, schedule := range cancelled {
		decision, err := repository.GetDecision(ctx, schedule.DecisionID)
		if err != nil {
			return fmt.Errorf("read cancelled decision: %w", err)
		}
		event := reminder.ReminderEvent{
			EventID:         stableID("event", schedule.ID+"|reminder_cancelled|0"),
			EventName:       "reminder_cancelled",
			SchemaVersion:   "v1",
			Source:          "reminder-service",
			UserID:          schedule.UserID,
			TaskDate:        schedule.TaskDate,
			Timezone:        timezone,
			EventTime:       now,
			DecisionID:      schedule.DecisionID,
			StrategyVersion: decision.StrategyVersion,
			Channel:         schedule.Channel,
			Payload: map[string]any{
				"cancel_reason":   string(reason),
				"previous_status": string(schedule.Status),
				"cancelled_at":    now.UTC().Format(time.RFC3339),
			},
		}
		if err := repository.AppendEvent(ctx, event); err != nil {
			return fmt.Errorf("append cancellation event: %w", err)
		}
	}
	return nil
}
