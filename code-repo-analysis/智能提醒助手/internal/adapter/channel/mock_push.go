package channel

import (
	"context"
	"sync"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

// MockPushSender 是本地 Push 渠道测试替身，用于 Demo、单测和 Mock 联调。
// 它支持幂等键、明确成功、明确失败、UNKNOWN 和状态查询，但不代表真实 Push 厂商已经具备
// 幂等与状态查询能力；真实能力必须在接入时由服务方核验。
type MockPushSender struct {
	mu sync.Mutex

	// Results 按发送调用次序依次返回；用尽后按 DefaultStatus 返回（缺省 SENT）。
	Results []reminder.PushResult
	// DefaultStatus 是未配置脚本结果时的返回状态。
	DefaultStatus reminder.DeliveryStatus
	// QueryStatus 是状态查询接口的返回状态；缺省 UNKNOWN。
	QueryStatus reminder.DeliveryStatus
	// SendErr、QueryErr 用于模拟渠道调用异常。
	SendErr  error
	QueryErr error

	requests []reminder.PushRequest
	queries  []reminder.DeliveryQuery
}

// Send 记录请求并返回脚本化结果。同一 idempotency_key 重复出现即为重试，由调用方保证复用。
func (m *MockPushSender) Send(_ context.Context, request reminder.PushRequest) (reminder.PushResult, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.requests = append(m.requests, request)
	if m.SendErr != nil {
		return reminder.PushResult{}, m.SendErr
	}
	if index := len(m.requests) - 1; index < len(m.Results) {
		return m.Results[index], nil
	}
	status := m.DefaultStatus
	if status == "" {
		status = reminder.DeliverySent
	}
	return reminder.PushResult{Status: string(status), ProviderCode: "mock"}, nil
}

// Query 返回配置的查询状态，缺省 UNKNOWN，表示无法确认。
func (m *MockPushSender) Query(_ context.Context, request reminder.DeliveryQuery) (reminder.DeliveryStatus, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.queries = append(m.queries, request)
	if m.QueryErr != nil {
		return reminder.DeliveryUnknown, m.QueryErr
	}
	if m.QueryStatus == "" {
		return reminder.DeliveryUnknown, nil
	}
	return m.QueryStatus, nil
}

// Requests 返回发送请求副本，供断言幂等键与尝试序号使用。
func (m *MockPushSender) Requests() []reminder.PushRequest {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]reminder.PushRequest(nil), m.requests...)
}

// Queries 返回状态查询请求副本。
func (m *MockPushSender) Queries() []reminder.DeliveryQuery {
	m.mu.Lock()
	defer m.mu.Unlock()
	return append([]reminder.DeliveryQuery(nil), m.queries...)
}
