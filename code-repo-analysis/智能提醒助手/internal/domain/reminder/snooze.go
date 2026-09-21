package reminder

import "time"

// SnoozeDelay 是「稍后提醒」的固定延后间隔：PRD 7.7 与 AC-013 要求延后后 1 小时再次提醒。
const SnoozeDelay = 60 * time.Minute

// SnoozeDurationMinutes 是 reminder_snoozed 事件中 snooze_duration_minutes 的固定取值（技术方案 4.3.2.4）。
const SnoozeDurationMinutes = 60

// SnoozeInput 是延后判定的全部业务输入，由应用层从任务、偏好与当日用量读到后传入。
type SnoozeInput struct {
	Now        time.Time
	Preference ReminderPreference
	Task       DailyTask
	Usage      DailyUsage
}

// SnoozePlan 是延后判定结果；Allowed 为 true 时 SnoozeUntil 是延后到的计划时刻，
// Allowed 为 false 时 Reason 是拒绝原因码（与 4.3.2.3 失败表逐行对应）。
type SnoozePlan struct {
	Allowed     bool
	Reason      ReasonCode
	SnoozeUntil time.Time
}

// PlanSnooze 按技术方案 4.1.3 固定的校验顺序判定延后是否成立：
// ③任务完成 → ④任务过期 → ⑤提醒关闭 → ⑥免打扰（顺延到窗口或拒绝）→ ⑦截止前不足 1 小时
// → ⑧Push 不可用 → ⑨当日 Push 合计达 2 次。
//
// 顺序即短路优先级：同一个请求只会得到一个 reason_code，前面的判定不成立时后面的规则不再参与，
// 因此调用方与测试可以按顺序逐条构造证据。①②（decision_id 归属与第二次入口）依赖持久化事实，
// 由应用层在调用本函数之前完成判定，不在本函数重复。
func PlanSnooze(input SnoozeInput) SnoozePlan {
	// ③ 任务已完成：今天不再需要提醒，延后也没有意义（AC-002 / AC-013 的复核口径）。
	if input.Task.IsComplete() {
		return SnoozePlan{Reason: ReasonTaskCompleted}
	}
	// ④ 任务已过期：截止时间已到或已过，延后只会产生过期提醒（任务系统无截止时间时不做该判定）。
	if !input.Task.Deadline.IsZero() && !input.Now.Before(input.Task.Deadline) {
		return SnoozePlan{Reason: ReasonTaskExpired}
	}
	// ⑤ 用户关闭提醒：不创建任何提醒，包括用户主动触发的延后。
	if !input.Preference.ReminderEnabled {
		return SnoozePlan{Reason: ReasonReminderDisabled}
	}
	// ⑥ 免打扰：一小时后落在免打扰区间时，按「延后到窗口或拒绝」顺延到本区间结束（下一个可用窗口）；
	// 顺延后仍超出「截止前 1 小时」则视为当天没有可用窗口。免打扰的时长计算必须用用户本地时区，
	// 而 Now 来自 Clock（UTC），所以先换算再判定。
	location := LocalLocation(input.Preference.Timezone)
	candidate := input.Now.Add(SnoozeDelay)
	quietStart, quietEnd := QuietHours(input.Preference)
	if InQuietHours(candidate.In(location), quietStart, quietEnd) {
		candidate = QuietHoursEndAfter(candidate.In(location), quietEnd)
		if !DeadlineAllows(input.Task.Deadline, candidate) {
			// 这里返回 QUIET_HOURS 而不是 INSUFFICIENT_TIME：用户能看到的原因是「当前处于免打扰」，
			// 与 4.3.2.3 失败表「进入免打扰且无可用窗口」一致，避免同一场景出现两个原因码。
			return SnoozePlan{Reason: ReasonQuietHours}
		}
	}
	// ⑦ 截止前不足 1 小时：不强行创建排程。
	if !DeadlineAllows(input.Task.Deadline, candidate) {
		return SnoozePlan{Reason: ReasonInsufficientTime}
	}
	// ⑧ Push 不可用：不静默改用其他渠道（站内承接为 P1）。
	if !PushChannelAvailable(input.Preference) {
		return SnoozePlan{Reason: ReasonNoAvailableChannel}
	}
	// ⑨ 当日 Push 合计已达 2 次：延后不占系统主动上限，但要计入合计上限。
	if verdict := (FrequencyGuard{}).CheckDailyPushTotal(input.Usage); !verdict.Allowed {
		return SnoozePlan{Reason: verdict.Reason}
	}
	return SnoozePlan{Allowed: true, Reason: ReasonEligible, SnoozeUntil: candidate}
}
