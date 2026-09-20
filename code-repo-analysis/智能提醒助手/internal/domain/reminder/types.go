package reminder

import "time"

// Trigger identifies the event that requested a reminder evaluation.
type Trigger string

const (
	TriggerDaily   Trigger = "DAILY"
	TriggerAppOpen Trigger = "APP_OPENED"
)

type Channel string

const (
	ChannelPush Channel = "push"
)

type Segment string

const (
	SegmentPassive    Segment = "PASSIVE"
	SegmentSelfDriven Segment = "SELF_DRIVEN"
	SegmentInactive   Segment = "INACTIVE"
	SegmentReturning  Segment = "RETURNING"
)

type ReasonCode string

const (
	ReasonEligible            ReasonCode = "ELIGIBLE"
	ReasonNoTask              ReasonCode = "NO_TASK"
	ReasonTaskCompleted       ReasonCode = "TASK_COMPLETED"
	ReasonTaskExpired         ReasonCode = "TASK_EXPIRED"
	ReasonReminderDisabled    ReasonCode = "REMINDER_DISABLED"
	ReasonDailyCapReached     ReasonCode = "DAILY_CAP_REACHED"
	ReasonNoAvailableChannel  ReasonCode = "NO_AVAILABLE_CHANNEL"
	ReasonUserInactive        ReasonCode = "USER_INACTIVE"
	ReasonInsufficientHistory ReasonCode = "INSUFFICIENT_HISTORY"
	ReasonReturningFirstDay   ReasonCode = "RETURNING_FIRST_DAY"
	ReasonDefaultWindow       ReasonCode = "DEFAULT_WINDOW"
)

type DecisionStatus string

const (
	DecisionScheduled DecisionStatus = "SCHEDULED"
	DecisionCancelled DecisionStatus = "CANCELLED"
)

type ScheduleStatus string

const (
	ScheduleScheduled ScheduleStatus = "SCHEDULED"
)

type ScheduleType string

const (
	ScheduleInitial ScheduleType = "INITIAL"
)

// DailyTask is the minimum task snapshot needed by FR-001.
type DailyTask struct {
	UserID           string
	TaskDate         string
	RequiredCount    int
	CompletedCount   int
	EstimatedMinutes int
	Deadline         time.Time
}

func (t DailyTask) HasTask() bool {
	return t.RequiredCount > 0
}

func (t DailyTask) IsComplete() bool {
	return t.HasTask() && t.CompletedCount >= t.RequiredCount
}

type ReminderPreference struct {
	Enabled      bool
	PushEnabled  bool
	Timezone     *time.Location
	DailyPushCap int
}

type BehaviorSummary struct {
	InactiveDays                 int
	DaysSinceLastOpen            *int
	CompleteDays7D               int
	ReminderAttributedComplete7D int
	HistoryDaysAvailable         int
}

type DailyUsage struct {
	PushSentCount int
}

type Decision struct {
	ID              string
	UserID          string
	TaskDate        string
	ShouldRemind    bool
	ScheduledAt     *time.Time
	Channel         Channel
	ReasonCode      ReasonCode
	StrategyVersion string
	UserSegment     Segment
	DedupeKey       string
	Status          DecisionStatus
	Version         int
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

type Schedule struct {
	ID              string
	DecisionID      string
	UserID          string
	TaskDate        string
	ScheduleVersion int
	Channel         Channel
	ScheduleType    ScheduleType
	ScheduledAt     time.Time
	Status          ScheduleStatus
	AttemptNo       int
	CreatedAt       time.Time
	UpdatedAt       time.Time
}

type ReminderEvent struct {
	EventID         string
	EventName       string
	DecisionID      string
	UserID          string
	TaskDate        string
	EventTime       time.Time
	StrategyVersion string
	Payload         map[string]any
}

type EvaluationInput struct {
	Now             time.Time
	Trigger         Trigger
	Task            DailyTask
	Preference      ReminderPreference
	Behavior        BehaviorSummary
	Usage           DailyUsage
	StrategyVersion string
}

type EvaluationPlan struct {
	Decision Decision
	Schedule *Schedule
}
