package task

import (
	"context"
	"errors"
	"testing"
	"time"
)

// TestFixtureRepositoryBuildsTaskFromTemplate 覆盖 Fixture 任务适配器的正常路径：
// 任务按请求里的 task_date 现场构造，预计用时缺失与 0 分钟必须可区分。
func TestFixtureRepositoryBuildsTaskFromTemplate(t *testing.T) {
	zero := 0
	repository := FixtureRepository{
		Now: func() time.Time { return time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC) },
		Users: map[string]Template{
			"user-with-estimate": {RequiredCount: 5, CompletedCount: 2, EstimatedMinutes: &zero, DeadlineLocal: "20:30", Timezone: "UTC"},
			"user-without-estimate": {
				RequiredCount:  3,
				DeadlineOffset: durationPointer(4 * time.Hour),
			},
		},
	}

	withEstimate, err := repository.GetDailyTask(context.Background(), "user-with-estimate", "2026-10-01")
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if withEstimate.UserID != "user-with-estimate" || withEstimate.TaskDate != "2026-10-01" ||
		withEstimate.RequiredCount != 5 || withEstimate.CompletedCount != 2 {
		t.Fatalf("unexpected task snapshot: %+v", withEstimate)
	}
	if withEstimate.EstimatedMinutes == nil || *withEstimate.EstimatedMinutes != 0 {
		t.Fatalf("zero estimate must stay a valid value: %+v", withEstimate.EstimatedMinutes)
	}
	if want := time.Date(2026, 10, 1, 20, 30, 0, 0, time.UTC); !withEstimate.Deadline.Equal(want) {
		t.Fatalf("deadline must use the requested task date: %v want %v", withEstimate.Deadline, want)
	}

	withoutEstimate, err := repository.GetDailyTask(context.Background(), "user-without-estimate", "2026-10-01")
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if withoutEstimate.EstimatedMinutes != nil {
		t.Fatalf("missing estimate must stay nil: %+v", withoutEstimate.EstimatedMinutes)
	}
	if want := time.Date(2026, 9, 20, 16, 0, 0, 0, time.UTC); !withoutEstimate.Deadline.Equal(want) {
		t.Fatalf("deadline offset must win over the absolute clock: %v want %v", withoutEstimate.Deadline, want)
	}
}

// TestFixtureRepositoryReturnsEmptyTaskForUnknownUser 覆盖未登记用户：
// 返回无必做任务的任务对象，由领域规则给出 NO_TASK，而不是在这里伪造拒因。
func TestFixtureRepositoryReturnsEmptyTaskForUnknownUser(t *testing.T) {
	repository := FixtureRepository{Users: map[string]Template{}}
	task, err := repository.GetDailyTask(context.Background(), "user-unknown", "2026-09-20")
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if task.UserID != "user-unknown" || task.TaskDate != "2026-09-20" || task.RequiredCount != 0 || task.CompletedCount != 0 {
		t.Fatalf("unexpected empty task: %+v", task)
	}
	if !task.Deadline.IsZero() {
		t.Fatalf("unknown user must not get a deadline: %v", task.Deadline)
	}
}

// TestFixtureRepositoryHonorsContext 覆盖依赖不可用时的快速失败。
func TestFixtureRepositoryHonorsContext(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := (FixtureRepository{}).GetDailyTask(ctx, "u1", "2026-09-20"); !errors.Is(err, context.Canceled) {
		t.Fatalf("expected context cancellation, got %v", err)
	}
}

// TestFixtureRepositoryFallsBackToSystemClock 覆盖 Now 缺省时取系统时钟的分支。
func TestFixtureRepositoryFallsBackToSystemClock(t *testing.T) {
	if (FixtureRepository{}).now().IsZero() {
		t.Fatal("default clock must be the system clock")
	}
}

// TestTemplateDeadlineFallbacks 覆盖截止时间解析的退化路径：
// 非法的本地时刻与缺失的本地时刻都表示任务系统没有给出可用截止时间（零值），评估与发送因此不施加临近截止约束。
func TestTemplateDeadlineFallbacks(t *testing.T) {
	taskDate := "2026-09-20"
	cases := []struct {
		name     string
		template Template
		wantZero bool
	}{
		{name: "empty local time", template: Template{}, wantZero: true},
		{name: "malformed local time", template: Template{DeadlineLocal: "25:99"}, wantZero: true},
		{name: "unknown timezone falls back to utc", template: Template{DeadlineLocal: "09:15", Timezone: "Mars/Olympus"}},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			deadline := testCase.template.deadline(taskDate, time.Now().UTC())
			if testCase.wantZero {
				if !deadline.IsZero() {
					t.Fatalf("expected a zero deadline: %v", deadline)
				}
				return
			}
			if want := time.Date(2026, 9, 20, 9, 15, 0, 0, time.UTC); !deadline.Equal(want) {
				t.Fatalf("deadline=%v want %v", deadline, want)
			}
		})
	}
}

// TestFixtureRepositoryDeadlineUsesUserTimezone 覆盖按用户本地时区解释截止时刻的情形。
func TestFixtureRepositoryDeadlineUsesUserTimezone(t *testing.T) {
	repository := FixtureRepository{Users: map[string]Template{
		"user-shanghai": {RequiredCount: 1, DeadlineLocal: "20:00", Timezone: "Asia/Shanghai"},
	}}
	task, err := repository.GetDailyTask(context.Background(), "user-shanghai", "2026-09-20")
	if err != nil {
		t.Fatalf("get task: %v", err)
	}
	if want := time.Date(2026, 9, 20, 12, 0, 0, 0, time.UTC); !task.Deadline.Equal(want) {
		t.Fatalf("deadline must be interpreted in the user timezone: %v want %v", task.Deadline, want)
	}
}

func durationPointer(value time.Duration) *time.Duration {
	return &value
}
