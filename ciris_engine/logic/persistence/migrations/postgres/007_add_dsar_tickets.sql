-- Migration 007: Add DSAR Tickets Table
-- Purpose: Replace in-memory dict with persistent storage for GDPR compliance
-- Impact: DSAR tickets survive server restarts, meeting 30-day response requirement

CREATE TABLE IF NOT EXISTS dsar_tickets (
    ticket_id TEXT PRIMARY KEY,
    request_type TEXT NOT NULL CHECK(request_type IN ('access', 'delete', 'export', 'correct')),
    email TEXT NOT NULL,
    user_identifier TEXT,
    details TEXT,
    urgent BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL CHECK(status IN ('pending_review', 'in_progress', 'completed', 'rejected')),
    submitted_at TIMESTAMP NOT NULL,
    estimated_completion TIMESTAMP NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    notes TEXT,
    automated BOOLEAN NOT NULL DEFAULT FALSE,
    access_package_json TEXT,  -- JSON serialized DSARAccessPackage
    export_package_json TEXT,  -- JSON serialized DSARExportPackage
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Index for status queries (admin filtering by status)
CREATE INDEX IF NOT EXISTS idx_dsar_tickets_status ON dsar_tickets(status);

-- Index for email lookups (user checking their requests)
CREATE INDEX IF NOT EXISTS idx_dsar_tickets_email ON dsar_tickets(email);

-- Index for user_identifier lookups (data deletion tracking)
CREATE INDEX IF NOT EXISTS idx_dsar_tickets_user_identifier ON dsar_tickets(user_identifier);

-- Index for request type queries (metrics by type)
CREATE INDEX IF NOT EXISTS idx_dsar_tickets_request_type ON dsar_tickets(request_type);

-- Index for timestamp queries (30-day response compliance)
CREATE INDEX IF NOT EXISTS idx_dsar_tickets_submitted_at ON dsar_tickets(submitted_at);

-- Composite index for common admin query (status + submitted date)
CREATE INDEX IF NOT EXISTS idx_dsar_tickets_status_submitted ON dsar_tickets(status, submitted_at);
