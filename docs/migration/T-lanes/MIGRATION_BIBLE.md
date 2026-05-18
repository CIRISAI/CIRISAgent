# T-Lane Migration Bible — CIRISAgent 2.9.0 Full A1 Absorption

This document is the single source of truth for migrating the agent's
legacy raw-sqlite3 callers to ciris-persist v1.5.19's typed substrate APIs.

**Why:** the agent currently has TWO libsqlite implementations writing to
`ciris_engine.db` (persist's bundled sqlx via Rust, Python's system
libsqlite3 via the `sqlite3` module). They share the WAL, which causes
page-level B-tree corruption (CIRISPersist#58). The fix is to make
persist the **only** writer.

**Goal:** every public function in `ciris_engine/logic/persistence/models/`
that currently uses `get_db_connection()` is rewritten to call
`engine.<substrate>_*` instead. Public function signatures stay
**unchanged** so callers across the codebase don't move.

---

## Persist 1.5.19 substrate APIs

| Substrate | Methods | Agent table replaced |
|---|---|---|
| `task_*` | upsert, get, list (filter+cursor+limit), update_status, delete, try_claim_shared | `tasks` |
| `thought_*` | upsert, get, list, update_status, get_descendants | `thoughts` |
| `correlation_*` | record, get, query, update_status | `service_correlations` |
| `scheduled_task_*` | upsert, list_due, update_after_trigger | `scheduled_tasks` |
| `ticket_*` | upsert, get, list, assign, update_status | `tickets` |
| `deferral_*` | record, get, list_active, resolve | `deferral_reports` |
| `ceremony_*` | record, get, list, update_status | `creation_ceremonies` |
| `continuity_*` | record, get_latest, record_reactivation | `continuity_awareness` |
| `feedback_*` | record, list, list_for_thought | `feedback_mappings` |
| `wa_cert_*` | upsert, get, get_by_kid, get_by_oauth, list_by_role, set_active, update_last_login | `wa_cert` |
| `lock_*` | try_acquire, get, release | `consolidation_locks` |

All methods take JSON-string payloads and return JSON strings (parse with
`json.loads`). Filters + cursors are also JSON strings.

### Cursor shape

All `*_list` methods accept the same cursor:

```python
cursor_json = json.dumps({
    "version": "v1",
    "last_ts": "9999-12-31T23:59:59Z",   # for head-anchored DESC
    "last_id": "",
})
```

Persist returns DESC by recorded_at. Callers needing ASC should sort
client-side after pagination completes.

### FK constraints (ORDER OF MIGRATION MATTERS)

```
cirislens_tasks  ←  cirislens_thoughts  ←  cirislens_scheduled_tasks
                                           cirislens_continuity_awareness
                 ←  cirislens_feedback_mappings (→ thoughts)
cirislens_thoughts  ←  cirislens_feedback_mappings.target_thought_id
```

**Sequence:**
1. `tasks.py` (no FK parents — migrate first)
2. `thoughts.py` (FK → tasks)
3. `scheduled_tasks` (FK → thoughts)
4. `feedback_mappings` (FK → thoughts)
5. Everything else is independent

If a migration lands mid-sequence (e.g., `thoughts.py` before `tasks.py`),
every test that does `add_task` + `add_thought` fails with persist's
FK constraint — **that's why the FK chain has to land together**.

---

## Field mapping pattern

Persist's payloads use **natural names** (matches agent pydantic fields)
plus a few JSON-field conventions:

### Tasks

| Agent `Task` field | Persist `task_upsert` payload |
|---|---|
| `task_id` | `task_id` |
| `channel_id` | `channel_id` |
| `description` | `description` |
| `status` (`TaskStatus` enum) | `status` (string value) |
| `priority` | `priority` |
| `created_at` / `updated_at` | same |
| `agent_occurrence_id` | same (default `"default"`) |
| `parent_task_id` | same (nullable) |
| `context` (TaskContext) | `context` (nested dict — persist json.dumps internally) |
| `outcome` | `outcome` (nested dict) |
| `retry_count` | same |
| `signed_by` / `signature` / `signed_at` | same |
| `preferred_language` | mirrored in `context.preferred_language` (persist doesn't have a top-level column) |
| `images` | not in persist; agent task carries it but it stays at agent layer |

Required minimum fields for `task_upsert`:
- `task_id`, `channel_id`, `description`, `status`, `created_at`, `updated_at`, `agent_occurrence_id`

### Thoughts

| Agent `Thought` field | Persist `thought_upsert` payload |
|---|---|
| `thought_id` | `thought_id` |
| `source_task_id` | `source_task_id` (FK to `cirislens_tasks.task_id`) |
| `agent_occurrence_id` | same |
| `channel_id` (Optional) | same |
| `thought_type` (`ThoughtType` enum) | `thought_type` (string value) |
| `status` (`ThoughtStatus` enum) | `status` (string value) |
| `created_at` / `updated_at` | same |
| `round_number` / `thought_depth` | same |
| `content` | same |
| `context` (Optional[ThoughtContext]) | `context` (nested dict) |
| `ponder_notes` (Optional[List[str]]) | `ponder_notes` (nested list) |
| `parent_thought_id` | same (nullable) |
| `final_action` (Optional[FinalAction]) | `final_action` (nested dict) |
| `preferred_language` | mirrored in `context.preferred_language` |
| `images` | not in persist (per-task) |

Required minimum: `thought_id`, `source_task_id`, `status`, `content`,
`created_at`, `updated_at`, `agent_occurrence_id`.

**Persist returns:**
```
{
  "thought_id": "...", "source_task_id": "...", "channel_id": null,
  "thought_type": "standard", "status": "pending",
  "created_at": "...", "updated_at": "...",
  "round_number": 0, "content": "...", "thought_depth": 0,
  "agent_occurrence_id": "default",
  "context": {...},          // parsed dict, NOT context_json string
  "ponder_notes": [...],     // parsed list
  "final_action": {...},     // parsed dict
}
```

---

## Reference implementation: thoughts.py skeleton

See `docs/migration/T-lanes/_thoughts_skeleton.py` in this same dir
for a worked example. It shows:

- `_get_engine()` helper that calls `get_persist_engine()` + raises
  cleanly if not bootstrapped
- `_thought_to_persist_payload(thought)` converter
- `_persist_row_to_thought(row)` reverse-converter
- `_list_with_filter(filter_dict, *, limit=None)` pagination helper
- Each public function preserved with the same signature, internals
  swapped

**Apply this exact pattern to every legacy table.**

---

## Test fixture infrastructure

A shared persist-engine fixture is already written at
`tests/fixtures/persist_engine.py`:

```python
@pytest.fixture
def persist_engine() -> Iterator[Engine]:
    """Wire a fresh persist Engine; restore module-global on teardown."""
```

Tests that previously did:

```python
@pytest.fixture
def temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    initialize_database(db_path)   # this wires persist via _bootstrap_persist_engine
    yield db_path
    if os.path.exists(db_path): os.unlink(db_path)
```

…actually already wire persist (via `initialize_database`). But they may
also call `get_db_connection(db_path)` for raw sqlite3 reads/writes —
those need to become persist calls.

### Test failure pattern after migration

The most common failure after migrating one table is:

```
sqlite3.IntegrityError: UNIQUE constraint failed: tasks.task_id
ciris_persist.Conflict: upsert_thought insert: FOREIGN KEY constraint failed
```

This means:
- The test calls `add_task` (raw sqlite3 → legacy `tasks` table)
- Then calls `add_thought` (migrated → `cirislens_thoughts`)
- Persist's FK on `source_task_id → cirislens_tasks(task_id)` fails because
  parent task isn't in `cirislens_tasks` (it's in legacy `tasks`)

**Fix:** migrate the FK chain together. tasks + thoughts + scheduled_tasks
+ feedback_mappings (and continuity_awareness) need to land in one
coordinated commit.

---

## Files and call-site inventory

| File | LOC | Functions | SQL sites | FK on |
|---|---|---|---|---|
| `ciris_engine/logic/persistence/models/tasks.py` | 1069 | 32 | 31 | (none) |
| `ciris_engine/logic/persistence/models/thoughts.py` | 430 | 14 | 15 | tasks |
| `ciris_engine/logic/persistence/models/correlations.py` | 881 | 15 | 15 | (none) |
| `ciris_engine/logic/persistence/models/deferral.py` | 68 | 2 | 2 | (none) |
| `ciris_engine/logic/services/lifecycle/scheduler/service.py` | varies | ~5 | ~5 | thoughts |
| `ciris_engine/logic/persistence/models/tickets.py` | varies | ~4 | ~4 | (none) |
| (cold tables — ceremonies, continuity, feedback, wa_cert, locks) | small | few each | few | various |

Use:
```bash
grep -n "^def \|^async def " <file>
grep -n "INSERT INTO\|UPDATE\|cursor.execute\|conn.execute" <file>
```

…to inventory before starting each file.

---

## "Persist isn't quite there yet" failure modes

When you hit a missing API, file an issue at CIRISAI/CIRISPersist with:
- Method name you expected (e.g., `thought_delete`)
- Agent-side caller path
- Example payload + expected return

Known gaps as of v1.5.19:
- `thought_delete` (not exposed; agent's `delete_thoughts_by_ids` becomes
  a soft no-op + warning — the function is unused by production code
  anyway)
- Date-range filters on `_list` methods (silently accepted but unfiltered;
  paginate + Python-filter as workaround)
- `cirisgraph_delete_edge` (already filed as upstream ask; the
  delete-cascade from `cirisgraph_delete_node(hard=True)` covers most
  needs)

---

## Sanity checklist before opening a PR

1. `python3 -m mypy <migrated_file>` — clean
2. `python3 -m pytest tests/<file_specific_tests> -n 8 --timeout=60 -q`
   — passes (after fixing test fixtures if needed)
3. Local smoke: wipe `~/ciris/data/ciris_engine.db*` and `/tmp/ciris-staged-qa`,
   run `python3 -m tools.qa_runner --from-staged`, confirm:
   - No "database disk image is malformed" errors
   - No "Invalid column type Text" errors
   - `sqlite3 ~/ciris/data/ciris_engine.db "PRAGMA integrity_check;"` returns `ok`
4. Commit message references CIRISAgent#763 (parent issue) and any
   filed CIRISPersist sub-issues.

---

## Coordinator notes (for the human running this)

The migration is partitioned into independent work items where possible:

- **TasksChain**: `tasks.py` + `thoughts.py` + `scheduled_tasks/service.py`
  + `feedback_mappings.py` + `continuity_awareness.py` migration (FK
  chain — must land together)
- **Correlations**: `correlations.py` (independent)
- **ColdTables**: `deferral.py` + `tickets.py` + `creation_ceremonies` +
  `wa_cert` + `consolidation_locks` (independent)
- **TestSweep**: bulk test-fixture updates (depends on TasksChain landing first)
- **Cleanup**: legacy-code review — remove dead `get_db_connection` callers,
  unused imports, optimization opportunities (depends on all above)

Each agent works in a worktree, pushes its own branch, opens a PR.
Coordinator merges in the order above (chain → others → tests → cleanup).
