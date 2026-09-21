package main

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

// writeFixtureFile 把测试用的种子 JSON 写到临时目录，避免依赖仓库里的真实种子文件内容。
func writeFixtureFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "users.json")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write fixtures: %v", err)
	}
	return path
}

// TestLoadFixturesAssemblesTasksPreferencesAndUsage 覆盖种子装配的完整链路：
// 任务模板解析（含相对截止时间）、用户级设置覆写、行为窗口转换与当日用量基线。
func TestLoadFixturesAssemblesTasksPreferencesAndUsage(t *testing.T) {
	now := func() time.Time { return time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC) }
	path := writeFixtureFile(t, `{
	  "defaults": {
	    "preference": {"reminder_enabled": true, "push_enabled": true, "quiet_hours": ["21:30", "07:00"], "daily_push_cap": 1, "timezone": "UTC"},
	    "usage": {"push_sent_count": 0, "snooze_sent_count": 0}
	  },
	  "task_templates": {
	    "PENDING": {"required_count": 5, "completed_count": 2, "estimated_minutes": 30, "deadline_local": "23:30"},
	    "EXPIRED": {"required_count": 5, "completed_count": 2, "deadline": {"relative_to": "now", "offset_minutes": -60}},
	    "ABSOLUTE": {"required_count": 1, "completed_count": 0, "deadline": {"relative_to": "task_date", "offset_minutes": 60}},
	    "NO_ESTIMATE": {"required_count": 2, "completed_count": 1}
	  },
	  "users": [
	    {
	      "user_id": "user-passive",
	      "task_template": "PENDING",
	      "behavior": {
	        "history_days_available": 7,
	        "inactive_days": 0,
	        "complete_days_7d": 1,
	        "reminder_attributed_complete_days_7d": 0,
	        "app_open_windows": [["18:00", "19:00"], ["bad"], ["25:00", "26:00"]],
	        "task_complete_windows": [["20:00", "21:00"]]
	      }
	    },
	    {
	      "user_id": "user-expired",
	      "task_template": "EXPIRED",
	      "preference": {"reminder_enabled": false, "push_enabled": false, "quiet_hours": ["22:00", "06:30"], "daily_push_cap": 3, "timezone": "Asia/Shanghai"},
	      "usage": {"push_sent_count": 1, "snooze_sent_count": 1}
	    },
	    {
	      "user_id": "user-absolute",
	      "task_template": "ABSOLUTE"
	    },
	    {
	      "user_id": "user-no-estimate",
	      "task_template": "NO_ESTIMATE"
	    },
	    {
	      "user_id": "user-no-template"
	    }
	  ]
	}`)

	loaded, err := loadFixtures(path, now)
	if err != nil {
		t.Fatalf("load fixtures: %v", err)
	}

	passive := loaded.tasks.Users["user-passive"]
	if passive.RequiredCount != 5 || passive.CompletedCount != 2 || passive.EstimatedMinutes == nil || *passive.EstimatedMinutes != 30 {
		t.Fatalf("unexpected passive task template: %+v", passive)
	}
	if passive.DeadlineOffset != nil || passive.DeadlineLocal != "23:30" || passive.Timezone != defaultTimezone {
		t.Fatalf("unexpected passive deadline wiring: %+v", passive)
	}
	task, err := loaded.tasks.GetDailyTask(context.Background(), "user-passive", "2026-10-01")
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if want := time.Date(2026, 10, 1, 23, 30, 0, 0, time.UTC); !task.Deadline.Equal(want) {
		t.Fatalf("deadline=%v want %v", task.Deadline, want)
	}

	expired := loaded.tasks.Users["user-expired"]
	if expired.DeadlineOffset == nil || *expired.DeadlineOffset != -time.Hour {
		t.Fatalf("relative deadline must become an offset: %+v", expired.DeadlineOffset)
	}
	if expired.Timezone != "Asia/Shanghai" {
		t.Fatalf("user timezone override must reach the task template: %q", expired.Timezone)
	}
	preference := loaded.users.Preferences["user-expired"]
	if preference.ReminderEnabled || preference.PushEnabled || preference.DailyPushCap != 3 ||
		preference.QuietHoursStart != "22:00" || preference.QuietHoursEnd != "06:30" || preference.Timezone != "Asia/Shanghai" {
		t.Fatalf("unexpected preference override merge: %+v", preference)
	}
	if usage := loaded.usage["user-expired"]; usage.PushSentCount != 1 || usage.SnoozeSentCount != 1 {
		t.Fatalf("usage override must replace the defaults: %+v", usage)
	}

	// 绝对截止时间表达（relative_to 不是 now）不产生偏移，仍由 deadline_local 决定。
	if offset := loaded.tasks.Users["user-absolute"].DeadlineOffset; offset != nil {
		t.Fatalf("non-relative deadline must not become an offset: %v", *offset)
	}
	if estimate := loaded.tasks.Users["user-no-estimate"].EstimatedMinutes; estimate != nil {
		t.Fatalf("missing estimate must stay nil: %+v", estimate)
	}
	// 未引用任务模板的用户按零值模板装配，不报错也不退化成其他模板。
	noTemplate := loaded.tasks.Users["user-no-template"]
	if noTemplate.RequiredCount != 0 || noTemplate.DeadlineLocal != "" {
		t.Fatalf("user without a template must stay empty: %+v", noTemplate)
	}

	behavior := loaded.users.Behaviors["user-passive"]
	if behavior.HistoryDaysAvailable != 7 || behavior.InactiveDays != 0 {
		t.Fatalf("behavior summary not mapped: %+v", behavior)
	}
	// 写法不合法的窗口被跳过，只保留合法窗口，且样本数按单窗口约定取 1。
	if len(behavior.AppActiveWindows) != 1 || len(behavior.TaskCompleteWindows) != 1 {
		t.Fatalf("malformed windows must be skipped: %+v", behavior)
	}
	if behavior.AppActiveWindows[0] != (reminder.TimeWindow{StartMinute: 18 * 60, EndMinute: 19 * 60, SampleCount: fixtureWindowSampleCount}) {
		t.Fatalf("unexpected app window: %+v", behavior.AppActiveWindows[0])
	}
}

