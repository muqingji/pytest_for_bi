package channel

import (
	"context"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

// TemplateRenderer 是 FR-008 的 Push 文案渲染器，实现 port.ContentRenderer。
// 文案规则、变量白名单、长度截断与入口规则都在 domain/reminder 的 RenderContent 中，
// 适配器只负责装配模板与渠道长度上限，保持「业务规则不进适配器层」的依赖方向。
type TemplateRenderer struct {
	Template reminder.ContentTemplate
	Limits   reminder.ContentLimits
}

// NewTemplateRenderer 用 PRD 7.8 的首期模板与技术方案 4.7 的默认长度上限构造渲染器。
func NewTemplateRenderer() TemplateRenderer {
	return TemplateRenderer{Template: reminder.DefaultPushTemplate(), Limits: reminder.DefaultContentLimits()}
}

// Render 生成文案与入口；校验失败返回 domain 的 ContentError，
// 由调用方按技术方案 4.3.2.2 记录 CONTENT_INVALID、不发送且不重试。
func (r TemplateRenderer) Render(_ context.Context, input reminder.RenderInput) (reminder.PushContent, error) {
	return reminder.RenderContent(input, r.Template, r.Limits)
}
