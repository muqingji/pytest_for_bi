package channel

import (
	"context"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

// PlaceholderRenderer 是 FR-005 阶段的 Push 文案占位实现：只透出落地页，不产生任何文案内容。
// 文案规则、剩余任务数与预计用时、长度截断和敏感字段白名单由 FR-008 实现后替换本实现，
// 本轮不在这里写任何产品文案，避免把 FR-008 的规则提前固化。
type PlaceholderRenderer struct{}

// Render 返回空文案与调用方给定的落地页。
func (PlaceholderRenderer) Render(_ context.Context, input reminder.RenderInput) (reminder.PushContent, error) {
	return reminder.PushContent{DeepLink: input.DeepLink}, nil
}
