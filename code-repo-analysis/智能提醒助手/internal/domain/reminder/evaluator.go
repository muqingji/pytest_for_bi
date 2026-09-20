package reminder

import "time"

// Evaluate applies the PRD rule order. It has no external side effects and is
// therefore reusable from daily evaluation and AppOpened handling.
func Evaluate(input EvaluationInput) EvaluationPlan {
	now := input.Now
	strategy := input.StrategyVersion
	if strategy == "" {
		strategy = "v1"
	}
	base := Decision{
		UserID:          input.Task.UserID,
		TaskDate:        input.Task.TaskDate,
		ShouldRemind:    false,
		StrategyVersion: strategy,
		DedupeKey:       input.Task.UserID + "|" + input.Task.TaskDate + "|" + strategy,
		Status:          DecisionCancelled,
		Version:         1,
		CreatedAt:       now,
		UpdatedAt:       now,
	}

	if !input.Task.HasTask() {
		return rejected(base, ReasonNoTask, SegmentPassive)
	}
	if input.Task.IsComplete() {
		return rejected(base, ReasonTaskCompleted, SegmentSelfDriven)
	}
	if !input.Task.Deadline.IsZero() && now.After(input.Task.Deadline) {
		return rejected(base, ReasonTaskExpired, SegmentPassive)
	}
	if !input.Preference.Enabled {
		return rejected(base, ReasonReminderDisabled, SegmentPassive)
	}

	segment := SegmentPassive
	reason := ReasonEligible
	if input.Behavior.HistoryDaysAvailable < 3 {
		reason = ReasonInsufficientHistory
	} else if input.Behavior.InactiveDays >= 3 {
		return rejected(base, ReasonUserInactive, SegmentInactive)
	} else if input.Trigger == TriggerAppOpen && input.Behavior.DaysSinceLastOpen != nil && *input.Behavior.DaysSinceLastOpen >= 3 && input.Behavior.InactiveDays == 0 {
		segment = SegmentReturning
		reason = ReasonReturningFirstDay
	} else if input.Behavior.CompleteDays7D >= 5 && input.Behavior.ReminderAttributedComplete7D <= 1 {
		segment = SegmentSelfDriven
	}
	// Returning users are cooled down on the first day. The P1 in-app handoff
	// is outside this slice, so no reminder schedule is created here.
	if segment == SegmentReturning {
		return rejected(base, ReasonReturningFirstDay, segment)
	}

	channel := ChannelPush
	if channel == ChannelPush && !input.Preference.PushEnabled {
		return rejected(base, ReasonNoAvailableChannel, segment)
	}
	if channel == ChannelPush && input.Usage.PushSentCount >= positiveOrDefault(input.Preference.DailyPushCap, 1) {
		return rejected(base, ReasonDailyCapReached, segment)
	}
	scheduledAt := plannedTime(input)
	base.ShouldRemind = true
	base.Status = DecisionScheduled
	base.Channel = channel
	base.ReasonCode = reason
	base.UserSegment = segment
	base.ScheduledAt = &scheduledAt

	return EvaluationPlan{
		Decision: base,
		Schedule: &Schedule{
			UserID:          base.UserID,
			TaskDate:        base.TaskDate,
			ScheduleVersion: 1,
			Channel:         channel,
			ScheduleType:    ScheduleInitial,
			ScheduledAt:     scheduledAt,
			Status:          ScheduleScheduled,
			AttemptNo:       0,
			CreatedAt:       now,
			UpdatedAt:       now,
		},
	}
}

func rejected(decision Decision, reason ReasonCode, segment Segment) EvaluationPlan {
	decision.ReasonCode = reason
	decision.UserSegment = segment
	return EvaluationPlan{Decision: decision}
}

func positiveOrDefault(value, fallback int) int {
	if value > 0 {
		return value
	}
	return fallback
}

func plannedTime(input EvaluationInput) time.Time {
	location := input.Preference.Timezone
	if location == nil {
		location = time.UTC
	}
	localDate, err := time.ParseInLocation("2006-01-02", input.Task.TaskDate, location)
	if err != nil {
		localDate = input.Now.In(location)
	}
	planned := time.Date(localDate.Year(), localDate.Month(), localDate.Day(), 19, 30, 0, 0, location)
	if planned.Before(input.Now) {
		return input.Now.Add(time.Minute)
	}
	return planned
}
