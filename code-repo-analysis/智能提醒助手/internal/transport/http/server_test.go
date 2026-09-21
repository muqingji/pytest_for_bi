package http

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net"
	nethttp "net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/application/snooze"
	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/transport/http/dto"
)

// testToken 是单测使用的静态令牌；与生产缺省值区分，避免测试无意中依赖 defaultToken。
const testToken = "unit-test-token"

// evaluateStub/dispatchStub/snoozeStub 是三个用例能力的桩：只记录入参并返回预设结果，
// 让入口层测试只验证「报文 ↔ 用例入参/结果」的映射，不掺入业务规则。
type evaluateStub struct {
	result evaluate.Result
	err    error
	got    evaluate.Request
	calls  int
}

func (s *evaluateStub) Evaluate(_ context.Context, request evaluate.Request) (evaluate.Result, error) {
	s.calls++
	s.got = request
	return s.result, s.err
}

type dispatchStub struct {
	result dispatch.Result
	err    error
	got    dispatch.Request
	calls  int
}

func (s *dispatchStub) DispatchDue(_ context.Context, request dispatch.Request) (dispatch.Result, error) {
	s.calls++
	s.got = request
	return s.result, s.err
}

type snoozeStub struct {
	result snooze.Result
	err    error
	got    snooze.Request
	calls  int
}

func (s *snoozeStub) Snooze(_ context.Context, request snooze.Request) (snooze.Result, error) {
	s.calls++
	s.got = request
	return s.result, s.err
}

func newTestServer(evaluate *evaluateStub, dispatch *dispatchStub, snooze *snoozeStub) Server {
	return Server{Evaluate: evaluate, Dispatch: dispatch, Snooze: snooze, Config: Config{Token: testToken}}
}

