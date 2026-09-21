package channel

import (
	"context"
	"errors"
	"testing"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

func TestMockPushSenderScriptsResultsAndRecordsRequests(t *testing.T) {
	sender := &MockPushSender{Results: []reminder.PushResult{{Status: string(reminder.DeliveryFailed), ErrorCode: "CHANNEL_SEND_FAILED"}}}
	failed, err := sender.Send(context.Background(), reminder.PushRequest{IdempotencyKey: "key-1", AttemptNo: 1})
	if err != nil || failed.Status != string(reminder.DeliveryFailed) || failed.ErrorCode != "CHANNEL_SEND_FAILED" {
		t.Fatalf("scripted result: %+v err=%v", failed, err)
	}
	// 脚本用尽后按默认状态返回，缺省为明确成功。
	sent, err := sender.Send(context.Background(), reminder.PushRequest{IdempotencyKey: "key-1", AttemptNo: 2})
	if err != nil || sent.Status != string(reminder.DeliverySent) || sent.ProviderCode != "mock" {
		t.Fatalf("default result: %+v err=%v", sent, err)
	}
	requests := sender.Requests()
	if len(requests) != 2 || requests[0].IdempotencyKey != requests[1].IdempotencyKey {
		t.Fatalf("expected both attempts to be recorded: %+v", requests)
	}
	requests[0].IdempotencyKey = "mutated"
	if sender.Requests()[0].IdempotencyKey != "key-1" {
		t.Fatal("Requests must return a copy")
	}
	if sender.DefaultStatus = reminder.DeliveryUnknown; sender.DefaultStatus != reminder.DeliveryUnknown {
		t.Fatal("unexpected default status")
	}
	unknown, err := sender.Send(context.Background(), reminder.PushRequest{})
	if err != nil || unknown.Status != string(reminder.DeliveryUnknown) {
		t.Fatalf("configured default: %+v err=%v", unknown, err)
	}
}

func TestMockPushSenderPropagatesErrors(t *testing.T) {
	sender := &MockPushSender{SendErr: errors.New("channel down"), QueryErr: errors.New("query down")}
	if _, err := sender.Send(context.Background(), reminder.PushRequest{}); err == nil {
		t.Fatal("expected the configured send error")
	}
	if _, err := sender.Query(context.Background(), reminder.DeliveryQuery{IdempotencyKey: "key-1"}); err == nil {
		t.Fatal("expected the configured query error")
	}
}

func TestMockPushSenderQueryStates(t *testing.T) {
	sender := &MockPushSender{}
	// 未配置查询结果时按 UNKNOWN 返回，表示无法确认，禁止盲目重发。
	status, err := sender.Query(context.Background(), reminder.DeliveryQuery{IdempotencyKey: "key-1", AttemptNo: 1})
	if err != nil || status != reminder.DeliveryUnknown {
		t.Fatalf("unexpected default query: %s err=%v", status, err)
	}
	sender.QueryStatus = reminder.DeliverySent
	status, err = sender.Query(context.Background(), reminder.DeliveryQuery{IdempotencyKey: "key-1", AttemptNo: 1})
	if err != nil || status != reminder.DeliverySent {
		t.Fatalf("unexpected query: %s err=%v", status, err)
	}
	queries := sender.Queries()
	if len(queries) != 2 || queries[0].IdempotencyKey != "key-1" {
		t.Fatalf("expected queries to be recorded: %+v", queries)
	}
	queries[0].IdempotencyKey = "mutated"
	if sender.Queries()[0].IdempotencyKey != "key-1" {
		t.Fatal("Queries must return a copy")
	}
}

func TestPlaceholderRendererOnlyExposesDeepLink(t *testing.T) {
	content, err := PlaceholderRenderer{}.Render(context.Background(), reminder.RenderInput{DeepLink: "today_task_page", RemainingCount: 2})
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	// 占位实现不产生任何文案：文案规则由 FR-008 实现后替换。
	if content.DeepLink != "today_task_page" || content.Title != "" || content.Body != "" {
		t.Fatalf("unexpected placeholder content: %+v", content)
	}
}
