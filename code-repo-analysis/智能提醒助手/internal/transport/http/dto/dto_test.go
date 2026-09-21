package dto

import (
	"encoding/json"
	"testing"
	"time"

	"intelligent-reminder-assistant/internal/application/dispatch"
	"intelligent-reminder-assistant/internal/application/evaluate"
	"intelligent-reminder-assistant/internal/application/snooze"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

// TestNewEvaluateResponseStatusMapping 覆盖 status 的四条口径（2026-09-21 决议 D1-A，以 IDL 为准）：
// 幂等命中、业务拒绝、回流首日（决策已生成但当天不发送）与正常生成。
func TestNewEvaluateResponseStatusMapping(t *testing.T) {
	scheduledAt := time.Date(2026, 9, 20, 18, 30, 0, 0, time.UTC)
	cases := []struct {
		name            string
		result          evaluate.Result
		wantStatus      string
		wantScheduledAt string
		wantChannel     string
	}{
		{
			name: "reused wins over the decision shape",
			result: evaluate.Result{Reused: true, Decision: reminder.Decision{
				ID: "decision-1", ShouldRemind: true, ReasonCode: reminder.ReasonEligible,
				StrategyVersion: "v1", UserSegment: reminder.SegmentPassive, ScheduledAt: &scheduledAt, Channel: reminder.ChannelPush,
			}},
			wantStatus: StatusReused, wantScheduledAt: "2026-09-20T18:30:00Z", wantChannel: string(reminder.ChannelPush),
		},
		{
			name: "business rejection",
			result: evaluate.Result{Decision: reminder.Decision{
				ID: "decision-2", ReasonCode: reminder.ReasonTaskCompleted, StrategyVersion: "v1", UserSegment: reminder.SegmentPassive,
			}},
			wantStatus: StatusRejected,
		},
		{
			name: "returning first day is a created decision without a push today",
			result: evaluate.Result{Decision: reminder.Decision{
				ID: "decision-3", ReasonCode: reminder.ReasonReturningFirstDay, StrategyVersion: "v1", UserSegment: reminder.SegmentReturning,
			}},
			wantStatus: StatusCreated,
		},
		{
			name: "eligible decision carries the schedule and channel",
			result: evaluate.Result{Decision: reminder.Decision{
				ID: "decision-4", ShouldRemind: true, ReasonCode: reminder.ReasonEligible, StrategyVersion: "v1",
				UserSegment: reminder.SegmentSelfDriven, ScheduledAt: &scheduledAt, Channel: reminder.ChannelPush,
			}},
			wantStatus: StatusCreated, wantScheduledAt: "2026-09-20T18:30:00Z", wantChannel: string(reminder.ChannelPush),
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			response := NewEvaluateResponse(testCase.result)
			if response.Status != testCase.wantStatus {
				t.Fatalf("status=%s want %s", response.Status, testCase.wantStatus)
			}
			if response.DecisionID != testCase.result.Decision.ID || response.StrategyVersion != "v1" ||
				response.UserSegment != string(testCase.result.Decision.UserSegment) ||
				response.ReasonCode != string(testCase.result.Decision.ReasonCode) ||
				response.ShouldRemind != testCase.result.Decision.ShouldRemind {
				t.Fatalf("decision fields must be mapped verbatim: %+v", response)
			}
			if response.ScheduledAt != testCase.wantScheduledAt || response.Channel != testCase.wantChannel {
				t.Fatalf("schedule fields: scheduled_at=%q channel=%q", response.ScheduledAt, response.Channel)
			}
		})
	}
}

// TestEvaluateResponseOmitsEmptyOptionalFields 覆盖 IDL 中可省字段的空值语义：
// 没有排程时不返回 scheduled_at、channel、user_segment。
func TestEvaluateResponseOmitsEmptyOptionalFields(t *testing.T) {
	response := NewEvaluateResponse(evaluate.Result{Decision: reminder.Decision{ID: "decision-1", ReasonCode: reminder.ReasonNoTask, StrategyVersion: "v1"}})
	encoded, err := json.Marshal(response)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	for _, field := range []string{"scheduled_at", "channel", "user_segment"} {
		if containsField(encoded, field) {
			t.Fatalf("%s must be omitted when empty: %s", field, encoded)
		}
	}
}

// TestNewDispatchResponseMapsCounts 覆盖批次计数字段的逐字段映射，游标缺省不返回。
func TestNewDispatchResponseMapsCounts(t *testing.T) {
	response := NewDispatchResponse(dispatch.Result{Scanned: 9, Claimed: 8, Sent: 7, Cancelled: 6, Failed: 5, Unknown: 4, Retried: 3, Finished: true})
	want := DispatchDueResponse{Scanned: 9, Claimed: 8, Sent: 7, Cancelled: 6, Failed: 5, Unknown: 4, Retried: 3, Finished: true}
	if response != want {
		t.Fatalf("unexpected dispatch response: %+v", response)
	}
	encoded, err := json.Marshal(response)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if containsField(encoded, "next_cursor") {
		t.Fatalf("next_cursor must be omitted locally: %s", encoded)
	}
}

// TestNewSnoozeResponseMapping 覆盖延后结果的两条路径：成功（带 snooze_until）与拒绝（不返回排程字段）。
func TestNewSnoozeResponseMapping(t *testing.T) {
	until := time.Date(2026, 9, 20, 20, 0, 0, 0, time.UTC)
	scheduled := NewSnoozeResponse(snooze.Result{
		ScheduleID: "schedule-2", Status: reminder.SnoozeScheduled, ReasonCode: reminder.ReasonEligible,
		SnoozeUntil: &until, Channel: reminder.ChannelPush, ScheduleType: reminder.ScheduleSnooze,
	})
	if scheduled.ScheduleID != "schedule-2" || scheduled.Status != string(reminder.SnoozeScheduled) ||
		scheduled.SnoozeUntil != "2026-09-20T20:00:00Z" || scheduled.Channel != string(reminder.ChannelPush) ||
		scheduled.ScheduleType != string(reminder.ScheduleSnooze) {
		t.Fatalf("unexpected scheduled response: %+v", scheduled)
	}

	rejected := NewSnoozeResponse(snooze.Result{Status: reminder.SnoozeRejected, ReasonCode: reminder.ReasonDecisionNotFound})
	if rejected.ScheduleID != "" || rejected.SnoozeUntil != "" || rejected.Channel != "" || rejected.ScheduleType != "" {
		t.Fatalf("rejected response must not carry schedule fields: %+v", rejected)
	}
	encoded, err := json.Marshal(rejected)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	if containsField(encoded, "snooze_until") {
		t.Fatalf("snooze_until must be omitted when rejected: %s", encoded)
	}
	if rejected.ReasonCode != string(reminder.ReasonDecisionNotFound) {
		t.Fatalf("reason code must be mapped verbatim: %+v", rejected)
	}
}

// TestFormatTimeNormalizesToUTC 覆盖时间串口径：统一换算到 UTC 并按秒级 RFC3339 输出。
func TestFormatTimeNormalizesToUTC(t *testing.T) {
	shanghai := time.FixedZone("UTC+8", 8*60*60)
	value := time.Date(2026, 9, 20, 18, 30, 45, 123456789, shanghai)
	if got := formatTime(value); got != "2026-09-20T10:30:45Z" {
		t.Fatalf("formatTime=%q", got)
	}
}

func containsField(encoded []byte, field string) bool {
	var decoded map[string]any
	if err := json.Unmarshal(encoded, &decoded); err != nil {
		return false
	}
	_, ok := decoded[field]
	return ok
}
