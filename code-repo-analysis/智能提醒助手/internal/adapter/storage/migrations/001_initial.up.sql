CREATE TABLE IF NOT EXISTS reminder_decision (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    task_date TEXT NOT NULL,
    should_remind INTEGER NOT NULL CHECK (should_remind IN (0, 1)),
    scheduled_at TEXT,
    channel TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    user_segment TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (user_id, task_date, strategy_version)
);

CREATE TABLE IF NOT EXISTS reminder_schedule (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    task_date TEXT NOT NULL,
    schedule_version INTEGER NOT NULL,
    channel TEXT NOT NULL,
    schedule_type TEXT NOT NULL,
    scheduled_at TEXT NOT NULL,
    status TEXT NOT NULL,
    lease_until TEXT,
    attempt_no INTEGER NOT NULL,
    cancel_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (decision_id, schedule_version),
    FOREIGN KEY (decision_id) REFERENCES reminder_decision(id)
);

CREATE TABLE IF NOT EXISTS reminder_delivery (
    id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    attempt_no INTEGER NOT NULL,
    status TEXT NOT NULL,
    provider_code TEXT,
    error_code TEXT,
    sent_at TEXT,
    delivered_at TEXT,
    opened_at TEXT,
    FOREIGN KEY (decision_id) REFERENCES reminder_decision(id),
    FOREIGN KEY (schedule_id) REFERENCES reminder_schedule(id)
);

CREATE TABLE IF NOT EXISTS reminder_event (
    event_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    task_date TEXT NOT NULL,
    event_time TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    payload TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES reminder_decision(id)
);

CREATE INDEX IF NOT EXISTS idx_reminder_schedule_due
    ON reminder_schedule(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_reminder_schedule_user_date
    ON reminder_schedule(user_id, task_date, channel);
CREATE INDEX IF NOT EXISTS idx_reminder_delivery_decision
    ON reminder_delivery(decision_id);
CREATE INDEX IF NOT EXISTS idx_reminder_event_decision
    ON reminder_event(decision_id);
