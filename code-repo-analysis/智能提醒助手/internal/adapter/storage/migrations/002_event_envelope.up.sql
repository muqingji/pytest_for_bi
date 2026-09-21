ALTER TABLE reminder_event ADD COLUMN schema_version TEXT NOT NULL DEFAULT 'v1';
ALTER TABLE reminder_event ADD COLUMN source TEXT NOT NULL DEFAULT 'reminder-service';
ALTER TABLE reminder_event ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC';
ALTER TABLE reminder_event ADD COLUMN channel TEXT NOT NULL DEFAULT '';
ALTER TABLE reminder_event ADD COLUMN experiment_group TEXT NOT NULL DEFAULT '';
