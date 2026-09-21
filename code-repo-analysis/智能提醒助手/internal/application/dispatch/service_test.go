package dispatch

import (
	"context"
	"errors"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/adapter/channel"
	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/port"
)

var fixedNow = time.Date(2026, 9, 20, 19, 30, 0, 0, time.UTC)

type clockFake struct{ now time.Time }

func (c clockFake) Now() time.Time { return c.now }

type preferenceFake struct {
	preference reminder.ReminderPreference
	err        error
}

func (f preferenceFake) Get(context.Context, string) (reminder.ReminderPreference, error) {
	return f.preference, f.err
}

type rendererFake struct {
	content reminder.PushContent
	err     error
	inputs  []reminder.RenderInput
}

func (f *rendererFake) Render(_ context.Context, input reminder.RenderInput) (reminder.PushContent, error) {
	f.inputs = append(f.inputs, input)
	return f.content, f.err
}

type repositoryFake struct {
	due            []reminder.Schedule
	listErr        error
	claimErr       error
	claimConflict  bool
	decision       reminder.Decision
	decisionErr    error
	usage          reminder.DailyUsage
	usageErr       error
	updateErr      error
	updateConflict bool
	deliveryErr    error
	eventErr       error

	claimed    map[string]bool
	updates    []reminder.ScheduleUpdate
	deliveries []reminder.Delivery
	events     []reminder.ReminderEvent
}

func (f *repositoryFake) GetDailyUsage(context.Context, string, string) (reminder.DailyUsage, error) {
	return f.usage, f.usageErr
}

func (f *repositoryFake) GetDecision(context.Context, string) (reminder.Decision, error) {
	return f.decision, f.decisionErr
}

func (f *repositoryFake) CreateDecisionAndSchedule(context.Context, reminder.Decision, *reminder.Schedule) (port.CreateResult, error) {
	return port.CreateResult{}, nil
}

func (f *repositoryFake) ListDueSchedules(context.Context, time.Time, int) ([]reminder.Schedule, error) {
	return f.due, f.listErr
}

func (f *repositoryFake) ClaimSchedule(_ context.Context, scheduleID string, now time.Time) (reminder.Schedule, error) {
	if f.claimErr != nil {
		return reminder.Schedule{}, f.claimErr
	}
	if f.claimed == nil {
		f.claimed = map[string]bool{}
	}
	// 抢占失败结束：同一排程只允许被成功抢占一次，模拟并发 worker 与条件更新语义。
	if f.claimConflict || f.claimed[scheduleID] {
		return reminder.Schedule{}, port.ErrConditionFailed
	}
	f.claimed[scheduleID] = true
	for _, schedule := range f.due {
		if schedule.ID == scheduleID {
			schedule.Status = reminder.ScheduleClaimed
			lease := now.Add(2 * time.Minute)
			schedule.LeaseUntil = &lease
			return schedule, nil
		}
	}
	return reminder.Schedule{}, port.ErrConditionFailed
}

func (f *repositoryFake) UpdateSchedule(_ context.Context, update reminder.ScheduleUpdate) error {
	if f.updateErr != nil {
		return f.updateErr
	}
	if f.updateConflict {
		return port.ErrConditionFailed
	}
	f.updates = append(f.updates, update)
	return nil
}

func (f *repositoryFake) UpdateDeliveryStatus(_ context.Context, delivery reminder.Delivery) error {
	if f.deliveryErr != nil {
		return f.deliveryErr
	}
	f.deliveries = append(f.deliveries, delivery)
	return nil
}

func (f *repositoryFake) AppendEvent(_ context.Context, event reminder.ReminderEvent) error {
	if f.eventErr != nil {
		return f.eventErr
	}
	f.events = append(f.events, event)
	return nil
}

func newService(repository *repositoryFake, preference preferenceFake, renderer *rendererFake, push port.PushSender) Service {
	return Service{
		Reminders:     repository,
		Preferences:   preference,
		Renderer:      renderer,
		Push:          push,
		Clock:         clockFake{now: fixedNow},
		MaxPushPerDay: 1,
	}
}

