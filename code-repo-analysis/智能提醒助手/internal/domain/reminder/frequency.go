package reminder

// FrequencyGuard 是评估、dispatch 共用的每日频控能力。
// 当日系统主动 Push 的用量只统计 schedule_type=INITIAL；SNOOZE 用量独立计量，
// 其计数与「当天 Push 总数不超过 2 次」的校验随 FR-007 实现，因此这里不对 SNOOZE 做上限拦截。
type FrequencyGuard struct {
	MaxPushPerDay int
}

// FrequencyVerdict 是频控判定结果；Allowed 为 false 时 Reason 为拒绝原因码。
type FrequencyVerdict struct {
	Allowed bool
	Reason  ReasonCode
}

// Check 判定本次排程是否仍可使用当日系统主动 Push 额度。
// 用量达到上限时返回 DAILY_CAP_REACHED，调用方据此不再创建或取消排程。
func (guard FrequencyGuard) Check(usage DailyUsage, preference ReminderPreference, scheduleType ScheduleType) FrequencyVerdict {
	if scheduleType == ScheduleSnooze {
		return FrequencyVerdict{Allowed: true}
	}
	limit := positiveOrDefault(preference.DailyPushCap, positiveOrDefault(guard.MaxPushPerDay, 1))
	if usage.PushSentCount >= limit {
		return FrequencyVerdict{Reason: ReasonDailyCapReached}
	}
	return FrequencyVerdict{Allowed: true}
}

// PushChannelAvailable 判定 Push 渠道是否可用。未授权时不调用渠道，直接跳过本次提醒。
func PushChannelAvailable(preference ReminderPreference) bool {
	return preference.PushEnabled
}
