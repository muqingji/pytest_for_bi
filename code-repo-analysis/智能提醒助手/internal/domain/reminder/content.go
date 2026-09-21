package reminder

import (
	"fmt"
	"strconv"
	"strings"
)

// ContentErrorCode 是技术方案 4.3.4 登记的内部错误码：只写入
// reminder_delivery.error_code 与告警指标，不作为 HTTP ErrorResponse.code 返回。
const ContentErrorCode = "CONTENT_INVALID"

// 文案渲染失败的子原因；只进结构化日志与告警，帮助定位是哪一类校验失败，
// 不进入用户可见文案，也不需要展示占位符（技术方案 4.3.2.2 的文案异常行）。
const (
	ContentReasonSnapshotUnavailable = "snapshot_unavailable"
	ContentReasonVariableMissing     = "variable_missing"
	ContentReasonInvalidValue        = "invalid_value"
	ContentReasonSensitiveField      = "sensitive_field"
)

// 模板变量白名单：只有这两个变量允许出现在 Push 文案模板里。
// 允许其它变量名意味着任务正文、姓名或成绩等敏感字段可能被渲染进 payload（FR-008）。
const (
	ContentVarRemainingCount   = "remaining_count"
	ContentVarEstimatedMinutes = "estimated_minutes"
)

// 本期 Push 按钮文案与客户端动作标识。
const (
	ContentOpenTaskLabel = "去完成任务"
	ContentSnoozeLabel   = "稍后提醒"
	// ContentSnoozeTarget 是「稍后提醒」的客户端动作标识；真实协议属生产接入核验（技术方案 9.3）。
	ContentSnoozeTarget = "snooze_entry"
)

// ContentError 表示文案渲染校验失败；Reason 取 ContentReason* 子原因。
type ContentError struct {
	Reason string
}

func (e ContentError) Error() string {
	return fmt.Sprintf("%s: %s", ContentErrorCode, e.Reason)
}

// ContentTemplate 是 Push 文案模板；只允许使用变量白名单中的变量。
type ContentTemplate struct {
	Title string
	Body  string
}

// DefaultPushTemplate 是 PRD 7.8 的首期文案模板。
// 模板固定、短语固定，保证文案结构确定、不制造焦虑，也不会被上游数据注入自由文本。
func DefaultPushTemplate() ContentTemplate {
	return ContentTemplate{
		Title: "今天还有 {remaining_count} 项学习任务",
		Body:  "预计用时 {estimated_minutes} 分钟，现在开始刚刚好",
	}
}

// ContentLimits 是渠道长度上限（UTF-8 字符数），对应配置 push_title_max_len / push_body_max_len。
type ContentLimits struct {
	TitleMaxLen int
	BodyMaxLen  int
}

// DefaultContentLimits 是技术方案 4.7 的当前默认值；属 MVP 设计假设，上线前按真实渠道限制核验。
func DefaultContentLimits() ContentLimits {
	return ContentLimits{TitleMaxLen: 30, BodyMaxLen: 60}
}

