package main

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	"intelligent-reminder-assistant/internal/adapter/task"
	"intelligent-reminder-assistant/internal/adapter/user"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

// 本地 Fixture 的默认值来自 testenv/fixtures/users.json 的 defaults 段与 PRD 7.3 的用户设置缺省值。
const (
	defaultQuietHoursStart = "21:30"
	defaultQuietHoursEnd   = "07:00"
	defaultTimezone        = "UTC"
	defaultDailyPushCap    = 1
	// fixtureWindowSampleCount 是 Fixture 行为窗口的样本数约定：users.json 只表达「窗口是否存在」，
	// 不表达样本分布；每个来源最多一个窗口，单窗口下 selectTimeWindow 的结果与样本数无关。
	fixtureWindowSampleCount = 1
)

// fixtures 是本地入口装配好的种子数据。
type fixtures struct {
	tasks task.FixtureRepository
	users user.MemoryRepository
	usage map[string]reminder.DailyUsage
}

// fixtureFile 是 testenv/fixtures/users.json 的结构，对应《测试数据构造说明》的用户、任务、行为与设置四节。
// 它只用于本地 Demo 与业务测试的种子装配，不是生产数据来源。
type fixtureFile struct {
	Defaults struct {
		Preference fixturePreference `json:"preference"`
		Usage      fixtureUsage      `json:"usage"`
	} `json:"defaults"`
	TaskTemplates map[string]fixtureTaskTemplate `json:"task_templates"`
	Users         []fixtureUser                  `json:"users"`
}

type fixtureUser struct {
	UserID       string             `json:"user_id"`
	TaskTemplate string             `json:"task_template"`
	Behavior     fixtureBehavior    `json:"behavior"`
	Preference   *fixturePreference `json:"preference"`
	Usage        *fixtureUsage      `json:"usage"`
}

type fixturePreference struct {
	ReminderEnabled *bool    `json:"reminder_enabled"`
	PushEnabled     *bool    `json:"push_enabled"`
	QuietHours      []string `json:"quiet_hours"`
	DailyPushCap    *int     `json:"daily_push_cap"`
	Timezone        string   `json:"timezone"`
}

type fixtureUsage struct {
	PushSentCount   int `json:"push_sent_count"`
	SnoozeSentCount int `json:"snooze_sent_count"`
}

type fixtureTaskTemplate struct {
	RequiredCount    int              `json:"required_count"`
	CompletedCount   int              `json:"completed_count"`
	EstimatedMinutes *int             `json:"estimated_minutes"`
	DeadlineLocal    string           `json:"deadline_local"`
	Deadline         *fixtureDeadline `json:"deadline"`
}

// fixtureDeadline 是相对当前时刻的截止时间表达（数据构造说明.md：用于构造必然过期或必然临近的场景）。
type fixtureDeadline struct {
	RelativeTo    string `json:"relative_to"`
	OffsetMinutes int    `json:"offset_minutes"`
}

type fixtureBehavior struct {
	HistoryDaysAvailable             int        `json:"history_days_available"`
	InactiveDays                     int        `json:"inactive_days"`
	CompleteDays7D                   int        `json:"complete_days_7d"`
	ReminderAttributedCompleteDays7D int        `json:"reminder_attributed_complete_days_7d"`
	DataDegraded                     bool       `json:"data_degraded"`
	AppOpenWindows                   [][]string `json:"app_open_windows"`
	TaskCompleteWindows              [][]string `json:"task_complete_windows"`
}

// loadFixtures 读取 Fixture 文件并装配任务、提醒设置、行为摘要与当日用量基线。
// 文件缺失、格式非法或引用了不存在的任务模板都直接报错：本地入口不允许用空数据顶替种子，
// 否则业务测试会得到看似正常但语义错误的结论。
func loadFixtures(path string, now func() time.Time) (fixtures, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return fixtures{}, fmt.Errorf("read fixtures: %w", err)
	}
	var file fixtureFile
	if err := json.Unmarshal(content, &file); err != nil {
		return fixtures{}, fmt.Errorf("parse fixtures %s: %w", path, err)
	}

	loaded := fixtures{
		tasks: task.FixtureRepository{
			Users: map[string]task.Template{},
			Now:   now,
		},
		users: user.MemoryRepository{
			Preferences: map[string]reminder.ReminderPreference{},
			Behaviors:   map[string]reminder.BehaviorSummary{},
		},
		usage: map[string]reminder.DailyUsage{},
	}
	for _, entry := range file.Users {
		template, err := file.templateOf(entry)
		if err != nil {
			return fixtures{}, err
		}
		preference := file.Defaults.Preference.merged(entry.Preference)
		loaded.tasks.Users[entry.UserID] = task.Template{
			RequiredCount:    template.RequiredCount,
			CompletedCount:   template.CompletedCount,
			EstimatedMinutes: template.EstimatedMinutes,
			DeadlineLocal:    template.DeadlineLocal,
			DeadlineOffset:   template.deadlineOffset(),
			Timezone:         preference.timezone(),
		}
		loaded.users.Preferences[entry.UserID] = preference.domainPreference()
		loaded.users.Behaviors[entry.UserID] = entry.Behavior.domainBehavior()
		loaded.usage[entry.UserID] = file.Defaults.Usage.merged(entry.Usage).domainUsage()
	}
	return loaded, nil
}

