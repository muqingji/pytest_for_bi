package http

import (
	"errors"
	"fmt"
	nethttp "net/http"
	"time"

	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/application/snooze"
	"intelligent-reminder-assistant/internal/domain/reminder"
	"intelligent-reminder-assistant/internal/transport/http/dto"
)

// pathDecisionID 是 snooze 路径参数名，与 IDL 的 `{decision_id}` 一致。
const pathDecisionID = "decision_id"

// maxDispatchBatchSize 对应 4.7 的 dispatch_batch_size=50，与 IDL 的 maximum 一致。
const maxDispatchBatchSize = 50

func (s Server) handleEvaluate(w nethttp.ResponseWriter, r *nethttp.Request) {
	current := scopeFrom(r.Context())
	var request dto.EvaluateReminderRequest
	if err := decodeBody(r, &request, false); err != nil {
		writeValidationError(w, current.requestID)
		return
	}
	useCase, err := newEvaluateRequest(request)
	if err != nil {
		writeValidationError(w, current.requestID)
		return
	}
	result, err := s.Evaluate.Evaluate(r.Context(), useCase)
	if err != nil {
		writeDependencyError(w, current.requestID, err)
		return
	}
	writeJSON(w, nethttp.StatusOK, dto.NewEvaluateResponse(result))
}

func (s Server) handleDispatch(w nethttp.ResponseWriter, r *nethttp.Request) {
	current := scopeFrom(r.Context())
	var request dto.DispatchDueRequest
	// dispatch-due 的 requestBody 在 IDL 中可选，空请求体等价于全部取默认值。
	if err := decodeBody(r, &request, true); err != nil {
		writeValidationError(w, current.requestID)
		return
	}
	useCase, err := newDispatchRequest(request)
	if err != nil {
		writeValidationError(w, current.requestID)
		return
	}
	result, err := s.Dispatch.DispatchDue(r.Context(), useCase)
	if err != nil {
		writeDependencyError(w, current.requestID, err)
		return
	}
	writeJSON(w, nethttp.StatusOK, dto.NewDispatchResponse(result))
}

func (s Server) handleSnooze(w nethttp.ResponseWriter, r *nethttp.Request) {
	current := scopeFrom(r.Context())
	var request dto.SnoozeReminderRequest
	if err := decodeBody(r, &request, false); err != nil {
		writeValidationError(w, current.requestID)
		return
	}
	useCase, err := newSnoozeRequest(r.PathValue(pathDecisionID), request)
	if err != nil {
		writeValidationError(w, current.requestID)
		return
	}
	result, err := s.Snooze.Snooze(r.Context(), useCase)
	// 第二次入口与入参问题属调用错误，按 4.3.2.3 返回 400，不伪装成业务拒绝。
	if errors.Is(err, snooze.ErrInvalidRequest) {
		writeValidationError(w, current.requestID)
		return
	}
	if err != nil {
		writeDependencyError(w, current.requestID, err)
		return
	}
	writeJSON(w, nethttp.StatusOK, dto.NewSnoozeResponse(result))
}

// newEvaluateRequest 按 4.3.2.1 的请求字段校验表校验并映射为用例入参：任何不满足契约的取值都返回错误，
// 由调用方转成 400 + INVALID_REQUEST，不做降级猜测，也不允许客户端传入服务端决策字段。
func newEvaluateRequest(request dto.EvaluateReminderRequest) (evaluate.Request, error) {
	if err := validateIdentifier("request_id", request.RequestID); err != nil {
		return evaluate.Request{}, err
	}
	if err := validateIdentifier("user_id", request.UserID); err != nil {
		return evaluate.Request{}, err
	}
	if _, err := time.Parse("2006-01-02", request.TaskDate); err != nil {
		return evaluate.Request{}, fmt.Errorf("task_date must be YYYY-MM-DD: %w", err)
	}
	trigger, err := parseTrigger(request.Trigger)
	if err != nil {
		return evaluate.Request{}, err
	}
	lastOpenAt, err := parseLastOpenAt(trigger, request.LastOpenAt)
	if err != nil {
		return evaluate.Request{}, err
	}
	return evaluate.Request{
		UserID:     request.UserID,
		TaskDate:   request.TaskDate,
		Trigger:    trigger,
		LastOpenAt: lastOpenAt,
	}, nil
}

