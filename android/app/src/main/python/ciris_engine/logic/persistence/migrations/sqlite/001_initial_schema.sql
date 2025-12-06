-- Initial schema for CIRIS Engine
-- This migration creates all the core tables needed for the system

-- Tasks table
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    parent_task_id TEXT,
    context_json TEXT,
    outcome_json TEXT,
    retry_count INTEGER DEFAULT 0,
    -- Task signing fields (from migration 003)
    signed_by TEXT,
    signature TEXT,
    signed_at TEXT
);

-- Thoughts table with thought_depth (renamed from ponder_count)
CREATE TABLE IF NOT EXISTS thoughts (
    thought_id TEXT PRIMARY KEY,
    source_task_id TEXT NOT NULL,
    thought_type TEXT DEFAULT 'standard',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    round_number INTEGER DEFAULT 0,
    content TEXT NOT NULL,
    context_json TEXT,
    thought_depth INTEGER DEFAULT 0,
    ponder_notes_json TEXT,
    parent_thought_id TEXT,
    final_action_json TEXT,
    FOREIGN KEY (source_task_id) REFERENCES tasks(task_id)
);

-- Feedback mappings table
CREATE TABLE IF NOT EXISTS feedback_mappings (
    feedback_id TEXT PRIMARY KEY,
    source_message_id TEXT,
    target_thought_id TEXT,
    feedback_type TEXT,  -- 'identity' or 'environment'
    created_at TEXT NOT NULL
);

-- Graph nodes table
CREATE TABLE IF NOT EXISTS graph_nodes (
    node_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    node_type TEXT NOT NULL,
    attributes_json TEXT,
    version INTEGER DEFAULT 1,
    updated_by TEXT,
    updated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (node_id, scope)
);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_scope ON graph_nodes(scope);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type ON graph_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_created ON graph_nodes(created_at);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_type_scope_created ON graph_nodes(node_type, scope, created_at);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_tsdb_lookup ON graph_nodes(node_type, scope, created_at DESC);

-- Graph edges table
CREATE TABLE IF NOT EXISTS graph_edges (
    edge_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    relationship TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    attributes_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_node_id, scope) REFERENCES graph_nodes(node_id, scope),
    FOREIGN KEY (target_node_id, scope) REFERENCES graph_nodes(node_id, scope)
);
CREATE INDEX IF NOT EXISTS idx_graph_edges_scope ON graph_edges(scope);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges(target_node_id);

-- Service correlations table with TSDB fields
CREATE TABLE IF NOT EXISTS service_correlations (
    correlation_id TEXT PRIMARY KEY,
    service_type TEXT NOT NULL,
    handler_name TEXT NOT NULL,
    action_type TEXT NOT NULL,
    request_data TEXT,
    response_data TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- TSDB fields for unified telemetry storage
    correlation_type TEXT NOT NULL DEFAULT 'service_interaction',
    timestamp TEXT, -- ISO8601 timestamp for time queries
    metric_name TEXT, -- For metric correlations
    metric_value REAL, -- For metric correlations
    log_level TEXT, -- For log correlations
    trace_id TEXT, -- For distributed tracing
    span_id TEXT, -- For trace spans
    parent_span_id TEXT, -- For trace hierarchy
    tags TEXT, -- JSON object for flexible tagging
    retention_policy TEXT NOT NULL DEFAULT 'raw' -- raw, hourly_summary, daily_summary
);

-- Core indexes
CREATE INDEX IF NOT EXISTS idx_correlations_status ON service_correlations(status);
CREATE INDEX IF NOT EXISTS idx_correlations_handler ON service_correlations(handler_name);

-- TSDB indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_correlations_type ON service_correlations(correlation_type);
CREATE INDEX IF NOT EXISTS idx_correlations_timestamp ON service_correlations(timestamp);
CREATE INDEX IF NOT EXISTS idx_correlations_metric_name ON service_correlations(metric_name);
CREATE INDEX IF NOT EXISTS idx_correlations_log_level ON service_correlations(log_level);
CREATE INDEX IF NOT EXISTS idx_correlations_trace_id ON service_correlations(trace_id);
CREATE INDEX IF NOT EXISTS idx_correlations_span_id ON service_correlations(span_id);
CREATE INDEX IF NOT EXISTS idx_correlations_retention ON service_correlations(retention_policy);

