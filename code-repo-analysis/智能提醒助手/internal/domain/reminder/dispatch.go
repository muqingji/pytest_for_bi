package reminder

import (
	"strconv"
	"strings"
	"time"
)

// DeliveryStatusOf 归一化渠道返回状态。未知取值（含厂商自定义错误码）一律按 UNKNOWN 处理，
// 必须先查询再决定，禁止盲目重发。
func DeliveryStatusOf(result PushResult) DeliveryStatus {
	switch strings.ToUpper(strings.TrimSpace(result.Status)) {
	case string(DeliverySent):
		return DeliverySent
	case string(DeliveryFailed):
		return DeliveryFailed
	default:
		return DeliveryUnknown
	}
}

// RetryAllowed 落实「明确失败最多重试一次」：尝试序号达到上限即不再重试。
func RetryAllowed(attemptNo, maxAttempts int) bool {
	if maxAttempts <= 0 {
		maxAttempts = 2
	}
	if attemptNo < 1 {
		return false
	}
	return attemptNo < maxAttempts
}

// NextScheduleStatus 由投递状态和是否仍可重试推导排程的下一步状态。
func NextScheduleStatus(status DeliveryStatus, retryAllowed bool) ScheduleStatus {
	switch status {
	case DeliverySent:
		return ScheduleSent
	case DeliveryFailed:
		if retryAllowed {
			return ScheduleRetryWait
		}
		return ScheduleFailed
	default:
		return ScheduleUnknown
	}
}

// DeliveryIdempotencyKey 生成渠道幂等键：
// {user_id}_{task_date}_{channel}_{decision_id}_{schedule_version}。
// 带 schedule_version 是为了让同一决策下的 INITIAL 与 SNOOZE 各自拥有一条投递记录，
// 重试时必须复用同一取值，避免产生第二条发送记录。
func DeliveryIdempotencyKey(schedule Schedule) string {
	return strings.Join([]string{
		schedule.UserID,
		schedule.TaskDate,
		string(schedule.Channel),
		schedule.DecisionID,
		strconv.Itoa(schedule.ScheduleVersion),
	}, "_")
}

// LocalLocation 解析用户 IANA 时区；缺失或非法时回退 UTC。
func LocalLocation(timezone string) *time.Location {
	if timezone != "" {
		if parsed, err := time.LoadLocation(timezone); err == nil {
			return parsed
		}
	}
	return time.UTC
}

// DeliveryExpireAt 返回用户本地当日 24:00，作为 Push 的过期时间；日期非法时返回零值。
func DeliveryExpireAt(taskDate, timezone string) time.Time {
	day, err := time.ParseInLocation("2006-01-02", taskDate, LocalLocation(timezone))
	if err != nil {
		return time.Time{}
	}
	return day.AddDate(0, 0, 1)
}
