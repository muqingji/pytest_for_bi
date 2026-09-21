package snooze

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

type clockFake struct{ now time.Time }

func (c clockFake) Now() time.Time { return c.now }

type taskFake struct {
	task reminder.DailyTask
	err  error
}

func (f taskFake) GetDailyTask(context.Context, string, string) (reminder.DailyTask, error) {
	return f.task, f.err
}

type preferenceFake struct {
	preference reminder.ReminderPreference
	err        error
}

func (f preferenceFake) Get(context.Context, string) (reminder.ReminderPreference, error) {
	return f.preference, f.err
}

// repositoryFake 实现 port.SnoozeRequestRepository，覆盖延后用例要用到的全部读取与写入，
// 未在本轮使用的方法保持最简实现，保证接口契约完整。
type repositoryFake struct {
	decision    reminder.Decision
	decisionErr error
	latest      reminder.Schedule
	latestErr   error
	usage       reminder.DailyUsage
	usageErr    error
	request     reminder.SnoozeRequest
	requestErr  error
	created     port.SnoozeCreateResult
	createErr   error
	eventErr    error
	events      []reminder.ReminderEvent
	requests    []reminder.SnoozeRequest
	schedules   []reminder.Schedule
}

func (f *repositoryFake) GetDailyUsage(context.Context, string, string) (reminder.DailyUsage, error) {
	return f.usage, f.usageErr
}

func (f *repositoryFake) GetDecision(context.Context, string) (reminder.Decision, error) {
	return f.decision, f.decisionErr
}

func (f *repositoryFake) GetLatestScheduleByDecision(context.Context, string) (reminder.Schedule, error) {
	return f.latest, f.latestErr
}

func (f *repositoryFake) GetSnoozeRequest(context.Context, string, string) (reminder.SnoozeRequest, error) {
	return f.request, f.requestErr
}

func (f *repositoryFake) CreateSnoozeSchedule(_ context.Context, request reminder.SnoozeRequest, schedule reminder.Schedule) (port.SnoozeCreateResult, error) {
	f.requests = append(f.requests, request)
	f.schedules = append(f.schedules, schedule)
	if f.createErr != nil {
		return port.SnoozeCreateResult{}, f.createErr
	}
	if f.created.Schedule.ID != "" {
		return f.created, nil
	}
	return port.SnoozeCreateResult{Schedule: schedule}, nil
}

func (f *repositoryFake) AppendEvent(_ context.Context, event reminder.ReminderEvent) error {
	if f.eventErr != nil {
		return f.eventErr
	}
	f.events = append(f.events, event)
	return nil
}

func (f *repositoryFake) CreateDecisionAndSchedule(context.Context, reminder.Decision, *reminder.Schedule) (port.CreateResult, error) {
	return port.CreateResult{}, nil
}

func (f *repositoryFake) ListDueSchedules(context.Context, time.Time, int) ([]reminder.Schedule, error) {
	return nil, nil
}

func (f *repositoryFake) ClaimSchedule(context.Context, string, time.Time) (reminder.Schedule, error) {
	return reminder.Schedule{}, nil
}

func (f *repositoryFake) UpdateSchedule(context.Context, reminder.ScheduleUpdate) error { return nil }

func (f *repositoryFake) UpdateDeliveryStatus(context.Context, reminder.Delivery) error { return nil }

var snoozeNow = time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)

func newRepositoryFake() *repositoryFake {
	return &repositoryFake{
		decision: reminder.Decision{
			ID: "decision-1", UserID: "user-snooze", TaskDate: "2026-09-20", ShouldRemind: true,
			Channel: reminder.ChannelPush, ReasonCode: reminder.ReasonEligible, StrategyVersion: "v1",
			UserSegment: reminder.SegmentPassive, Status: reminder.DecisionScheduled, Version: 1,
			CreatedAt: snoozeNow, UpdatedAt: snoozeNow,
		},
		latest: reminder.Schedule{
			ID: "schedule-1", DecisionID: "decision-1", UserID: "user-snooze", TaskDate: "2026-09-20",
			ScheduleVersion: 1, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleInitial,
			ScheduledAt: snoozeNow.Add(30 * time.Minute), Status: reminder.ScheduleScheduled,
			CreatedAt: snoozeNow, UpdatedAt: snoozeNow,
		},
		requestErr: port.ErrNotFound,
	}
}

func newService(repository *repositoryFake, task taskFake, preference preferenceFake) Service {
	return Service{Reminders: repository, Tasks: task, Preferences: preference, Clock: clockFake{now: snoozeNow}}
}