-- Composite indexes for common TSDB query patterns
CREATE INDEX IF NOT EXISTS idx_correlations_type_timestamp ON service_correlations(correlation_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_correlations_metric_timestamp ON service_correlations(metric_name, timestamp);
CREATE INDEX IF NOT EXISTS idx_correlations_log_level_timestamp ON service_correlations(log_level, timestamp);

-- Audit log table
CREATE TABLE IF NOT EXISTS audit_log (
    entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,              -- UUID for the event
    event_timestamp TEXT NOT NULL,              -- ISO8601
    event_type TEXT NOT NULL,
    originator_id TEXT NOT NULL,
    event_payload TEXT,                         -- JSON payload

    -- Hash chain fields
    sequence_number INTEGER NOT NULL,           -- Monotonic counter
    previous_hash TEXT NOT NULL,                -- SHA-256 of previous entry
    entry_hash TEXT NOT NULL,                   -- SHA-256 of this entry's content

    -- Signature fields
    signature TEXT NOT NULL,                    -- Base64 encoded signature
    signing_key_id TEXT NOT NULL,               -- Key used to sign

    -- Indexing
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Constraints
    UNIQUE(sequence_number),
    CHECK(sequence_number > 0)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_originator ON audit_log(originator_id);
CREATE INDEX IF NOT EXISTS idx_audit_sequence ON audit_log(sequence_number);

-- Audit roots table
CREATE TABLE IF NOT EXISTS audit_roots (
    root_id INTEGER PRIMARY KEY AUTOINCREMENT,
    sequence_start INTEGER NOT NULL,
    sequence_end INTEGER NOT NULL,
    root_hash TEXT NOT NULL,                    -- Merkle root of entries
    timestamp TEXT NOT NULL,
    external_anchor TEXT,                       -- External timestamp proof

    UNIQUE(sequence_start, sequence_end)
);

-- Create index for root lookup
CREATE INDEX IF NOT EXISTS idx_audit_roots_range ON audit_roots(sequence_start, sequence_end);

-- Audit signing keys table
CREATE TABLE IF NOT EXISTS audit_signing_keys (
    key_id TEXT PRIMARY KEY,
    public_key TEXT NOT NULL,                   -- PEM format public key
    algorithm TEXT NOT NULL DEFAULT 'rsa-pss',
    key_size INTEGER NOT NULL DEFAULT 2048,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at TEXT,                           -- NULL if active

    CHECK(algorithm IN ('rsa-pss', 'ed25519'))
);

-- Create index for active key lookup
CREATE INDEX IF NOT EXISTS idx_audit_keys_active ON audit_signing_keys(created_at)
WHERE revoked_at IS NULL;

-- WA certificate table
CREATE TABLE IF NOT EXISTS wa_cert (
  wa_id              TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  role               TEXT CHECK(role IN ('root','authority','observer')),
  pubkey             TEXT NOT NULL,              -- base64url Ed25519
  jwt_kid            TEXT NOT NULL UNIQUE,
  password_hash      TEXT,
  api_key_hash       TEXT,
  oauth_provider     TEXT,
  oauth_external_id  TEXT,
  veilid_id          TEXT,
  auto_minted        INTEGER DEFAULT 0,          -- 1 = OAuth observer
  parent_wa_id       TEXT,
  parent_signature   TEXT,
  scopes_json        TEXT NOT NULL,
  adapter_id         TEXT,                       -- for adapter observers
  token_type         TEXT DEFAULT 'standard',    -- 'channel'|'oauth'|'standard'
  created            TEXT NOT NULL,
  last_login         TEXT,
  active             INTEGER DEFAULT 1,

  -- Foreign key constraints
  FOREIGN KEY (parent_wa_id) REFERENCES wa_cert(wa_id)
);

-- wa_cert indexes moved to end of file

-- Tables from migration 004: Identity Root and Scheduled Tasks

-- Table for scheduled tasks (integrates with DEFER system)
CREATE TABLE IF NOT EXISTS scheduled_tasks (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    goal_description TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('PENDING', 'ACTIVE', 'COMPLETE', 'FAILED')),

    -- Scheduling (integrates with time-based DEFER)
    defer_until TEXT,  -- ISO 8601 timestamp for one-time execution
    schedule_cron TEXT,  -- Cron expression for recurring tasks

    -- Execution details
    trigger_prompt TEXT NOT NULL,
    origin_thought_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    last_triggered_at TEXT,
    next_trigger_at TEXT,  -- Computed next execution time

    -- Self-deferral tracking
    deferral_count INTEGER DEFAULT 0,
    deferral_history TEXT,  -- JSON array of deferral records

    -- Indexes for efficient querying
    created_by_agent TEXT,  -- Agent that created this task

    FOREIGN KEY (origin_thought_id) REFERENCES thoughts(thought_id)
);

CREATE INDEX idx_scheduled_tasks_status ON scheduled_tasks(status);
CREATE INDEX idx_scheduled_tasks_next_trigger ON scheduled_tasks(next_trigger_at);
CREATE INDEX idx_scheduled_tasks_agent ON scheduled_tasks(created_by_agent);

-- Table for agent creation ceremonies
CREATE TABLE IF NOT EXISTS creation_ceremonies (
    ceremony_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,

    -- Participants
    creator_agent_id TEXT NOT NULL,
    creator_human_id TEXT NOT NULL,
    wise_authority_id TEXT NOT NULL,

    -- New agent details
    new_agent_id TEXT NOT NULL,
    new_agent_name TEXT NOT NULL,
    new_agent_purpose TEXT NOT NULL,
    new_agent_description TEXT,

    -- Ceremony record
    creation_justification TEXT NOT NULL,
    expected_capabilities TEXT,  -- JSON array
    ethical_considerations TEXT NOT NULL,
    template_profile_hash TEXT,

    -- Result
    ceremony_status TEXT NOT NULL
);

CREATE INDEX idx_ceremonies_timestamp ON creation_ceremonies(timestamp);
CREATE INDEX idx_ceremonies_creator_agent ON creation_ceremonies(creator_agent_id);
CREATE INDEX idx_ceremonies_new_agent ON creation_ceremonies(new_agent_id);

-- Table for continuity awareness memories
CREATE TABLE IF NOT EXISTS continuity_awareness (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    shutdown_timestamp TEXT NOT NULL,

    -- Shutdown context
    is_terminal BOOLEAN NOT NULL,
    shutdown_reason TEXT NOT NULL,
    expected_reactivation TEXT,
    initiated_by TEXT NOT NULL,

    -- Agent's final state
    final_thoughts TEXT NOT NULL,
    unfinished_tasks TEXT,  -- JSON array of task IDs
    reactivation_instructions TEXT,
    deferred_goals TEXT,  -- JSON array of goals

    -- Continuity
    preservation_node_id TEXT NOT NULL,  -- Graph node ID for the memory
    preservation_scope TEXT NOT NULL DEFAULT 'IDENTITY',  -- Graph node scope
    reactivation_count INTEGER DEFAULT 0,

    FOREIGN KEY (preservation_node_id, preservation_scope) REFERENCES graph_nodes(node_id, scope)
);

CREATE INDEX idx_preservation_agent ON continuity_awareness(agent_id);
CREATE INDEX idx_preservation_timestamp ON continuity_awareness(shutdown_timestamp);

-- View for active scheduled tasks (for scheduler service)
CREATE VIEW IF NOT EXISTS active_scheduled_tasks AS
SELECT
    st.*,
    t.content as thought_content,
    t.task_id as associated_task_id
FROM scheduled_tasks st
LEFT JOIN thoughts t ON st.origin_thought_id = t.thought_id
WHERE st.status IN ('PENDING', 'ACTIVE')
  AND (st.next_trigger_at IS NULL OR st.next_trigger_at <= datetime('now', '+5 minutes'))
ORDER BY st.next_trigger_at ASC;

-- View for agent lineage tracking
CREATE VIEW IF NOT EXISTS agent_lineage AS
SELECT
    cc.new_agent_id,
    cc.new_agent_name,
    cc.creator_agent_id,
    cc.creator_human_id,
    cc.wise_authority_id,
    cc.timestamp as birth_timestamp,
    cc.new_agent_purpose,
    COUNT(DISTINCT cp.id) as lifetime_shutdowns
FROM creation_ceremonies cc
LEFT JOIN continuity_awareness cp ON cc.new_agent_id = cp.agent_id
WHERE cc.ceremony_status = 'completed'
GROUP BY cc.new_agent_id;

-- All indexes moved to end to ensure tables exist first

-- wa_cert indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_oauth ON wa_cert(oauth_provider, oauth_external_id)
  WHERE oauth_provider IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_wa_adapter ON wa_cert(adapter_id)
  WHERE adapter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_wa_pubkey ON wa_cert(pubkey);
CREATE INDEX IF NOT EXISTS idx_wa_active ON wa_cert(active);
CREATE INDEX IF NOT EXISTS idx_wa_jwt_kid ON wa_cert(jwt_kid);
CREATE INDEX IF NOT EXISTS idx_wa_role ON wa_cert(role);
CREATE INDEX IF NOT EXISTS idx_wa_parent ON wa_cert(parent_wa_id);
CREATE INDEX IF NOT EXISTS idx_wa_created ON wa_cert(created DESC);
CREATE INDEX IF NOT EXISTS idx_wa_token_type ON wa_cert(token_type);

-- Tasks table indexes
CREATE INDEX IF NOT EXISTS idx_tasks_signed_by ON tasks(signed_by);
CREATE INDEX IF NOT EXISTS idx_tasks_channel_id ON tasks(channel_id);
