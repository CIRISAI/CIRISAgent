# Cleanup & Review — CIRISAgent 2.9.0 Full A1 Absorption

Companion to `MIGRATION_BIBLE.md`. Captures the dead-code review performed
during the T-lane migration, what was deleted now, what is staged for
post-FK-chain cleanup, and optimization opportunities for follow-up PRs.

## Status at time of writing

When this review started, the sibling agent branches —
`release/2.9.0-taskschain`, `release/2.9.0-correlations`,
`release/2.9.0-coldtables` — all pointed at the same SHA as
`release/2.9.0`. None of the migration commits had landed yet, so the
**majority of the legacy-callers inventory could only be IDENTIFIED**,
not deleted. What you find in this branch is the safe subset that became
dead from migrations that are already in (A1 graph absorption, A3 audit,
D1 incidents, D2 maintenance), plus their associated tests.

When the FK chain (tasks + thoughts + scheduled_tasks + feedback_mappings
+ continuity_awareness) and the rest of the T-lanes land, re-run this
review — most of §B and §C below opens up.

---

## A. Deleted now (this branch)

Four small focused commits — each runs mypy clean on changed files and
leaves the relevant pytest suites no worse than the
`release/2.9.0`-HEAD baseline.

| SHA | Title | LOC | Notes |
|---|---|---|---|
| `99555f731` | remove dead edge-delete helpers in persistence.models.graph | -78 | `delete_graph_edge`, `delete_edges_for_node`, `_engine_db_path`, top-level `sqlite3` import + their exports in two `__init__.py` files. Zero callers verified across `ciris_engine/`, `tests/`, `tools/`, `ciris_adapters/`. |
| `3939c2f32` | drop obsolete tests/.../test_graph.py | -252 | All 7 tests already `pytest.mark.skip`'d post-A1; patched `graph.get_db_connection` (a symbol that no longer exists). Coverage for the cirisgraph_* path now lives in `tests/ciris_engine/logic/services/graph/*` (598 tests). |
| `4fda108f9` | drop unused public retry helpers + obsolete migration guide | -262 | `with_retry`, `get_db_connection_with_retry`, `execute_with_retry` had zero callers anywhere. Kept `is_retryable_error` + `DEFAULT_*` (still used by `core.RetryConnection`). Also drops `RETRY_MIGRATION_GUIDE.md` since it documented APIs we just removed. |
| `fb9fb89c7` | drop vestigial mock_graph_db placeholder | -8 | The `mock_graph_db = MagicMock()` "back-compat placeholder" + its yielded `"graph_db"` dict key in two snapshot-test fixtures had no consumer. 110 system_snapshot tests stay green. |

**Net: 580 LOC removed.**

---

## B. Staged for post-FK-chain cleanup (DO NOT delete until siblings land)

These will become dead once `tasks.py` / `thoughts.py` / `correlations.py`
absorb. **Verifying each will require re-running the grep audits below
after the migration commits land — the FK chain blocks them today
because the legacy callers all still go through `get_db_connection`.**

### B.1 — `ciris_engine/logic/persistence/utils.py`

`map_row_to_task` and `map_row_to_thought` row-mappers. Today they're called by:
- `persistence/models/tasks.py` (every list/get function)
- `persistence/models/thoughts.py` (every list/get function)
- `services/infrastructure/database_maintenance/service.py`
- `tests/test_task_persistence_fix.py`
- `tests/ciris_engine/logic/persistence/models/test_tasks_any_occurrence.py`
- `tests/ciris_engine/logic/adapters/test_native_vision.py`
- `tests/ciris_engine/logic/processors/states/test_work_processor_tickets.py`

After TasksChain lands, the production callers in `tasks.py` / `thoughts.py`
go away. The test callers will need to be rewritten against persist's
return-shape OR converted to `engine.task_get` / `engine.thought_get`
directly. Audit command:

```bash
grep -rln "map_row_to_task\|map_row_to_thought" ciris_engine/ tests/ tools/
```

### B.2 — `persistence/db/operations.py`

`insert_node_if_not_exists`, `batch_insert_nodes_if_not_exist`,
`insert_edge_if_not_exists`, `batch_insert_edges_if_not_exist`,
`upsert_node` — all write to the legacy `graph_nodes` / `graph_edges`
tables.

Currently called by `services/graph/tsdb_consolidation/edge_manager.py`
(many call sites) for consolidation-time summary node / edge creation.
Persist has typed equivalents (`cirisgraph_upsert_node`,
`cirisgraph_upsert_edge`). When `edge_manager.py` is migrated to persist,
this whole file goes.

### B.3 — `persistence/db/core.py` (mostly)

Once nothing calls `get_db_connection`, this entire file goes — including
`RetryConnection`, `PostgreSQLConnectionWrapper`, `PostgreSQLCursorWrapper`,
the connection diagnostics, the bootstrap helpers. **What must remain
in some form:** the persist Engine bootstrap path (`_bootstrap_persist_engine`,
which `initialize_database` calls). That bootstrap is what wires the
`set_persist_engine` global the rest of the agent reads.