// RenderContent 生成 Push 文案与入口（FR-008 / AC-014）。
//
// 校验顺序固定为「快照可信性 -> 变量取值 -> 入口合法性 -> 模板变量白名单 -> 长度」：
// 任一失败都返回 ContentError，调用方据此不发送、不重试、不写旧快照、不展示占位符。
// 先校验快照再校验取值，是因为读取失败时入参本身不可信，任何取值判断都没有意义。
func RenderContent(input RenderInput, template ContentTemplate, limits ContentLimits) (PushContent, error) {
	if input.SnapshotReadFailed {
		// 发送前读取最新任务状态失败：宁可不发，也不能用评估时点的旧快照渲染出过期文案。
		return PushContent{}, ContentError{Reason: ContentReasonSnapshotUnavailable}
	}
	if input.EstimatedMinutes == nil {
		return PushContent{}, ContentError{Reason: ContentReasonVariableMissing}
	}
	if input.RemainingCount <= 0 || *input.EstimatedMinutes < 0 || input.DeepLink == "" {
		// 剩余任务数为 0 或负数说明上游资格判断未短路；预计用时为负、落地页为空同样属输入不完整。
		return PushContent{}, ContentError{Reason: ContentReasonInvalidValue}
	}
	actions, err := contentActions(input)
	if err != nil {
		return PushContent{}, err
	}
	if limits.TitleMaxLen <= 0 || limits.BodyMaxLen <= 0 {
		// 长度上限来自配置：非正数会让截断规则失去意义，按配置错误拒绝而不是静默跳过截断。
		return PushContent{}, ContentError{Reason: ContentReasonInvalidValue}
	}
	values := map[string]string{
		ContentVarRemainingCount:   strconv.Itoa(input.RemainingCount),
		ContentVarEstimatedMinutes: strconv.Itoa(*input.EstimatedMinutes),
	}
	title, err := renderTemplate(template.Title, values)
	if err != nil {
		return PushContent{}, err
	}
	body, err := renderTemplate(template.Body, values)
	if err != nil {
		return PushContent{}, err
	}
	if len([]rune(title)) > limits.TitleMaxLen {
		// 标题承载剩余任务数，不参与截断：超限说明模板或取值非法，直接拒绝而不是截掉数量字段。
		return PushContent{}, ContentError{Reason: ContentReasonInvalidValue}
	}
	return PushContent{
		Title:    title,
		Body:     truncateRunes(body, limits.BodyMaxLen),
		DeepLink: input.DeepLink,
		Actions:  actions,
	}, nil
}

// contentActions 按排程类型生成按钮与入口：
// 系统主动 Push 提供「去完成任务」与「稍后提醒」；延后提醒只提供「去完成任务」，
// 不再提供再次延后入口（PRD 7.7 与技术方案 9.1 的 FR-008 行）。未登记的排程类型按非法取值拒绝，
// 避免未知类型默认拿到延后入口而绕过「延后链条最多一段」。
func contentActions(input RenderInput) ([]PushAction, error) {
	openTask := PushAction{Type: PushActionOpenTask, Label: ContentOpenTaskLabel, Target: input.DeepLink}
	switch input.ScheduleType {
	case ScheduleInitial:
		return []PushAction{
			openTask,
			{Type: PushActionSnooze, Label: ContentSnoozeLabel, Target: ContentSnoozeTarget},
		}, nil
	case ScheduleSnooze:
		return []PushAction{openTask}, nil
	default:
		return nil, ContentError{Reason: ContentReasonInvalidValue}
	}
}

// renderTemplate 按变量白名单渲染模板。
// values 只会由 RenderContent 填入白名单变量的取值，因此出现任何未登记的变量名
// （例如 {task_title}、{user_name}、{score}）都说明文案可能携带任务正文、姓名或成绩，
// 一律按敏感字段校验失败处理，并且不输出半成品文案。
// 模板里未被识别的花括号按普通文本原样保留，避免把用户可见文案截断。
func renderTemplate(text string, values map[string]string) (string, error) {
	var out strings.Builder
	rest := text
	for {
		start := strings.Index(rest, "{")
		if start < 0 {
			out.WriteString(rest)
			return out.String(), nil
		}
		end := strings.Index(rest[start:], "}")
		if end < 0 {
			out.WriteString(rest)
			return out.String(), nil
		}
		out.WriteString(rest[:start])
		name := rest[start+1 : start+end]
		value, ok := values[name]
		if !ok {
			return "", ContentError{Reason: ContentReasonSensitiveField}
		}
		out.WriteString(value)
		rest = rest[start+end+1:]
	}
}

// truncateRunes 按 UTF-8 字符数截断正文尾部并补省略号：只截尾部，
// 保证标题里的剩余任务数不会因截断丢失，且截断后总长不超过上限。
func truncateRunes(text string, max int) string {
	runes := []rune(text)
	if len(runes) <= max {
		return text
	}
	if max <= 1 {
		return "…"
	}
	return string(runes[:max-1]) + "…"
}
