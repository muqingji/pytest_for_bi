package reminder

import (
	"strings"
	"testing"
	"time"
)

func intPtr(value int) *int { return &value }

func validRenderInput() RenderInput {
	return RenderInput{
		UserID:           "user-passive",
		DecisionID:       "decision-1",
		ScheduleID:       "schedule-1",
		ScheduleType:     ScheduleInitial,
		RemainingCount:   2,
		EstimatedMinutes: intPtr(35),
		DeepLink:         "today_task_page",
		SnapshotReadAt:   time.Date(2026, 9, 20, 11, 30, 0, 0, time.UTC),
	}
}

func TestDefaultPushTemplateMatchesPRD(t *testing.T) {
	template := DefaultPushTemplate()
	if template.Title != "今天还有 {remaining_count} 项学习任务" {
		t.Fatalf("title template = %q", template.Title)
	}
	if template.Body != "预计用时 {estimated_minutes} 分钟，现在开始刚刚好" {
		t.Fatalf("body template = %q", template.Body)
	}
	limits := DefaultContentLimits()
	if limits.TitleMaxLen != 30 || limits.BodyMaxLen != 60 {
		t.Fatalf("default limits = %+v", limits)
	}
}

func TestRenderContentUsesLatestTaskSnapshotForInitialSchedule(t *testing.T) {
	content, err := RenderContent(validRenderInput(), DefaultPushTemplate(), DefaultContentLimits())
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	if content.Title != "今天还有 2 项学习任务" {
		t.Fatalf("title = %q", content.Title)
	}
	if content.Body != "预计用时 35 分钟，现在开始刚刚好" {
		t.Fatalf("body = %q", content.Body)
	}
	if content.DeepLink != "today_task_page" {
		t.Fatalf("deep link = %q", content.DeepLink)
	}
	// 系统主动 Push 提供「去完成任务」与「稍后提醒」两个入口。
	want := []PushAction{
		{Type: PushActionOpenTask, Label: ContentOpenTaskLabel, Target: "today_task_page"},
		{Type: PushActionSnooze, Label: ContentSnoozeLabel, Target: ContentSnoozeTarget},
	}
	assertActions(t, content.Actions, want)
}

func TestRenderContentOmitsSnoozeEntryForSnoozeSchedule(t *testing.T) {
	input := validRenderInput()
	input.ScheduleType = ScheduleSnooze
	content, err := RenderContent(input, DefaultPushTemplate(), DefaultContentLimits())
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	// 延后提醒只提供去完成任务的入口，不再提供再次延后入口（PRD 7.7）。
	assertActions(t, content.Actions, []PushAction{
		{Type: PushActionOpenTask, Label: ContentOpenTaskLabel, Target: "today_task_page"},
	})
}

func TestRenderContentAcceptsTaskBoundaryValues(t *testing.T) {
	input := validRenderInput()
	input.RemainingCount = 1
	input.EstimatedMinutes = intPtr(0)
	content, err := RenderContent(input, DefaultPushTemplate(), DefaultContentLimits())
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	// 剩余 1 项与 0 分钟是合法边界值，不能当成变量缺失。
	if content.Title != "今天还有 1 项学习任务" {
		t.Fatalf("title = %q", content.Title)
	}
	if content.Body != "预计用时 0 分钟，现在开始刚刚好" {
		t.Fatalf("body = %q", content.Body)
	}
}

func TestRenderContentTruncatesBodyAndKeepsTaskCountField(t *testing.T) {
	limits := DefaultContentLimits()
	limits.BodyMaxLen = 5
	content, err := RenderContent(validRenderInput(), DefaultPushTemplate(), limits)
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	if content.Body != "预计用时…" {
		t.Fatalf("body = %q", content.Body)
	}
	// 标题承载剩余任务数，不参与截断。
	if content.Title != "今天还有 2 项学习任务" {
		t.Fatalf("title = %q", content.Title)
	}
}

func TestRenderContentTruncatesBodyToEllipsisWhenLimitIsOne(t *testing.T) {
	limits := DefaultContentLimits()
	limits.BodyMaxLen = 1
	content, err := RenderContent(validRenderInput(), DefaultPushTemplate(), limits)
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	if content.Body != "…" {
		t.Fatalf("body = %q", content.Body)
	}
}

func TestRenderContentKeepsUnclosedPlaceholderAsLiteralText(t *testing.T) {
	template := ContentTemplate{Title: "今天还有 2 项学习任务", Body: "预计用时 {estimated_minutes 分钟"}
	// 模板缺少右花括号时按普通文本渲染，不把用户可见文案截断。
	content, err := RenderContent(validRenderInput(), template, DefaultContentLimits())
	if err != nil {
		t.Fatalf("render: %v", err)
	}
	if content.Body != "预计用时 {estimated_minutes 分钟" {
		t.Fatalf("body = %q", content.Body)
	}
}

