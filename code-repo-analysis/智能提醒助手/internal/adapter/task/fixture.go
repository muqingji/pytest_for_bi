package task

import (
	"context"
	"time"

	"intelligent-reminder-assistant/internal/domain/reminder"
)

// Template 是本地 Fixture 里单个用户的任务模板（`testenv/fixtures/users.json` 的任务模板与该用户的时区解析结果）。
// 它只用于本地 Demo 与业务测试的种子数据，不代表生产任务系统的字段契约。
type Template struct {
	RequiredCount  int
	CompletedCount int
	// EstimatedMinutes 为 nil 表示任务系统未返回该字段，与 0 分钟区分（技术方案 9.3 FR-008 第 2 条）。
	EstimatedMinutes *int
	// DeadlineLocal 是任务日期当天的本地 HH:mm（按 Timezone 解释），使同一个种子用户对任意任务日期都返回同一状态。
	DeadlineLocal string
	// DeadlineOffset 非 nil 时优先于 DeadlineLocal，用于构造必然过期或必然临近的相对时刻。
	DeadlineOffset *time.Duration
	// Timezone 是解释 DeadlineLocal 的用户本地时区；缺失或非法时按 UTC 处理。
	Timezone string
}

// FixtureRepository 是 Fixture 驱动的任务适配器：任务按请求里的 task_date 现场构造，
// 不预置固定日期，因此同一个种子用户对任意 task_date 都返回同一状态（数据构造说明.md「task_date 不写死」的约定）。
type FixtureRepository struct {
	// Users 按 user_id 索引任务模板；未登记的用户按「当天没有任务」返回。
	Users map[string]Template
	// Now 提供「相对当前时刻」截止时间的基准；缺省取系统时钟。
	Now func() time.Time
}

// GetDailyTask 返回种子任务快照。未登记的用户返回无必做任务的任务对象，
// 交由领域规则给出 NO_TASK，而不是在此处伪造拒因。
func (r FixtureRepository) GetDailyTask(ctx context.Context, userID, taskDate string) (reminder.DailyTask, error) {
	if err := ctx.Err(); err != nil {
		return reminder.DailyTask{}, err
	}
	task := reminder.DailyTask{UserID: userID, TaskDate: taskDate}
	template, ok := r.Users[userID]
	if !ok {
		return task, nil
	}
	task.RequiredCount = template.RequiredCount
	task.CompletedCount = template.CompletedCount
	if template.EstimatedMinutes != nil {
		minutes := *template.EstimatedMinutes
		task.EstimatedMinutes = &minutes
	}
	task.Deadline = template.deadline(taskDate, r.now())
	return task, nil
}

func (r FixtureRepository) now() time.Time {
	if r.Now != nil {
		return r.Now()
	}
	return time.Now().UTC()
}

// deadline 解析任务截止时间：相对时刻优先，其次按用户本地时区解释当天的 HH:mm。
// 两者都不可用时返回零值，表示任务系统未给出截止时间，评估与发送都不施加「截止前不足 1 小时」约束。
func (t Template) deadline(taskDate string, now time.Time) time.Time {
	if t.DeadlineOffset != nil {
		return now.Add(*t.DeadlineOffset)
	}
	if t.DeadlineLocal == "" {
		return time.Time{}
	}
	deadline, err := time.ParseInLocation("2006-01-02 15:04", taskDate+" "+t.DeadlineLocal, reminder.LocalLocation(t.Timezone))
	if err != nil {
		return time.Time{}
	}
	return deadline
}
