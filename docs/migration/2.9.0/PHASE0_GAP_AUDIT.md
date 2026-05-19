# Phase 0 — Persist Substrate Gap Audit

Generated inventory of every raw-SQL touch point in `ciris_engine/` and which persist substrate covers it (or where the gap sits).

**Persist version:** 1.5.19 — exposes **198** public methods on `ciris_persist.Engine`.


## Persist substrate inventory

Methods grouped by prefix. The agent talks to these; everything else is a candidate gap.

### `_misc_*` (2)
```
  maintain
  sign
```

### `aggregate_*` (5)
```
  aggregate_audit_chain
  aggregate_llm_costs
  aggregate_scoring_factors
  aggregate_scoring_factors_batch
  aggregate_scrub_stats
```

### `attach_*` (3)
```
  attach_attestation_pqc_signature
  attach_key_pqc_signature
  attach_revocation_pqc_signature
```

### `audit_*` (5)
```
  audit_canonicalize_for_hash
  audit_canonicalize_for_signing
  audit_list_entries
  audit_record_entry
  audit_verify_chain
```

### `backfill_*` (1)
```
  backfill_v020_trust_rows
```

### `body_*` (1)
```
  body_sha256
```

### `cancel_*` (1)
```
  cancel_outbound
```

### `canonicalize_*` (2)
```
  canonicalize_envelope
  canonicalize_envelope_for_signing
```

### `ceremony_*` (4)
```
  ceremony_get
  ceremony_list
  ceremony_record
  ceremony_update_status
```

### `cirisgraph_*` (7)
```
  cirisgraph_delete_node
  cirisgraph_get_edges_for_node
  cirisgraph_get_node
  cirisgraph_query_nodes
  cirisgraph_traverse_k_hop
  cirisgraph_upsert_edge
  cirisgraph_upsert_node
```

### `cirisnode_*` (15)
```
  cirisnode_cast_vote
  cirisnode_get_credits_ledger
  cirisnode_get_expertise_ledger
  cirisnode_list_contributions
  cirisnode_list_votes
  cirisnode_put_contribution
  cirisnode_put_moderation_event
  cirisnode_put_promotion_attestation
  cirisnode_put_reconsideration_attestation
  cirisnode_put_reconsideration_request
  cirisnode_put_slashing_attestation
  cirisnode_read_vote_weight
  cirisnode_routable_contributors
  cirisnode_update_credits_ledger
  cirisnode_update_expertise_ledger
```

### `claim_*` (1)
```
  claim_pending_outbound
```

### `conscience_*` (1)
```
  conscience_override_rates
```

### `continuity_*` (3)
```
  continuity_get_latest
  continuity_record
  continuity_record_reactivation
```

### `corpus_*` (1)
```
  corpus_shape
```

### `correlation_*` (4)
```
  correlation_get
  correlation_query
  correlation_record
  correlation_update_status
```

### `count_*` (3)
```
  count_identity_changes
  count_overrides
  count_traces
```

### `cross_*` (1)
```
  cross_agent_divergence
```

### `current_*` (1)
```
  current_sth
```

### `debug_*` (1)
```
  debug_canonicalize
```

### `deferral_*` (4)
```
  deferral_get
  deferral_list_active
  deferral_record
  deferral_resolve
```

### `delete_*` (1)
```
  delete_traces_for_agent
```

### `enqueue_*` (1)
```
  enqueue_outbound
```

### `federation_*` (4)
```
  federation_grant_trust
  federation_list_trusted_keys
  federation_lookup_trust
  federation_revoke_trust
```

### `feedback_*` (3)
```
  feedback_list
  feedback_list_for_thought
  feedback_record
```

### `fetch_*` (1)
```
  fetch_trace_events_page
```

### `get_*` (8)
```
  get_calibration_bundle_by_version
  get_classifications
  get_current_calibration_bundle
  get_detection_events
  get_features
  get_trace_detail
  get_trace_summary
  get_trust_grant
```

### `grant_*` (1)
```
  grant_trust
```

### `hash_*` (1)
```
  hash_chain_gaps
```

### `incident_*` (4)
```
  incident_correlate
  incident_list
  incident_record
  incident_transition
```