// templateOf 解析用户引用的任务模板；引用不存在的模板属种子数据错误，直接报错而不是退化成无任务。
func (f fixtureFile) templateOf(entry fixtureUser) (fixtureTaskTemplate, error) {
	if entry.TaskTemplate == "" {
		return fixtureTaskTemplate{}, nil
	}
	template, ok := f.TaskTemplates[entry.TaskTemplate]
	if !ok {
		return fixtureTaskTemplate{}, fmt.Errorf("fixture user %s references unknown task template %q", entry.UserID, entry.TaskTemplate)
	}
	return template, nil
}

// merged 把用户级覆写合并到 defaults.preference 之上：用户只需写与默认不同的字段。
func (p fixturePreference) merged(override *fixturePreference) fixturePreference {
	if override == nil {
		return p
	}
	merged := p
	if override.ReminderEnabled != nil {
		merged.ReminderEnabled = override.ReminderEnabled
	}
	if override.PushEnabled != nil {
		merged.PushEnabled = override.PushEnabled
	}
	if override.QuietHours != nil {
		merged.QuietHours = override.QuietHours
	}
	if override.DailyPushCap != nil {
		merged.DailyPushCap = override.DailyPushCap
	}
	if override.Timezone != "" {
		merged.Timezone = override.Timezone
	}
	return merged
}

func (u fixtureUsage) merged(override *fixtureUsage) fixtureUsage {
	if override == nil {
		return u
	}
	return *override
}

func (p fixturePreference) reminderEnabled() bool {
	return boolOrDefault(p.ReminderEnabled, true)
}

func (p fixturePreference) pushEnabled() bool {
	return boolOrDefault(p.PushEnabled, true)
}

func (p fixturePreference) dailyPushCap() int {
	if p.DailyPushCap != nil && *p.DailyPushCap > 0 {
		return *p.DailyPushCap
	}
	return defaultDailyPushCap
}

// quietHours 返回 [开始, 结束] 的本地时刻；缺失或写法不合法时回落到默认免打扰区间。
func (p fixturePreference) quietHours() (string, string) {
	if len(p.QuietHours) != 2 {
		return defaultQuietHoursStart, defaultQuietHoursEnd
	}
	start, startErr := parseLocalMinute(p.QuietHours[0])
	_, endErr := parseLocalMinute(p.QuietHours[1])
	if startErr != nil || endErr != nil || start == 0 && p.QuietHours[0] != "00:00" {
		return defaultQuietHoursStart, defaultQuietHoursEnd
	}
	return p.QuietHours[0], p.QuietHours[1]
}

func (p fixturePreference) timezone() string {
	if p.Timezone == "" {
		return defaultTimezone
	}
	return p.Timezone
}

func (p fixturePreference) domainPreference() reminder.ReminderPreference {
	start, end := p.quietHours()
	return reminder.ReminderPreference{
		ReminderEnabled: p.reminderEnabled(),
		PushEnabled:     p.pushEnabled(),
		QuietHoursStart: start,
		QuietHoursEnd:   end,
		DailyPushCap:    p.dailyPushCap(),
		Timezone:        p.timezone(),
	}
}

func (u fixtureUsage) domainUsage() reminder.DailyUsage {
	return reminder.DailyUsage{PushSentCount: u.PushSentCount, SnoozeSentCount: u.SnoozeSentCount}
}

func (b fixtureBehavior) domainBehavior() reminder.BehaviorSummary {
	return reminder.BehaviorSummary{
		InactiveDays:                 b.InactiveDays,
		CompleteDays7D:               b.CompleteDays7D,
		ReminderAttributedComplete7D: b.ReminderAttributedCompleteDays7D,
		HistoryDaysAvailable:         b.HistoryDaysAvailable,
		DataDegraded:                 b.DataDegraded,
		TaskCompleteWindows:          toTimeWindows(b.TaskCompleteWindows),
		AppActiveWindows:             toTimeWindows(b.AppOpenWindows),
	}
}

// deadlineOffset 返回相对当前时刻的截止时间偏移；非相对表达返回 nil，由 DeadlineLocal 决定。
func (t fixtureTaskTemplate) deadlineOffset() *time.Duration {
	if t.Deadline == nil || t.Deadline.RelativeTo != "now" {
		return nil
	}
	offset := time.Duration(t.Deadline.OffsetMinutes) * time.Minute
	return &offset
}

// toTimeWindows 把 Fixture 的本地时刻区间转成领域窗口，跳过写法不合法的区间。
func toTimeWindows(windows [][]string) []reminder.TimeWindow {
	result := make([]reminder.TimeWindow, 0, len(windows))
	for _, window := range windows {
		if len(window) != 2 {
			continue
		}
		start, startErr := parseLocalMinute(window[0])
		end, endErr := parseLocalMinute(window[1])
		if startErr != nil || endErr != nil {
			continue
		}
		result = append(result, reminder.TimeWindow{
			StartMinute: start,
			EndMinute:   end,
			SampleCount: fixtureWindowSampleCount,
		})
	}
	return result
}

func parseLocalMinute(value string) (int, error) {
	parsed, err := time.Parse("15:04", value)
	if err != nil {
		return 0, err
	}
	return parsed.Hour()*60 + parsed.Minute(), nil
}

func boolOrDefault(value *bool, fallback bool) bool {
	if value == nil {
		return fallback
	}
	return *value
}
