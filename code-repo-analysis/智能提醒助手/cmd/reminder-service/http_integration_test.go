package main

import (
	"context"
	"encoding/json"
	"net"
	nethttp "net/http"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// 本文件是本地 HTTP 入口的模块集成测试：真实 SQLite + 真实种子文件 + 真实装配（assemble）
// + 真实 HTTP 监听，验证 pytest 的请求方式在本地确实可用。联调类型为本地 Mock 联调（MockPushSender，不发真实 Push）。
//
// 时间通过 nowFunc 固定，避免结论随运行时刻漂移；固定值选在免打扰区间之外且早于种子截止时间。

// fixedEntryNow 是本地入口集成测试使用的固定时刻（种子行为的窗口之外、免打扰之外）。
var fixedEntryNow = time.Date(2026, 9, 21, 10, 0, 0, 0, time.UTC)

// startHTTPEntry 装配并启动本地入口，返回基地址与关闭函数。
func startHTTPEntry(t *testing.T) (string, func()) {
	t.Helper()
	store := openIntegrationStore(t, filepath.Join(t.TempDir(), "http-entry.db"))
	seeds, err := loadFixtures(repoFixturePath(t), nowFunc)
	if err != nil {
		_ = store.Close()
		t.Fatalf("load fixtures: %v", err)
	}
	server := assemble(store, seeds, testServiceToken)
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		_ = store.Close()
		t.Fatalf("listen: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan error, 1)
	go func() { done <- server.ServeListener(ctx, listener) }()

	return "http://" + listener.Addr().String(), func() {
		cancel()
		select {
		case err := <-done:
			if err != nil {
				t.Errorf("local entry shutdown: %v", err)
			}
		case <-time.After(10 * time.Second):
			t.Error("local entry did not stop")
		}
		_ = store.Close()
	}
}

// postJSON 发一次 JSON 请求并解出响应体；token 为空时不带鉴权头。
func postJSON(t *testing.T, base, path, token, body string) (int, map[string]any) {
	t.Helper()
	request, err := nethttp.NewRequest(nethttp.MethodPost, base+path, strings.NewReader(body))
	if err != nil {
		t.Fatalf("build request %s: %v", path, err)
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("X-Request-ID", "integration-rid")
	if token != "" {
		request.Header.Set("Authorization", "Bearer "+token)
	}
	response, err := nethttp.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("call %s: %v", path, err)
	}
	defer func() { _ = response.Body.Close() }()
	var decoded map[string]any
	if err := json.NewDecoder(response.Body).Decode(&decoded); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	if got := response.Header.Get("X-Request-ID"); got != "integration-rid" {
		t.Fatalf("%s must echo X-Request-ID: %q", path, got)
	}
	return response.StatusCode, decoded
}

// TestHTTPEntryIntegrationClosesThePushLoop 覆盖本地入口的完整链路：
// 评估生成 Push 排程（幂等）→ 到期前调度不发 → 到点后调度发出 → 延后第二次入口被拒 → 鉴权与参数错误拦截。
func TestHTTPEntryIntegrationClosesThePushLoop(t *testing.T) {
	restore := nowFunc
	nowFunc = func() time.Time { return fixedEntryNow }
	defer func() { nowFunc = restore }()

	base, stop := startHTTPEntry(t)
	defer stop()

	taskDate := fixedEntryNow.Format("2006-01-02")
	evaluateBody := `{"request_id":"req-1","user_id":"user-passive","task_date":"` + taskDate + `","trigger":"DAILY_BATCH"}`

	status, created := postJSON(t, base, "/internal/v1/reminders/evaluate", testServiceToken, evaluateBody)
	if status != nethttp.StatusOK || created["status"] != "CREATED" || created["should_remind"] != true {
		t.Fatalf("evaluate status=%d body=%v", status, created)
	}
	if created["channel"] != "push" || created["scheduled_at"] != "2026-09-21T19:30:00Z" {
		t.Fatalf("unexpected schedule fields: %v", created)
	}
	decisionID, _ := created["decision_id"].(string)
	if decisionID == "" {
		t.Fatalf("decision id must be returned: %v", created)
	}

	// 幂等：同一 (user_id, task_date, strategy_version) 重复评估返回原决策，不新建排程。
	status, reused := postJSON(t, base, "/internal/v1/reminders/evaluate", testServiceToken, evaluateBody)
	if status != nethttp.StatusOK || reused["status"] != "REUSED" || reused["decision_id"] != decisionID {
		t.Fatalf("repeated evaluate must be idempotent: status=%d body=%v", status, reused)
	}

	// 其他注册用户按种子状态给出业务拒绝，仍是 200 + 业务字段。
	status, expired := postJSON(t, base, "/internal/v1/reminders/evaluate", testServiceToken,
		`{"request_id":"req-2","user_id":"user-passive-expired","task_date":"`+taskDate+`","trigger":"DAILY_BATCH"}`)
	if status != nethttp.StatusOK || expired["status"] != "REJECTED" || expired["reason_code"] != "TASK_EXPIRED" {
		t.Fatalf("expired task must be a business rejection: status=%d body=%v", status, expired)
	}
	status, noTask := postJSON(t, base, "/internal/v1/reminders/evaluate", testServiceToken,
		`{"request_id":"req-3","user_id":"user-passive-no-task","task_date":"`+taskDate+`","trigger":"DAILY_BATCH"}`)
	if status != nethttp.StatusOK || noTask["status"] != "REJECTED" || noTask["reason_code"] != "NO_TASK" {
		t.Fatalf("no task must be a business rejection: status=%d body=%v", status, noTask)
	}

	// 排程时刻在 19:30，10:00 扫描不到到期排程。
	status, pending := postJSON(t, base, "/internal/v1/reminders/dispatch-due", testServiceToken, "")
	if status != nethttp.StatusOK || pending["scanned"] != float64(0) || pending["sent"] != float64(0) {
		t.Fatalf("no schedule is due yet: status=%d body=%v", status, pending)
	}

	// 时间推进到排程之后，同一批次必须真的发出这条 Push。
	nowFunc = func() time.Time { return time.Date(2026, 9, 21, 20, 0, 0, 0, time.UTC) }
	status, sent := postJSON(t, base, "/internal/v1/reminders/dispatch-due", testServiceToken, `{"batch_size":50}`)
	if status != nethttp.StatusOK || sent["scanned"] != float64(1) || sent["sent"] != float64(1) || sent["finished"] != true {
		t.Fatalf("due schedule must be sent: status=%d body=%v", status, sent)
	}

	// 延后入口：同一决策第二次调用（换 request_id）属非法调用，返回 400 而非业务拒绝。
	snoozeBody := `{"request_id":"snooze-1","user_id":"user-passive"}`
	status, snoozed := postJSON(t, base, "/internal/v1/reminders/"+decisionID+"/snooze", testServiceToken, snoozeBody)
	if status != nethttp.StatusOK || snoozed["status"] != "SCHEDULED" || snoozed["snooze_until"] != "2026-09-21T21:00:00Z" ||
		snoozed["schedule_type"] != "SNOOZE" {
		t.Fatalf("snooze must create a deferred push: status=%d body=%v", status, snoozed)
	}
	status, second := postJSON(t, base, "/internal/v1/reminders/"+decisionID+"/snooze", testServiceToken,
		`{"request_id":"snooze-2","user_id":"user-passive"}`)
	if status != nethttp.StatusBadRequest || second["code"] != "INVALID_REQUEST" {
		t.Fatalf("second snooze entry must be rejected as an invalid call: status=%d body=%v", status, second)
	}
	// 同一 request_id 重复调用返回原排程（幂等），不产生第三次 Push。
	status, repeated := postJSON(t, base, "/internal/v1/reminders/"+decisionID+"/snooze", testServiceToken, snoozeBody)
	if status != nethttp.StatusOK || repeated["status"] != "REUSED" {
		t.Fatalf("repeated snooze request must reuse the schedule: status=%d body=%v", status, repeated)
	}

	// 鉴权、未知路由与参数错误都在业务逻辑之前拦截。
	if status, envelope := postJSON(t, base, "/internal/v1/reminders/dispatch-due", "", ""); status != nethttp.StatusUnauthorized ||
		envelope["code"] != "INVALID_REQUEST" {
		t.Fatalf("missing credential must be 401: status=%d body=%v", status, envelope)
	}
	if status, _ := postJSON(t, base, "/internal/v1/reminders/unknown", testServiceToken, ""); status != nethttp.StatusNotFound {
		t.Fatalf("unknown route must be 404: %d", status)
	}
	status, invalid := postJSON(t, base, "/internal/v1/reminders/evaluate", testServiceToken,
		`{"request_id":"req-9","task_date":"`+taskDate+`","trigger":"DAILY_BATCH"}`)
	if status != nethttp.StatusBadRequest || invalid["code"] != "INVALID_REQUEST" {
		t.Fatalf("missing user_id must be 400: status=%d body=%v", status, invalid)
	}
}

// TestHTTPEntryIntegrationRejectsSecondSnoozeAfterCompletion 覆盖发送后的任务完成复核：
// 任务在发送前被完成时，评估路径取消未发送排程并记录取消原因（HTTP 入口逐字段可见）。
func TestHTTPEntryIntegrationCancelsPendingScheduleWhenTaskCompleted(t *testing.T) {
	restore := nowFunc
	nowFunc = func() time.Time { return fixedEntryNow }
	defer func() { nowFunc = restore }()

	base, stop := startHTTPEntry(t)
	defer stop()

	taskDate := fixedEntryNow.Format("2006-01-02")
	status, created := postJSON(t, base, "/internal/v1/reminders/evaluate", testServiceToken,
		`{"request_id":"req-1","user_id":"user-passive","task_date":"`+taskDate+`","trigger":"DAILY_BATCH"}`)
	if status != nethttp.StatusOK || created["status"] != "CREATED" {
		t.Fatalf("evaluate status=%d body=%v", status, created)
	}

	// 同一任务日期由另一策略版本触发一次已完成任务的评估，排程必须被取消且不再发送。
	status, completed := postJSON(t, base, "/internal/v1/reminders/evaluate", testServiceToken,
		`{"request_id":"req-2","user_id":"user-completed-before-send","task_date":"`+taskDate+`","trigger":"DAILY_BATCH"}`)
	if status != nethttp.StatusOK || completed["status"] != "REJECTED" || completed["reason_code"] != "TASK_COMPLETED" {
		t.Fatalf("completed task must be rejected: status=%d body=%v", status, completed)
	}

	nowFunc = func() time.Time { return time.Date(2026, 9, 21, 23, 0, 0, 0, time.UTC) }
	status, dispatched := postJSON(t, base, "/internal/v1/reminders/dispatch-due", testServiceToken, "")
	if status != nethttp.StatusOK || dispatched["sent"] != float64(0) {
		t.Fatalf("nothing may be sent after cancellation: status=%d body=%v", status, dispatched)
	}
}
