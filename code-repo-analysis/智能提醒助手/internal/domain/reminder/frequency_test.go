package reminder

import "testing"

func TestFrequencyGuardUsesUserCapAndIgnoresSnooze(t *testing.T) {
	guard := FrequencyGuard{}
	preference := ReminderPreference{PushEnabled: true, DailyPushCap: 1}
	if verdict := guard.Check(DailyUsage{PushSentCount: 0}, preference, ScheduleInitial); !verdict.Allowed || verdict.Reason != "" {
		t.Fatalf("expected allowed under the cap: %+v", verdict)
	}
	// 系统主动 Push 达到用户设置的上限：评估返回并记录 DAILY_CAP_REACHED。
	if verdict := guard.Check(DailyUsage{PushSentCount: 1}, preference, ScheduleInitial); verdict.Allowed || verdict.Reason != ReasonDailyCapReached {
		t.Fatalf("expected DAILY_CAP_REACHED at the cap: %+v", verdict)
	}
	// 用户设置缺失时用 guard 默认上限（技术方案 4.7 的 max_push_per_day=1）。
	if verdict := (FrequencyGuard{MaxPushPerDay: 1}).Check(DailyUsage{PushSentCount: 1}, ReminderPreference{}, ScheduleInitial); verdict.Allowed {
		t.Fatal("expected the guard default cap to block the second system push")
	}
	// 用户设置优先于 guard 默认值。
	if verdict := guard.Check(DailyUsage{PushSentCount: 1}, ReminderPreference{DailyPushCap: 2}, ScheduleInitial); !verdict.Allowed {
		t.Fatalf("expected the user cap to win: %+v", verdict)
	}
	// SNOOZE 用量独立计量：系统主动用量已满也不拦延后提醒，计数与每天最多 2 次校验随 FR-007 实现。
	if verdict := guard.Check(DailyUsage{PushSentCount: 1}, preference, ScheduleSnooze); !verdict.Allowed {
		t.Fatalf("expected snooze usage to be metered separately: %+v", verdict)
	}
}

func TestPushChannelAvailabilityFollowsUserSetting(t *testing.T) {
	if PushChannelAvailable(ReminderPreference{PushEnabled: true}) != true {
		t.Fatal("expected authorized push to be available")
	}
	if PushChannelAvailable(ReminderPreference{PushEnabled: false}) != false {
		t.Fatal("expected unauthorized push to be unavailable")
	}
}
