package main

import (
	"context"
	"database/sql"
	"path/filepath"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/adapter/channel"
	"intelligent-reminder-assistant/internal/adapter/task"
	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/application/snooze"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

// 本文件是 AC-011「事件链路完整」的模块集成测试：真实 SQLite + 真实应用用例装配
// （application/evaluate、application/dispatch、application/snooze），断言提醒服务产生的事件
// 都携带 decision_id 与 strategy_version，并且同一 decision_id 下可以按事件序列串联。
//
// 为什么三段链路共用一套结果：AC-011 是横切验收项（PRD 11.2/11.3），它验收的正是
// 「决策、发送、取消、延后」这些链路段能否用同一个 decision_id 串起来，三段共用
// `reminder_event` 这一条模块链路，责任边界见技术方案 4.1.4。
//
// 打开、开始、完成事件由既有 App 与任务系统产生（技术方案 4.1.4），本测试不伪造它们，
// 也不引入事件查询接口：关联键的完整性只通过库表断言验证。

const eventChainTaskDate = "2026-09-20"

// eventChainClock 是事件链用例的固定时钟（默认窗口 19:30 之前），保证评估能产出可发送排程，
// 用例结论不随运行时刻漂移。
var eventChainClock = time.Date(2026, 9, 20, 18, 0, 0, 0, time.UTC)

// eventChainTasks 返回与固定时钟自洽的任务快照：截止时间为时钟 +4 小时，
// 使 19:30 的默认窗口既在免打扰区间之外，也满足「截止前不足 1 小时不提醒」的约束。
func eventChainTasks(taskDate string, completed bool) task.MemoryRepository {
	estimated := 30
	dailyTask := reminder.DailyTask{
		UserID: "user-passive", TaskDate: taskDate, RequiredCount: 5, CompletedCount: 2,
		EstimatedMinutes: &estimated, Deadline: eventChainClock.Add(4 * time.Hour),
	}
	if completed {
		dailyTask.CompletedCount = dailyTask.RequiredCount
	}
	return task.MemoryRepository{Tasks: map[string]reminder.DailyTask{task.Key("user-passive", taskDate): dailyTask}}
}

// eventChainEvent 是事件链断言读取的一行 reminder_event。
type eventChainEvent struct {
	name     string
	decision string
	strategy string
	userID   string
	taskDate string
	eventAt  time.Time
}

// assertEventChain 断言同一 decision_id 下的事件集合、关联键和顺序：
// 事件名必须与期望序列完全一致（既不缺链路段，也不串入其他决策的事件），
// 每行的 decision_id、strategy_version、user_id、task_date 必须与决策一致，事件时间不得倒序。
// 同时做一次全表断言：不允许存在缺关联键的事件行（AC-011 要求每个事件都带 decision_id 和 strategy_version）。
func assertEventChain(t *testing.T, path, decisionID, strategyVersion string, wantNames ...string) {
	t.Helper()
	db, err := sql.Open("sqlite", path)
	if err != nil {
		t.Fatalf("open event chain database: %v", err)
	}
	defer func() { _ = db.Close() }()
	rows, err := db.Query(
		`SELECT event_name, decision_id, strategy_version, user_id, task_date, event_time
		   FROM reminder_event WHERE decision_id = ? ORDER BY event_time, event_name`, decisionID)
	if err != nil {
		t.Fatalf("query event chain: %v", err)
	}
	defer func() { _ = rows.Close() }()
	var chain []eventChainEvent
	for rows.Next() {
		var event eventChainEvent
		var eventAt string
		if err := rows.Scan(&event.name, &event.decision, &event.strategy, &event.userID, &event.taskDate, &eventAt); err != nil {
			t.Fatalf("scan event chain: %v", err)
		}
		parsed, err := time.Parse(time.RFC3339Nano, eventAt)
		if err != nil {
			t.Fatalf("parse event_time %q: %v", eventAt, err)
		}
		event.eventAt = parsed
		chain = append(chain, event)
	}
	if err := rows.Err(); err != nil {
		t.Fatalf("iterate event chain: %v", err)
	}

	if len(chain) != len(wantNames) {
		t.Fatalf("decision %s events = %d, want %d (%v)", decisionID, len(chain), len(wantNames), wantNames)
	}
	for index, want := range wantNames {
		if chain[index].name != want {
			t.Fatalf("decision %s event[%d] = %s, want %s", decisionID, index, chain[index].name, want)
		}
	}
	for index, event := range chain {
		// 关联键与归属：事件必须挂在同一条决策上，否则链路无法按 decision_id 串联。
		if event.decision != decisionID {
			t.Fatalf("event %s is linked to %s, want %s", event.name, event.decision, decisionID)
		}
		if event.strategy != strategyVersion || event.strategy == "" {
			t.Fatalf("event %s strategy_version = %q, want %q", event.name, event.strategy, strategyVersion)
		}
		expectedDate := eventChainTaskDate
		if eventChainDateOverride != "" {
			expectedDate = eventChainDateOverride
		}
		if event.userID != "user-passive" || event.taskDate != expectedDate {
			t.Fatalf("event %s has unexpected owner: %s/%s", event.name, event.userID, event.taskDate)
		}
		// 事件时间不得倒序：后续链路段不能早于前一段，否则序列无法解释。
		if index > 0 && event.eventAt.Before(chain[index-1].eventAt) {
			t.Fatalf("event %s happened before %s", event.name, chain[index-1].name)
		}
	}

	var missing int
	if err := directQueryRow(t, path,
		`SELECT COUNT(*) FROM reminder_event WHERE decision_id = '' OR strategy_version = ''`, nil,
		func(row *sql.Row) error { return row.Scan(&missing) }); err != nil {
		t.Fatalf("count events without link keys: %v", err)
	}
	if missing != 0 {
		t.Fatalf("%d events are missing decision_id or strategy_version", missing)
	}
}

// TestEventChainIntegrationLinksDecisionAndDeliveryEvents 验证「决策 -> 发送」链路段：
// 真实评估用例写出决策事件，真实 dispatch 用例写出发送事件，两者必须挂在同一个 decision_id 上，
// 且同一天另一个策略版本的决策只拥有自己的事件（事件不跨决策串链）。
func TestEventChainIntegrationLinksDecisionAndDeliveryEvents(t *testing.T) {
	path := filepath.Join(t.TempDir(), "event-chain-send.db")
	store := openIntegrationStore(t, path)
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	users := fixtureUsers("user-passive")

	// 链路起点：真实评估用例按固定时钟写出决策与 reminder_decision_created。
	evaluator := evaluate.Service{
		Tasks: eventChainTasks(eventChainTaskDate, false), Preferences: users, Behaviors: users,
		Reminders: store, Clock: fixedClock{now: eventChainClock}, StrategyVersion: "v1",
	}
	first, err := evaluator.Evaluate(ctx, evaluate.Request{UserID: "user-passive", TaskDate: eventChainTaskDate})
	if err != nil || !first.Decision.ShouldRemind || first.Decision.ID == "" {
		t.Fatalf("evaluate: err=%v decision=%+v", err, first.Decision)
	}

	// 同一用户、另一策略版本的决策：其候选窗口落在截止时间之后，只产生决策事件、不产生排程，
	// 用于断言事件不会跨 decision_id 串链（AC-011 的边界等价类）。
	second, err := evaluate.Service{
		Tasks: eventChainTasks("2026-09-21", false), Preferences: users, Behaviors: users,
		Reminders: store, Clock: fixedClock{now: eventChainClock}, StrategyVersion: "v2",
	}.Evaluate(ctx, evaluate.Request{UserID: "user-passive", TaskDate: "2026-09-21"})
	if err != nil || second.Decision.ID == "" || second.Decision.ShouldRemind {
		t.Fatalf("second evaluate must be a rejection without a schedule: err=%v decision=%+v", err, second.Decision)
	}

	// 链路段：真实 dispatch 用例在排程到期后发送，写出 reminder_sent。
	push := &channel.MockPushSender{}
	dispatcher := integrationService(store, users, push, eventChainTasks(eventChainTaskDate, false))
	dispatcher.Clock = fixedClock{now: eventChainClock.Add(91 * time.Minute)}
	counts, err := dispatcher.DispatchDue(ctx, dispatch.Request{BatchSize: 50})
	if err != nil || counts.Sent != 1 {
		t.Fatalf("dispatch: err=%v counts=%+v", err, counts)
	}

	assertEventChain(t, path, first.Decision.ID, "v1", "reminder_decision_created", "reminder_sent")
	assertEventChain(t, path, second.Decision.ID, "v2", "reminder_decision_created")
}

// TestEventChainIntegrationLinksCancellationEvents 验证「决策 -> 取消」链路段：
// 任务已完成导致评估拒绝时，取消事件必须与决策事件同属一个 decision_id。
// 该路径由任务完成短路触发，不依赖运行时刻，因此沿用真实系统时钟。
func TestEventChainIntegrationLinksCancellationEvents(t *testing.T) {
	path := filepath.Join(t.TempDir(), "event-chain-cancel.db")
	now := time.Now().UTC()
	taskDate := now.Format("2006-01-02")
	store := openIntegrationStore(t, path, seededSchedule{id: "schedule-1", scheduledAt: now.Add(time.Hour)})
	defer func() { _ = store.Close() }()

	users := fixtureUsers("user-passive")
	result, err := evaluate.Service{
		Tasks: completedTasks("user-passive", taskDate), Preferences: users, Behaviors: users,
		Reminders: store, Clock: systemClock{}, StrategyVersion: "v1",
	}.Evaluate(context.Background(), evaluate.Request{UserID: "user-passive", TaskDate: taskDate})
	if err != nil || result.Decision.ReasonCode != reminder.ReasonTaskCompleted {
		t.Fatalf("evaluate completed task: err=%v decision=%+v", err, result.Decision)
	}

	// 等价的固定日期口径：本用例的决策日期取自运行当天，因此按同一日期校验链路。
	assertEventChainWithDate(t, path, result.Decision.ID, "v1", taskDate, "reminder_decision_created", "reminder_cancelled")
}

// TestEventChainIntegrationLinksSnoozeEvents 验证「决策 -> 延后」链路段：
// 用户在既有决策上点击稍后提醒后，reminder_snoozed 必须能与该决策的决策事件按 decision_id 串联。
func TestEventChainIntegrationLinksSnoozeEvents(t *testing.T) {
	path := filepath.Join(t.TempDir(), "event-chain-snooze.db")
	store := openIntegrationStore(t, path)
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	users := fixtureUsers("user-passive")

	evaluator := evaluate.Service{
		Tasks: eventChainTasks(eventChainTaskDate, false), Preferences: users, Behaviors: users,
		Reminders: store, Clock: fixedClock{now: eventChainClock}, StrategyVersion: "v1",
	}
	decision, err := evaluator.Evaluate(ctx, evaluate.Request{UserID: "user-passive", TaskDate: eventChainTaskDate})
	if err != nil || !decision.Decision.ShouldRemind {
		t.Fatalf("evaluate: err=%v decision=%+v", err, decision.Decision)
	}

	// 延后路径用固定时钟，保证「一小时后」落在默认窗口内且不落入免打扰区间。
	snoozed, err := snooze.Service{
		Reminders: store, Preferences: users, Tasks: eventChainTasks(eventChainTaskDate, false),
		Clock: fixedClock{now: eventChainClock.Add(5 * time.Minute)},
	}.Snooze(ctx, snooze.Request{UserID: "user-passive", DecisionID: decision.Decision.ID, RequestID: "snooze-1"})
	if err != nil || snoozed.Status != reminder.SnoozeScheduled {
		t.Fatalf("snooze: err=%v result=%+v", err, snoozed)
	}

	assertEventChain(t, path, decision.Decision.ID, "v1", "reminder_decision_created", "reminder_snoozed")
}

// assertEventChainWithDate 与 assertEventChain 断言一致，只把任务日期换成调用方给出的取值，
// 供按运行当天判定的取消用例复用（避免把「今天」写死在常量里）。
func assertEventChainWithDate(t *testing.T, path, decisionID, strategyVersion, taskDate string, wantNames ...string) {
	t.Helper()
	previous := eventChainDateOverride
	eventChainDateOverride = taskDate
	t.Cleanup(func() { eventChainDateOverride = previous })
	assertEventChain(t, path, decisionID, strategyVersion, wantNames...)
}

// eventChainDateOverride 让取消用例用运行当天的任务日期做归属断言：其余用例使用固定日期。
var eventChainDateOverride = ""
