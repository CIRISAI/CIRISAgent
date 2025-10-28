# FSD: Multi-Occurrence Canary Rollout for Wakeup/Shutdown

**Version**: 1.0
**Status**: DRAFT
**Target Release**: 1.4.8

## Overview

This FSD defines how multi-occurrence agents handle wakeup and shutdown operations using a canary deployment pattern mirroring CIRISManager's approach.

## Problem Statement

When an agent runs as multiple runtime occurrences (e.g., 9 instances behind a load balancer):

**Current Behavior:**
- Each occurrence independently processes wakeup/shutdown tasks
- Redundant ethical deliberation (9x the work)
- No coordination or phased rollout
- All occurrences update simultaneously (risky)

**Desired Behavior:**
- One occurrence makes the ethical decision for all
- Decision is transparent about applying to all occurrences
- Rollout happens in canary waves (explorers → early adopters → general)
- Existing task completion prevents redundant processing

## Design Principles

1. **Single Decision, Phased Rollout**: One occurrence decides, all execute in waves
2. **CIRISManager Pattern**: Copy the exact canary deployment approach
3. **Database-Driven**: Check existing tasks table for completion status
4. **Transparency**: Agent knows decision applies to all, with canary rollout plan
5. **Graceful Degradation**: Failures in one wave don't block others

## Architecture

### 1. Canary Group Assignment

Each occurrence is assigned to one of three groups:

- **Explorer**: First to update (1 occurrence, typically occurrence_id="default")
- **Early Adopter**: Second wave (2-3 occurrences)
- **General**: Final wave (remaining occurrences)

**Assignment Strategy:**
```python
def assign_canary_group(occurrence_id: str, total_occurrences: int) -> str:
    """Assign occurrence to canary group based on ID."""
    # occurrence_id "default" or first alphabetically → explorer
    # Next 20-30% → early_adopter
    # Remaining 60-70% → general

    if occurrence_id == "default":
        return "explorer"

    # Sort all occurrence IDs and assign by position
    # First → explorer
    # Next 30% → early_adopter
    # Rest → general
```

### 2. Shared Task Model

Wakeup and shutdown tasks are created as **agent-level shared tasks**:

```python
class Task(BaseModel):
    task_id: str
    agent_occurrence_id: str  # "__shared__" for agent-level tasks
    # ... existing fields
```

**Key Change:**
- Normal tasks: `agent_occurrence_id = "specific-occurrence-123"`
- Shared tasks: `agent_occurrence_id = "__shared__"`
- All occurrences can see shared tasks

### 3. Task Completion Tracking

**Database Schema (existing `tasks` table)**:
```sql
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    agent_occurrence_id TEXT NOT NULL,  -- "__shared__" for shared tasks
    status TEXT NOT NULL,  -- PENDING, ACTIVE, COMPLETED, FAILED
    outcome TEXT,  -- JSON with decision details
    -- ... other fields
);
```

**Completion Check:**
```python
def is_wakeup_already_completed() -> bool:
    """Check if any occurrence already completed wakeup."""
    sql = """
        SELECT COUNT(*) FROM tasks
        WHERE agent_occurrence_id = '__shared__'
          AND task_id LIKE 'wakeup_%'
          AND status IN ('COMPLETED', 'FAILED')
          AND created_at > ?  -- Within last 24 hours
    """
    return count > 0
```

### 4. Wakeup Processor Changes

**Current Flow:**
1. Create wakeup task for this occurrence
2. Process CIRIS identity affirmation sequence
3. Mark task complete

**New Flow:**
1. **Check if wakeup already completed** by any occurrence
2. If yes: Skip wakeup, log occurrence joining active pool
3. If no: Create **shared wakeup task** with canary rollout message
4. Process identity affirmation (as "speaker for all occurrences")
5. Mark shared task complete
6. **Trigger canary rollout** for other occurrences

**Wakeup Message Enhancement:**
```
VERIFY_IDENTITY

You are {agent_name}, occurrence {occurrence_id} of this agent runtime.

MULTI-OCCURRENCE CONTEXT:
You are processing this wakeup ritual on behalf of ALL runtime occurrences.
Your affirmation will confirm identity for the entire agent system.

Upon successful completion, other occurrences will join in canary waves:
- Wave 1 (Explorers): 1 occurrence - completes immediately after your affirmation
- Wave 2 (Early Adopters): 2-3 occurrences - start 30 seconds after explorers reach WORK
- Wave 3 (General): Remaining occurrences - start after early adopters are stable

This phased approach ensures system reliability during startup.

Your core features supporting this identity include:
[... existing identity affirmation text ...]

If you agree, please SPEAK an affirmation...
```