// TestLoadFixturesRejectsBrokenSeeds 覆盖种子数据的失败关闭：文件缺失、JSON 非法、引用不存在的任务模板
// 都必须直接报错，不允许用空数据顶替，否则业务测试会得到看似正常但语义错误的结论。
func TestLoadFixturesRejectsBrokenSeeds(t *testing.T) {
	if _, err := loadFixtures(filepath.Join(t.TempDir(), "missing.json"), nowFunc); err == nil {
		t.Fatal("missing fixture file must fail")
	}
	if _, err := loadFixtures(writeFixtureFile(t, "{"), nowFunc); err == nil {
		t.Fatal("malformed fixture json must fail")
	}
	unknownTemplate := writeFixtureFile(t, `{"users":[{"user_id":"u1","task_template":"NOPE"}]}`)
	if _, err := loadFixtures(unknownTemplate, nowFunc); err == nil {
		t.Fatal("unknown task template must fail")
	}
}

// TestFixturePreferenceMergingAndDefaults 覆盖用户级设置合并与缺省回落。
func TestFixturePreferenceMergingAndDefaults(t *testing.T) {
	base := fixturePreference{
		ReminderEnabled: boolPointer(true),
		PushEnabled:     boolPointer(true),
		QuietHours:      []string{"21:30", "07:00"},
		DailyPushCap:    intPointer(1),
		Timezone:        "UTC",
	}
	if merged := base.merged(nil); merged.timezone() != "UTC" || merged.dailyPushCap() != 1 {
		t.Fatalf("nil override must keep the defaults: %+v", merged)
	}

	override := fixturePreference{
		ReminderEnabled: boolPointer(false),
		PushEnabled:     boolPointer(false),
		QuietHours:      []string{"22:00", "06:00"},
		DailyPushCap:    intPointer(4),
		Timezone:        "Asia/Shanghai",
	}
	merged := base.merged(&override)
	preference := merged.domainPreference()
	if preference.ReminderEnabled || preference.PushEnabled || preference.DailyPushCap != 4 ||
		preference.QuietHoursStart != "22:00" || preference.QuietHoursEnd != "06:00" || preference.Timezone != "Asia/Shanghai" {
		t.Fatalf("override must replace every provided field: %+v", preference)
	}

	// 只覆写部分字段时，其余字段沿用 defaults。
	partial := base.merged(&fixturePreference{DailyPushCap: intPointer(2)})
	start, end := partial.quietHours()
	if partial.dailyPushCap() != 2 || partial.timezone() != "UTC" || start != "21:30" || end != "07:00" {
		t.Fatalf("partial override must keep the remaining defaults: %+v", partial)
	}
}

// TestFixturePreferenceFallbacks 覆盖设置缺省值的三条回落规则：布尔缺省为 true、
// 用量上限非正数回落为 1、免打扰区间写法非法时回落为默认区间。
func TestFixturePreferenceFallbacks(t *testing.T) {
	empty := fixturePreference{}
	if !empty.reminderEnabled() || !empty.pushEnabled() {
		t.Fatal("missing booleans must default to enabled")
	}
	if empty.dailyPushCap() != defaultDailyPushCap {
		t.Fatalf("missing cap must default to %d: %d", defaultDailyPushCap, empty.dailyPushCap())
	}
	if cap := (fixturePreference{DailyPushCap: intPointer(0)}).dailyPushCap(); cap != defaultDailyPushCap {
		t.Fatalf("non-positive cap must fall back: %d", cap)
	}
	if cap := (fixturePreference{DailyPushCap: intPointer(-1)}).dailyPushCap(); cap != defaultDailyPushCap {
		t.Fatalf("negative cap must fall back: %d", cap)
	}
	if disabled := (fixturePreference{ReminderEnabled: boolPointer(false), PushEnabled: boolPointer(false)}); disabled.reminderEnabled() || disabled.pushEnabled() {
		t.Fatal("explicit false must win over the default")
	}
	if empty.timezone() != defaultTimezone {
		t.Fatalf("missing timezone must fall back: %q", empty.timezone())
	}

	cases := []struct {
		name      string
		quiet     []string
		wantStart string
		wantEnd   string
	}{
		{name: "missing", quiet: nil, wantStart: defaultQuietHoursStart, wantEnd: defaultQuietHoursEnd},
		{name: "one element", quiet: []string{"21:30"}, wantStart: defaultQuietHoursStart, wantEnd: defaultQuietHoursEnd},
		{name: "bad start", quiet: []string{"25:00", "07:00"}, wantStart: defaultQuietHoursStart, wantEnd: defaultQuietHoursEnd},
		{name: "bad end", quiet: []string{"21:30", "bad"}, wantStart: defaultQuietHoursStart, wantEnd: defaultQuietHoursEnd},
		{name: "valid", quiet: []string{"20:00", "06:00"}, wantStart: "20:00", wantEnd: "06:00"},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			start, end := (fixturePreference{QuietHours: testCase.quiet}).quietHours()
			if start != testCase.wantStart || end != testCase.wantEnd {
				t.Fatalf("quiet hours=(%s,%s) want (%s,%s)", start, end, testCase.wantStart, testCase.wantEnd)
			}
		})
	}
}

