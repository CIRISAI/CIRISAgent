-- Migration 008: Rename dsar_tickets to tickets and add SOP architecture
-- Purpose: Make tickets universal with DSAR as always-present default capability
-- Impact: All agents have DSAR SOPs, agents can add custom ticket SOPs via templates
--
-- Architecture Decision:
-- - DSAR is universal (GDPR compliance required for all agents)
-- - Other ticket types (appointments, incidents) are agent-specific
-- - SOP column links to agent template ticket configuration
-- - Metadata JSON stores stage progress and results

-- Step 1: Create new tickets table with SOP architecture
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    sop TEXT NOT NULL,  -- Standard Operating Procedure (e.g., "DSAR_ACCESS", "APPOINTMENT_SCHEDULE")
    ticket_type TEXT NOT NULL,  -- Category (e.g., "dsar", "appointment", "incident")
    status TEXT NOT NULL CHECK(status IN ('pending', 'in_progress', 'completed', 'cancelled', 'failed')),
    priority INTEGER NOT NULL DEFAULT 5 CHECK(priority BETWEEN 1 AND 10),  -- 1=lowest, 10=urgent

    -- Contact & identification
    email TEXT NOT NULL,
    user_identifier TEXT,

    -- Lifecycle timestamps
    submitted_at TIMESTAMP NOT NULL,
    deadline TIMESTAMP,  -- Calculated from SOP config
    last_updated TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,

    -- Workflow state
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,  -- Stage progress, results, SOP-specific data
    notes TEXT,

    -- Tracking
    automated BOOLEAN NOT NULL DEFAULT FALSE,
    correlation_id TEXT,  -- Links to tasks/thoughts processing this ticket

    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Step 2: Migrate existing dsar_tickets to new tickets table
INSERT INTO tickets (
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
    created_at
)
SELECT
    ticket_id,
    -- Map request_type to SOP
    CASE request_type
        WHEN 'access' THEN 'DSAR_ACCESS'
        WHEN 'delete' THEN 'DSAR_DELETE'
        WHEN 'export' THEN 'DSAR_EXPORT'
        WHEN 'correct' THEN 'DSAR_RECTIFY'
        ELSE 'DSAR_ACCESS'  -- fallback
    END as sop,
    'dsar' as ticket_type,
    -- Map old status to new status
    CASE status
        WHEN 'pending_review' THEN 'pending'
        WHEN 'in_progress' THEN 'in_progress'
        WHEN 'completed' THEN 'completed'
        WHEN 'rejected' THEN 'cancelled'
        ELSE 'pending'
    END as status,
    -- Map urgent flag to priority
    CASE urgent
        WHEN TRUE THEN 9  -- urgent = priority 9
        ELSE 5  -- normal = priority 5
    END as priority,
    email,
    user_identifier,
    submitted_at,
    estimated_completion as deadline,
    last_updated,
    CASE
        WHEN status = 'completed' THEN last_updated
        ELSE NULL
    END as completed_at,
    -- Build metadata JSONB from legacy fields
    jsonb_build_object(
        'legacy_request_type', request_type,
        'legacy_details', COALESCE(details, ''),
        'access_package', COALESCE(access_package_json::jsonb, 'null'::jsonb),
        'export_package', COALESCE(export_package_json::jsonb, 'null'::jsonb),
        'stages', '{}'::jsonb
    ) as metadata,
    notes,
    automated,
    created_at
FROM dsar_tickets;

-- Step 3: Drop old dsar_tickets table
DROP TABLE dsar_tickets;

-- Step 4: Create indexes for new tickets table
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

-- GIN index for JSONB metadata queries (PostgreSQL specific)
CREATE INDEX IF NOT EXISTS idx_tickets_metadata_gin ON tickets USING GIN (metadata);
