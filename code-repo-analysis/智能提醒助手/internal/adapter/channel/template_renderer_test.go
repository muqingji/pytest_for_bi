package channel

import (
	"context"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

func validContentInput() reminder.RenderInput {
	estimatedMinutes := 35
	return reminder.RenderInput{
		UserID:           "user-passive",
		DecisionID:       "decision-1",
		ScheduleID:       "schedule-1",
		ScheduleType:     reminder.ScheduleInitial,
		RemainingCount:   2,
		EstimatedMinutes: &estimatedMinutes,
		DeepLink:         "today_task_page",
		SnapshotReadAt:   time.Date(2026, 9, 20, 11, 30, 0, 0, time.UTC),
	}
}

func TestNewTemplateRendererUsesPRDTemplateAndDefaultLimits(t *testing.T) {
	renderer := NewTemplateRenderer()
	if renderer.Template != reminder.DefaultPushTemplate() {
		t.Fatalf("template = %+v", renderer.Template)
	}
	if renderer.Limits != reminder.DefaultContentLimits() {
		t.Fatalf("limits = %+v", renderer.Limits)
	}
	content, err := renderer.Render(context.Background(), validContentInput())
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	if content.Title != "今天还有 2 项学习任务" || content.Body != "预计用时 35 分钟，现在开始刚刚好" {
		t.Fatalf("content = %+v", content)
	}
	if content.DeepLink != "today_task_page" || len(content.Actions) != 2 {
		t.Fatalf("content = %+v", content)
	}
}

func TestTemplateRendererHonoursConfiguredBodyLimit(t *testing.T) {
	renderer := NewTemplateRenderer()
	renderer.Limits.BodyMaxLen = 6
	content, err := renderer.Render(context.Background(), validContentInput())
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	// 正文超长只截尾部并补省略号，标题里的剩余任务数保持不变。
	if content.Body != "预计用时 …" {
		t.Fatalf("body = %q", content.Body)
	}
	if content.Title != "今天还有 2 项学习任务" {
		t.Fatalf("title = %q", content.Title)
	}
}

func TestTemplateRendererReturnsContentErrorForStaleSnapshot(t *testing.T) {
	input := validContentInput()
	input.SnapshotReadFailed = true
	_, err := NewTemplateRenderer().Render(context.Background(), input)
	contentErr, ok := err.(reminder.ContentError)
	if !ok {
		t.Fatalf("error = %v (%T)", err, err)
	}
	if contentErr.Reason != reminder.ContentReasonSnapshotUnavailable {
		t.Fatalf("reason = %q", contentErr.Reason)
	}
}
