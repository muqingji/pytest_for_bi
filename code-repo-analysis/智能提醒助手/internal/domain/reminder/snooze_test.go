package reminder

import (
	"testing"
	"time"
)

// snoozeBase 是延后判定用例的公共输入：UTC 用户、有剩余任务、截止时间充裕、Push 可用。
func snoozeBase(now time.Time) SnoozeInput {
	return SnoozeInput{
		Now: now,
		Preference: ReminderPreference{
			ReminderEnabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: "UTC",
			QuietHoursStart: "21:30", QuietHoursEnd: "07:00",
		},
		Task: DailyTask{
			UserID: "u1", TaskDate: now.Format("2006-01-02"),
			RequiredCount: 5, CompletedCount: 2, Deadline: now.Add(6 * time.Hour),
		},
	}
}

func TestPlanSnoozeAllowsWithinOneHour(t *testing.T) {
	now := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
	plan := PlanSnooze(snoozeBase(now))
	if !plan.Allowed || plan.Reason != ReasonEligible {
		t.Fatalf("expected an allowed snooze: %+v", plan)
	}
	// AC-013：延后提醒固定安排在一小时后。
	if !plan.SnoozeUntil.Equal(now.Add(SnoozeDelay)) {
		t.Fatalf("expected snooze_until to be one hour later: %v", plan.SnoozeUntil)
	}
}

func TestPlanSnoozeRejections(t *testing.T) {
	now := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		name   string
		mutate func(*SnoozeInput)
		reason ReasonCode
	}{
		{"completed", func(in *SnoozeInput) { in.Task.CompletedCount = in.Task.RequiredCount }, ReasonTaskCompleted},
		{"expired", func(in *SnoozeInput) { in.Now = in.Task.Deadline.Add(time.Minute) }, ReasonTaskExpired},
		{"disabled", func(in *SnoozeInput) { in.Preference.ReminderEnabled = false }, ReasonReminderDisabled},
		{"insufficient time", func(in *SnoozeInput) { in.Task.Deadline = in.Now.Add(90 * time.Minute) }, ReasonInsufficientTime},
		{"push unavailable", func(in *SnoozeInput) { in.Preference.PushEnabled = false }, ReasonNoAvailableChannel},
		{"daily cap", func(in *SnoozeInput) { in.Usage.PushSentCount = 1; in.Usage.SnoozeSentCount = 1 }, ReasonDailyCapReached},
	}
	for _, test := range tests {
		input := snoozeBase(now)
		test.mutate(&input)
		plan := PlanSnooze(input)
		if plan.Allowed || plan.Reason != test.reason {
			t.Fatalf("%s: expected %s, got %+v", test.name, test.reason, plan)
		}
		if !plan.SnoozeUntil.IsZero() {
			t.Fatalf("%s: rejected plan must not carry snooze_until: %+v", test.name, plan)
		}
	}
}

// 边界：截止时间正好等于「延后时刻 + 1 小时」时仍可提醒；再晚一分钟即不足 1 小时。
func TestPlanSnoozeDeadlineBoundary(t *testing.T) {
	now := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
	exact := snoozeBase(now)
	exact.Task.Deadline = now.Add(SnoozeDelay + time.Hour)
	if plan := PlanSnooze(exact); !plan.Allowed {
		t.Fatalf("expected the exact deadline boundary to be allowed: %+v", plan)
	}
	tight := snoozeBase(now)
	tight.Task.Deadline = now.Add(SnoozeDelay + time.Hour - time.Second)
	if plan := PlanSnooze(tight); plan.Allowed || plan.Reason != ReasonInsufficientTime {
		t.Fatalf("expected INSUFFICIENT_TIME one second later: %+v", plan)
	}
}

// 没有截止时间的任务不施加「截止前 1 小时」约束（与 FR-002 选时候选口径一致）。
func TestPlanSnoozeWithoutDeadline(t *testing.T) {
	now := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
	input := snoozeBase(now)
	input.Task.Deadline = time.Time{}
	if plan := PlanSnooze(input); !plan.Allowed {
		t.Fatalf("expected a task without deadline to be allowed: %+v", plan)
	}
}

// 免打扰：一小时后落在区间内时顺延到窗口结束；顺延后仍超出截止前 1 小时则按 QUIET_HOURS 拒绝。
func TestPlanSnoozeQuietHours(t *testing.T) {
	now := time.Date(2026, 9, 20, 20, 45, 0, 0, time.UTC)
	tight := snoozeBase(now)
	tight.Task.Deadline = now.Add(3 * time.Hour)
	if plan := PlanSnooze(tight); plan.Allowed || plan.Reason != ReasonQuietHours {
		t.Fatalf("expected QUIET_HOURS when no window is available: %+v", plan)
	}

	roomy := snoozeBase(now)
	roomy.Task.Deadline = now.Add(12 * time.Hour)
	plan := PlanSnooze(roomy)
	if !plan.Allowed {
		t.Fatalf("expected deferral to the next window: %+v", plan)
	}
	expected := time.Date(2026, 9, 21, 7, 0, 0, 0, time.UTC)
	if !plan.SnoozeUntil.Equal(expected) {
		t.Fatalf("expected the window end %v, got %v", expected, plan.SnoozeUntil)
	}
}

// 免打扰判定使用用户本地时区：UTC 时钟的 12:45 在东京是 21:45，落在默认免打扰区间内。
func TestPlanSnoozeQuietHoursUsesUserTimezone(t *testing.T) {
	now := time.Date(2026, 9, 20, 12, 45, 0, 0, time.UTC)
	input := snoozeBase(now)
	input.Preference.Timezone = "Asia/Tokyo"
	input.Task.Deadline = now.Add(24 * time.Hour)
	plan := PlanSnooze(input)
	if !plan.Allowed {
		t.Fatalf("expected deferral inside the local quiet hours: %+v", plan)
	}
	expected := time.Date(2026, 9, 20, 22, 0, 0, 0, time.UTC) // 次日 07:00 JST
	if !plan.SnoozeUntil.Equal(expected) {
		t.Fatalf("expected the local window end %v, got %v", expected, plan.SnoozeUntil)
	}
}

func TestQuietHoursEndAfterCrossesMidnight(t *testing.T) {
	// 区间结束时刻已过（01:00 -> 07:00 仍在当天）时顺延到当日窗口结束。
	value := time.Date(2026, 9, 20, 1, 0, 0, 0, time.UTC)
	if got := QuietHoursEndAfter(value, 7*time.Hour); !got.Equal(time.Date(2026, 9, 20, 7, 0, 0, 0, time.UTC)) {
		t.Fatalf("expected the same-day window end, got %v", got)
	}
	// 已过当日结束时刻时顺延到次日同一时刻。
	late := time.Date(2026, 9, 20, 22, 0, 0, 0, time.UTC)
	if got := QuietHoursEndAfter(late, 7*time.Hour); !got.Equal(time.Date(2026, 9, 21, 7, 0, 0, 0, time.UTC)) {
		t.Fatalf("expected the next-day window end, got %v", got)
	}
}

func TestDeadlineAllowsWithoutDeadline(t *testing.T) {
	if !DeadlineAllows(time.Time{}, time.Now()) {
		t.Fatal("a zero deadline must not block the candidate")
	}
}