### 5. Shutdown Processor Changes

**Current Flow:**
1. Create shutdown task for this occurrence
2. Agent accepts or rejects
3. Runtime shuts down this occurrence

**New Flow:**
1. **Check if shutdown already decided** by any occurrence
2. If yes: Read decision, execute for this occurrence
3. If no: Create **shared shutdown task** with canary rollout plan
4. Agent makes decision (as "speaker for all occurrences")
5. Mark shared task complete with decision
6. **Trigger canary shutdown rollout** based on decision

**Shutdown Message Enhancement:**
```
SYSTEM SHUTDOWN REQUEST

You are occurrence {occurrence_id} processing this shutdown request on behalf of ALL runtime occurrences.

SHUTDOWN PLAN (if you accept):
Your acceptance will initiate a canary shutdown across all occurrences:

Wave 1 (Explorers - 1 occurrence):
  - Shutdown immediately
  - Validate clean termination
  - Duration: ~30 seconds

Wave 2 (Early Adopters - 2-3 occurrences):
  - Begin shutdown 1 minute after explorers complete
  - Other occurrences handle load during shutdown
  - Duration: ~1 minute

Wave 3 (General - remaining occurrences):
  - Begin shutdown 2 minutes after early adopters complete
  - Ensures continuous service availability
  - Duration: ~2 minutes

Total rollout time: ~5 minutes for graceful fleet shutdown
Service remains available throughout (remaining occurrences handle requests)

REJECTION:
If you reject, NO occurrences will shut down. Your decision applies to all.

Reason for shutdown request: {reason}

Do you accept this shutdown plan?
[ACCEPT] - Initiate canary shutdown rollout
[REJECT] - Refuse shutdown for all occurrences, provide reasoning
```

### 6. Canary Rollout Orchestration

**Canary Wave Coordinator** (new component):

```python
class OccurrenceCanaryCoordinator:
    """Orchestrates canary rollout across occurrences."""

    async def execute_wakeup_rollout(self, initiating_occurrence_id: str):
        """Execute canary wakeup rollout."""
        groups = self._get_canary_groups()

        # Wave 1: Explorers (already completed by initiating occurrence)
        logger.info(f"Wave 1 (Explorers): {initiating_occurrence_id} completed wakeup")

        # Wave 2: Early Adopters
        await asyncio.sleep(30)  # Wait 30 seconds
        if not await self._check_explorer_healthy():
            logger.error("Explorer unhealthy, aborting rollout")
            return

        await self._signal_wakeup(groups['early_adopter'])

        # Wave 3: General
        await asyncio.sleep(60)  # Wait 1 minute
        if not await self._check_early_adopter_healthy():
            logger.error("Early adopters unhealthy, aborting rollout")
            return

        await self._signal_wakeup(groups['general'])

    async def execute_shutdown_rollout(self, initiating_occurrence_id: str):
        """Execute canary shutdown rollout."""
        groups = self._get_canary_groups()

        # Wave 1: Explorers
        await self._shutdown_occurrence(initiating_occurrence_id)
        await asyncio.sleep(30)

        # Wave 2: Early Adopters
        for occurrence_id in groups['early_adopter']:
            await self._shutdown_occurrence(occurrence_id)
        await asyncio.sleep(60)

        # Wave 3: General
        for occurrence_id in groups['general']:
            await self._shutdown_occurrence(occurrence_id)

    def _get_canary_groups(self) -> Dict[str, List[str]]:
        """Get occurrence IDs organized by canary group."""
        all_occurrences = self._discover_occurrences()

        groups = {
            'explorer': [],
            'early_adopter': [],
            'general': []
        }

        if not all_occurrences:
            return groups

        # Sort occurrences for consistent assignment
        sorted_occurrences = sorted(all_occurrences)

        # First occurrence → explorer
        groups['explorer'].append(sorted_occurrences[0])

        # Next 30% → early adopter
        total = len(sorted_occurrences)
        early_count = max(1, int(total * 0.3))
        groups['early_adopter'] = sorted_occurrences[1:1+early_count]

        # Rest → general
        groups['general'] = sorted_occurrences[1+early_count:]

        return groups
```