func dueSchedule(scheduleType reminder.ScheduleType) reminder.Schedule {
	return reminder.Schedule{
		ID: "schedule-1", DecisionID: "decision-1", UserID: "user-passive", TaskDate: "2026-09-20",
		ScheduleVersion: 1, Channel: reminder.ChannelPush, ScheduleType: scheduleType,
		ScheduledAt: fixedNow.Add(-time.Minute), Status: reminder.ScheduleScheduled,
		CreatedAt: fixedNow, UpdatedAt: fixedNow,
	}
}

func decisionFixture() reminder.Decision {
	return reminder.Decision{ID: "decision-1", UserID: "user-passive", TaskDate: "2026-09-20", StrategyVersion: "v1"}
}

func enabledPreference() preferenceFake {
	return preferenceFake{preference: reminder.ReminderPreference{ReminderEnabled: true, PushEnabled: true, DailyPushCap: 1, Timezone: "UTC"}}
}

func repositoryWithDue(scheduleType reminder.ScheduleType) *repositoryFake {
	return &repositoryFake{due: []reminder.Schedule{dueSchedule(scheduleType)}, decision: decisionFixture()}
}

func TestDispatchSendsDueScheduleAndKeepsOneDelivery(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	renderer := &rendererFake{content: reminder.PushContent{DeepLink: "today_task_page"}}
	push := &channel.MockPushSender{}
	counts, err := newService(repository, enabledPreference(), renderer, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Scanned != 1 || counts.Claimed != 1 || counts.Sent != 1 || counts.Cancelled != 0 || counts.Failed != 0 || counts.Unknown != 0 || counts.Retried != 0 || !counts.Finished {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	requests := push.Requests()
	if len(requests) != 1 || requests[0].AttemptNo != 1 || requests[0].IdempotencyKey != "user-passive_2026-09-20_push_decision-1_1" {
		t.Fatalf("unexpected push requests: %+v", requests)
	}
	// 过期时间取用户本地当日 24:00。
	if requests[0].ExpireAt.UTC().Format(time.RFC3339) != "2026-09-21T00:00:00Z" {
		t.Fatalf("unexpected expire time: %s", requests[0].ExpireAt)
	}
	if len(repository.deliveries) != 1 || repository.deliveries[0].Status != reminder.DeliverySent || repository.deliveries[0].SentAt == nil {
		t.Fatalf("unexpected delivery record: %+v", repository.deliveries)
	}
	// 排程状态按状态机推进：CLAIMED -> SENDING -> SENT。
	wantStatuses := []reminder.ScheduleStatus{reminder.ScheduleSending, reminder.ScheduleSent}
	if len(repository.updates) != len(wantStatuses) {
		t.Fatalf("unexpected schedule updates: %+v", repository.updates)
	}
	for index, want := range wantStatuses {
		if repository.updates[index].ToStatus != want {
			t.Fatalf("update %d: got %s want %s", index, repository.updates[index].ToStatus, want)
		}
	}
	if len(repository.events) != 1 || repository.events[0].EventName != "reminder_sent" || repository.events[0].StrategyVersion != "v1" {
		t.Fatalf("unexpected events: %+v", repository.events)
	}
}

func TestDispatchCancelsWhenDailyCapReached(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	repository.usage = reminder.DailyUsage{PushSentCount: 1}
	push := &channel.MockPushSender{}
	counts, err := newService(repository, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Cancelled != 1 || counts.Sent != 0 || counts.Claimed != 1 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	if len(push.Requests()) != 0 {
		t.Fatal("daily cap must stop the second system push")
	}
	if len(repository.updates) != 1 || repository.updates[0].ToStatus != reminder.ScheduleCancelled || repository.updates[0].CancelReason != reminder.ReasonDailyCapReached {
		t.Fatalf("unexpected cancel update: %+v", repository.updates)
	}
	if len(repository.events) != 1 || repository.events[0].EventName != "reminder_cancelled" {
		t.Fatalf("unexpected events: %+v", repository.events)
	}
	if repository.events[0].Payload["cancel_reason"] != string(reminder.ReasonDailyCapReached) {
		t.Fatalf("unexpected cancel payload: %+v", repository.events[0].Payload)
	}
}

func TestDispatchSnoozeUsageIsMeteredSeparately(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleSnooze)
	repository.usage = reminder.DailyUsage{PushSentCount: 1}
	push := &channel.MockPushSender{}
	counts, err := newService(repository, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Sent != 1 || counts.Cancelled != 0 {
		t.Fatalf("snooze push must not consume the system cap: %+v", counts)
	}
	if len(push.Requests()) != 1 {
		t.Fatal("expected the snooze reminder to be sent")
	}
}

func TestDispatchSkipsUnauthorizedPush(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	push := &channel.MockPushSender{}
	preference := enabledPreference()
	preference.preference.PushEnabled = false
	counts, err := newService(repository, preference, &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Cancelled != 1 || counts.Sent != 0 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	if len(push.Requests()) != 0 {
		t.Fatal("unauthorized push must not call the channel")
	}
	if repository.updates[0].CancelReason != reminder.ReasonNoAvailableChannel {
		t.Fatalf("unexpected cancel reason: %+v", repository.updates[0])
	}
}

func TestDispatchRetriesExplicitFailureOnceAndReusesIdempotencyKey(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	push := &channel.MockPushSender{Results: []reminder.PushResult{
		{Status: string(reminder.DeliveryFailed), ErrorCode: "CHANNEL_SEND_FAILED"},
		{Status: string(reminder.DeliveryFailed), ErrorCode: "CHANNEL_SEND_FAILED"},
	}}
	counts, err := newService(repository, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Failed != 1 || counts.Retried != 1 || counts.Sent != 0 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	requests := push.Requests()
	if len(requests) != 2 {
		t.Fatalf("expected exactly one retry: %+v", requests)
	}
	if requests[0].IdempotencyKey != requests[1].IdempotencyKey {
		t.Fatal("retry must reuse the same idempotency key")
	}
	if requests[1].AttemptNo != 2 {
		t.Fatalf("unexpected attempt number: %+v", requests[1])
	}
	lastDelivery := repository.deliveries[len(repository.deliveries)-1]
	if len(repository.deliveries) != 3 || lastDelivery.AttemptNo != 2 || lastDelivery.Status != reminder.DeliveryFailed {
		t.Fatalf("unexpected deliveries: %+v", repository.deliveries)
	}
	if repository.deliveries[0].IdempotencyKey != lastDelivery.IdempotencyKey {
		t.Fatal("delivery retries must not create a second business reminder record")
	}
	names := []string{}
	for _, event := range repository.events {
		names = append(names, event.EventName)
	}
	if len(names) != 2 || names[0] != "reminder_failed" || names[1] != "reminder_failed" {
		t.Fatalf("unexpected events: %v", names)
	}
	if repository.events[0].Payload["will_retry"] != true || repository.events[1].Payload["will_retry"] != false {
		t.Fatalf("unexpected failure payloads: %+v", repository.events)
	}
	wantStatuses := []reminder.ScheduleStatus{reminder.ScheduleSending, reminder.ScheduleRetryWait, reminder.ScheduleSending, reminder.ScheduleFailed}
	for index, want := range wantStatuses {
		if repository.updates[index].ToStatus != want {
			t.Fatalf("update %d: got %s want %s", index, repository.updates[index].ToStatus, want)
		}
	}
}

func TestDispatchSucceedsOnRetry(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	push := &channel.MockPushSender{Results: []reminder.PushResult{
		{Status: string(reminder.DeliveryFailed), ErrorCode: "CHANNEL_SEND_FAILED"},
		{Status: string(reminder.DeliverySent)},
	}}
	counts, err := newService(repository, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Sent != 1 || counts.Retried != 1 || counts.Failed != 0 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	if repository.deliveries[len(repository.deliveries)-1].Status != reminder.DeliverySent {
		t.Fatalf("unexpected deliveries: %+v", repository.deliveries)
	}
}

func TestDispatchKeepsUnknownForReconcileAndQueriesOnce(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	push := &channel.MockPushSender{Results: []reminder.PushResult{{Status: string(reminder.DeliveryUnknown)}}}
	counts, err := newService(repository, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Unknown != 1 || counts.Sent != 0 || counts.Failed != 0 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
	if len(push.Queries()) != 1 || push.Queries()[0].IdempotencyKey != "user-passive_2026-09-20_push_decision-1_1" {
		t.Fatalf("unexpected queries: %+v", push.Queries())
	}
	if repository.deliveries[len(repository.deliveries)-1].Status != reminder.DeliveryUnknown {
		t.Fatalf("unexpected deliveries: %+v", repository.deliveries)
	}
	if repository.updates[1].ToStatus != reminder.ScheduleUnknown {
		t.Fatalf("unexpected schedule status: %+v", repository.updates)
	}
	if repository.events[0].Payload["delivery_status"] != string(reminder.DeliveryUnknown) {
		t.Fatalf("unexpected event payload: %+v", repository.events[0].Payload)
	}
}

func TestDispatchResolvesUnknownThroughQuery(t *testing.T) {
	cases := map[reminder.DeliveryStatus]string{
		reminder.DeliverySent:   "sent",
		reminder.DeliveryFailed: "failed",
	}
	for queryStatus, name := range cases {
		repository := repositoryWithDue(reminder.ScheduleInitial)
		push := &channel.MockPushSender{
			Results:     []reminder.PushResult{{Status: string(reminder.DeliveryUnknown)}},
			QueryStatus: queryStatus,
		}
		counts, err := newService(repository, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
		if err != nil {
			t.Fatalf("%s: dispatch: %v", name, err)
		}
		switch queryStatus {
		case reminder.DeliverySent:
			if counts.Sent != 1 || counts.Unknown != 0 {
				t.Fatalf("%s: unexpected counts: %+v", name, counts)
			}
		case reminder.DeliveryFailed:
			if counts.Failed != 1 || counts.Unknown != 0 {
				t.Fatalf("%s: unexpected counts: %+v", name, counts)
			}
		}
	}
}

func TestDispatchTreatsChannelErrorAndQueryErrorAsUnknown(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	push := &channel.MockPushSender{SendErr: errors.New("channel timeout"), QueryErr: errors.New("query timeout")}
	counts, err := newService(repository, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("dispatch: %v", err)
	}
	if counts.Unknown != 1 {
		t.Fatalf("unexpected counts: %+v", counts)
	}
}

func TestDispatchReleasesClaimOnDependencyFailures(t *testing.T) {
	cases := map[string]func() (Service, *repositoryFake, *channel.MockPushSender){
		"decision read": func() (Service, *repositoryFake, *channel.MockPushSender) {
			repository := repositoryWithDue(reminder.ScheduleInitial)
			repository.decisionErr = errors.New("database down")
			push := &channel.MockPushSender{}
			return newService(repository, enabledPreference(), &rendererFake{}, push), repository, push
		},
		"preference read": func() (Service, *repositoryFake, *channel.MockPushSender) {
			repository := repositoryWithDue(reminder.ScheduleInitial)
			preference := enabledPreference()
			preference.err = errors.New("preference timeout")
			push := &channel.MockPushSender{}
			return newService(repository, preference, &rendererFake{}, push), repository, push
		},
		"usage read": func() (Service, *repositoryFake, *channel.MockPushSender) {
			repository := repositoryWithDue(reminder.ScheduleInitial)
			repository.usageErr = errors.New("usage query failed")
			push := &channel.MockPushSender{}
			return newService(repository, enabledPreference(), &rendererFake{}, push), repository, push
		},
		"render": func() (Service, *repositoryFake, *channel.MockPushSender) {
			repository := repositoryWithDue(reminder.ScheduleInitial)
			push := &channel.MockPushSender{}
			return newService(repository, enabledPreference(), &rendererFake{err: errors.New("render failed")}, push), repository, push
		},
	}
	for name, build := range cases {
		service, repository, push := build()
		if _, err := service.DispatchDue(context.Background(), Request{}); err == nil {
			t.Fatalf("%s: expected dependency error", name)
		}
		if len(push.Requests()) != 0 {
			t.Fatalf("%s: dependency failure must not call the channel", name)
		}
		last := repository.updates[len(repository.updates)-1]
		if last.ToStatus != reminder.ScheduleScheduled || last.FromStatus != reminder.ScheduleClaimed {
			t.Fatalf("%s: expected the claim to be released: %+v", name, repository.updates)
		}
	}
}

func TestDispatchSurfacesDatabaseErrors(t *testing.T) {
	cases := map[string]func(*repositoryFake){
		"list":     func(repository *repositoryFake) { repository.listErr = errors.New("list failed") },
		"claim":    func(repository *repositoryFake) { repository.claimErr = errors.New("claim failed") },
		"delivery": func(repository *repositoryFake) { repository.deliveryErr = errors.New("delivery failed") },
		"update":   func(repository *repositoryFake) { repository.updateErr = errors.New("update failed") },
		"event":    func(repository *repositoryFake) { repository.eventErr = errors.New("event failed") },
	}
	for name, broken := range cases {
		repository := repositoryWithDue(reminder.ScheduleInitial)
		broken(repository)
		if _, err := newService(repository, enabledPreference(), &rendererFake{}, &channel.MockPushSender{}).DispatchDue(context.Background(), Request{}); err == nil {
			t.Fatalf("%s: expected database error", name)
		}
	}
}

func TestDispatchEndsWhenClaimFailsAndWhenConditionUpdatesLose(t *testing.T) {
	conflict := repositoryWithDue(reminder.ScheduleInitial)
	conflict.claimConflict = true
	push := &channel.MockPushSender{}
	counts, err := newService(conflict, enabledPreference(), &rendererFake{}, push).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("claim conflict must end quietly: %v", err)
	}
	if counts.Claimed != 0 || counts.Sent != 0 || len(push.Requests()) != 0 || len(conflict.updates) != 0 {
		t.Fatalf("claim conflict must not send or update: %+v", counts)
	}
	// 条件更新被其他执行者抢先时放弃本次动作，但仍按业务结果计数与记录事件。
	lost := repositoryWithDue(reminder.ScheduleInitial)
	lost.updateConflict = true
	counts, err = newService(lost, enabledPreference(), &rendererFake{}, &channel.MockPushSender{}).DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("condition conflict must not fail the batch: %v", err)
	}
	if counts.Sent != 1 || len(lost.events) != 1 {
		t.Fatalf("unexpected counts after condition conflict: %+v", counts)
	}
}

func TestDispatchIsIdempotentAcrossRepeatedBatches(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	push := &channel.MockPushSender{}
	service := newService(repository, enabledPreference(), &rendererFake{}, push)
	first, err := service.DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("first batch: %v", err)
	}
	second, err := service.DispatchDue(context.Background(), Request{})
	if err != nil {
		t.Fatalf("second batch: %v", err)
	}
	if first.Sent != 1 || second.Sent != 0 || second.Claimed != 0 {
		t.Fatalf("unexpected batch results: %+v %+v", first, second)
	}
	if len(push.Requests()) != 1 {
		t.Fatal("repeated dispatch must not create a second send record")
	}
	if len(repository.deliveries) != 1 {
		t.Fatalf("repeated dispatch must keep exactly one delivery record: %+v", repository.deliveries)
	}
}

func TestDispatchValidatesBatchSize(t *testing.T) {
	repository := repositoryWithDue(reminder.ScheduleInitial)
	service := newService(repository, enabledPreference(), &rendererFake{}, &channel.MockPushSender{})
	if _, err := service.DispatchDue(context.Background(), Request{BatchSize: -1}); err == nil {
		t.Fatal("expected a negative batch size to be rejected")
	}
	if _, err := service.DispatchDue(context.Background(), Request{BatchSize: 51}); err == nil {
		t.Fatal("expected a batch size above the hard cap to be rejected")
	}
	if _, err := service.DispatchDue(context.Background(), Request{BatchSize: 1}); err != nil {
		t.Fatalf("explicit batch size: %v", err)
	}
	// 空批次：没有到期排程时返回全 0 计数并标记 finished。
	empty := &repositoryFake{}
	counts, err := newService(empty, enabledPreference(), &rendererFake{}, &channel.MockPushSender{}).DispatchDue(context.Background(), Request{})
	if err != nil || counts.Scanned != 0 || !counts.Finished {
		t.Fatalf("unexpected empty batch result: %+v err=%v", counts, err)
	}
}
