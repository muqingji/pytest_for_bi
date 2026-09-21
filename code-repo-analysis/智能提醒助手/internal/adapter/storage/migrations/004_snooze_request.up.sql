-- 延后提醒（FR-007）的请求幂等记录：技术方案 4.5.1 的 reminder_snooze_request。
-- 唯一键 (request_id, decision_id) 保证重复点击/重试只产生一个 SNOOZE 排程与一条 reminder_snoozed 事件；
-- 与 reminder_schedule 的 (decision_id, schedule_version) 唯一键配合，用于区分
-- 「同一 request_id 重放」（返回 REUSED）与「换 request_id 的第二次入口」（返回 INVALID_REQUEST）。
CREATE TABLE IF NOT EXISTS reminder_snooze_request (
    request_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    schedule_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    task_date TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (request_id, decision_id),
    FOREIGN KEY (decision_id) REFERENCES reminder_decision(id),
    FOREIGN KEY (schedule_id) REFERENCES reminder_schedule(id)
);

CREATE INDEX IF NOT EXISTS idx_reminder_snooze_request_schedule
    ON reminder_snooze_request(schedule_id);