Recommendation: split `core.py` into `legacy_connection.py` (everything
that exists for the pre-persist tables) and `persist_bootstrap.py`
(the engine-wiring path). Then `legacy_connection.py` can die as a unit.

### B.4 — `persistence/db/migration_runner.py`

Per the bible: load-bearing for the one-time A0a graph migration on
upgrade from <2.9.0. Keep it after T-lanes land. It can only die when
upgrade-from-2.8 is no longer supported (probably 3.0.0).

### B.5 — `persistence/db/retry.py` (remaining surface)

`is_retryable_error` and `DEFAULT_*` constants stay until
`core.RetryConnection` dies (i.e., until `get_db_connection` callers all
absorb). Then `retry.py` deletes as a unit. Already trimmed to 38 LOC
in commit `4fda108f9`.

### B.6 — Legacy SQL migration files

`ciris_engine/logic/persistence/migrations/{sqlite,postgres}/*.sql`:

| Migration | Tables | Recommendation |
|---|---|---|
| 001 | tasks, thoughts, feedback_mappings, **graph_nodes, graph_edges**, service_correlations | **Hollow but keep** — graph_nodes / graph_edges are read by `tools/ops/migrate_to_persist.py` (A0a) during upgrade. Drop the migrated-table CREATEs (tasks, thoughts, feedback_mappings, service_correlations) only after every install base is on a version that's already past A0a. |
| 002 | retry_status | Hollow when tasks absorb |
| 003 | task signing fields | Hollow when tasks absorb |
| 004 | occurrence_id | Hollow when tasks + thoughts + service_correlations all absorb |
| 005 | consolidation_locks | Hollow when locks absorb (ColdTables) |
| 006 | service_correlations unique index | Hollow when Correlations absorbs |
| 007 | dsar_tickets | Hollow when tickets absorbs (ColdTables) |
| 008 | rename to tickets | Hollow when tickets absorbs |
| 009 | ticket status columns | Hollow when tickets absorbs |
| 010 | images on tasks | Hollow when tasks absorbs |
| 011 | deferral_reports | Hollow when deferral absorbs (ColdTables) |