// serveRequest 发一次请求并返回记录器；authorized 为真时带上合法 Bearer 令牌。
func serveRequest(t *testing.T, handler nethttp.Handler, method, path, body string, header map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Authorization", "Bearer "+testToken)
	for name, value := range header {
		request.Header.Set(name, value)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func decodeResponse(t *testing.T, recorder *httptest.ResponseRecorder, target any) {
	t.Helper()
	if contentType := recorder.Header().Get("Content-Type"); contentType != "application/json; charset=utf-8" {
		t.Fatalf("unexpected content type %q", contentType)
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), target); err != nil {
		t.Fatalf("decode response %s: %v", recorder.Body.String(), err)
	}
}

// TestHandlerRoutesThreeEndpoints 覆盖三个接口的正常链路：请求字段原样进入用例入参，
// 用例结果按 DTO 映射返回，且调用方传入的 X-Request-ID 被回写。
func TestHandlerRoutesThreeEndpoints(t *testing.T) {
	evaluateUseCase := &evaluateStub{result: evaluate.Result{Decision: reminder.Decision{
		ID: "decision-1", ShouldRemind: true, ReasonCode: reminder.ReasonDefaultWindow,
		UserSegment: reminder.SegmentPassive, StrategyVersion: "v1", Channel: reminder.ChannelPush,
	}}}
	dispatchUseCase := &dispatchStub{result: dispatch.Result{Scanned: 3, Claimed: 2, Sent: 1, Finished: true}}
	snoozeUseCase := &snoozeStub{result: snooze.Result{
		ScheduleID: "schedule-2", Status: reminder.SnoozeScheduled, ReasonCode: reminder.ReasonEligible,
		Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleSnooze,
	}}
	handler := newTestServer(evaluateUseCase, dispatchUseCase, snoozeUseCase).Handler()

	evaluateRecorder := serveRequest(t, handler, nethttp.MethodPost, "/internal/v1/reminders/evaluate",
		`{"request_id":"req-1","user_id":"user-passive","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`,
		map[string]string{headerRequestID: "caller-rid"})
	if evaluateRecorder.Code != nethttp.StatusOK {
		t.Fatalf("evaluate status=%d body=%s", evaluateRecorder.Code, evaluateRecorder.Body.String())
	}
	if got := evaluateRecorder.Header().Get(headerRequestID); got != "caller-rid" {
		t.Fatalf("request id must be echoed: %q", got)
	}
	if evaluateUseCase.calls != 1 || evaluateUseCase.got.UserID != "user-passive" ||
		evaluateUseCase.got.TaskDate != "2026-09-20" || evaluateUseCase.got.Trigger != reminder.TriggerDaily ||
		evaluateUseCase.got.LastOpenAt != nil {
		t.Fatalf("unexpected evaluate request: %+v", evaluateUseCase.got)
	}
	var evaluateResponse dto.EvaluateReminderResponse
	decodeResponse(t, evaluateRecorder, &evaluateResponse)
	if evaluateResponse.Status != dto.StatusCreated || evaluateResponse.DecisionID != "decision-1" ||
		evaluateResponse.UserSegment != string(reminder.SegmentPassive) || evaluateResponse.StrategyVersion != "v1" {
		t.Fatalf("unexpected evaluate response: %+v", evaluateResponse)
	}

	dispatchRecorder := serveRequest(t, handler, nethttp.MethodPost, "/internal/v1/reminders/dispatch-due", "", nil)
	if dispatchRecorder.Code != nethttp.StatusOK {
		t.Fatalf("dispatch status=%d body=%s", dispatchRecorder.Code, dispatchRecorder.Body.String())
	}
	if dispatchUseCase.calls != 1 || dispatchUseCase.got.BatchSize != 0 {
		t.Fatalf("empty body must fall back to the use-case default: %+v", dispatchUseCase.got)
	}
	var dispatchResponse dto.DispatchDueResponse
	decodeResponse(t, dispatchRecorder, &dispatchResponse)
	if dispatchResponse.Scanned != 3 || dispatchResponse.Claimed != 2 || dispatchResponse.Sent != 1 || !dispatchResponse.Finished {
		t.Fatalf("unexpected dispatch response: %+v", dispatchResponse)
	}

	snoozeRecorder := serveRequest(t, handler, nethttp.MethodPost, "/internal/v1/reminders/decision-1/snooze",
		`{"request_id":"req-2","user_id":"user-passive"}`, nil)
	if snoozeRecorder.Code != nethttp.StatusOK {
		t.Fatalf("snooze status=%d body=%s", snoozeRecorder.Code, snoozeRecorder.Body.String())
	}
	if snoozeUseCase.calls != 1 || snoozeUseCase.got.DecisionID != "decision-1" ||
		snoozeUseCase.got.RequestID != "req-2" || snoozeUseCase.got.UserID != "user-passive" {
		t.Fatalf("unexpected snooze request: %+v", snoozeUseCase.got)
	}
	var snoozeResponse dto.SnoozeReminderResponse
	decodeResponse(t, snoozeRecorder, &snoozeResponse)
	if snoozeResponse.Status != string(reminder.SnoozeScheduled) || snoozeResponse.ScheduleID != "schedule-2" ||
		snoozeResponse.ScheduleType != string(reminder.ScheduleSnooze) {
		t.Fatalf("unexpected snooze response: %+v", snoozeResponse)
	}
}

// TestHandlerRejectsCredentialVariants 覆盖鉴权失败的三种写法：缺失、方案不对、令牌不对；
// 三种都必须在进入业务逻辑之前返回 401，且不得调用用例。
func TestHandlerRejectsCredentialVariants(t *testing.T) {
	cases := []struct {
		name   string
		header string
	}{
		{name: "missing", header: ""},
		{name: "wrong scheme", header: "Basic " + testToken},
		{name: "wrong token", header: "Bearer other-token"},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			evaluateUseCase := &evaluateStub{}
			handler := newTestServer(evaluateUseCase, &dispatchStub{}, &snoozeStub{}).Handler()
			request := httptest.NewRequest(nethttp.MethodPost, "/internal/v1/reminders/evaluate",
				strings.NewReader(`{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`))
			if testCase.header != "" {
				request.Header.Set("Authorization", testCase.header)
			}
			recorder := httptest.NewRecorder()
			handler.ServeHTTP(recorder, request)

			if recorder.Code != nethttp.StatusUnauthorized {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			var envelope dto.ErrorResponse
			decodeResponse(t, recorder, &envelope)
			if envelope.Code != codeInvalidRequest || envelope.Retryable {
				t.Fatalf("unexpected credential error envelope: %+v", envelope)
			}
			if evaluateUseCase.calls != 0 {
				t.Fatalf("credential failure must not reach the use case: %d", evaluateUseCase.calls)
			}
		})
	}
}

