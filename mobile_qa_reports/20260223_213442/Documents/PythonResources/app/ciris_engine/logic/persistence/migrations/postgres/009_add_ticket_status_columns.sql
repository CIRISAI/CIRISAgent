-- Migration 009: Add ticket status handling for multi-occurrence coordination
-- Purpose: Support comprehensive ticket lifecycle with atomic claiming
-- Date: 2025-11-07
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

-- Step 1: Add agent_occurrence_id column with default '__shared__'
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS agent_occurrence_id TEXT NOT NULL DEFAULT '__shared__';

-- Step 2: Drop old status CHECK constraint
ALTER TABLE tickets DROP CONSTRAINT IF EXISTS tickets_status_check;

-- Step 3: Add new status CHECK constraint with expanded values
ALTER TABLE tickets ADD CONSTRAINT tickets_status_check CHECK(status IN (
    'pending',      -- Created, awaiting assignment
    'assigned',     -- Claimed by occurrence, not yet started
    'in_progress',  -- Actively being processed
    'blocked',      -- Needs external input (stops task generation)
    'deferred',     -- Postponed to future time (stops task generation)
    'completed',    -- Successfully finished (terminal)
    'cancelled',    -- User/admin cancelled (terminal)
    'failed'        -- Processing failed (terminal)
));

-- Step 4: Create new index for multi-occurrence coordination
CREATE INDEX IF NOT EXISTS idx_tickets_occurrence_status ON tickets(agent_occurrence_id, status);