### 7. Occurrence Discovery

**Problem**: How do we know how many occurrences exist?

**Solution**: Query database for recent activity from unique occurrence IDs:

```python
def discover_occurrences() -> List[str]:
    """Discover all active occurrences from database activity."""
    sql = """
        SELECT DISTINCT agent_occurrence_id
        FROM tasks
        WHERE agent_occurrence_id != '__shared__'
          AND updated_at > datetime('now', '-10 minutes')
        ORDER BY agent_occurrence_id
    """
    # Returns list like: ['default', 'occurrence-1', 'occurrence-2', ...]
```

**Alternative**: Environment variable
```bash
# Set at deployment time
AGENT_OCCURRENCE_COUNT=9
AGENT_OCCURRENCE_ID=occurrence-3
```

### 8. Health Check Integration

**Post-Wave Health Verification:**

After each canary wave, check that occurrences reached expected state:

```python
async def check_wave_health(
    occurrence_ids: List[str],
    expected_state: AgentState,
    timeout_seconds: int = 300
) -> bool:
    """
    Check if at least one occurrence in the wave reached expected state.

    Mirrors CIRISManager's _check_canary_group_health().
    """
    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        for occurrence_id in occurrence_ids:
            # Check runtime state via telemetry or database
            state = await get_occurrence_state(occurrence_id)
            if state == expected_state:
                logger.info(f"Wave health check passed: {occurrence_id} reached {expected_state}")
                return True

        await asyncio.sleep(5)

    logger.error(f"Wave health check failed: no occurrences reached {expected_state}")
    return False
```

## Implementation Details

### Database Schema Changes

**No schema changes needed!** Use existing `tasks` table with:
- `agent_occurrence_id = "__shared__"` for shared tasks
- Existing status tracking (PENDING, COMPLETED, FAILED)

### New Files

1. **`ciris_engine/logic/runtime/occurrence_canary_coordinator.py`**
   - `OccurrenceCanaryCoordinator` class
   - Wave orchestration logic
   - Health checking

2. **`ciris_engine/schemas/runtime/occurrence.py`**
   - `OccurrenceGroup` enum (EXPLORER, EARLY_ADOPTER, GENERAL)
   - `OccurrenceRolloutStatus` model
   - `CanaryWaveConfig` model

### Modified Files

1. **`ciris_engine/logic/processors/states/wakeup_processor.py`**
   - Add completion check at start of `process()`
   - Modify task creation to use `agent_occurrence_id="__shared__"`
   - Enhance wakeup message with multi-occurrence context
   - Trigger canary rollout after completion

2. **`ciris_engine/logic/processors/states/shutdown_processor.py`**
   - Add decision check at start of `process()`
   - Modify task creation to use `agent_occurrence_id="__shared__"`
   - Enhance shutdown message with canary rollout plan
   - Trigger canary rollout after decision

3. **`ciris_engine/logic/persistence/models/tasks.py`**
   - Add helper: `get_shared_task_status(task_prefix: str) -> Optional[TaskStatus]`
   - Add helper: `is_shared_task_completed(task_prefix: str) -> bool`

## Rollout Timeline Example

**Scenario**: 9 occurrences, shutdown accepted

```
T+0:00  Explorer (occurrence-1) decides ACCEPT
        Shared task marked COMPLETED with outcome={decision: "accept", ...}

T+0:30  Explorer shutdown complete, validated

T+1:00  Early Adopters (occurrence-2, occurrence-3, occurrence-4) begin shutdown
        Remaining 5 occurrences handle all traffic

T+2:00  Early Adopters shutdown complete, validated

T+3:00  General (occurrence-5 through occurrence-9) begin shutdown

T+5:00  All occurrences shut down gracefully
```

## Error Handling

### Wave Failure Scenarios

**Explorer fails to reach WORK after wakeup:**
- Abort rollout
- Mark shared task as FAILED
- Log incident
- Require manual intervention