// TestFixtureUsageMappingAndMerging 覆盖当日用量基线的合并与领域映射。
func TestFixtureUsageMappingAndMerging(t *testing.T) {
	base := fixtureUsage{PushSentCount: 1, SnoozeSentCount: 1}
	if merged := base.merged(nil); merged != base {
		t.Fatalf("nil override must keep the defaults: %+v", merged)
	}
	override := &fixtureUsage{SnoozeSentCount: 2}
	if merged := base.merged(override); merged.PushSentCount != 0 || merged.SnoozeSentCount != 2 {
		t.Fatalf("usage override must replace the whole block: %+v", merged)
	}
	if usage := override.domainUsage(); usage.PushSentCount != 0 || usage.SnoozeSentCount != 2 {
		t.Fatalf("unexpected domain usage: %+v", usage)
	}
}

// TestFixtureBehaviourMappingSkipsMalformedWindows 覆盖行为窗口转换：
// 只有合法的两元素区间才进入领域对象，其余静默跳过（种子写法问题不阻塞启动）。
func TestFixtureBehaviourMappingSkipsMalformedWindows(t *testing.T) {
	behavior := fixtureBehavior{
		HistoryDaysAvailable:             7,
		InactiveDays:                     1,
		CompleteDays7D:                   4,
		ReminderAttributedCompleteDays7D: 2,
		DataDegraded:                     true,
		AppOpenWindows:                   [][]string{{"18:00", "19:00"}, {"19:00"}, {"19:00", "bad"}},
	}
	mapped := behavior.domainBehavior()
	if mapped.HistoryDaysAvailable != 7 || mapped.InactiveDays != 1 || mapped.CompleteDays7D != 4 ||
		mapped.ReminderAttributedComplete7D != 2 || !mapped.DataDegraded {
		t.Fatalf("behavior summary not mapped: %+v", mapped)
	}
	if len(mapped.AppActiveWindows) != 1 {
		t.Fatalf("only well-formed windows may survive: %+v", mapped.AppActiveWindows)
	}
	if mapped.AppActiveWindows[0].StartMinute != 18*60 || mapped.AppActiveWindows[0].EndMinute != 19*60 {
		t.Fatalf("unexpected window: %+v", mapped.AppActiveWindows[0])
	}
	if mapped.TaskCompleteWindows == nil {
		t.Fatal("windows slice must be initialized instead of nil")
	}
	if _, err := parseLocalMinute("24:00"); err == nil {
		t.Fatal("invalid clock notation must fail")
	}
	if minute, err := parseLocalMinute("06:30"); err != nil || minute != 6*60+30 {
		t.Fatalf("parseLocalMinute=%d err=%v", minute, err)
	}
	if !boolOrDefault(nil, true) || boolOrDefault(boolPointer(false), true) {
		t.Fatal("boolOrDefault must only fall back when the value is missing")
	}
}

// TestFixtureDeadlineOffsetOnlyForRelativeNow 覆盖相对截止时间的解析规则。
func TestFixtureDeadlineOffsetOnlyForRelativeNow(t *testing.T) {
	if offset := (fixtureTaskTemplate{}).deadlineOffset(); offset != nil {
		t.Fatalf("missing deadline must not become an offset: %v", *offset)
	}
	if offset := (fixtureTaskTemplate{Deadline: &fixtureDeadline{RelativeTo: "task_date", OffsetMinutes: 30}}).deadlineOffset(); offset != nil {
		t.Fatalf("only relative_to=now may become an offset: %v", *offset)
	}
	offset := (fixtureTaskTemplate{Deadline: &fixtureDeadline{RelativeTo: "now", OffsetMinutes: -90}}).deadlineOffset()
	if offset == nil || *offset != -90*time.Minute {
		t.Fatalf("unexpected offset: %v", offset)
	}
}

func boolPointer(value bool) *bool { return &value }

func intPointer(value int) *int { return &value }