### `keyring_*` (2)
```
  keyring_path
  keyring_storage_kind
```

### `list_*` (10)
```
  list_attestations
  list_attestations_by
  list_attestations_for
  list_federation_keys
  list_llm_calls
  list_outbound
  list_revocations
  list_tasks
  list_trace_summaries
  list_trust_grants
```

### `local_*` (6)
```
  local_key_id
  local_pqc_key_id
  local_pqc_public_key_b64
  local_pqc_sign
  local_public_key_b64
  local_sign
```

### `lock_*` (3)
```
  lock_get
  lock_release
  lock_try_acquire
```

### `lookup_*` (3)
```
  lookup_keys_for_identity
  lookup_public_key
  lookup_trust_grant
```

### `maintenance_*` (3)
```
  maintenance_archive_expired
  maintenance_prune_audit_chain
  maintenance_vacuum
```

### `mark_*` (4)
```
  mark_ack_received
  mark_replay_resolved
  mark_transport_delivered
  mark_transport_failed
```

### `match_*` (1)
```
  match_ack_to_outbound
```

### `outbound_*` (1)
```
  outbound_status
```

### `public_*` (1)
```
  public_key_b64
```

### `put_*` (5)
```
  put_attestation
  put_calibration_bundle
  put_detection_event
  put_public_key
  put_revocation
```

### `receive_*` (1)
```
  receive_and_persist
```

### `register_*` (2)
```
  register_federation_key
  register_public_key
```

### `replay_*` (1)
```
  replay_abandoned
```

### `revocations_*` (1)
```
  revocations_for
```

### `revoke_*` (1)
```
  revoke_trust_grant
```

### `run_*` (1)
```
  run_pqc_sweep
```

### `scheduled_*` (3)
```
  scheduled_task_list_due
  scheduled_task_update_after_trigger
  scheduled_task_upsert
```

### `secrets_*` (18)
```
  secrets_decapsulate
  secrets_decrypt
  secrets_encrypt
  secrets_forget_secret
  secrets_get_access_logs
  secrets_get_filter_config
  secrets_get_service_stats
  secrets_is_healthy
  secrets_list_stored
  secrets_migrate_to_hardware_key
  secrets_process_incoming_text
  secrets_recall_secret
  secrets_reencrypt_all
  secrets_retrieve_secret
  secrets_rotate_master_key
  secrets_store_secret
  secrets_test_encryption
  secrets_update_filter_config
```

### `set_*` (2)
```
  set_classifications
  set_features
```

### `sweep_*` (3)
```
  sweep_ack_timeouts
  sweep_expired_claims
  sweep_ttl_expired
```

### `task_*` (6)
```
  task_delete
  task_get
  task_list
  task_try_claim_shared
  task_update_status
  task_upsert
```

### `telemetry_*` (4)
```
  telemetry_consolidate_period
  telemetry_list_metrics
  telemetry_record_metric
  telemetry_record_metrics_batch
```

### `temporal_*` (1)
```
  temporal_drift
```

### `thought_*` (5)
```
  thought_get
  thought_get_descendants
  thought_list
  thought_update_status
  thought_upsert
```

### `ticket_*` (5)
```
  ticket_assign
  ticket_get
  ticket_list
  ticket_update_status
  ticket_upsert
```

### `trust_*` (2)
```
  trust_grant_consistency_proof
  trust_grant_inclusion_proof
```

### `verify_*` (6)
```
  verify_hybrid
  verify_hybrid_via_directory
  verify_signed_attestation
  verify_signed_key_record
  verify_signed_revocation
  verify_trace
```

### `wa_*` (7)
```
  wa_cert_get
  wa_cert_get_by_kid
  wa_cert_get_by_oauth
  wa_cert_list_by_role
  wa_cert_set_active
  wa_cert_update_last_login
  wa_cert_upsert
```

## Raw-SQL consumers in `ciris_engine/`

### `import sqlite3` direct importers
**Total: 17** lines across 17 files.