**"Hollow" means**: keep the file (for the schema_migrations history table's
sake; deleting a migration's filename causes `run_migrations` to think
it's pending and re-run it), but blank the body of the migrated tables.
Add a top-of-file comment pointing at the persist substrate that
replaces it.

**Risk**: option 2 (delete) breaks upgrades from any version that ran
that migration. For 11 migrations covering 6 substrates the risk is
high. Recommend `hollow` for all 11, not `delete`.

---

## C. Test-infrastructure simplifications recommended

### C.1 — Pattern of patching `get_db_connection` at module path

Currently 47 test files patch `get_db_connection` somewhere. After
T-lanes land:

- For graph: those patches already fail-silent / no-op (the symbol
  doesn't exist on `persistence.models.graph` anymore). When the
  TasksChain lands, the same will be true of `persistence.models.tasks`
  and `persistence.models.thoughts`.
- For correlations: same pattern, post-Correlations lane.

The right replacement is to use `tests/fixtures/persist_engine.py`,
which wires a real persist Engine on a temp SQLite. Patches become
no-ops or unnecessary.

**Recommended test-sweep PR after T-lanes:**
1. Replace every `patch("...persistence.models.tasks.get_db_connection")`
   with the `persist_engine` fixture
2. Same for `thoughts`, `correlations`, `tickets`, `deferral`
3. Delete `test_correlations.py::test_..._uses_correct_placeholders`-style
   tests — placeholder translation is persist's responsibility now

### C.2 — `tests/test_services/test_database_maintenance_multi_occurrence.py`

Carries an `insert_raw_thought` helper (line 365) that does raw-sqlite3
inserts to the legacy `thoughts` table. After thoughts absorption, this
helper either:
- Migrates to `engine.thought_upsert` with deliberately-malformed
  payloads (to keep testing that the maintenance service handles bad
  context_json gracefully)
- OR gets deleted along with the tests that use it, if the malformed-
  context cleanup logic in the maintenance service is itself dead post-
  absorption (TBD — depends on whether persist's `thought_upsert`
  rejects bad context_json or accepts it)

Flag for the post-thoughts-migration test sweep.

### C.3 — `tests/conftest_config_mock.py`

Reviewed: doesn't patch any `get_db_connection` symbols. No action needed
in cleanup scope.

### C.4 — `tests/fixtures/persist_engine.py`

The shared fixture is already correct shape. After T-lanes, more tests
will adopt it. Keep an eye on its `engine.<substrate>_*` defaults —
if every test re-wires the same channel_id / occurrence_id, factor that
into the fixture itself.

---

## D. Optimization opportunities (future PRs)

### D.1 — N+1 in `persistence/analytics.py`

`get_tasks_needing_seed_thought` (line 47) loops over `active_tasks`
and calls `get_thoughts_by_task_id` for each. For an agent with N
active tasks this is N+1 database round-trips through persist.

After thoughts absorbs, persist's `thought_list` with a `source_task_id IN (...)`
filter would batch this to one call. Same for
`get_tasks_needing_recovery_thought`.

### D.2 — Unused `db_path` parameter threading

82 occurrences of `db_path: Optional[str] = None` in
`persistence/models/`. After full absorption, persist's Engine is a
module global — there is no per-call DB path to thread anymore. Every
such parameter becomes vestigial.

Recommendation: **don't** rip them out wholesale, because that's a
giant signature-change churn across the call graph. Instead, after
absorption, add a single deprecation warning when `db_path` is passed
non-None, and remove the parameter in 3.0.0.

### D.3 — Redundant `asyncio.to_thread` wrappers

Per the bible: "persist methods are sync (Rust+tokio internally);
wrapping a sync call in `asyncio.to_thread` may be redundant if persist
methods don't block the GIL." Today:

- `incident_capture_handler.py:268` — `await asyncio.to_thread(engine.incident_record, ...)`
- `audit_service/service.py:1320` — `await asyncio.to_thread(self._write_to_persist_chain, entry)`
- `audit_service/service.py:1292` — `await asyncio.to_thread(_create_tables)` (this one is legit — table-creation is one-shot startup, no perf concern)
- `incident_service/service.py:270` — `await asyncio.to_thread(self._query_persist_incidents, cutoff_time)`
- `persistence/models/thoughts.py:177, 213, 234` — three wrappers around sync persistence calls

These deserve a **benchmark check** before changes. The cost of
`asyncio.to_thread` is a context-switch + GIL-release-acquire-cycle;
on a hot path that's measurable. If persist's Rust internals don't
hold the GIL during the call (likely — persist uses sqlx which goes
through `tokio::task::spawn_blocking` internally), then the agent's
`to_thread` is double-wrapping and dropping a useless context switch
is a small but free win.

**Open question for the persist team:** does
`engine.incident_record()` ever hold the Python GIL longer than ~50µs?
If yes, keep the `to_thread`. If no, drop it.

### D.4 — Two passes over `pending + processing` in analytics.py

```python
pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING, occurrence_id)
processing_thoughts = get_thoughts_by_status(ThoughtStatus.PROCESSING, occurrence_id)
all_thoughts = pending_thoughts + processing_thoughts
```

This is two persist calls + list-concat. Once persist's `thought_list`
supports multi-status filter (`status IN ('pending', 'processing')`)
this becomes one call. Filed as gap below.

---

## E. Persist API gaps observed

These were not in the bible's known-gaps section but came up during the
review. Suggested issues for CIRISPersist:

| Gap | Agent caller | Workaround in place |
|---|---|---|
| `cirisgraph_delete_edge` (typed bulk delete) | `memory_service` forget path | None needed — `cirisgraph_delete_node(hard=True)` cascades. Filed in cirisgraph delete-cascade docs. |
| `cirisgraph_delete_edges_for_node` (typed) | (was `delete_edges_for_node`) | Same — cascade covers it. |
| `thought_list` with `status IN (...)` multi-filter | `persistence.analytics.get_pending_thoughts_for_active_tasks` | Two list calls + python concat (D.4 above) |
| `thought_list` with `source_task_id IN (...)` batch | `persistence.analytics.get_tasks_needing_seed_thought` | N+1 loop (D.1 above) |
| `thought_delete` | `delete_thoughts_by_ids` | Function will become soft no-op post-thoughts-absorption per bible §"Known gaps". |

---

## F. Documentation updates recommended (post-T-lanes)

When T-lanes land:

1. `ciris_engine/logic/persistence/README.md` — verify the architecture
   description still matches (haven't audited yet)
2. Drop the comment block at the top of `persistence/models/graph.py`
   line 16-18 once `cirisgraph_delete_edge` lands upstream (the gap-
   reference becomes stale)
3. `ciris_engine/logic/services/lifecycle/scheduler/README.md` — likely
   still references `get_db_connection`-era patterns, audit after
   TasksChain lands.

---

## Test posture at cleanup-branch tip

Run on this branch (4fda108f9, 99555f731, etc. applied):

```bash
python3 -m pytest tests/ciris_engine/logic/persistence/ tests/ciris_engine/logic/services/graph/ tests/test_correlations.py -q --timeout=60 -n 16
# => 965/966 passed, 1 pre-existing failure in test_graph_metrics_agg (not introduced by cleanup)
```

Pre-existing failures (verified by git-stash + re-run on
`release/2.9.0` HEAD):
- `test_graph_metrics_agg::TestAuditServiceMetrics::test_audit_metrics_change_with_activity`
- `test_tsdb_edge_creation::*` (4 errors when run as collection of
  `tests/ciris_engine/logic/services/graph/`, but each passes
  individually — parallelism/ordering flake)

No new failures introduced. mypy clean on every changed file.

---

## Quick reference for the coordinator

When merging T-lanes into release/2.9.0:

1. Land TasksChain first (FK root)
2. Land Correlations + ColdTables in parallel (independent)
3. Land TestSweep (cleans up the patched-`get_db_connection` test
   surface)
4. Land this cleanup branch
5. Re-run audit commands in §B above. Each now-dead helper from B.1-B.6
   becomes a small follow-up PR.
6. Triage §D optimization opportunities into the 2.9.1 backlog.
