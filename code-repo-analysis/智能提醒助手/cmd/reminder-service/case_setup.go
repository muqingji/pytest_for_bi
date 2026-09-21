// 本文件实现本地接口自动化的逐 Case 前置状态播种。
// 它只在显式传入 -setup 时生效，不参与生产业务请求，也不改变任何领域判定。
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"intelligent-reminder-assistant/internal/adapter/storage"
	"intelligent-reminder-assistant/internal/domain/reminder"
)

// caseSetupFile 是 pytest 从单条 Case 的 test_data 生成的临时文件。
// user_id 和 task_date 负责把服务端状态绑定回唯一 Fixture；setup 保留 Case 中的原始结构，
// 防止测试运行器另造一份无法追踪的数据。
type caseSetupFile struct {
	UserID   string           `json:"user_id"`
	TaskDate string           `json:"task_date"`
	Setup    fixtureCaseSetup `json:"setup"`
}

type fixtureCaseSetup struct {
	Schedule               *fixtureSchedule       `json:"schedule"`
	InitialDecision        *fixtureSchedule       `json:"initial_decision"`
	ChannelResult          string                 `json:"channel_result"`
	LatestTask             *fixtureLatestTask     `json:"latest_task"`
	ExpectedChannelPayload *fixtureChannelPayload `json:"expected_channel_payload"`
}

type fixtureSchedule struct {
	DecisionID   string `json:"decision_id"`
	ScheduleID   string `json:"schedule_id"`
	ScheduleType string `json:"schedule_type"`
	Status       string `json:"status"`
	ScheduledAt  string `json:"scheduled_at"`
}

type fixtureLatestTask struct {
	RequiredCount    int `json:"required_count"`
	CompletedCount   int `json:"completed_count"`
	RemainingCount   int `json:"remaining_count"`
	EstimatedMinutes int `json:"estimated_minutes"`
}

type fixtureChannelPayload struct {
	RemainingCount   int    `json:"remaining_count"`
	EstimatedMinutes int    `json:"estimated_minutes"`
	Action           string `json:"action"`
}

// seedCaseSetup 把单条 Case 需要的 decision 与 INITIAL schedule 写入空白临时库。
// dispatch 和 snooze 接口本身不接受这些服务端字段，因此只能在进程启动、对外监听之前播种；
// 这既保持 HTTP 契约不变，也确保请求到达时看到的是完整且隔离的前置状态。
func seedCaseSetup(ctx context.Context, store *storage.Store, seeds fixtures, path string, now time.Time) error {
	if path == "" {
		return nil
	}
	content, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read case setup: %w", err)
	}
	var file caseSetupFile
	if err := json.Unmarshal(content, &file); err != nil {
		return fmt.Errorf("parse case setup %s: %w", path, err)
	}
	if file.UserID == "" || file.TaskDate == "" {
		return fmt.Errorf("case setup user_id and task_date are required")
	}
	if _, exists := seeds.tasks.Users[file.UserID]; !exists {
		return fmt.Errorf("case setup user %q is not present in fixtures", file.UserID)
	}
	if file.Setup.ChannelResult != "" && file.Setup.ChannelResult != "SUCCESS" {
		return fmt.Errorf("case setup channel_result %q is unsupported by the local success stub", file.Setup.ChannelResult)
	}
	if err := validateSetupTask(ctx, seeds, file); err != nil {
		return err
	}

	seed, err := file.Setup.scheduleSeed()
	if err != nil {
		return err
	}
	if seed == nil {
		return nil
	}
	scheduledAt, err := time.Parse(time.RFC3339, seed.ScheduledAt)
	if err != nil {
		return fmt.Errorf("parse case setup scheduled_at %q: %w", seed.ScheduledAt, err)
	}
	scheduleType, status, err := validateScheduleSeed(*seed)
	if err != nil {
		return err
	}

	decision := reminder.Decision{
		ID:              seed.DecisionID,
		UserID:          file.UserID,
		TaskDate:        file.TaskDate,
		ShouldRemind:    true,
		ScheduledAt:     &scheduledAt,
		Channel:         reminder.ChannelPush,
		ReasonCode:      reminder.ReasonEligible,
		StrategyVersion: defaultStrategyVersion,
		UserSegment:     reminder.SegmentPassive,
		DedupeKey:       file.UserID + "|" + file.TaskDate + "|" + defaultStrategyVersion,
		Status:          reminder.DecisionScheduled,
		Version:         1,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	schedule := &reminder.Schedule{
		ID:              seed.ScheduleID,
		DecisionID:      seed.DecisionID,
		UserID:          file.UserID,
		TaskDate:        file.TaskDate,
		ScheduleVersion: 1,
		Channel:         reminder.ChannelPush,
		ScheduleType:    scheduleType,
		ScheduledAt:     scheduledAt,
		Status:          status,
		CreatedAt:       now,
		UpdatedAt:       now,
	}
	if _, err := store.CreateDecisionAndSchedule(ctx, decision, schedule); err != nil {
		return fmt.Errorf("seed case decision and schedule: %w", err)
	}
	return nil
}