// TestHandlerAcceptsDefaultTokenWhenUnconfigured 覆盖 Config.Token 为空时回落到 defaultToken。
func TestHandlerAcceptsDefaultTokenWhenUnconfigured(t *testing.T) {
	server := Server{Evaluate: &evaluateStub{}, Dispatch: &dispatchStub{}, Snooze: &snoozeStub{}}
	request := httptest.NewRequest(nethttp.MethodPost, "/internal/v1/reminders/dispatch-due", nil)
	request.Header.Set("Authorization", "Bearer "+defaultToken)
	recorder := httptest.NewRecorder()
	server.Handler().ServeHTTP(recorder, request)

	if recorder.Code != nethttp.StatusOK {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

// TestHandlerReturnsJSONNotFoundForUnknownRouteAndMethod 覆盖未匹配路径与方法不匹配：
// 两者都不得进入业务逻辑，且必须是 JSON 错误信封而不是空响应。
func TestHandlerReturnsJSONNotFoundForUnknownRouteAndMethod(t *testing.T) {
	cases := []struct {
		name   string
		method string
		path   string
	}{
		{name: "unknown route", method: nethttp.MethodPost, path: "/internal/v1/reminders/nope"},
		{name: "root route", method: nethttp.MethodGet, path: "/"},
		{name: "wrong method", method: nethttp.MethodGet, path: "/internal/v1/reminders/evaluate"},
		{name: "missing decision id", method: nethttp.MethodPost, path: "/internal/v1/reminders//snooze"},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			evaluateUseCase := &evaluateStub{}
			dispatchUseCase := &dispatchStub{}
			snoozeUseCase := &snoozeStub{}
			handler := newTestServer(evaluateUseCase, dispatchUseCase, snoozeUseCase).Handler()
			recorder := serveRequest(t, handler, testCase.method, testCase.path, "", nil)

			if recorder.Code != nethttp.StatusNotFound {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			var envelope dto.ErrorResponse
			decodeResponse(t, recorder, &envelope)
			if envelope.Code != codeInvalidRequest || envelope.Message != messageNotFound || envelope.RequestID == "" {
				t.Fatalf("unexpected not-found envelope: %+v", envelope)
			}
			if evaluateUseCase.calls+dispatchUseCase.calls+snoozeUseCase.calls != 0 {
				t.Fatal("unmatched route must not reach any use case")
			}
		})
	}
}

// TestHandlerRejectsMalformedBodies 覆盖请求体不是合法 JSON 的两种接口：
// evaluate 的请求体必填，dispatch 的请求体可选但非空时必须能解析。
func TestHandlerRejectsMalformedBodies(t *testing.T) {
	handler := newTestServer(&evaluateStub{}, &dispatchStub{}, &snoozeStub{}).Handler()
	for _, path := range []string{"/internal/v1/reminders/evaluate", "/internal/v1/reminders/dispatch-due"} {
		recorder := serveRequest(t, handler, nethttp.MethodPost, path, "{", nil)
		if recorder.Code != nethttp.StatusBadRequest {
			t.Fatalf("%s status=%d body=%s", path, recorder.Code, recorder.Body.String())
		}
		var envelope dto.ErrorResponse
		decodeResponse(t, recorder, &envelope)
		if envelope.Code != codeInvalidRequest || envelope.Message != messageInvalidRequest {
			t.Fatalf("unexpected validation envelope: %+v", envelope)
		}
	}
}

// TestHandlerRejectsInvalidEvaluateFields 覆盖 4.3.2.1 的字段校验表：任何不满足契约的取值都返回 400，
// 不降级猜测、不进入用例。
func TestHandlerRejectsInvalidEvaluateFields(t *testing.T) {
	longIdentifier := strings.Repeat("a", maxIdentifierLength+1)
	cases := []struct {
		name string
		body string
	}{
		{name: "missing request id", body: `{"user_id":"u1","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`},
		{name: "over-long request id", body: `{"request_id":"` + longIdentifier + `","user_id":"u1","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`},
		{name: "missing user id", body: `{"request_id":"req-1","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`},
		{name: "over-long user id", body: `{"request_id":"req-1","user_id":"` + longIdentifier + `","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`},
		{name: "bad task date", body: `{"request_id":"req-1","user_id":"u1","task_date":"2026/09/20","trigger":"DAILY_BATCH"}`},
		{name: "unknown trigger", body: `{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"MANUAL"}`},
		{name: "last open at on daily batch", body: `{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"DAILY_BATCH","last_open_at":"2026-09-19T10:00:00Z"}`},
		{name: "missing last open at for app opened", body: `{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"APP_OPENED"}`},
		{name: "bad last open at", body: `{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"APP_OPENED","last_open_at":"2026-09-19 10:00:00"}`},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			evaluateUseCase := &evaluateStub{}
			handler := newTestServer(evaluateUseCase, &dispatchStub{}, &snoozeStub{}).Handler()
			recorder := serveRequest(t, handler, nethttp.MethodPost, "/internal/v1/reminders/evaluate", testCase.body, nil)
			if recorder.Code != nethttp.StatusBadRequest {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			if evaluateUseCase.calls != 0 {
				t.Fatal("invalid fields must not reach the use case")
			}
		})
	}
}