func defaultService(repository *repositoryFake) Service {
	return newService(repository,
		taskFake{task: reminder.DailyTask{UserID: "user-snooze", TaskDate: "2026-09-20", RequiredCount: 5, CompletedCount: 2, Deadline: snoozeNow.Add(6 * time.Hour)}},
		preferenceFake{preference: reminder.ReminderPreference{ReminderEnabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: "UTC", QuietHoursStart: "21:30", QuietHoursEnd: "07:00"}},
	)
}

func snoozeRequest() Request {
	return Request{UserID: "user-snooze", DecisionID: "decision-1", RequestID: "snooze-1"}
}

func TestSnoozeCreatesScheduleAndEvent(t *testing.T) {
	repository := newRepositoryFake()
	result, err := defaultService(repository).Snooze(context.Background(), snoozeRequest())
	if err != nil {
		t.Fatalf("snooze: %v", err)
	}
	expectedUntil := snoozeNow.Add(reminder.SnoozeDelay)
	if result.ScheduleID != stableID("schedule", "decision-1|2") || result.Status != reminder.SnoozeScheduled ||
		result.ReasonCode != reminder.ReasonEligible || result.Channel != reminder.ChannelPush ||
		result.ScheduleType != reminder.ScheduleSnooze || result.SnoozeUntil == nil || !result.SnoozeUntil.Equal(expectedUntil) {
		t.Fatalf("unexpected result: %+v", result)
	}
	if len(repository.schedules) != 1 {
		t.Fatalf("expected one written schedule: %+v", repository.schedules)
	}
	written := repository.schedules[0]
	if written.ScheduleVersion != 2 || written.ScheduleType != reminder.ScheduleSnooze ||
		written.Status != reminder.ScheduleScheduled || written.Channel != reminder.ChannelPush ||
		!written.ScheduledAt.Equal(expectedUntil) || written.DecisionID != "decision-1" {
		t.Fatalf("unexpected schedule: %+v", written)
	}
	if len(repository.requests) != 1 || repository.requests[0].RequestID != "snooze-1" ||
		repository.requests[0].ScheduleID != written.ID || repository.requests[0].UserID != "user-snooze" {
		t.Fatalf("unexpected snooze request record: %+v", repository.requests)
	}
	if len(repository.events) != 1 {
		t.Fatalf("expected exactly one event: %+v", repository.events)
	}
	event := repository.events[0]
	if event.EventName != "reminder_snoozed" || event.DecisionID != "decision-1" || event.TaskDate != "2026-09-20" ||
		event.Channel != reminder.ChannelPush || event.StrategyVersion != "v1" || event.Timezone != "UTC" {
		t.Fatalf("unexpected event envelope: %+v", event)
	}
	// 技术方案 4.3.2.4：payload 必须带延后时刻、固定 60 分钟时长与延后前的计划时间。
	if event.Payload["snooze_until"] != expectedUntil || event.Payload["snooze_duration_minutes"] != reminder.SnoozeDurationMinutes {
		t.Fatalf("unexpected payload: %+v", event.Payload)
	}
	if event.Payload["original_scheduled_at"] != snoozeNow.Add(30*time.Minute) {
		t.Fatalf("expected the original scheduled time: %+v", event.Payload)
	}
}

// AC-013：重复点击按同一 request_id 幂等返回原排程，不创建新排程、不重复写事件。
func TestSnoozeReusesExistingScheduleForRepeatedRequest(t *testing.T) {
	repository := newRepositoryFake()
	snoozeSchedule := reminder.Schedule{
		ID: "schedule-snooze", DecisionID: "decision-1", UserID: "user-snooze", TaskDate: "2026-09-20",
		ScheduleVersion: 2, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleSnooze,
		ScheduledAt: snoozeNow.Add(time.Hour), Status: reminder.ScheduleScheduled,
	}
	repository.request = reminder.SnoozeRequest{RequestID: "snooze-1", DecisionID: "decision-1", ScheduleID: snoozeSchedule.ID}
	repository.requestErr = nil
	repository.latest = snoozeSchedule
	result, err := defaultService(repository).Snooze(context.Background(), snoozeRequest())
	if err != nil {
		t.Fatalf("snooze: %v", err)
	}
	if result.Status != reminder.SnoozeReused || result.ScheduleID != snoozeSchedule.ID || result.ScheduleType != reminder.ScheduleSnooze {
		t.Fatalf("expected REUSED with the original schedule: %+v", result)
	}
	if len(repository.schedules) != 0 || len(repository.events) != 0 {
		t.Fatalf("a replayed request must not write again: schedules=%+v events=%+v", repository.schedules, repository.events)
	}
}

