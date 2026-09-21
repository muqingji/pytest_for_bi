// Package dto 定义三个内部接口的请求与响应报文，字段名、类型与必填性以 IDL 为唯一事实源
// （docs/api/reminder-service.openapi.yaml，技术方案 4.3.1）。
//
// 本包只做「报文字段 ↔ 用例入参/结果」的映射：是否提醒、原因码、排程时刻、幂等命中都由应用层给出，
// DTO 不复制任何业务规则，也不允许把服务端决策字段做成请求字段。
package dto

import (
	"time"

	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/application/snooze"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

// EvaluateReminderRequest 是 EvaluateReminder 的请求体（IDL `EvaluateReminderRequest`）。
type EvaluateReminderRequest struct {
	RequestID string `json:"request_id"`
	UserID    string `json:"user_id"`
	TaskDate  string `json:"task_date"`
	Trigger   string `json:"trigger"`
	// LastOpenAt 用指针区分「未提供」与「无历史打开记录」：IDL 中该字段对 APP_OPENED 是条件必填，
	// 无历史打开记录必须传空串而不是省略或 null。
	LastOpenAt *string `json:"last_open_at"`
}

// EvaluateReminderResponse 是 EvaluateReminder 的响应体（IDL `EvaluateReminderResponse`）。
type EvaluateReminderResponse struct {
	DecisionID      string `json:"decision_id"`
	Status          string `json:"status"`
	ReasonCode      string `json:"reason_code"`
	ShouldRemind    bool   `json:"should_remind"`
	ScheduledAt     string `json:"scheduled_at,omitempty"`
	Channel         string `json:"channel,omitempty"`
	UserSegment     string `json:"user_segment,omitempty"`
	StrategyVersion string `json:"strategy_version"`
}

// DispatchDueRequest 是 DispatchDue 的请求体（IDL `DispatchDueRequest`）。
// BatchSize 用指针区分「未提供」（取默认 50）与显式 0（越界，按参数错误拒绝）。
type DispatchDueRequest struct {
	BatchSize *int   `json:"batch_size"`
	Cursor    string `json:"cursor"`
}

// DispatchDueResponse 是 DispatchDue 的响应体（IDL `DispatchDueResponse`），只含计数与游标，不含用户级明细。
type DispatchDueResponse struct {
	Scanned    int    `json:"scanned"`
	Claimed    int    `json:"claimed"`
	Sent       int    `json:"sent"`
	Cancelled  int    `json:"cancelled"`
	Failed     int    `json:"failed"`
	Unknown    int    `json:"unknown"`
	Retried    int    `json:"retried"`
	NextCursor string `json:"next_cursor,omitempty"`
	Finished   bool   `json:"finished"`
}

// SnoozeReminderRequest 是 SnoozeReminder 的请求体（IDL `SnoozeReminderRequest`）；decision_id 在路径中。
type SnoozeReminderRequest struct {
	RequestID string `json:"request_id"`
	UserID    string `json:"user_id"`
}

// SnoozeReminderResponse 是 SnoozeReminder 的响应体（IDL `SnoozeReminderResponse`）。
// REJECTED 时 schedule_id 为空串（字段仍返回），排程字段整体缺省。
type SnoozeReminderResponse struct {
	ScheduleID   string `json:"schedule_id"`
	Status       string `json:"status"`
	ReasonCode   string `json:"reason_code"`
	SnoozeUntil  string `json:"snooze_until,omitempty"`
	Channel      string `json:"channel,omitempty"`
	ScheduleType string `json:"schedule_type,omitempty"`
}

// ErrorResponse 是三个接口共用的错误响应（IDL `ErrorResponse`）。
type ErrorResponse struct {
	Code      string `json:"code"`
	Message   string `json:"message"`
	Retryable bool   `json:"retryable"`
	RequestID string `json:"request_id"`
}

// EvaluateReminderResponse.status 的取值（IDL）。
const (
	StatusCreated  = "CREATED"
	StatusReused   = "REUSED"
	StatusRejected = "REJECTED"
)

// NewEvaluateResponse 映射评估结果。
//
// status 口径（2026-09-21 决议 D1-A，以 IDL 为准）：幂等命中为 REUSED；本次结论未进入提醒策略
// 且属资格、设置、频控、渠道类拒绝为 REJECTED；其余为 CREATED，包含 should_remind=true 与「回流首日」
// 这类决策已生成、当天不发送的明确结论（IDL 的 returning_first_day 示例即 CREATED + should_remind=false）。
func NewEvaluateResponse(result evaluate.Result) EvaluateReminderResponse {
	decision := result.Decision
	response := EvaluateReminderResponse{
		DecisionID:      decision.ID,
		Status:          StatusCreated,
		ReasonCode:      string(decision.ReasonCode),
		ShouldRemind:    decision.ShouldRemind,
		UserSegment:     string(decision.UserSegment),
		StrategyVersion: decision.StrategyVersion,
	}
	switch {
	case result.Reused:
		response.Status = StatusReused
	case !decision.ShouldRemind && decision.ReasonCode != reminder.ReasonReturningFirstDay:
		response.Status = StatusRejected
	}
	if decision.ScheduledAt != nil {
		response.ScheduledAt = formatTime(*decision.ScheduledAt)
	}
	if decision.Channel != "" {
		response.Channel = string(decision.Channel)
	}
	return response
}

// NewDispatchResponse 映射批次结果；游标字段本地不产生，缺省不返回。
func NewDispatchResponse(result dispatch.Result) DispatchDueResponse {
	return DispatchDueResponse{
		Scanned:   result.Scanned,
		Claimed:   result.Claimed,
		Sent:      result.Sent,
		Cancelled: result.Cancelled,
		Failed:    result.Failed,
		Unknown:   result.Unknown,
		Retried:   result.Retried,
		Finished:  result.Finished,
	}
}

// NewSnoozeResponse 映射延后结果；拒绝时不返回排程字段（IDL：仅 SCHEDULED/REUSED 时返回）。
func NewSnoozeResponse(result snooze.Result) SnoozeReminderResponse {
	response := SnoozeReminderResponse{
		ScheduleID:   result.ScheduleID,
		Status:       string(result.Status),
		ReasonCode:   string(result.ReasonCode),
		Channel:      string(result.Channel),
		ScheduleType: string(result.ScheduleType),
	}
	if result.SnoozeUntil != nil {
		response.SnoozeUntil = formatTime(*result.SnoozeUntil)
	}
	return response
}

// formatTime 统一输出 UTC RFC3339 秒级时间串（IDL 的 date-time 口径）。
func formatTime(value time.Time) string {
	return value.UTC().Format(time.RFC3339)
}
