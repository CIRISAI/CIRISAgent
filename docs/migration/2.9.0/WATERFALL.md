# 2.9.0 Waterfall: Full Persist Absorption

**Goal.** Zero `import sqlite3`, zero `import psycopg2`, zero `import aiosqlite` in production code. `requirements.txt` loses both binary deps. Persist owns SQLite and Postgres natively through its sqlx-bundled connection layer.

**Why this is 2.9.0.** The substrate-substitution trajectory (Persist → Edge → LensCore → NodeCore) only works if the agent has a single DB boundary. Today the agent has dozens of raw-sqlite3 call sites, two parallel DB files (`secrets.db`, `revocations.db`), and a psycopg2 path that lives outside persist. 2.9.0 collapses all of that into one substrate before later versions swap the engine implementation underneath.

---

## Phase 0 — Persist substrate gap analysis

Lock down what persist 1.5.19 exposes vs. what the agent still needs from raw SQL. No code changes in this phase; the deliverable is a gap report and upstream issues on CIRISPersist for every missing substrate method.

**Audit targets:**
- TSDB consolidation pipeline (6h → daily → weekly → monthly aggregation). Persist exposes `telemetry_consolidate_period` and `telemetry_record_metric*` only. Whole consolidation pipeline (`services/graph/tsdb_consolidation/*.py`, ~6,680 LOC) needs a `tsdb_*` substrate.
- Token revocations. No `revocation_*` substrate; agent maintains `revocations.db` via aiosqlite. Decide: new substrate vs. fold into `wa_cert.active`.
- Memory query helpers. `system_snapshot_helpers.py` + `memory_queries.py` + `memory_query_helpers.py` route reads through raw SQL. Audit whether existing graph substrate covers them or new methods are needed.
- Postgres DSN wiring. Persist's sqlx Postgres path ships but has never been exercised by the agent. Verify against a live instance.

**Exit gate:** every remaining raw-SQL call site in the agent maps to either an existing persist method or a filed upstream issue.

---

## Phase 1 — Postgres handover to persist

The original plan was "delete the psycopg2 wrappers + wire persist for Postgres". Reality: the wrappers are still load-bearing for raw-SQL callers (TSDB, audit, system_snapshot, secrets) that won't migrate until Phases 2-4. Deleting the wrappers in Phase 1 would break every Postgres deployment immediately. Scope adjusted accordingly.

**Phase 1 actually delivers:**

- Verify persist's Postgres path works end-to-end (`_bootstrap_persist_engine` already routes `postgres://` DSNs straight to `Engine(dsn, signing_key_id)`; persist's sqlx handles connection + schema). Confirmed working against `postgres:16-alpine` locally.
- Add CI matrix entry `test-postgres` that spins up a real Postgres service container and runs the persistence-layer tests against persist-on-Postgres.
- Document the deferred deletion: psycopg2 wrappers and `get_db_connection`'s Postgres branch stay until Phase 5, after Phases 2-4 retire every raw-SQL caller.

**Exit gate:** persist's Postgres path verified in CI. The fact that `import psycopg2` still appears in `core.py` is an explicit Phase 5 deletion — tracked, not a regression.

---

## Phase 2 — Secondary stores

### 2a. Secrets store → persist substrate
`secrets/store.py` rewrites every `get_db_connection()` call (12 sites) to engine calls: `secrets_store_secret`, `secrets_recall_secret`, `secrets_retrieve_secret`, `secrets_forget_secret`, `secrets_list_stored`, `secrets_get_access_logs`, `secrets_encrypt`, `secrets_decrypt`, `secrets_rotate_master_key`, `secrets_reencrypt_all`, `secrets_migrate_to_hardware_key`, `secrets_decapsulate`, `secrets_process_incoming_text`, `secrets_get_filter_config`, `secrets_update_filter_config`, `secrets_get_service_stats`, `secrets_is_healthy`, `secrets_test_encryption`.

Drop the standalone `secrets.db` file path; persist owns that table.

**Scope finding (Phase 1 investigation):** This is not a connection swap — it's a semantic API change. The agent's current `SecretRecord` exposes `encrypted_value`/`salt`/`nonce`/`encryption_key_ref` as fields and runs its own AES-GCM encryption before storing the ciphertext. Persist's `secrets_*` substrate owns the entire crypto + storage lifecycle and returns opaque handles. Migrating requires:
1. Adapting `SecretRecord` to be a persist-handle wrapper, not a struct of crypto bytes.
2. Re-encrypting existing stored secrets under persist's master key (one-shot boot-time migration).
3. Verifying persist's `secrets_decapsulate` / `secrets_process_incoming_text` match the agent's pipeline semantics for detected-secret auto-decapsulation.

Sequenced **after** 2c + 3a to let those establish the pattern. Treat 2a as its own design pass with a follow-up doc.

### 2b. Token revocations → persist substrate
`auth_service.py` swaps `aiosqlite.connect(self._revocations_db_path)` for a persist substrate call (substrate decided in Phase 0 — either new `revocation_*` methods or fold into `wa_cert.active`).

Drop `revocations.db` as a separate file.

### 2c. Small modules
Single-call-site swaps: `setup/location.py`, `utils/occurrence_utils.py`, `persistence/models/queue_status.py`, `services/infrastructure/resource_monitor/service.py`.

**Exit gate:** `aiosqlite` no longer imported in `auth_service.py`. `secrets.db` + `revocations.db` no longer created. Five small modules no longer touch sqlite3 or `get_db_connection`.