// 并发下另一个请求抢先创建时按幂等命中返回既有排程。
func TestSnoozeReturnsReusedWhenCreateConflicts(t *testing.T) {
	repository := newRepositoryFake()
	existing := reminder.Schedule{ID: "schedule-snooze", DecisionID: "decision-1", ScheduleType: reminder.ScheduleSnooze, Channel: reminder.ChannelPush, ScheduledAt: snoozeNow.Add(time.Hour)}
	repository.created = port.SnoozeCreateResult{Schedule: existing, Reused: true}
	result, err := defaultService(repository).Snooze(context.Background(), snoozeRequest())
	if err != nil {
		t.Fatalf("snooze: %v", err)
	}
	if result.Status != reminder.SnoozeReused || result.ScheduleID != existing.ID {
		t.Fatalf("expected REUSED after a create conflict: %+v", result)
	}
	if len(repository.events) != 0 {
		t.Fatalf("a conflicting create must not write an event: %+v", repository.events)
	}
}

// 技术方案 4.3.1：不存在与不属于该 user 的 decision_id 返回完全一致的拒绝体。
func TestSnoozeRejectsUnknownOrForeignDecision(t *testing.T) {
	unknown := newRepositoryFake()
	unknown.decisionErr = port.ErrNotFound
	foreign := newRepositoryFake()
	foreign.decision.UserID = "someone-else"
	for name, repository := range map[string]*repositoryFake{"unknown": unknown, "foreign": foreign} {
		result, err := defaultService(repository).Snooze(context.Background(), snoozeRequest())
		if err != nil {
			t.Fatalf("%s: snooze: %v", name, err)
		}
		if result.Status != reminder.SnoozeRejected || result.ReasonCode != reminder.ReasonDecisionNotFound || result.ScheduleID != "" {
			t.Fatalf("%s: expected DECISION_NOT_FOUND: %+v", name, result)
		}
		if result.Channel != "" || result.ScheduleType != "" || result.SnoozeUntil != nil {
			t.Fatalf("%s: a rejected result must not carry schedule fields: %+v", name, result)
		}
		if len(repository.events) != 0 {
			t.Fatalf("%s: a rejected request must not write an event: %+v", name, repository.events)
		}
	}
}

// 调用错误（400 INVALID_REQUEST）：入参非法、没有可延后的 INITIAL 排程、或第二次入口。
func TestSnoozeRejectsInvalidCalls(t *testing.T) {
	long := strings.Repeat("x", maxFieldLength+1)
	tests := []struct {
		name    string
		request Request
		mutate  func(*repositoryFake)
	}{
		{"missing request id", Request{UserID: "user-snooze", DecisionID: "decision-1"}, nil},
		{"missing user", Request{DecisionID: "decision-1", RequestID: "snooze-1"}, nil},
		{"missing decision", Request{UserID: "user-snooze", RequestID: "snooze-1"}, nil},
		{"too long request id", Request{UserID: "user-snooze", DecisionID: "decision-1", RequestID: long}, nil},
		{"too long decision id", Request{UserID: "user-snooze", DecisionID: long, RequestID: "snooze-1"}, nil},
		{"too long user id", Request{UserID: long, DecisionID: "decision-1", RequestID: "snooze-1"}, nil},
		{"no schedule", snoozeRequest(), func(f *repositoryFake) { f.latestErr = port.ErrNotFound }},
		{"second entry", snoozeRequest(), func(f *repositoryFake) { f.latest.ScheduleType = reminder.ScheduleSnooze }},
	}
	for _, test := range tests {
		repository := newRepositoryFake()
		if test.mutate != nil {
			test.mutate(repository)
		}
		result, err := defaultService(repository).Snooze(context.Background(), test.request)
		if !errors.Is(err, ErrInvalidRequest) || result.Status != "" {
			t.Fatalf("%s: expected INVALID_REQUEST, got result=%+v err=%v", test.name, result, err)
		}
		if len(repository.events) != 0 {
			t.Fatalf("%s: an invalid call must not write an event", test.name)
		}
	}
}

