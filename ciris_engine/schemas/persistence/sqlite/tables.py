"""
Database Table Schemas v1 - SQLite table definitions for CIRIS Agent

Provides SQL DDL for all database tables used by the agent.
"""

# Tasks table for tracking agent tasks
# Note: images_json column is added by migration 010_add_images_to_tasks.sql
TASKS_TABLE_V1 = """
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
"""

# Thoughts table for agent reasoning
THOUGHTS_TABLE_V1 = """
CREATE TABLE IF NOT EXISTS thoughts (
    thought_id TEXT PRIMARY KEY,
    source_task_id TEXT NOT NULL,
    channel_id TEXT,
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
"""

# Feedback mappings for tracking responses
FEEDBACK_MAPPINGS_TABLE_V1 = """
CREATE TABLE IF NOT EXISTS feedback_mappings (
    feedback_id TEXT PRIMARY KEY,
    source_message_id TEXT,
    target_thought_id TEXT,
    feedback_type TEXT,  -- 'identity' or 'environment'
    created_at TEXT NOT NULL
);
"""

# Graph nodes for memory storage
GRAPH_NODES_TABLE_V1 = """
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
"""

# Graph edges for relationships
GRAPH_EDGES_TABLE_V1 = """
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
"""

# Service correlations with TSDB capabilities
SERVICE_CORRELATIONS_TABLE_V1 = """
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
"""

# Audit log with hash chain and signatures
AUDIT_LOG_TABLE_V1 = """
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
"""

# Audit roots for Merkle tree verification
AUDIT_ROOTS_TABLE_V1 = """
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
"""

# Audit signing keys
AUDIT_SIGNING_KEYS_TABLE_V1 = """
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
"""

# WA certificate table
WA_CERT_TABLE_V1 = """
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
  oauth_links_json   TEXT,
  veilid_id          TEXT,
  auto_minted        INTEGER DEFAULT 0,          -- 1 = OAuth observer
  parent_wa_id       TEXT,
  parent_signature   TEXT,
  scopes_json        TEXT NOT NULL,
  custom_permissions_json TEXT,                  -- Additional permissions beyond scopes
  adapter_id         TEXT,                       -- for adapter observers
  adapter_name       TEXT,                       -- Name of the adapter (Discord, CLI, etc)
  adapter_metadata_json TEXT,                    -- Platform-specific metadata
  token_type         TEXT DEFAULT 'standard',    -- 'channel'|'oauth'|'standard'
  created            TEXT NOT NULL,
  last_login         TEXT,
  active             INTEGER DEFAULT 1,

  -- Foreign key constraints
  FOREIGN KEY (parent_wa_id) REFERENCES wa_cert(wa_id)
);

-- Performance and constraint indexes
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
"""

# Deferral reports table for WA deferral tracking
DEFERRAL_REPORTS_TABLE_V1 = """
CREATE TABLE IF NOT EXISTS deferral_reports (
    message_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    thought_id TEXT NOT NULL,
    package_json TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_deferral_reports_task ON deferral_reports(task_id);
CREATE INDEX IF NOT EXISTS idx_deferral_reports_thought ON deferral_reports(thought_id);
"""

# All table definitions
ALL_TABLES = [
    TASKS_TABLE_V1,
    THOUGHTS_TABLE_V1,
    FEEDBACK_MAPPINGS_TABLE_V1,
    GRAPH_NODES_TABLE_V1,
    GRAPH_EDGES_TABLE_V1,
    SERVICE_CORRELATIONS_TABLE_V1,
    AUDIT_LOG_TABLE_V1,
    AUDIT_ROOTS_TABLE_V1,
    AUDIT_SIGNING_KEYS_TABLE_V1,
    WA_CERT_TABLE_V1,
    DEFERRAL_REPORTS_TABLE_V1,
]

__all__ = [
    "TASKS_TABLE_V1",
    "THOUGHTS_TABLE_V1",
    "FEEDBACK_MAPPINGS_TABLE_V1",
    "GRAPH_NODES_TABLE_V1",
    "GRAPH_EDGES_TABLE_V1",
    "SERVICE_CORRELATIONS_TABLE_V1",
    "AUDIT_LOG_TABLE_V1",
    "AUDIT_ROOTS_TABLE_V1",
    "AUDIT_SIGNING_KEYS_TABLE_V1",
    "WA_CERT_TABLE_V1",
    "DEFERRAL_REPORTS_TABLE_V1",
    "ALL_TABLES",
]