// TestHandlerMapsAppOpenedLastOpenAt 覆盖 APP_OPENED 的 last_open_at 三种合法写法：
// 有历史打开记录时解析为时间点，空串表示没有历史记录（nil），并原样传递 trigger。
func TestHandlerMapsAppOpenedLastOpenAt(t *testing.T) {
	cases := []struct {
		name     string
		body     string
		wantOpen *time.Time
	}{
		{
			name:     "with history",
			body:     `{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"APP_OPENED","last_open_at":"2026-09-19T10:00:00Z"}`,
			wantOpen: func() *time.Time { value := time.Date(2026, 9, 19, 10, 0, 0, 0, time.UTC); return &value }(),
		},
		{name: "without history", body: `{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"APP_OPENED","last_open_at":""}`, wantOpen: nil},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			evaluateUseCase := &evaluateStub{}
			handler := newTestServer(evaluateUseCase, &dispatchStub{}, &snoozeStub{}).Handler()
			recorder := serveRequest(t, handler, nethttp.MethodPost, "/internal/v1/reminders/evaluate", testCase.body, nil)
			if recorder.Code != nethttp.StatusOK {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			if evaluateUseCase.got.Trigger != reminder.TriggerAppOpen {
				t.Fatalf("trigger must be APP_OPENED: %+v", evaluateUseCase.got)
			}
			switch {
			case testCase.wantOpen == nil && evaluateUseCase.got.LastOpenAt != nil:
				t.Fatalf("expected nil last_open_at: %+v", evaluateUseCase.got.LastOpenAt)
			case testCase.wantOpen != nil && (evaluateUseCase.got.LastOpenAt == nil || !evaluateUseCase.got.LastOpenAt.Equal(*testCase.wantOpen)):
				t.Fatalf("unexpected last_open_at: %+v", evaluateUseCase.got.LastOpenAt)
			}
		})
	}
}

// TestHandlerValidatesDispatchBatchSize 覆盖 4.3.2.2 的批次校验：缺省取用例默认值，
// 越界与类型不符返回 400，游标不支持。
func TestHandlerValidatesDispatchBatchSize(t *testing.T) {
	cases := []struct {
		name      string
		body      string
		wantCode  int
		wantBatch int
	}{
		{name: "omitted", body: `{}`, wantCode: nethttp.StatusOK, wantBatch: 0},
		{name: "lower bound", body: `{"batch_size":1}`, wantCode: nethttp.StatusOK, wantBatch: 1},
		{name: "upper bound", body: `{"batch_size":50}`, wantCode: nethttp.StatusOK, wantBatch: maxDispatchBatchSize},
		{name: "zero", body: `{"batch_size":0}`, wantCode: nethttp.StatusBadRequest},
		{name: "over upper bound", body: `{"batch_size":51}`, wantCode: nethttp.StatusBadRequest},
		{name: "wrong type", body: `{"batch_size":"50"}`, wantCode: nethttp.StatusBadRequest},
		{name: "cursor", body: `{"cursor":"page-2"}`, wantCode: nethttp.StatusBadRequest},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			dispatchUseCase := &dispatchStub{}
			handler := newTestServer(&evaluateStub{}, dispatchUseCase, &snoozeStub{}).Handler()
			recorder := serveRequest(t, handler, nethttp.MethodPost, "/internal/v1/reminders/dispatch-due", testCase.body, nil)
			if recorder.Code != testCase.wantCode {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			if testCase.wantCode == nethttp.StatusBadRequest {
				if dispatchUseCase.calls != 0 {
					t.Fatal("invalid batch parameters must not reach the use case")
				}
				return
			}
			if dispatchUseCase.got.BatchSize != testCase.wantBatch {
				t.Fatalf("batch size=%d want %d", dispatchUseCase.got.BatchSize, testCase.wantBatch)
			}
		})
	}
}

