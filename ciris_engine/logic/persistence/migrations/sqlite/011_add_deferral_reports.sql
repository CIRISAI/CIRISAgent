-- Migration 011: Add deferral_reports table
-- Required for WA deferral tracking and resolution

CREATE TABLE IF NOT EXISTS deferral_reports (
    message_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    thought_id TEXT NOT NULL,
    package_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deferral_reports_task ON deferral_reports(task_id);
CREATE INDEX IF NOT EXISTS idx_deferral_reports_thought ON deferral_reports(thought_id);
