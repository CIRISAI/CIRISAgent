-- Migration 009: Add ticket status handling for multi-occurrence coordination
-- Purpose: Support comprehensive ticket lifecycle with atomic claiming
-- Date: 2025-11-07

-- Disable foreign key constraints temporarily for table recreation
PRAGMA foreign_keys=OFF;

-- Begin transaction for atomic table recreation
BEGIN TRANSACTION;

--
-- Changes:
-- 1. Add agent_occurrence_id column for multi-occurrence coordination
-- 2. Expand status CHECK constraint to support full lifecycle
--
-- New Status Values:
-- - assigned: Ticket claimed by specific occurrence
-- - blocked: Ticket requires external intervention (stops task generation)
-- - deferred: Ticket postponed to future time or awaiting human response
--
-- Architecture:
-- - PENDING tickets use agent_occurrence_id="__shared__" for atomic claiming
-- - WorkProcessor atomically claims PENDING → ASSIGNED with occurrence_id
-- - BLOCKED/DEFERRED tickets do not generate new tasks until state changes
-- - COMPLETED/FAILED tickets are terminal states

-- Step 1: Create new tickets table with expanded status constraint and agent_occurrence_id
-- SQLite doesn't support modifying CHECK constraints, so we recreate the table
CREATE TABLE IF NOT EXISTS tickets_new (
    ticket_id TEXT PRIMARY KEY,
    sop TEXT NOT NULL,
    ticket_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN (
        'pending',      -- Created, awaiting assignment
        'assigned',     -- Claimed by occurrence, not yet started
        'in_progress',  -- Actively being processed
        'blocked',      -- Needs external input (stops task generation)
        'deferred',     -- Postponed to future time (stops task generation)
        'completed',    -- Successfully finished (terminal)
        'cancelled',    -- User/admin cancelled (terminal)
        'failed'        -- Processing failed (terminal)
    )),
    priority INTEGER NOT NULL DEFAULT 5 CHECK(priority BETWEEN 1 AND 10),

    -- Contact & identification
    email TEXT NOT NULL,
    user_identifier TEXT,

    -- Lifecycle timestamps
    submitted_at TEXT NOT NULL,
    deadline TEXT,
    last_updated TEXT NOT NULL,
    completed_at TEXT,

    -- Workflow state
    metadata TEXT NOT NULL DEFAULT '{}',
    notes TEXT,

    -- Tracking
    automated INTEGER NOT NULL DEFAULT 0,
    correlation_id TEXT,
    agent_occurrence_id TEXT NOT NULL DEFAULT '__shared__',

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Step 2: Copy data from old table to new table, adding agent_occurrence_id='__shared__'
INSERT INTO tickets_new SELECT
    ticket_id,
    sop,
    ticket_type,
    status,
    priority,
    email,
    user_identifier,
    submitted_at,
    deadline,
    last_updated,
    completed_at,
    metadata,
    notes,
    automated,
    correlation_id,
    '__shared__' as agent_occurrence_id,  -- Default to __shared__ for existing tickets
    created_at
FROM tickets;

-- Step 3: Drop the view that depends on thoughts table (will be recreated later)
DROP VIEW IF EXISTS active_scheduled_tasks;

-- Step 4: Drop old table and rename new table
DROP TABLE tickets;
ALTER TABLE tickets_new RENAME TO tickets;

-- Step 5: Recreate all indexes
CREATE INDEX IF NOT EXISTS idx_tickets_sop ON tickets(sop);
CREATE INDEX IF NOT EXISTS idx_tickets_type ON tickets(ticket_type);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_tickets_email ON tickets(email);
CREATE INDEX IF NOT EXISTS idx_tickets_user_identifier ON tickets(user_identifier);
CREATE INDEX IF NOT EXISTS idx_tickets_submitted_at ON tickets(submitted_at);
CREATE INDEX IF NOT EXISTS idx_tickets_deadline ON tickets(deadline);
CREATE INDEX IF NOT EXISTS idx_tickets_correlation_id ON tickets(correlation_id);

-- Composite indexes for common queries
CREATE INDEX IF NOT EXISTS idx_tickets_status_submitted ON tickets(status, submitted_at);
CREATE INDEX IF NOT EXISTS idx_tickets_sop_status ON tickets(sop, status);
CREATE INDEX IF NOT EXISTS idx_tickets_type_status ON tickets(ticket_type, status);

-- Step 6: Add new index for multi-occurrence coordination
CREATE INDEX IF NOT EXISTS idx_tickets_occurrence_status ON tickets(agent_occurrence_id, status);

-- Step 7: Recreate the view with correct column reference (fixing bug from migration 001)
CREATE VIEW IF NOT EXISTS active_scheduled_tasks AS
SELECT
    st.*,
    t.content as thought_content,
    t.thought_id as associated_thought_id
FROM scheduled_tasks st
LEFT JOIN thoughts t ON st.origin_thought_id = t.thought_id
WHERE st.status IN ('PENDING', 'ACTIVE')
  AND (st.next_trigger_at IS NULL OR st.next_trigger_at <= datetime('now', '+5 minutes'))
ORDER BY st.next_trigger_at ASC;

-- Commit transaction
COMMIT;

-- Re-enable foreign key constraints
PRAGMA foreign_keys=ON;
