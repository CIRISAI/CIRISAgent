-- Migration 005: Add consolidation_locks table for TSDB consolidation coordination
-- Enables multiple instances to coordinate consolidation work without conflicting
-- Uses conditional UPDATE pattern for lock acquisition (like distributed job queue)

CREATE TABLE IF NOT EXISTS consolidation_locks (
    lock_key TEXT PRIMARY KEY,           -- e.g., "basic:2025-10-22T06:00:00+00:00"
    locked_by TEXT,                      -- Hostname or instance ID holding the lock
    locked_at TIMESTAMP,                 -- Timestamp when lock was acquired
    lock_timeout_seconds INTEGER DEFAULT 300  -- Auto-expire locks after 5 minutes
);

-- Index for finding expired locks
CREATE INDEX IF NOT EXISTS idx_consolidation_locks_expiry
    ON consolidation_locks(locked_at);

-- Note: Lock acquisition uses conditional UPDATE:
--   UPDATE consolidation_locks
--   SET locked_by = $1, locked_at = $2
--   WHERE lock_key = $3 AND (locked_by IS NULL OR locked_at < $4)
--
-- If rowcount > 0, lock was acquired
-- If rowcount = 0, lock is held by another instance