| file | substrate hint |
|---|---|
| `ciris_engine/logic/adapters/api/routes/audit.py` | audit |
| `ciris_engine/logic/adapters/api/routes/setup/location.py` | set |
| `ciris_engine/logic/audit/hash_chain.py` | audit, hash |
| `ciris_engine/logic/audit/signature_manager.py` | audit |
| `ciris_engine/logic/audit/verifier.py` | audit |
| `ciris_engine/logic/persistence/db/core.py` | UNCLASSIFIED |
| `ciris_engine/logic/persistence/db/migration_runner.py` | run |
| `ciris_engine/logic/persistence/db/retry.py` | UNCLASSIFIED |
| `ciris_engine/logic/persistence/db/setup.py` | set |
| `ciris_engine/logic/services/graph/audit_service/service.py` | audit |
| `ciris_engine/logic/services/graph/tsdb_consolidation/cleanup_helpers.py` | tsdb (GAP) |
| `ciris_engine/logic/services/graph/tsdb_consolidation/db_query_helpers.py` | tsdb (GAP) |
| `ciris_engine/logic/services/graph/tsdb_consolidation/extensive_helpers.py` | tsdb (GAP) |
| `ciris_engine/logic/services/graph/tsdb_consolidation/profound_helpers.py` | tsdb (GAP) |
| `ciris_engine/logic/services/graph/tsdb_consolidation/query_manager.py` | tsdb (GAP) |
| `ciris_engine/logic/utils/directory_setup.py` | set |
| `ciris_engine/logic/utils/occurrence_utils.py` | task/occurrence |

### `get_db_connection(` call sites
**Total: 54** calls across **19** files.

| file | count | substrate hint |
|---|---|---|
| `ciris_engine/logic/secrets/store.py` | 12 | secrets |
| `ciris_engine/logic/services/graph/tsdb_consolidation/edge_manager.py` | 9 | tsdb (GAP) |
| `ciris_engine/logic/services/graph/tsdb_consolidation/service.py` | 8 | tsdb (GAP) |
| `ciris_engine/logic/services/graph/tsdb_consolidation/query_manager.py` | 5 | tsdb (GAP) |
| `ciris_engine/logic/adapters/api/routes/setup/location.py` | 3 | set |
| `ciris_engine/logic/adapters/api/routes/memory_filters.py` | 2 | graph/memory |
| `ciris_engine/logic/adapters/api/routes/system_extensions.py` | 2 | UNCLASSIFIED |
| `ciris_engine/logic/context/system_snapshot_helpers.py` | 2 | multiple (graph/task/thought) |
| `ciris_engine/logic/adapters/api/routes/memory_queries.py` | 1 | graph/memory |
| `ciris_engine/logic/adapters/api/routes/memory_query_helpers.py` | 1 | graph/memory |
| `ciris_engine/logic/persistence/models/queue_status.py` | 1 | UNCLASSIFIED |
| `ciris_engine/logic/persistence/stores/__init__.py` | 1 | UNCLASSIFIED |
| `ciris_engine/logic/runtime/ciris_runtime.py` | 1 | run |
| `ciris_engine/logic/runtime/initialization_steps.py` | 1 | run |
| `ciris_engine/logic/services/graph/telemetry_service/helpers.py` | 1 | telemetry |
| `ciris_engine/logic/services/graph/telemetry_service/service.py` | 1 | telemetry |
| `ciris_engine/logic/services/infrastructure/database_maintenance/service.py` | 1 | maintenance |
| `ciris_engine/logic/services/infrastructure/resource_monitor/service.py` | 1 | UNCLASSIFIED |
| `ciris_engine/logic/utils/occurrence_utils.py` | 1 | task/occurrence |

### `psycopg2` references
**Total: 10** lines across 1 files.

- `ciris_engine/logic/persistence/db/core.py:53:# Try to import psycopg2 for PostgreSQL support`
- `ciris_engine/logic/persistence/db/core.py:55:    import psycopg2`
- `ciris_engine/logic/persistence/db/core.py:56:    import psycopg2.extras`
- `ciris_engine/logic/persistence/db/core.py:61:    logger.debug("psycopg2 not available - PostgreSQL support disabled")`
- `ciris_engine/logic/persistence/db/core.py:100:        """Initialize wrapper with psycopg2 cursor."""`
- `ciris_engine/logic/persistence/db/core.py:175:        """Initialize wrapper with psycopg2 connection."""`
- `ciris_engine/logic/persistence/db/core.py:637:            "PostgreSQL connection requested but psycopg2 not installed. Install with: pip install psycopg2-binary"`
- `ciris_engine/logic/persistence/db/core.py:639:    conn = psycopg2.connect(adapter.db_url)`
- `ciris_engine/logic/persistence/db/core.py:640:    conn.cursor_factory = psycopg2.extras.RealDictCursor`
- `ciris_engine/logic/persistence/db/core.py:855:        - PostgreSQL: psycopg2 connection with dict cursor factory`