// TestHandlerValidatesSnoozeRequest 覆盖 4.3.2.3 的路径参数与请求体校验，
// 以及「第二次入口属非法调用」的 400 映射（snooze.ErrInvalidRequest 不伪装成业务拒绝）。
func TestHandlerValidatesSnoozeRequest(t *testing.T) {
	longIdentifier := strings.Repeat("a", maxIdentifierLength+1)
	cases := []struct {
		name       string
		path       string
		body       string
		stubError  error
		wantStatus int
		wantCalls  int
	}{
		{name: "missing request id", path: "/internal/v1/reminders/decision-1/snooze", body: `{"user_id":"u1"}`, wantStatus: nethttp.StatusBadRequest},
		{name: "missing user id", path: "/internal/v1/reminders/decision-1/snooze", body: `{"request_id":"req-1"}`, wantStatus: nethttp.StatusBadRequest},
		{name: "over-long user id", path: "/internal/v1/reminders/decision-1/snooze", body: `{"request_id":"req-1","user_id":"` + longIdentifier + `"}`, wantStatus: nethttp.StatusBadRequest},
		{
			name: "second entry", path: "/internal/v1/reminders/decision-1/snooze", body: `{"request_id":"req-1","user_id":"u1"}`,
			stubError: snooze.ErrInvalidRequest, wantStatus: nethttp.StatusBadRequest, wantCalls: 1,
		},
		{name: "valid", path: "/internal/v1/reminders/decision-1/snooze", body: `{"request_id":"req-1","user_id":"u1"}`, wantStatus: nethttp.StatusOK, wantCalls: 1},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			snoozeUseCase := &snoozeStub{err: testCase.stubError}
			handler := newTestServer(&evaluateStub{}, &dispatchStub{}, snoozeUseCase).Handler()
			recorder := serveRequest(t, handler, nethttp.MethodPost, testCase.path, testCase.body, nil)
			if recorder.Code != testCase.wantStatus {
				t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
			}
			if snoozeUseCase.calls != testCase.wantCalls {
				t.Fatalf("calls=%d want %d", snoozeUseCase.calls, testCase.wantCalls)
			}
		})
	}
}

// TestHandlerMapsDependencyFailures 覆盖依赖错误映射：超时按 504 + DEPENDENCY_TIMEOUT（可重试），
// 其余按 500 + DEPENDENCY_UNAVAILABLE，三个接口口径一致。
func TestHandlerMapsDependencyFailures(t *testing.T) {
	paths := []string{
		"/internal/v1/reminders/evaluate",
		"/internal/v1/reminders/dispatch-due",
		"/internal/v1/reminders/decision-1/snooze",
	}
	cases := []struct {
		name         string
		err          error
		wantStatus   int
		wantCode     string
		wantRetry    bool
	}{
		{name: "deadline exceeded", err: context.DeadlineExceeded, wantStatus: nethttp.StatusGatewayTimeout, wantCode: codeDependencyTimeout, wantRetry: true},
		{name: "canceled", err: context.Canceled, wantStatus: nethttp.StatusGatewayTimeout, wantCode: codeDependencyTimeout, wantRetry: true},
		{name: "unavailable", err: errors.New("task service down"), wantStatus: nethttp.StatusInternalServerError, wantCode: codeDependencyUnavailable, wantRetry: true},
	}
	for _, path := range paths {
		for _, testCase := range cases {
			t.Run(path+"/"+testCase.name, func(t *testing.T) {
				handler := newTestServer(
					&evaluateStub{err: testCase.err},
					&dispatchStub{err: testCase.err},
					&snoozeStub{err: testCase.err},
				).Handler()
				recorder := serveRequest(t, handler, nethttp.MethodPost, path,
					`{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`, nil)
				if recorder.Code != testCase.wantStatus {
					t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
				}
				var envelope dto.ErrorResponse
				decodeResponse(t, recorder, &envelope)
				if envelope.Code != testCase.wantCode || envelope.Retryable != testCase.wantRetry || envelope.RequestID == "" {
					t.Fatalf("unexpected dependency envelope: %+v", envelope)
				}
			})
		}
	}
}

