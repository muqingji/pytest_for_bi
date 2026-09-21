// 本文件覆盖逐 Case 前置状态播种的成功与失败边界，防止坏 Fixture 被静默写入测试库。
package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/adapter/storage"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

func writeCaseSetupFile(t *testing.T, content string) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "case-setup.json")
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("write case setup: %v", err)
	}
	return path
}

func caseSetupDependencies(t *testing.T) (*storage.Store, fixtures) {
	t.Helper()
	store, err := storage.Open(filepath.Join(t.TempDir(), "setup.db"))
	if err != nil {
		t.Fatalf("open setup store: %v", err)
	}
	if err := store.Migrate(context.Background()); err != nil {
		t.Fatalf("migrate setup store: %v", err)
	}
	seeds, err := loadFixtures(repoFixturePath(t), nowFunc)
	if err != nil {
		t.Fatalf("load repository fixtures: %v", err)
	}
	return store, seeds
}

// TestSeedCaseSetupCreatesDispatchAndSnoozeState 验证两种已审批 setup 结构都能落到真实 SQLite：
// dispatch 使用到期 SCHEDULED 排程，snooze 使用已发送 INITIAL 排程。
func TestSeedCaseSetupCreatesDispatchAndSnoozeState(t *testing.T) {
	now := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
	tests := []struct {
		name       string
		userID     string
		setupKey   string
		status     reminder.ScheduleStatus
		extraSetup string
	}{
		{name: "dispatch", userID: "case-disp-012", setupKey: "schedule", status: reminder.ScheduleScheduled, extraSetup: `,"channel_result":"SUCCESS"`},
		{name: "snooze", userID: "case-snz-001", setupKey: "initial_decision", status: reminder.ScheduleSent},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			store, seeds := caseSetupDependencies(t)
			defer func() { _ = store.Close() }()
			content := `{"user_id":"` + testCase.userID + `","task_date":"2026-09-20","setup":{"` + testCase.setupKey + `":{` +
				`"decision_id":"decision-` + testCase.name + `","schedule_id":"schedule-` + testCase.name + `",` +
				`"schedule_type":"INITIAL","status":"` + string(testCase.status) + `","scheduled_at":"2026-09-20T11:59:00Z"}` + testCase.extraSetup + `}}`
			if err := seedCaseSetup(context.Background(), store, seeds, writeCaseSetupFile(t, content), now); err != nil {
				t.Fatalf("seed case setup: %v", err)
			}
			decision, err := store.GetDecision(context.Background(), "decision-"+testCase.name)
			if err != nil || decision.UserID != testCase.userID || decision.TaskDate != "2026-09-20" {
				t.Fatalf("unexpected seeded decision: %+v err=%v", decision, err)
			}
			schedule, err := store.GetLatestScheduleByDecision(context.Background(), decision.ID)
			if err != nil || schedule.Status != testCase.status || schedule.ScheduleType != reminder.ScheduleInitial {
				t.Fatalf("unexpected seeded schedule: %+v err=%v", schedule, err)
			}
		})
	}
}

// TestSeedCaseSetupValidatesLatestTaskAndPayload 证明 TC-007 的 5/3/20 快照不是说明文字：
// 播种前会从绑定 Fixture 读取任务，并核对剩余数、预计用时与 OPEN_TASK 操作。
func TestSeedCaseSetupValidatesLatestTaskAndPayload(t *testing.T) {
	store, seeds := caseSetupDependencies(t)
	defer func() { _ = store.Close() }()
	content := `{
  "user_id":"case-disp-013","task_date":"2026-09-20","setup":{
    "schedule":{"decision_id":"decision-payload","schedule_id":"schedule-payload","schedule_type":"INITIAL","status":"SCHEDULED","scheduled_at":"2026-09-20T11:59:00Z"},
    "channel_result":"SUCCESS",
    "latest_task":{"required_count":5,"completed_count":3,"remaining_count":2,"estimated_minutes":20},
    "expected_channel_payload":{"remaining_count":2,"estimated_minutes":20,"action":"OPEN_TASK"}
  }
}`
	if err := seedCaseSetup(context.Background(), store, seeds, writeCaseSetupFile(t, content), time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)); err != nil {
		t.Fatalf("valid task-bound setup must be seeded: %v", err)
	}
}

// TestSeedCaseSetupRejectsInvalidFiles 覆盖 setup 文件、绑定关系和渠道桩配置的失败关闭。
func TestSeedCaseSetupRejectsInvalidFiles(t *testing.T) {
	store, seeds := caseSetupDependencies(t)
	defer func() { _ = store.Close() }()
	now := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
	if err := seedCaseSetup(context.Background(), store, seeds, "", now); err != nil {
		t.Fatalf("empty setup path must be a no-op: %v", err)
	}
	tests := []struct {
		name    string
		path    string
		content string
		want    string
	}{
		{name: "missing file", path: filepath.Join(t.TempDir(), "missing.json"), want: "read case setup"},
		{name: "bad json", content: `{`, want: "parse case setup"},
		{name: "missing binding", content: `{"setup":{}}`, want: "user_id and task_date"},
		{name: "unknown fixture", content: `{"user_id":"missing","task_date":"2026-09-20","setup":{}}`, want: "is not present"},
		{name: "unsupported channel", content: `{"user_id":"case-disp-012","task_date":"2026-09-20","setup":{"channel_result":"FAILED"}}`, want: "unsupported by the local success stub"},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			path := testCase.path
			if path == "" {
				path = writeCaseSetupFile(t, testCase.content)
			}
			if err := seedCaseSetup(context.Background(), store, seeds, path, now); err == nil || !strings.Contains(err.Error(), testCase.want) {
				t.Fatalf("error=%v want substring %q", err, testCase.want)
			}
		})
	}
}

