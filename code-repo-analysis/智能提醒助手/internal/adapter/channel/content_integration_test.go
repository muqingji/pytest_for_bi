package channel

import (
	"context"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

// 本文件是 FR-008 的模块集成测试：真实渲染器（TemplateRenderer）+ 真实领域规则 + Mock Push 渠道。
// 它验证「渲染内容 -> 渠道请求 payload」这一条链路，包括剩余任务数、预计用时、落地页和入口列表。
// 发送动作与投递记录属于 FR-005 的 dispatch 链路，快照读取随 FR-004 接入，本文件不覆盖这两段。

func TestContentRenderingIntegrationCarriesRenderedPayloadToChannel(t *testing.T) {
	sender := &MockPushSender{}
	content, err := NewTemplateRenderer().Render(context.Background(), validContentInput())
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	// 按技术方案 4.3.3 的 PushRequest 契约把渲染结果交给渠道；字段映射与 dispatch 的发送链路一致。
	request := reminder.PushRequest{
		IdempotencyKey: "user-passive_2026-09-20_push_decision-1_1",
		UserID:         "user-passive",
		DecisionID:     "decision-1",
		Title:          content.Title,
		Body:           content.Body,
		DeepLink:       content.DeepLink,
		Actions:        content.Actions,
		AttemptNo:      1,
		ExpireAt:       time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC),
	}
	if _, err := sender.Send(context.Background(), request); err != nil {
		t.Fatalf("send: %v", err)
	}
	requests := sender.Requests()
	if len(requests) != 1 {
		t.Fatalf("channel requests = %d, want 1", len(requests))
	}
	sent := requests[0]
	if sent.Title != "今天还有 2 项学习任务" {
		t.Fatalf("title = %q", sent.Title)
	}
	if sent.Body != "预计用时 35 分钟，现在开始刚刚好" {
		t.Fatalf("body = %q", sent.Body)
	}
	if sent.DeepLink != "today_task_page" {
		t.Fatalf("deep link = %q", sent.DeepLink)
	}
	// 内容不含任务正文、成绩、姓名等敏感字段：payload 只由固定模板与白名单变量构成。
	assertIntegrationActions(t, sent.Actions, []reminder.PushActionType{
		reminder.PushActionOpenTask,
		reminder.PushActionSnooze,
	})
}

func TestContentRenderingIntegrationOmitsSnoozeEntryForSnoozeSchedule(t *testing.T) {
	input := validContentInput()
	input.ScheduleType = reminder.ScheduleSnooze
	content, err := NewTemplateRenderer().Render(context.Background(), input)
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	sender := &MockPushSender{}
	if _, err := sender.Send(context.Background(), reminder.PushRequest{
		IdempotencyKey: "user-passive_2026-09-20_push_decision-1_2",
		UserID:         input.UserID,
		DecisionID:     input.DecisionID,
		Title:          content.Title,
		Body:           content.Body,
		DeepLink:       content.DeepLink,
		Actions:        content.Actions,
		AttemptNo:      1,
		ExpireAt:       time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC),
	}); err != nil {
		t.Fatalf("send: %v", err)
	}
	assertIntegrationActions(t, sender.Requests()[0].Actions, []reminder.PushActionType{reminder.PushActionOpenTask})
}

func assertIntegrationActions(t *testing.T, got []reminder.PushAction, want []reminder.PushActionType) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("actions = %+v, want %+v", got, want)
	}
	for index := range want {
		if got[index].Type != want[index] {
			t.Fatalf("action[%d] = %+v, want type %s", index, got[index], want[index])
		}
	}
}