// parseTrigger 把报文的 trigger 映射为领域触发来源。两者取值逐字一致（IDL 与领域常量同一套取值，
// 见 2026-09-21 决议 D2-A），因此这里是 1:1 映射而不是翻译表；未知枚举按 4.3.2.1 拒绝。
func parseTrigger(value string) (reminder.Trigger, error) {
	trigger := reminder.Trigger(value)
	switch trigger {
	case reminder.TriggerDaily, reminder.TriggerAppOpen, reminder.TriggerTaskChanged, reminder.TriggerPreferenceChanged:
		return trigger, nil
	default:
		return "", fmt.Errorf("unknown trigger %q", value)
	}
}

// parseLastOpenAt 按 4.3.2.1 处理 last_open_at：仅 APP_OPENED 允许出现且条件必填；
// 空串表示没有历史打开记录（返回 nil，不判定回流首日，由用例记录行为数据降级）；非空必须是 RFC3339。
func parseLastOpenAt(trigger reminder.Trigger, value *string) (*time.Time, error) {
	if trigger != reminder.TriggerAppOpen {
		if value != nil && *value != "" {
			return nil, fmt.Errorf("last_open_at must be empty when trigger is %s", reminder.TriggerAppOpen)
		}
		return nil, nil
	}
	if value == nil {
		return nil, fmt.Errorf("last_open_at is required when trigger is %s", reminder.TriggerAppOpen)
	}
	if *value == "" {
		return nil, nil
	}
	parsed, err := time.Parse(time.RFC3339, *value)
	if err != nil {
		return nil, fmt.Errorf("last_open_at must be RFC3339: %w", err)
	}
	return &parsed, nil
}

// newDispatchRequest 按 4.3.2.2 校验批次入参。执行时间与用户清单不接受客户端传入：
// 批次对象由服务端按到期条件扫描，这里只映射批大小。
func newDispatchRequest(request dto.DispatchDueRequest) (dispatch.Request, error) {
	if request.Cursor != "" {
		// 本地交付不实现游标续跑（按到期条件扫描，单批处理完即 finished），
		// 收到游标按 4.3.2.2「无法解析的游标」口径拒绝，不做全量重扫。
		return dispatch.Request{}, errors.New("cursor is not supported by the local entry")
	}
	if request.BatchSize == nil {
		// 缺省交给用例取配置默认值 50。
		return dispatch.Request{}, nil
	}
	if *request.BatchSize < 1 || *request.BatchSize > maxDispatchBatchSize {
		return dispatch.Request{}, fmt.Errorf("batch_size must be between 1 and %d", maxDispatchBatchSize)
	}
	return dispatch.Request{BatchSize: *request.BatchSize}, nil
}

// newSnoozeRequest 按 4.3.2.3 校验路径参数与请求体。
// user_id 与鉴权上下文的一致性由生产鉴权层保证：本地静态令牌不携带用户身份，故不在此处判定 403。
func newSnoozeRequest(decisionID string, request dto.SnoozeReminderRequest) (snooze.Request, error) {
	if err := validateIdentifier(pathDecisionID, decisionID); err != nil {
		return snooze.Request{}, err
	}
	if err := validateIdentifier("request_id", request.RequestID); err != nil {
		return snooze.Request{}, err
	}
	if err := validateIdentifier("user_id", request.UserID); err != nil {
		return snooze.Request{}, err
	}
	return snooze.Request{
		UserID:     request.UserID,
		DecisionID: decisionID,
		RequestID:  request.RequestID,
	}, nil
}

// validateIdentifier 校验 1–64 字符的标识字段（IDL 对 request_id、user_id、decision_id 的统一约束）。
func validateIdentifier(name, value string) error {
	if value == "" || len(value) > maxIdentifierLength {
		return fmt.Errorf("%s must be 1-%d characters", name, maxIdentifierLength)
	}
	return nil
}