// TestRequestIDUsesCallerSeamThenEntropy 覆盖链路 ID 的三个来源：调用方传入、缺省生成器、随机源退化。
func TestRequestIDUsesCallerSeamThenEntropy(t *testing.T) {
	server := Server{Evaluate: &evaluateStub{}, Dispatch: &dispatchStub{}, Snooze: &snoozeStub{},
		Config: Config{Token: testToken}, NewRequestID: func() string { return "req-from-seam" }}
	recorder := serveRequest(t, server.Handler(), nethttp.MethodPost, "/internal/v1/reminders/dispatch-due", "", nil)
	if got := recorder.Header().Get(headerRequestID); got != "req-from-seam" {
		t.Fatalf("seam must supply the request id: %q", got)
	}

	original := randomSource
	defer func() { randomSource = original }()
	randomSource = func([]byte) (int, error) { return 0, errors.New("no entropy") }
	if fallback := randomRequestID(); !strings.HasPrefix(fallback, "req-") {
		t.Fatalf("fallback request id must keep the req- prefix: %q", fallback)
	}
	randomSource = original
	if generated := randomRequestID(); !strings.HasPrefix(generated, "req-") || len(generated) != len("req-")+32 {
		t.Fatalf("random request id must be 128-bit hex: %q", generated)
	}
}

// TestTimeoutAndShutdownDefaults 覆盖超时与退出等待时长的缺省值与覆写值。
func TestTimeoutAndShutdownDefaults(t *testing.T) {
	server := Server{}
	if got := server.timeout(0, DefaultTimeoutEvaluate); got != DefaultTimeoutEvaluate {
		t.Fatalf("zero config must fall back to the interface budget: %v", got)
	}
	if got := server.timeout(time.Second, DefaultTimeoutEvaluate); got != time.Second {
		t.Fatalf("configured budget must win: %v", got)
	}
	if got := server.shutdownTimeout(); got != defaultShutdownTimeout {
		t.Fatalf("default shutdown timeout: %v", got)
	}
	server.ShutdownTimeout = time.Millisecond
	if got := server.shutdownTimeout(); got != time.Millisecond {
		t.Fatalf("overridden shutdown timeout: %v", got)
	}
}

// TestConfiguredBudgetsAreApplied 覆盖 Config 里显式超时的装配路径（三个接口都走同一段取值逻辑）。
func TestConfiguredBudgetsAreApplied(t *testing.T) {
	server := newTestServer(&evaluateStub{}, &dispatchStub{}, &snoozeStub{})
	server.Config.TimeoutEvaluate = time.Second
	server.Config.TimeoutDispatch = 2 * time.Second
	server.Config.TimeoutSnooze = 3 * time.Second
	handler := server.Handler()
	for _, path := range []string{
		"/internal/v1/reminders/evaluate",
		"/internal/v1/reminders/dispatch-due",
		"/internal/v1/reminders/decision-1/snooze",
	} {
		recorder := serveRequest(t, handler, nethttp.MethodPost, path,
			`{"request_id":"req-1","user_id":"u1","task_date":"2026-09-20","trigger":"DAILY_BATCH"}`, nil)
		if recorder.Code != nethttp.StatusOK {
			t.Fatalf("%s status=%d body=%s", path, recorder.Code, recorder.Body.String())
		}
	}
}