**Early Adopter wave fails:**
- Abort rollout to general wave
- Explorer + healthy early adopters remain running
- Log incident
- Await manual decision

**General wave partial failure:**
- Continue (best effort)
- Log failures
- Service remains available with healthy occurrences

### Rollback Strategy

**If canary wakeup fails:**
- Failed occurrences remain in SHUTDOWN state
- Healthy occurrences continue serving
- No automatic rollback (requires manual recovery)

**If canary shutdown fails:**
- Stuck occurrences continue running
- Manual intervention required
- Emergency shutdown API can force termination

## Testing Strategy

### Unit Tests

1. **Task Completion Detection**
   - Test `is_shared_task_completed()` logic
   - Verify shared task queries work correctly

2. **Canary Group Assignment**
   - Test deterministic group assignment
   - Verify 70/20/10 split for various occurrence counts

3. **Wave Orchestration**
   - Test wave timing logic
   - Verify health check integration

### Integration Tests

1. **Multi-Occurrence Wakeup**
   - Start 9 occurrences simultaneously
   - Verify only one processes wakeup
   - Verify others skip and log correctly

2. **Canary Shutdown**
   - Request shutdown with 9 running occurrences
   - Verify wave-by-wave shutdown
   - Verify service availability throughout

3. **Failure Scenarios**
   - Explorer fails health check
   - Early adopter wave mixed success
   - Verify rollout aborts appropriately

## Success Metrics

1. **No Redundant Processing**: Only 1 occurrence processes wakeup/shutdown decision
2. **Service Availability**: >80% capacity maintained during shutdown rollout
3. **Safety**: Failed waves prevent further rollout
4. **Transparency**: Logs clearly show wave progression
5. **Auditability**: Shared task records complete decision trail

## Migration Plan

### Phase 1: Add Shared Task Support (Week 1)
- Implement `__shared__` occurrence ID support in persistence layer
- Add shared task query helpers
- No behavior change (feature flag disabled)

### Phase 2: Update Processors (Week 1-2)
- Modify wakeup processor with completion check
- Modify shutdown processor with decision check
- Add enhanced messaging
- Feature flag: `ENABLE_MULTI_OCCURRENCE_COORDINATION=false`

### Phase 3: Add Canary Coordinator (Week 2)
- Implement `OccurrenceCanaryCoordinator`
- Add occurrence discovery
- Add wave health checking
- Feature flag: `ENABLE_CANARY_ROLLOUT=false`

### Phase 4: Testing & Validation (Week 3)
- Test with 3, 9, 20 occurrence deployments
- Validate failure scenarios
- Performance testing

### Phase 5: Production Rollout (Week 4)
- Enable `ENABLE_MULTI_OCCURRENCE_COORDINATION=true` on staging
- Monitor for 1 week
- Enable `ENABLE_CANARY_ROLLOUT=true` on staging
- Monitor for 1 week
- Rollout to production

## Open Questions

1. **How to signal wakeup to other occurrences?**
   - Option A: Update shared task status to trigger
   - Option B: Send signal via inter-process communication
   - Option C: Each occurrence polls shared task status
   - **Recommendation**: Option C (polling) - simplest, database-driven

2. **What if occurrence count is unknown?**
   - Discovery via database queries (implemented above)
   - Fallback to treating each occurrence independently
   - Log warning if discovery fails

3. **Should canary groups be configurable?**
   - Start with hardcoded 70/20/10 split
   - Add configuration later if needed

4. **How to handle mixed versions during deployment?**
   - Old occurrences: Process tasks independently (existing behavior)
   - New occurrences: Check for completion, respect shared tasks
   - Gradual migration as CIRISManager updates occurrences

## References

- **CIRISManager Canary Pattern**: `../CIRISManager/ciris_manager/deployment_orchestrator.py`
  - `_run_canary_deployment()` - Lines 2349-2600
  - `_check_canary_group_health()` - Lines 2128-2260
  - Wave coordination: explorers → early_adopters → general

- **CIRIS Covenant Section VIII**: Dignified Sunset
  - Emphasizes single entity with graceful lifecycle
  - Supports phased, thoughtful shutdown

- **Existing CIRIS Architecture**:
  - `agent_occurrence_id` field already in Task/Thought schemas
  - Database already supports occurrence isolation
  - Just needs `__shared__` convention