// TestFixtureCaseSetupSelectsOneSchedule 验证两种 setup 语义互斥，也允许纯静态 Fixture 的 Case 不带排程。
func TestFixtureCaseSetupSelectsOneSchedule(t *testing.T) {
	schedule := &fixtureSchedule{DecisionID: "d"}
	if got, err := (fixtureCaseSetup{Schedule: schedule}).scheduleSeed(); err != nil || got != schedule {
		t.Fatalf("schedule seed=%+v err=%v", got, err)
	}
	if got, err := (fixtureCaseSetup{InitialDecision: schedule}).scheduleSeed(); err != nil || got != schedule {
		t.Fatalf("initial decision seed=%+v err=%v", got, err)
	}
	if got, err := (fixtureCaseSetup{}).scheduleSeed(); err != nil || got != nil {
		t.Fatalf("empty setup must not create a schedule: %+v err=%v", got, err)
	}
	if _, err := (fixtureCaseSetup{Schedule: schedule, InitialDecision: schedule}).scheduleSeed(); err == nil {
		t.Fatal("two schedule sources must be rejected")
	}
}

// TestValidateScheduleSeedRejectsMalformedState 覆盖标识、类型和状态约束，避免非法行造成“扫描为零”的伪结果。
func TestValidateScheduleSeedRejectsMalformedState(t *testing.T) {
	valid := fixtureSchedule{DecisionID: "d", ScheduleID: "s", ScheduleType: "INITIAL", Status: "SCHEDULED", ScheduledAt: "2026-09-20T11:59:00Z"}
	if scheduleType, status, err := validateScheduleSeed(valid); err != nil || scheduleType != reminder.ScheduleInitial || status != reminder.ScheduleScheduled {
		t.Fatalf("valid seed rejected: type=%s status=%s err=%v", scheduleType, status, err)
	}
	tests := []fixtureSchedule{
		{ScheduleType: "INITIAL", Status: "SCHEDULED"},
		{DecisionID: "d", ScheduleID: "s", ScheduleType: "SNOOZE", Status: "SCHEDULED", ScheduledAt: valid.ScheduledAt},
		{DecisionID: "d", ScheduleID: "s", ScheduleType: "INITIAL", Status: "FAILED", ScheduledAt: valid.ScheduledAt},
	}
	for _, seed := range tests {
		if _, _, err := validateScheduleSeed(seed); err == nil {
			t.Fatalf("invalid schedule seed must fail: %+v", seed)
		}
	}
}

// TestSeedCaseSetupRejectsInvalidStateAndStorageFailure 覆盖时间解析、任务绑定及最终写库失败。
func TestSeedCaseSetupRejectsInvalidStateAndStorageFailure(t *testing.T) {
	store, seeds := caseSetupDependencies(t)
	now := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC)
	base := `{"user_id":"case-disp-013","task_date":"2026-09-20","setup":%s}`
	tests := []struct {
		name  string
		setup string
		ctx   context.Context
		want  string
	}{
		{name: "bad time", setup: `{"schedule":{"decision_id":"d","schedule_id":"s","schedule_type":"INITIAL","status":"SCHEDULED","scheduled_at":"bad"}}`, want: "parse case setup scheduled_at"},
		{name: "bad task", setup: `{"latest_task":{"required_count":99}}`, want: "does not match fixture task"},
		{name: "bad payload", setup: `{"expected_channel_payload":{"remaining_count":2,"estimated_minutes":20,"action":"SNOOZE"}}`, want: "does not match fixture task"},
	}
	cancelled, cancel := context.WithCancel(context.Background())
	cancel()
	tests = append(tests, struct {
		name  string
		setup string
		ctx   context.Context
		want  string
	}{name: "cancelled task read", setup: `{"latest_task":{"required_count":5,"completed_count":3,"remaining_count":2,"estimated_minutes":20}}`, ctx: cancelled, want: "read case setup fixture task"})
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			ctx := testCase.ctx
			if ctx == nil {
				ctx = context.Background()
			}
			path := writeCaseSetupFile(t, strings.Replace(base, "%s", testCase.setup, 1))
			if err := seedCaseSetup(ctx, store, seeds, path, now); err == nil || !strings.Contains(err.Error(), testCase.want) {
				t.Fatalf("error=%v want substring %q", err, testCase.want)
			}
		})
	}
	if err := store.Close(); err != nil {
		t.Fatalf("close setup store: %v", err)
	}
	valid := strings.Replace(base, "%s", `{"schedule":{"decision_id":"d","schedule_id":"s","schedule_type":"INITIAL","status":"SCHEDULED","scheduled_at":"2026-09-20T11:59:00Z"}}`, 1)
	if err := seedCaseSetup(context.Background(), store, seeds, writeCaseSetupFile(t, valid), now); err == nil || !strings.Contains(err.Error(), "seed case decision and schedule") {
		t.Fatalf("closed storage must fail: %v", err)
	}
}