// TestHandlersWithoutTransportContext 覆盖 handler 被直接调用（没有经过 transport 中间件）时的退化路径：
// 链路 ID 缺省为空串，仍要返回结构化错误而不是 panic。
func TestHandlersWithoutTransportContext(t *testing.T) {
	server := newTestServer(&evaluateStub{}, &dispatchStub{}, &snoozeStub{})
	recorder := httptest.NewRecorder()
	server.handleEvaluate(recorder, httptest.NewRequest(nethttp.MethodPost, "/internal/v1/reminders/evaluate", strings.NewReader("{")))
	if recorder.Code != nethttp.StatusBadRequest {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var envelope dto.ErrorResponse
	decodeResponse(t, recorder, &envelope)
	if envelope.RequestID != "" {
		t.Fatalf("missing transport scope must yield an empty request id: %+v", envelope)
	}
}

// TestDecodeBodyAllowsEmptyOnlyWhenPermitted 覆盖 requestBody 可选接口对空请求体的处理。
func TestDecodeBodyAllowsEmptyOnlyWhenPermitted(t *testing.T) {
	var target struct {
		BatchSize *int `json:"batch_size"`
	}
	if err := decodeBody(httptest.NewRequest(nethttp.MethodPost, "/", nil), &target, true); err != nil {
		t.Fatalf("empty optional body must be accepted: %v", err)
	}
	if err := decodeBody(httptest.NewRequest(nethttp.MethodPost, "/", nil), &target, false); err == nil {
		t.Fatal("empty required body must be rejected")
	}
}

// TestValidateIdentifierBounds 直接覆盖标识字段的 1–64 字符边界。
func TestValidateIdentifierBounds(t *testing.T) {
	if err := validateIdentifier("user_id", ""); err == nil {
		t.Fatal("empty identifier must be rejected")
	}
	if err := validateIdentifier("user_id", strings.Repeat("a", maxIdentifierLength)); err != nil {
		t.Fatalf("64-character identifier must be accepted: %v", err)
	}
	if err := validateIdentifier("user_id", strings.Repeat("a", maxIdentifierLength+1)); err == nil {
		t.Fatal("65-character identifier must be rejected")
	}
}

// TestServeStartsAndStopsOnContextCancel 覆盖 Serve 的成功启动与 ctx 取消后的优雅退出。
func TestServeStartsAndStopsOnContextCancel(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	server := newTestServer(&evaluateStub{}, &dispatchStub{}, &snoozeStub{})
	done := make(chan error, 1)
	go func() { done <- server.Serve(ctx, "127.0.0.1:0") }()

	time.Sleep(50 * time.Millisecond)
	cancel()
	select {
	case err := <-done:
		if err != nil {
			t.Fatalf("graceful shutdown must not report an error: %v", err)
		}
	case <-time.After(5 * time.Second):
		t.Fatal("Serve did not return after context cancellation")
	}
}

// TestServeRejectsUnusableAddress 覆盖监听失败时的快速失败路径。
func TestServeRejectsUnusableAddress(t *testing.T) {
	server := newTestServer(&evaluateStub{}, &dispatchStub{}, &snoozeStub{})
	if err := server.Serve(context.Background(), "127.0.0.1:not-a-port"); err == nil {
		t.Fatal("expected listen error")
	}
}

// TestServeListenerReportsServeError 覆盖监听器被外部关闭时的错误返回：
// 不是 ErrServerClosed 时必须把原始错误暴露给调用方，且关闭协程不得悬挂。
func TestServeListenerReportsServeError(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	server := newTestServer(&evaluateStub{}, &dispatchStub{}, &snoozeStub{})
	server.ShutdownTimeout = time.Millisecond
	done := make(chan error, 1)
	go func() { done <- server.ServeListener(context.Background(), listener) }()

	time.Sleep(50 * time.Millisecond)
	if err := listener.Close(); err != nil {
		t.Fatalf("close listener: %v", err)
	}
	select {
	case err := <-done:
		if err == nil {
			t.Fatal("expected the serve error to surface")
		}
	case <-time.After(5 * time.Second):
		t.Fatal("ServeListener did not return after the listener closed")
	}
}

// TestServeListenerServesRequestsOverTheNetwork 覆盖真实网络路径上的请求处理。
func TestServeListenerServesRequestsOverTheNetwork(t *testing.T) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	server := newTestServer(&evaluateStub{}, &dispatchStub{}, &snoozeStub{})
	done := make(chan error, 1)
	go func() { done <- server.ServeListener(ctx, listener) }()

	request, err := nethttp.NewRequest(nethttp.MethodPost, "http://"+listener.Addr().String()+"/internal/v1/reminders/dispatch-due", bytes.NewReader(nil))
	if err != nil {
		t.Fatalf("build request: %v", err)
	}
	request.Header.Set("Authorization", "Bearer "+testToken)
	response, err := nethttp.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("do request: %v", err)
	}
	defer func() { _ = response.Body.Close() }()
	if response.StatusCode != nethttp.StatusOK {
		t.Fatalf("status=%d", response.StatusCode)
	}
	cancel()
	if err := <-done; err != nil {
		t.Fatalf("graceful shutdown must not report an error: %v", err)
	}
}
