CREATE TABLE reminder_event_v3 (
    event_id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    schema_version TEXT NOT NULL DEFAULT 'v1',
    source TEXT NOT NULL DEFAULT 'reminder-service',
    decision_id TEXT,
    user_id TEXT NOT NULL,
    task_date TEXT NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'UTC',
    event_time TEXT NOT NULL,
    strategy_version TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    experiment_group TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL,
    FOREIGN KEY (decision_id) REFERENCES reminder_decision(id)
);

INSERT INTO reminder_event_v3 (
    event_id, event_name, schema_version, source, decision_id, user_id,
    task_date, timezone, event_time, strategy_version, channel,
    experiment_group, payload
)
SELECT event_id, event_name, schema_version, source, decision_id, user_id,
       task_date, timezone, event_time, strategy_version, channel,
       experiment_group, payload
FROM reminder_event;

DROP TABLE reminder_event;
ALTER TABLE reminder_event_v3 RENAME TO reminder_event;
CREATE INDEX IF NOT EXISTS idx_reminder_event_decision
    ON reminder_event(decision_id);