// scheduleSeed 接受 dispatch 用的 schedule 或 snooze 用的 initial_decision，两者只能出现一个。
// 保留这两个业务语义名称，pytest 可以直接消费已审批 Case 的 test_data.setup，无需做隐式字段改写。
func (s fixtureCaseSetup) scheduleSeed() (*fixtureSchedule, error) {
	if s.Schedule != nil && s.InitialDecision != nil {
		return nil, fmt.Errorf("case setup must contain only one of schedule or initial_decision")
	}
	if s.Schedule != nil {
		return s.Schedule, nil
	}
	return s.InitialDecision, nil
}

// validateScheduleSeed 在写库前收紧测试数据边界。当前 10 条 Case 只需要 INITIAL 前置排程；
// 非法状态若被写入会让测试以“扫描不到数据”的方式误绿，因此这里直接失败。
func validateScheduleSeed(seed fixtureSchedule) (reminder.ScheduleType, reminder.ScheduleStatus, error) {
	if seed.DecisionID == "" || seed.ScheduleID == "" || seed.ScheduledAt == "" {
		return "", "", fmt.Errorf("case setup decision_id, schedule_id and scheduled_at are required")
	}
	if seed.ScheduleType != string(reminder.ScheduleInitial) {
		return "", "", fmt.Errorf("case setup schedule_type %q is unsupported; want INITIAL", seed.ScheduleType)
	}
	status := reminder.ScheduleStatus(seed.Status)
	if status != reminder.ScheduleScheduled && status != reminder.ScheduleSent {
		return "", "", fmt.Errorf("case setup schedule status %q is unsupported", seed.Status)
	}
	return reminder.ScheduleInitial, status, nil
}

// validateSetupTask 校验 Case 中显式声明的“发送前最新任务快照”确实来自同一个 Fixture。
// setup 不负责改写任务；不一致时直接阻止服务启动，避免 TC-007 声称使用 5/3/20，实际却发送另一组数据。
func validateSetupTask(ctx context.Context, seeds fixtures, file caseSetupFile) error {
	if file.Setup.LatestTask == nil && file.Setup.ExpectedChannelPayload == nil {
		return nil
	}
	task, err := seeds.tasks.GetDailyTask(ctx, file.UserID, file.TaskDate)
	if err != nil {
		return fmt.Errorf("read case setup fixture task: %w", err)
	}
	remaining := task.RequiredCount - task.CompletedCount
	if file.Setup.LatestTask != nil {
		latest := file.Setup.LatestTask
		if task.EstimatedMinutes == nil || task.RequiredCount != latest.RequiredCount || task.CompletedCount != latest.CompletedCount ||
			remaining != latest.RemainingCount || *task.EstimatedMinutes != latest.EstimatedMinutes {
			return fmt.Errorf("case setup latest_task does not match fixture task for %s", file.UserID)
		}
	}
	if file.Setup.ExpectedChannelPayload != nil {
		payload := file.Setup.ExpectedChannelPayload
		if task.EstimatedMinutes == nil || remaining != payload.RemainingCount || *task.EstimatedMinutes != payload.EstimatedMinutes || payload.Action != string(reminder.PushActionOpenTask) {
			return fmt.Errorf("case setup expected_channel_payload does not match fixture task for %s", file.UserID)
		}
	}
	return nil
}