// 业务拒绝一律 200 + REJECTED + reason_code（4.3.2.3 失败表）。
func TestSnoozeRejectsBusinessRules(t *testing.T) {
	tests := []struct {
		name   string
		task   func(reminder.DailyTask) reminder.DailyTask
		pref   func(reminder.ReminderPreference) reminder.ReminderPreference
		usage  reminder.DailyUsage
		now    time.Time
		reason reminder.ReasonCode
	}{
		{"completed", func(task reminder.DailyTask) reminder.DailyTask {
			task.CompletedCount = task.RequiredCount
			return task
		}, nil, reminder.DailyUsage{}, snoozeNow, reminder.ReasonTaskCompleted},
		{"expired", nil, nil, reminder.DailyUsage{}, snoozeNow.Add(7 * time.Hour), reminder.ReasonTaskExpired},
		{"disabled", nil, func(p reminder.ReminderPreference) reminder.ReminderPreference { p.ReminderEnabled = false; return p }, reminder.DailyUsage{}, snoozeNow, reminder.ReasonReminderDisabled},
		{"quiet hours", nil, nil, reminder.DailyUsage{}, time.Date(2026, 9, 20, 20, 45, 0, 0, time.UTC), reminder.ReasonQuietHours},
		{"push unavailable", nil, func(p reminder.ReminderPreference) reminder.ReminderPreference { p.PushEnabled = false; return p }, reminder.DailyUsage{}, snoozeNow, reminder.ReasonNoAvailableChannel},
		{"daily cap", nil, nil, reminder.DailyUsage{PushSentCount: 1, SnoozeSentCount: 1}, snoozeNow, reminder.ReasonDailyCapReached},
	}
	for _, test := range tests {
		repository := newRepositoryFake()
		service := defaultService(repository)
		service.Clock = clockFake{now: test.now}
		task := service.Tasks.(taskFake)
		task.task.Deadline = test.now.Add(time.Hour)
		if test.task != nil {
			task.task = test.task(task.task)
		}
		service.Tasks = task
		if test.pref != nil {
			preference := service.Preferences.(preferenceFake)
			preference.preference = test.pref(preference.preference)
			service.Preferences = preference
		}
		repository.usage = test.usage
		result, err := service.Snooze(context.Background(), snoozeRequest())
		if err != nil {
			t.Fatalf("%s: snooze: %v", test.name, err)
		}
		if result.Status != reminder.SnoozeRejected || result.ReasonCode != test.reason || result.ScheduleID != "" {
			t.Fatalf("%s: expected %s, got %+v", test.name, test.reason, result)
		}
		if len(repository.schedules) != 0 || len(repository.events) != 0 {
			t.Fatalf("%s: a rejected request must not write data", test.name)
		}
	}
}

// 依赖错误必须向上传递，不能被当成业务拒绝（失败关闭）。
func TestSnoozePropagatesDependencyErrors(t *testing.T) {
	dependency := errors.New("dependency down")
	tests := []struct {
		name   string
		mutate func(*repositoryFake, *Service)
	}{
		{"decision", func(f *repositoryFake, _ *Service) { f.decisionErr = dependency }},
		{"snooze request", func(f *repositoryFake, _ *Service) { f.requestErr = dependency }},
		{"latest schedule", func(f *repositoryFake, _ *Service) { f.latestErr = dependency }},
		{"task", func(_ *repositoryFake, s *Service) { s.Tasks = taskFake{err: dependency} }},
		{"preference", func(_ *repositoryFake, s *Service) { s.Preferences = preferenceFake{err: dependency} }},
		{"usage", func(f *repositoryFake, _ *Service) { f.usageErr = dependency }},
		{"create", func(f *repositoryFake, _ *Service) { f.createErr = dependency }},
		{"event", func(f *repositoryFake, _ *Service) { f.eventErr = dependency }},
	}
	for _, test := range tests {
		repository := newRepositoryFake()
		service := defaultService(repository)
		test.mutate(repository, &service)
		if _, err := service.Snooze(context.Background(), snoozeRequest()); !errors.Is(err, dependency) {
			t.Fatalf("%s: expected the dependency error to surface, got %v", test.name, err)
		}
	}
	// 幂等命中路径上的读取失败同样要暴露为依赖错误。
	repository := newRepositoryFake()
	repository.requestErr = nil
	service := defaultService(repository)
	repository.latestErr = dependency
	if _, err := service.Snooze(context.Background(), snoozeRequest()); !errors.Is(err, dependency) {
		t.Fatalf("expected the reuse path to surface the dependency error: %v", err)
	}
}
