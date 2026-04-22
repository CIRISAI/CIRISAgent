-- Migration 004: Add agent_occurrence_id for multi-instance deployment support
-- Enables running multiple API-only CIRIS agent instances against the same SQLite database
-- Each runtime instance processes only its own work while sharing a single agent identity

-- Add agent_occurrence_id to tasks table
ALTER TABLE tasks ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';

-- Add agent_occurrence_id to thoughts table
ALTER TABLE thoughts ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';

-- Add agent_occurrence_id to scheduled_tasks table
ALTER TABLE scheduled_tasks ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';

-- Add agent_occurrence_id to service_correlations for per-instance telemetry
ALTER TABLE service_correlations ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';

-- Create composite indexes for efficient occurrence-scoped queries

-- Tasks indexes
CREATE INDEX IF NOT EXISTS idx_tasks_occurrence_status
    ON tasks(agent_occurrence_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_tasks_occurrence_channel
    ON tasks(agent_occurrence_id, channel_id, status);

-- Thoughts indexes
CREATE INDEX IF NOT EXISTS idx_thoughts_occurrence_status
    ON thoughts(agent_occurrence_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_thoughts_occurrence_task
    ON thoughts(agent_occurrence_id, source_task_id);

-- Scheduled tasks index
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_occurrence
    ON scheduled_tasks(agent_occurrence_id, status, next_trigger_at);

-- Service correlations index
CREATE INDEX IF NOT EXISTS idx_correlations_occurrence
    ON service_correlations(agent_occurrence_id);

-- Note: Existing rows automatically get 'default' value via DEFAULT clause
-- Note: graph_nodes, graph_edges, audit_log, and wa_cert remain global (no occurrence_id)
--       - Memory is shared across all occurrences (single agent identity/knowledge)
--       - Audit trail is global for complete history
--       - WA certificates are shared (single agent identity)
