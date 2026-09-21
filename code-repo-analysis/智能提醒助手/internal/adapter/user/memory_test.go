package user

import (
	"context"
	"errors"
	"testing"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

func TestMemoryRepositoryDefaultsAndNormalizesPreferences(t *testing.T) {
	repo := MemoryRepository{Preferences: map[string]reminder.ReminderPreference{
		"u1": {ReminderEnabled: true, PushEnabled: true},
	}}
	pref, err := repo.Get(context.Background(), "u1")
	if err != nil || pref.QuietHoursStart != "21:30" || pref.QuietHoursEnd != "07:00" || pref.Timezone != "UTC" || pref.DailyPushCap != 1 {
		t.Fatalf("normalized preference: %+v err=%v", pref, err)
	}
	missing, err := (MemoryRepository{}).Get(context.Background(), "missing")
	if err != nil || !missing.ReminderEnabled || missing.Timezone != "UTC" {
		t.Fatalf("default preference: %+v err=%v", missing, err)
	}
}

func TestMemoryRepositoryHonorsErrorsAndContext(t *testing.T) {
	repo := MemoryRepository{
		PreferenceErrors: map[string]error{"u1": errors.New("preference failed")},
		BehaviorErrors:   map[string]error{"u1": errors.New("behavior failed")},
	}
	if _, err := repo.Get(context.Background(), "u1"); err == nil {
		t.Fatal("expected preference error")
	}
	if _, err := repo.GetRecent(context.Background(), "u1", 7); err == nil {
		t.Fatal("expected behavior error")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := repo.Get(ctx, "u1"); err == nil {
		t.Fatal("expected canceled preference context")
	}
	if _, err := repo.GetRecent(ctx, "u1", 7); err == nil {
		t.Fatal("expected canceled behavior context")
	}
}