func TestRenderContentRejectsUnregisteredTemplateVariable(t *testing.T) {
	template := ContentTemplate{Title: "今天还有 {remaining_count} 项学习任务", Body: "{task_title} 现在开始刚刚好"}
	_, err := RenderContent(validRenderInput(), template, DefaultContentLimits())
	assertContentError(t, err, ContentReasonSensitiveField)
}

func TestRenderContentRejectsInvalidInputs(t *testing.T) {
	cases := []struct {
		name       string
		mutate     func(*RenderInput)
		template   ContentTemplate
		limits     ContentLimits
		wantReason string
	}{
		{
			name:       "发送前读取任务状态失败",
			mutate:     func(input *RenderInput) { input.SnapshotReadFailed = true },
			template:   DefaultPushTemplate(),
			limits:     DefaultContentLimits(),
			wantReason: ContentReasonSnapshotUnavailable,
		},
		{
			name:       "预计用时缺失",
			mutate:     func(input *RenderInput) { input.EstimatedMinutes = nil },
			template:   DefaultPushTemplate(),
			limits:     DefaultContentLimits(),
			wantReason: ContentReasonVariableMissing,
		},
		{
			name:       "剩余任务数为零",
			mutate:     func(input *RenderInput) { input.RemainingCount = 0 },
			template:   DefaultPushTemplate(),
			limits:     DefaultContentLimits(),
			wantReason: ContentReasonInvalidValue,
		},
		{
			name:       "剩余任务数为负数",
			mutate:     func(input *RenderInput) { input.RemainingCount = -1 },
			template:   DefaultPushTemplate(),
			limits:     DefaultContentLimits(),
			wantReason: ContentReasonInvalidValue,
		},
		{
			name:       "预计用时为负数",
			mutate:     func(input *RenderInput) { input.EstimatedMinutes = intPtr(-1) },
			template:   DefaultPushTemplate(),
			limits:     DefaultContentLimits(),
			wantReason: ContentReasonInvalidValue,
		},
		{
			name:       "落地页为空",
			mutate:     func(input *RenderInput) { input.DeepLink = "" },
			template:   DefaultPushTemplate(),
			limits:     DefaultContentLimits(),
			wantReason: ContentReasonInvalidValue,
		},
		{
			name:       "排程类型未登记",
			mutate:     func(input *RenderInput) { input.ScheduleType = "" },
			template:   DefaultPushTemplate(),
			limits:     DefaultContentLimits(),
			wantReason: ContentReasonInvalidValue,
		},
		{
			name:       "标题超出长度上限",
			mutate:     func(*RenderInput) {},
			template:   DefaultPushTemplate(),
			limits:     ContentLimits{TitleMaxLen: 5, BodyMaxLen: 60},
			wantReason: ContentReasonInvalidValue,
		},
		{
			name:       "正文长度上限为配置错误值",
			mutate:     func(*RenderInput) {},
			template:   DefaultPushTemplate(),
			limits:     ContentLimits{TitleMaxLen: 30, BodyMaxLen: 0},
			wantReason: ContentReasonInvalidValue,
		},
		{
			name:       "标题长度上限为配置错误值",
			mutate:     func(*RenderInput) {},
			template:   DefaultPushTemplate(),
			limits:     ContentLimits{TitleMaxLen: 0, BodyMaxLen: 60},
			wantReason: ContentReasonInvalidValue,
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			input := validRenderInput()
			testCase.mutate(&input)
			_, err := RenderContent(input, testCase.template, testCase.limits)
			assertContentError(t, err, testCase.wantReason)
		})
	}
}

func assertActions(t *testing.T, got, want []PushAction) {
	t.Helper()
	if len(got) != len(want) {
		t.Fatalf("actions = %+v, want %+v", got, want)
	}
	for index := range want {
		if got[index] != want[index] {
			t.Fatalf("action[%d] = %+v, want %+v", index, got[index], want[index])
		}
	}
}

func assertContentError(t *testing.T, err error, wantReason string) {
	t.Helper()
	if err == nil {
		t.Fatal("expected content error")
	}
	contentErr, ok := err.(ContentError)
	if !ok {
		t.Fatalf("error type = %T, want ContentError", err)
	}
	if contentErr.Reason != wantReason {
		t.Fatalf("reason = %q, want %q", contentErr.Reason, wantReason)
	}
	// 错误文本必须带上写入 delivery.error_code 的内部错误码，便于日志与告警归因。
	if !strings.Contains(err.Error(), ContentErrorCode) {
		t.Fatalf("error text = %q, want code %s", err.Error(), ContentErrorCode)
	}
}