---

## Phase 3 — Domain migrations (Phase-0-blocked)

### 3a. Audit chain
`audit/{hash_chain, signature_manager, verifier, signing_protocol, key_migration}.py` plus `services/graph/audit_service/service.py` swap raw sqlite3 for persist's audit substrate: `audit_record_entry`, `audit_list_entries`, `audit_verify_chain`, `audit_canonicalize_for_hash`, `audit_canonicalize_for_signing`, `aggregate_audit_chain`, `maintenance_prune_audit_chain`.

Hash chain verifier needs careful migration — it walks rows in order and recomputes hashes. Persist's `audit_verify_chain` should produce identical output; verify against a real production audit log before deleting the Python verifier.

**Exit gate:** audit module no longer imports sqlite3. Hash chain integrity verified end-to-end against pre/post-migration sample.

### 3b. TSDB consolidation
`services/graph/tsdb_consolidation/*.py` (11 files, ~6,680 LOC) collapses into persist's TSDB substrate (added in Phase 0). Aggregation logic moves entirely to the Rust side; agent code becomes a thin orchestrator that calls `engine.tsdb_consolidate_*` per period type.

Largest single piece in the entire waterfall. Heavy verification required: persist's aggregation must produce byte-identical summaries to the Python version, or an explicit one-shot re-baseline migration runs at first 2.9.0 boot.

**Exit gate:** TSDB module no longer imports sqlite3. Consolidation outputs match pre-migration baselines.

### 3c. System snapshot helpers
`context/system_snapshot_helpers.py` swaps its two `persistence.get_db_connection()` sites for the appropriate persist substrate (graph or new methods depending on Phase 0 findings).

**Exit gate:** system snapshot no longer touches raw SQL.

---

## Phase 4 — Remaining `get_db_connection` callers

Sweep the long tail:
- `adapters/api/routes/{audit, memory_filters, memory_queries, memory_query_helpers, system_extensions, setup/location}.py`
- `services/graph/telemetry_service/{service, helpers}.py`
- `services/infrastructure/database_maintenance/service.py`
- `runtime/{ciris_runtime, initialization_steps}.py`

Each call site swaps to the appropriate persist substrate. Any sites that slipped past Phase 0 surface here and block the phase until the missing substrate is added upstream.

**Exit gate:** `get_db_connection` has zero call sites outside `persistence/db/` itself.

---

## Phase 5 — Bootstrap teardown

With nothing left calling `get_db_connection`:

- Delete `get_db_connection`, `get_db_connection_with_retry`, the connection-wrapper classes, the dialect adapter from `persistence/db/`.
- Delete `_PGConnectionWrapper`, `_PGCursorWrapper`, `_create_postgres_connection`, the psycopg2 import block (deferred from Phase 1 — the wrappers were load-bearing until Phase 4 finished migrating raw-SQL callers).
- `migration_runner.py` becomes either a thin first-boot shim (upgrade pre-persist DBs once, noop forever after) or is deleted entirely if persist's own migration runner covers the upgrade path.
- `setup.py`, `retry.py` deleted or reduced to empty re-exports (then deleted in 2.9.1).
- `initialize_database()` shrinks to: resolve DSN → build persist Engine → wire `set_persist_engine()`.

**Exit gate:** No `import sqlite3` outside the bootstrap entry point. No `import psycopg2`. No `import aiosqlite`.

---

## Phase 6 — Requirements + ship

```diff
# requirements.txt
-aiosqlite>=0.20.0,<1.0.0
-psycopg2-binary>=2.9.0,<3.0.0
```

`sqlite3` is stdlib — no requirements change, just gone from `import` lines.

Update `setup.py` to drop `migrations/sqlite/*.sql` from package data, or keep one final upgrade-path migration as a resource for 2.8.x → 2.9.0 upgrades.

Bump version to `2.9.0`. Tag.

**Exit gate:** Fresh install on a clean venv has zero sqlite3/psycopg2/aiosqlite presence. Full QA matrix (SQLite + Postgres) green. Production agents upgrade cleanly from 2.8.x.

---

## Sequence summary

```
Phase 0  ───────►  Phase 1  ────►  Phase 2  ────►  Phase 3  ────►  Phase 4  ────►  Phase 5  ────►  Phase 6
gap-audit          postgres        secondary       domain          remaining       bootstrap       ship
+ upstream         handover        stores          migrations      callers         teardown        2.9.0
filings                            (secrets,       (audit,
                                    revoc,          TSDB,
                                    setup,          snapshot)
                                    occurrence,
                                    queue,
                                    resmon)
```

Phases gate on each other — a phase doesn't start until its predecessor's exit gate is met. Phase 3 has a hard dependency on Phase 0 deliverables landing in a published persist version. Phase 5 cannot start until Phase 4 is complete (the deletions break callers otherwise).

---

## What later versions inherit

This waterfall leaves the codebase in the right shape for substrate substitution. Each later swap is a one-import change at the bootstrap because 2.9.0 ripped out every direct DB call.

- **2.9.1 — Edge.** Persist Engine swapped for Edge crate. Single substitution point in `initialize_database()`. No agent-side raw SQL means no friction.
- **2.9.2 — LensCore.** Lens substrate replaces the lens-tee files. Independent of DB layer; unblocked by 2.9.0 cleaning up the substrate seams.
- **2.9.3 — NodeCore.** Federation / multi-agent substrate. Independent of DB layer.