### `aiosqlite` references
**Total: 4** lines across 1 files.

- `ciris_engine/logic/adapters/api/services/auth_service.py:16:import aiosqlite`
- `ciris_engine/logic/adapters/api/services/auth_service.py:157:            async with aiosqlite.connect(self._revocations_db_path) as db:`
- `ciris_engine/logic/adapters/api/services/auth_service.py:179:            async with aiosqlite.connect(self._revocations_db_path) as db:`
- `ciris_engine/logic/adapters/api/services/auth_service.py:1203:            async with aiosqlite.connect(self._revocations_db_path) as db:`

## Gaps requiring upstream CIRISPersist work

Substrate that does NOT exist in persist 1.5.19 today.


### Gap #1 — TSDB consolidation pipeline
**Scale:** ~6,680 LOC across 11 files under `services/graph/tsdb_consolidation/`.

**Today:** persist exposes `telemetry_consolidate_period`, `telemetry_record_metric`, `telemetry_record_metrics_batch`, `telemetry_list_metrics` only — sufficient for ingest, *not* for the 6h → daily → weekly → monthly aggregation pipeline.

**Needed:** new `tsdb_*` substrate covering:
- Period-window queries (basic, extensive, profound)
- Cross-period aggregation (week boundaries, month boundaries)
- Edge aggregation for consolidated summaries
- Cleanup / pruning of consolidated periods
- Conditional consolidation lock (`acquire_consolidation_lock`, currently uses persist's `lock_*` substrate already)

**Risk:** Outputs must match byte-for-byte or require an explicit one-shot re-baseline migration on first 2.9.0 boot.


### Gap #2 — Token revocations
**Scale:** 3 call sites in `adapters/api/services/auth_service.py`, single-purpose `revocations.db` file.

**Today:** no `revocation_*` substrate. Schema is `(token_hash, revoked_at, revoked_by, reason)`. Persist has `revoke_trust_grant` and `federation_revoke_trust` but those are trust-grant revocations, not service-token revocations.

**Decision:** folding into `wa_cert.active` does **NOT** work — `token_hash` is not a `wa_id`. These are service tokens, not WA certificates.

**Resolved approach:** new `service_token_revocation_*` substrate filed upstream. Schema mirrors the existing table verbatim. Methods needed:
- `service_token_revocation_record(payload)` — insert
- `service_token_revocation_list()` — load all on startup (agent caches in memory)
- `service_token_revocation_check(token_hash)` — optional point lookup

### Gap #3 — Memory query helpers
**Scale:** `adapters/api/routes/memory_queries.py`, `memory_query_helpers.py`, `memory_filters.py`; ~5 call sites.

**Queries audited:**
1. `SELECT node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at FROM graph_nodes WHERE updated_at >= ? AND updated_at < ? AND NOT (node_type = 'tsdb_data' AND node_id LIKE 'metric_%') [AND scope = ?] [AND node_type = ?]` — time-range listing with exclusion filter.
2. `SELECT COUNT(*) FROM graph_nodes` / `FROM graph_edges` — aggregate counts.
3. `SELECT node_type, COUNT(*) FROM graph_nodes GROUP BY node_type` — group-by aggregate.
4. `SELECT oauth_provider, oauth_external_id FROM wa_cert WHERE wa_id = ? AND oauth_provider IS NOT NULL AND active = 1` — OAuth identity lookup. Already covered by `wa_cert_get_by_oauth` (reverse direction works for one site; for `wa_id → oauth` direction we can use `wa_cert_get(wa_id)` and read the fields).

**Coverage check:**
- Query 1: persist's `cirisgraph_list_nodes` does time-range + scope + type filters. Missing: the `NOT (node_type = 'tsdb_data' AND node_id LIKE ...)` exclusion. Either filter client-side after a wider query, or file a `cirisgraph_list_nodes` extension that accepts an exclusion pattern.
- Query 2-3: persist has `cirisgraph_count_nodes` and `cirisgraph_count_edges` (verify in Phase 0 deep dive); group-by is the gap. File `cirisgraph_count_nodes_by_type` if missing.
- Query 4: maps to `wa_cert_get(wa_id)` — no upstream work needed.

**Resolved approach:** file a single upstream issue covering: (a) optional exclusion-pattern arg on `cirisgraph_list_nodes`, (b) `cirisgraph_count_*_by_type` group-by counters. If persist already has them, this gap is closed without filings.


### Exception — `setup/location.py` (cities.db)

`adapters/api/routes/setup/location.py` is **NOT** a Phase 1-6 target. It opens `cities.db`, a static FTS5-indexed geo-reference database that ships as read-only application data. Persist is designed for agent state — runtime tasks, thoughts, audit, secrets — and is the wrong tool for static lookup files.

This file's `import sqlite3` and its `_get_db_connection()` helper stay. They never call into `persistence/db/`'s `get_db_connection()`; they construct their own stdlib `sqlite3.connect()` against the data file. No persist substrate would replace FTS5 city search.

This is the **only** documented stdlib-sqlite3 holdout after 2.9.0 lands. Future versions may move geo data behind an API or to a dedicated reference-data substrate, but that's out of scope for the persist absorption.

### Gap #4 — Postgres path verification
**Scale:** `persistence/db/core.py` — entire `_PG*` wrapper layer (~250 LOC).

**Today:** persist 1.5.19 sqlx-bundles Postgres. Agent never wires Engine for Postgres DSNs — always falls back to its own psycopg2 path.

**Needed:** stand up a real Postgres in CI, run full QA suite against persist-on-Postgres, document any divergence from SQLite behavior. Not a substrate gap per se, but a verification gap.


## Phase mapping

How each gap maps to the waterfall phases:

| Gap | Resolves in | Notes |
|---|---|---|
| #1 TSDB substrate | Phase 0 (upstream filing) → Phase 3b (consume) | Largest single piece; blocks 3b |
| #2 Revocations | Phase 0 (decision) → Phase 2b (consume) | If Option 2 chosen, no upstream work needed |
| #3 Memory queries | Phase 0 (per-query audit) → Phase 4 (consume) | May surface new substrate needs late |
| #4 Postgres verification | Phase 1 (CI matrix) | Verification, not new substrate |

## Files filed upstream

Verified persist 1.5.19 surface (198 methods). Confirmed gaps:

- [x] [**CIRISPersist#63** — TSDB consolidation substrate.](https://github.com/CIRISAI/CIRISPersist/issues/63) `tsdb_*` methods covering period-window queries (basic/extensive/profound), cross-period aggregation, edge aggregation, cleanup/pruning. Replaces 6,680 LOC of Python aggregation under `services/graph/tsdb_consolidation/`.
- [x] [**CIRISPersist#64** — service token revocation substrate.](https://github.com/CIRISAI/CIRISPersist/issues/64) Three methods: `service_token_revocation_record`, `service_token_revocation_list`, `service_token_revocation_check`. Replaces `revoked_service_tokens.db` (aiosqlite) entirely.
- [x] [**CIRISPersist#65** — cirisgraph list/count gaps.](https://github.com/CIRISAI/CIRISPersist/issues/65) `cirisgraph_query_nodes` exists but the agent needs: (a) optional exclusion-pattern arg (for the `NOT (node_type='tsdb_data' AND node_id LIKE 'metric_%')` filter), (b) `cirisgraph_count_nodes_by_type` group-by counter, (c) `cirisgraph_count_nodes` / `cirisgraph_count_edges` totals.

Verification gap (no upstream filing — agent-side work only):

- [ ] **Postgres CI matrix.** Stand up a real Postgres container in CI. Run the QA suite against persist's sqlx-Postgres backend. Document any divergence from SQLite behavior. Lands inside Phase 1.
- [ ] CIRISPersist#TBD — memory query gaps (filled in after per-query audit)