package reminder

import (
	"testing"
	"time"
)

func TestDeliveryStatusNormalization(t *testing.T) {
	cases := map[string]DeliveryStatus{
		"SENT":         DeliverySent,
		" failed ":     DeliveryFailed,
		"UNKNOWN":      DeliveryUnknown,
		"SENDING":      DeliveryUnknown,
		"RATE_LIMITED": DeliveryUnknown,
		"":             DeliveryUnknown,
	}
	for input, expected := range cases {
		if actual := DeliveryStatusOf(PushResult{Status: input}); actual != expected {
			t.Fatalf("status %q: got %s want %s", input, actual, expected)
		}
	}
}

func TestRetryAllowedCapsAtOneRetry(t *testing.T) {
	if !RetryAllowed(1, 2) {
		t.Fatal("expected the first explicit failure to allow one retry")
	}
	if RetryAllowed(2, 2) {
		t.Fatal("expected the second attempt to exhaust retries")
	}
	if RetryAllowed(3, 2) {
		t.Fatal("expected no retry beyond the attempt cap")
	}
	// 未配置尝试上限时按技术方案默认值 2 处理。
	if !RetryAllowed(1, 0) {
		t.Fatal("expected the default attempt cap of 2")
	}
	if RetryAllowed(0, 2) {
		t.Fatal("expected an invalid attempt number to stop retrying")
	}
}

func TestNextScheduleStatusDerivation(t *testing.T) {
	if status := NextScheduleStatus(DeliverySent, false); status != ScheduleSent {
		t.Fatalf("sent: %s", status)
	}
	if status := NextScheduleStatus(DeliveryFailed, true); status != ScheduleRetryWait {
		t.Fatalf("failed with retry: %s", status)
	}
	if status := NextScheduleStatus(DeliveryFailed, false); status != ScheduleFailed {
		t.Fatalf("failed without retry: %s", status)
	}
	if status := NextScheduleStatus(DeliveryUnknown, true); status != ScheduleUnknown {
		t.Fatalf("unknown: %s", status)
	}
}

func TestDeliveryIdempotencyKeyKeepsScheduleVersion(t *testing.T) {
	schedule := Schedule{UserID: "user-passive", TaskDate: "2026-09-20", Channel: ChannelPush, DecisionID: "decision-1", ScheduleVersion: 1}
	if key := DeliveryIdempotencyKey(schedule); key != "user-passive_2026-09-20_push_decision-1_1" {
		t.Fatalf("unexpected idempotency key: %s", key)
	}
	// SNOOZE 排程使用递增版本，因此与 INITIAL 排程不会共用同一把幂等键。
	schedule.ScheduleVersion = 2
	schedule.ScheduleType = ScheduleSnooze
	if key := DeliveryIdempotencyKey(schedule); key != "user-passive_2026-09-20_push_decision-1_2" {
		t.Fatalf("unexpected snooze idempotency key: %s", key)
	}
}

func TestLocalLocationAndDeliveryExpireAt(t *testing.T) {
	if location := LocalLocation(""); location != time.UTC {
		t.Fatalf("empty timezone should fall back to UTC: %s", location)
	}
	if location := LocalLocation("Not/AZone"); location != time.UTC {
		t.Fatalf("invalid timezone should fall back to UTC: %s", location)
	}
	location := LocalLocation("Asia/Shanghai")
	expireAt := DeliveryExpireAt("2026-09-20", "Asia/Shanghai")
	if expireAt.IsZero() || location.String() != "Asia/Shanghai" {
		t.Fatalf("unexpected timezone or expire time: %s %s", location, expireAt)
	}
	if name, offset := expireAt.Zone(); name != "CST" || offset != 8*60*60 {
		t.Fatalf("expected the user local zone: %s %d", name, offset)
	}
	if expireAt.UTC().Format(time.RFC3339) != "2026-09-20T16:00:00Z" {
		t.Fatalf("local midnight should be 16:00Z: %s", expireAt.UTC())
	}
	if !DeliveryExpireAt("not-a-date", "UTC").IsZero() {
		t.Fatal("expected zero time for an invalid task date")
	}
}
