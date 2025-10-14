# Multi-Occurrence API Deployment - Implementation Plan

## Executive Summary

**Goal**: Enable running multiple API-only CIRIS agent instances (occurrences) against the same SQLite database, with each runtime instance processing only its own work while sharing a single agent identity.

**Status**: ✅ FEASIBLE - Implementation is straightforward with clear phase boundaries

**Effort Estimate**: ~8-12 hours development + 4-6 hours testing

---

## Architecture Analysis

### Current Single-Occurrence Assumptions

After comprehensive codebase review, the following components assume single-tenant access:

#### 1. **Schema Layer** (`001_initial_schema.sql`)
```sql
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    channel_id TEXT NOT NULL,
    -- NO agent_occurrence_id column
    ...
);

CREATE TABLE IF NOT EXISTS thoughts (
    thought_id TEXT PRIMARY KEY,
    source_task_id TEXT NOT NULL,
    -- NO agent_occurrence_id column
    ...
);
```
- **Issue**: All rows are globally visible to all processors
- **Impact**: Multiple instances would compete for the same tasks/thoughts

#### 2. **Domain Models** (`schemas/runtime/models.py:63-109`)
```python
class Task(BaseModel):
    task_id: str
    channel_id: str
    # Missing: agent_occurrence_id field
    ...

class Thought(BaseModel):
    thought_id: str
    source_task_id: str
    # Missing: agent_occurrence_id field
    ...
```
- **Issue**: No field to track which occurrence owns each work item
- **Impact**: Cannot filter at application layer

#### 3. **Persistence API** (`logic/persistence/models/tasks.py`)
```python
def get_tasks_by_status(status: TaskStatus, db_path: Optional[str] = None) -> List[Task]:
    """Returns all tasks with the given status from the tasks table."""
    sql = "SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC"
    # Missing: WHERE agent_occurrence_id = ? clause
```
- **Issue**: 17 functions query globally without occurrence filtering
- **Impact**: Tasks created by occurrence A would be picked up by occurrence B

**Key Functions Requiring Changes**:
- `get_tasks_by_status()` (L17)
- `get_all_tasks()` (L36)
- `add_task()` (L51)
- `get_task_by_id()` (L83)
- `update_task_status()` (L98)
- `get_pending_tasks_for_activation()` (L173)
- `count_tasks()` (L181)
- `get_active_task_for_channel()` (L267) ⚠️ **CRITICAL**
- `set_task_updated_info_flag()` (L291) ⚠️ **CRITICAL**

#### 4. **Queue Management** (`logic/processors/support/task_manager.py`, `thought_manager.py`)

**TaskManager**:
```python
def create_task(self, description: str, channel_id: str, ...) -> Task:
    """Create a new task with v1 schema."""
    task = Task(
        task_id=str(uuid.uuid4()),
        channel_id=channel_id,
        # Missing: agent_occurrence_id=self.occurrence_id
        ...
    )
    persistence.add_task(task)
```
- **Issue**: No occurrence_id stamping on creation (L34-75)
- **Issue**: `activate_pending_tasks()` pulls from global pool (L77-107)

**ThoughtManager**:
```python
def generate_seed_thought(self, task: Task, round_number: int) -> Optional[Thought]:
    thought = Thought(
        thought_id=generate_thought_id(...),
        # Missing: agent_occurrence_id from task
        ...
    )
```
- **Issue**: No occurrence_id propagation (L32-109)
- **Issue**: `populate_queue()` uses global analytics (L126-161)

#### 5. **Analytics** (`logic/persistence/analytics.py`)
```python
def get_pending_thoughts_for_active_tasks(limit: Optional[int] = None) -> List[Thought]:
    """Return all thoughts pending or processing for ACTIVE tasks."""
    active_tasks = get_tasks_by_status(TaskStatus.ACTIVE)
    # Missing: occurrence_id filter
```
- **Issue**: All 8 functions operate on global dataset (L13-70)
- **Impact**: Queue metrics and task selection would see other instances' work

#### 6. **Observer Layer** (`logic/adapters/base_observer.py`)
```python
async def _create_passive_observation_result(...) -> Optional[PassiveObservationResult]:
    # Check if there's an active task for this channel
    existing_task = get_active_task_for_channel(channel_id)
    # Issue: Would find tasks from OTHER occurrences!

    task = Task(
        task_id=str(uuid.uuid4()),
        channel_id=channel_id,
        # Missing: agent_occurrence_id=self.runtime.occurrence_id
        ...
    )
```
- **Issue**: Task creation without occurrence stamping (L554-568)
- **Issue**: `get_active_task_for_channel()` checks globally (L525) ⚠️ **CRITICAL**

#### 7. **Runtime Configuration**
- **Issue**: No `agent_occurrence_id` config parameter exposed
- **Issue**: No mechanism to inject occurrence_id into TaskManager/ThoughtManager
- **File**: `schemas/config/essential.py:63-123`

---

## Implementation Plan

### Phase 1: Schema Migration (Priority: CRITICAL)

**Goal**: Add `agent_occurrence_id` column to tasks and thoughts tables

**Migration File**: `ciris_engine/logic/persistence/migrations/00X_add_occurrence_id.sql`

```sql
-- Add agent_occurrence_id to tasks table
ALTER TABLE tasks ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';

-- Add agent_occurrence_id to thoughts table
ALTER TABLE thoughts ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';

-- Create composite indexes for efficient occurrence-scoped queries
CREATE INDEX IF NOT EXISTS idx_tasks_occurrence_status
    ON tasks(agent_occurrence_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_tasks_occurrence_channel
    ON tasks(agent_occurrence_id, channel_id, status);

CREATE INDEX IF NOT EXISTS idx_thoughts_occurrence_status
    ON thoughts(agent_occurrence_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_thoughts_occurrence_task
    ON thoughts(agent_occurrence_id, source_task_id);

-- Backfill existing rows with 'default' occurrence
-- (Already handled by DEFAULT value in ALTER TABLE)

-- Update scheduled_tasks if scheduler will run per-occurrence
ALTER TABLE scheduled_tasks ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_occurrence
    ON scheduled_tasks(agent_occurrence_id, status, next_trigger_at);
```

**Testing**:
- ✅ Verify migration runs cleanly on fresh DB
- ✅ Verify migration runs cleanly on existing DB with data
- ✅ Verify indexes exist after migration
- ✅ Verify all existing rows have 'default' value

**Rollback Strategy**:
SQLite doesn't support `ALTER TABLE DROP COLUMN` directly, so rollback requires:
1. Create new tables without occurrence_id
2. Copy data back (excluding occurrence_id)
3. Drop old tables, rename new tables

**Effort**: 1-2 hours

---

### Phase 2: Domain Models (Priority: HIGH)

**Goal**: Add `agent_occurrence_id` field to Task, Thought, and Context models

**File**: `ciris_engine/schemas/runtime/models.py`

```python
class TaskContext(BaseModel):
    """Typed context for tasks."""
    channel_id: Optional[str] = Field(None, description="Channel where task originated")
    user_id: Optional[str] = Field(None, description="User who created task")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    parent_task_id: Optional[str] = Field(None, description="Parent task if nested")
    agent_occurrence_id: str = Field(  # NEW
        "default",
        description="Runtime occurrence ID that owns this task"
    )

class Task(BaseModel):
    """Core task object - the unit of work."""
    task_id: str = Field(..., description="Unique task identifier")
    channel_id: str = Field(..., description="Channel where task originated")
    agent_occurrence_id: str = Field(  # NEW
        "default",
        description="Runtime occurrence ID that owns this task"
    )
    # ... rest of fields

class ThoughtContext(BaseModel):
    """Typed context for thoughts."""
    task_id: str = Field(..., description="Parent task ID")
    channel_id: Optional[str] = Field(None, description="Channel where thought operates")
    agent_occurrence_id: str = Field(  # NEW
        "default",
        description="Runtime occurrence ID (inherited from task)"
    )
    # ... rest of fields

class Thought(BaseModel):
    """Core thought object - a single reasoning step."""
    thought_id: str = Field(..., description="Unique thought identifier")
    source_task_id: str = Field(..., description="Task that generated this thought")
    agent_occurrence_id: str = Field(  # NEW
        "default",
        description="Runtime occurrence ID (inherited from task)"
    )
    # ... rest of fields
```

**Testing**:
- ✅ Verify mypy passes with new fields
- ✅ Verify Pydantic validation works
- ✅ Verify model_dump() includes new fields
- ✅ Verify JSON serialization/deserialization works

**Effort**: 0.5 hours

---

### Phase 3: Persistence API Updates (Priority: CRITICAL)

**Goal**: Thread `agent_occurrence_id` through all persistence functions

**File**: `ciris_engine/logic/persistence/models/tasks.py`

#### 3.1: Update Read Functions

```python
def get_tasks_by_status(
    status: TaskStatus,
    occurrence_id: str,  # NEW parameter
    db_path: Optional[str] = None
) -> List[Task]:
    """Returns all tasks with the given status and occurrence from the tasks table."""
    sql = "SELECT * FROM tasks WHERE status = ? AND agent_occurrence_id = ? ORDER BY created_at ASC"
    #                                           ^^^ NEW clause
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (status.value, occurrence_id))  # Added occurrence_id
            rows = cursor.fetchall()
            for row in rows:
                tasks_list.append(map_row_to_task(row))
    except Exception as e:
        logger.exception(f"Failed to get tasks with status {status.value}: {e}")
    return tasks_list

# Similar updates for:
def get_all_tasks(occurrence_id: str, db_path: Optional[str] = None) -> List[Task]: ...
def get_task_by_id(task_id: str, occurrence_id: str, db_path: Optional[str] = None) -> Optional[Task]: ...
def get_pending_tasks_for_activation(occurrence_id: str, limit: int = 10, db_path: Optional[str] = None) -> List[Task]: ...
def count_tasks(status: Optional[TaskStatus], occurrence_id: str, db_path: Optional[str] = None) -> int: ...
def get_active_task_for_channel(channel_id: str, occurrence_id: str, db_path: Optional[str] = None) -> Optional[Task]: ...
```

#### 3.2: Update Write Functions

```python
def add_task(task: Task, db_path: Optional[str] = None) -> str:
    """Add task with occurrence_id field."""
    task_dict = task.model_dump(mode="json")
    sql = """
        INSERT INTO tasks (
            task_id, channel_id, agent_occurrence_id, description, status, ...
        )                     ^^^ NEW column
        VALUES (
            :task_id, :channel_id, :agent_occurrence_id, :description, :status, ...
        )
    """
    params = {
        **task_dict,
        "status": task.status.value,
        "agent_occurrence_id": task.agent_occurrence_id,  # NEW
        # ... rest of params
    }
    # ... rest of function

def update_task_status(
    task_id: str,
    new_status: TaskStatus,
    occurrence_id: str,  # NEW parameter for safety check
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None
) -> bool:
    """Update task status only if it belongs to this occurrence."""
    sql = """
        UPDATE tasks
        SET status = ?, updated_at = ?
        WHERE task_id = ? AND agent_occurrence_id = ?
    """                         ^^^ NEW safety check
    params = (new_status.value, time_service.now_iso(), task_id, occurrence_id)
    # ... rest of function
```

#### 3.3: Critical Safety Update

```python
def set_task_updated_info_flag(
    task_id: str,
    updated_content: str,
    occurrence_id: str,  # NEW parameter
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None
) -> bool:
    """Set updated_info_available flag only if task belongs to this occurrence."""
    # First verify the task belongs to this occurrence
    task = get_task_by_id(task_id, occurrence_id, db_path)
    if not task or task.agent_occurrence_id != occurrence_id:
        logger.warning(
            f"Task {task_id} does not belong to occurrence {occurrence_id}, "
            f"cannot set updated_info_available flag"
        )
        return False

    # ... rest of existing logic with occurrence_id in WHERE clause
    sql = """
        UPDATE tasks
        SET updated_info_available = 1,
            updated_info_content = ?,
            updated_at = ?
        WHERE task_id = ? AND agent_occurrence_id = ?
    """                         ^^^ NEW safety check
    params = (updated_content, time_service.now_iso(), task_id, occurrence_id)
    # ... rest of function
```

**Similar updates needed for**:
- `ciris_engine/logic/persistence/models/thoughts.py` (12 functions)
- `ciris_engine/logic/persistence/utils.py` (`map_row_to_task`, `map_row_to_thought`)

**Testing**:
- ✅ Unit tests for each function with occurrence filtering
- ✅ Verify cross-occurrence isolation (occurrence A can't see occurrence B's tasks)
- ✅ Verify safety checks prevent cross-occurrence updates

**Effort**: 3-4 hours

---

### Phase 4: Queue Services (Priority: HIGH)

**Goal**: Update TaskManager and ThoughtManager to inject and use occurrence_id

**File**: `ciris_engine/logic/processors/support/task_manager.py`

```python
class TaskManager:
    """Manages task lifecycle operations."""

    def __init__(
        self,
        max_active_tasks: int = 10,
        time_service: Optional["TimeServiceProtocol"] = None,
        agent_occurrence_id: str = "default",  # NEW parameter
    ) -> None:
        self.max_active_tasks = max_active_tasks
        self._time_service = time_service
        self.agent_occurrence_id = agent_occurrence_id  # NEW field

    def create_task(
        self,
        description: str,
        channel_id: str,
        priority: int = 0,
        context: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[str] = None,
    ) -> Task:
        """Create a new task with occurrence_id stamped."""
        task_context = TaskContext(
            channel_id=channel_id,
            user_id=context_dict.get("user_id"),
            correlation_id=context_dict.get("correlation_id", str(uuid.uuid4())),
            parent_task_id=parent_task_id,
            agent_occurrence_id=self.agent_occurrence_id,  # NEW
        )

        task = Task(
            task_id=str(uuid.uuid4()),
            channel_id=channel_id,
            agent_occurrence_id=self.agent_occurrence_id,  # NEW
            description=description,
            status=TaskStatus.PENDING,
            # ... rest of fields
        )
        persistence.add_task(task)
        return task

    def activate_pending_tasks(self) -> int:
        """Activate pending tasks up to the configured limit (occurrence-scoped)."""
        num_active = persistence.count_active_tasks(self.agent_occurrence_id)  # NEW param
        can_activate = max(0, self.max_active_tasks - num_active)

        if can_activate == 0:
            return 0

        pending_tasks = persistence.get_pending_tasks_for_activation(
            occurrence_id=self.agent_occurrence_id,  # NEW param
            limit=can_activate
        )

        activated_count = 0
        for task in pending_tasks:
            if persistence.update_task_status(
                task.task_id,
                TaskStatus.ACTIVE,
                self.agent_occurrence_id,  # NEW param
                self.time_service
            ):
                activated_count += 1
        return activated_count

    def get_tasks_needing_seed(self, limit: int = 50) -> List[Task]:
        """Get active tasks that need seed thoughts (occurrence-scoped)."""
        tasks = persistence.get_tasks_needing_seed_thought(
            self.agent_occurrence_id,  # NEW param
            limit
        )
        # ... rest of function
```

**File**: `ciris_engine/logic/processors/support/thought_manager.py`

```python
class ThoughtManager:
    """Manages thought generation, queueing, and processing."""

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        max_active_thoughts: int = 50,
        default_channel_id: Optional[str] = None,
        agent_occurrence_id: str = "default",  # NEW parameter
    ) -> None:
        self.time_service = time_service
        self.max_active_thoughts = max_active_thoughts
        self.default_channel_id = default_channel_id
        self.agent_occurrence_id = agent_occurrence_id  # NEW field
        self.processing_queue: Deque[ProcessingQueueItem] = collections.deque()

    def generate_seed_thought(self, task: Task, round_number: int = 0) -> Optional[Thought]:
        """Generate a seed thought for a task - inherit occurrence_id from task."""
        thought_context = ThoughtContext(
            task_id=task.task_id,
            channel_id=task.context.channel_id if task.context else None,
            agent_occurrence_id=task.agent_occurrence_id,  # NEW - inherit from task
            round_number=round_number,
            depth=0,
            parent_thought_id=None,
            correlation_id=task.context.correlation_id if task.context else str(uuid.uuid4()),
        )

        thought = Thought(
            thought_id=generate_thought_id(...),
            source_task_id=task.task_id,
            agent_occurrence_id=task.agent_occurrence_id,  # NEW - inherit from task
            channel_id=channel_id,
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            # ... rest of fields
        )
        persistence.add_thought(thought)
        return thought

    def populate_queue(self, round_number: int) -> int:
        """Populate the processing queue (occurrence-scoped)."""
        self.processing_queue.clear()

        pending_thoughts = persistence.get_pending_thoughts_for_active_tasks(
            occurrence_id=self.agent_occurrence_id,  # NEW param
            limit=self.max_active_thoughts
        )
        # ... rest of function
```

**File**: `ciris_engine/logic/persistence/analytics.py`

```python
def get_pending_thoughts_for_active_tasks(
    occurrence_id: str,  # NEW parameter
    limit: Optional[int] = None
) -> List[Thought]:
    """Return all thoughts pending or processing for ACTIVE tasks (occurrence-scoped)."""
    active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, occurrence_id)  # NEW param
    active_task_ids = {t.task_id for t in active_tasks}
    pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING, occurrence_id)  # NEW param
    processing_thoughts = get_thoughts_by_status(ThoughtStatus.PROCESSING, occurrence_id)  # NEW param
    all_thoughts = pending_thoughts + processing_thoughts
    filtered = [th for th in all_thoughts if th.source_task_id in active_task_ids]
    if limit is not None:
        return filtered[:limit]
    return filtered

# Similar updates for all 8 functions in analytics.py
```

**Testing**:
- ✅ Verify occurrence isolation in task activation
- ✅ Verify occurrence isolation in thought generation
- ✅ Verify queue population only sees own work
- ✅ Integration test: Two TaskManagers with different occurrence_ids don't interfere

**Effort**: 2-3 hours

---

### Phase 5: Observer & Adapter Layers (Priority: CRITICAL)

**Goal**: Stamp occurrence_id on task creation and filter lookups

**File**: `ciris_engine/logic/adapters/base_observer.py`

```python
class BaseObserver[MessageT: BaseModel](ABC):
    """Common functionality for message observers."""

    def __init__(
        self,
        on_observe: Callable[[JSONDict], Awaitable[None]],
        bus_manager: Optional[BusManager] = None,
        memory_service: Optional[Any] = None,
        agent_id: Optional[str] = None,
        filter_service: Optional[Any] = None,
        secrets_service: Optional[SecretsService] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        auth_service: Optional[Any] = None,
        observer_wa_id: Optional[str] = None,
        agent_occurrence_id: str = "default",  # NEW parameter
        *,
        origin_service: str = "unknown",
        resource_monitor: Optional[ResourceMonitorServiceProtocol] = None,
    ) -> None:
        # ... existing fields
        self.agent_occurrence_id = agent_occurrence_id  # NEW field

    async def _create_passive_observation_result(
        self, msg: MessageT, priority: int = 0, filter_result: Optional[Any] = None
    ) -> Optional[PassiveObservationResult]:
        """Create passive observation result (task + thought) with occurrence_id."""

        # CRITICAL: Check for existing task WITH occurrence filtering
        from ciris_engine.logic.persistence.models.tasks import (
            get_active_task_for_channel,
            set_task_updated_info_flag,
        )

        existing_task = get_active_task_for_channel(
            channel_id,
            self.agent_occurrence_id  # NEW param - only check OUR tasks
        )

        if existing_task and self.time_service:
            # Try to update the existing task
            update_content = f"@{msg.author_name} (ID: {msg.author_id}): {formatted_passive_content}"
            success = set_task_updated_info_flag(
                existing_task.task_id,
                update_content,
                self.agent_occurrence_id,  # NEW param - safety check
                self.time_service
            )
            if success:
                return PassiveObservationResult(
                    task_id=existing_task.task_id,
                    task_created=False,
                    existing_task_updated=True,
                )

        # Create new task with occurrence_id
        task = Task(
            task_id=str(uuid.uuid4()),
            channel_id=getattr(msg, "channel_id", "system"),
            agent_occurrence_id=self.agent_occurrence_id,  # NEW field
            description=description,
            status=TaskStatus.ACTIVE,
            priority=priority,
            created_at=self.time_service.now_iso() if self.time_service else ...,
            updated_at=self.time_service.now_iso() if self.time_service else ...,
            context=TaskContext(
                channel_id=getattr(msg, "channel_id", None),
                user_id=msg.author_id,
                correlation_id=msg.message_id,
                parent_task_id=None,
                agent_occurrence_id=self.agent_occurrence_id,  # NEW field
            ),
        )
        await self._sign_and_add_task(task)

        # Create thought with occurrence_id inherited from task
        thought = Thought(
            thought_id=generate_thought_id(...),
            source_task_id=task.task_id,
            agent_occurrence_id=self.agent_occurrence_id,  # NEW field
            channel_id=getattr(msg, "channel_id", None),
            # ... rest of fields
            context=ThoughtModelContext(
                task_id=task.task_id,
                channel_id=getattr(msg, "channel_id", None),
                agent_occurrence_id=self.agent_occurrence_id,  # NEW field
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id=msg.message_id,
            ),
        )
        persistence.add_thought(thought)

        return PassiveObservationResult(
            task_id=task.task_id,
            task_created=True,
            thought_id=thought.thought_id,
            existing_task_updated=False,
        )
```

**Adapter-specific changes**:
Each adapter (Discord, API, CLI) needs to inject occurrence_id when creating observers:

**File**: `ciris_engine/logic/adapters/api/adapter.py`

```python
# During adapter startup (around L318-333)
observer = self.create_observer(
    on_observe=self.process_observation,
    bus_manager=self.bus_manager,
    agent_id=agent_id,
    agent_occurrence_id=occurrence_id,  # NEW - from runtime config
    # ... other params
)
```

**Testing**:
- ✅ Verify tasks created by observer have correct occurrence_id
- ✅ Verify existing task lookup only finds same-occurrence tasks
- ✅ Integration test: Two observers with different occurrence_ids create isolated tasks

**Effort**: 2-3 hours

---

### Phase 6: Runtime Configuration (Priority: HIGH)

**Goal**: Expose `agent_occurrence_id` as a configurable setting

**File**: `ciris_engine/schemas/config/essential.py`

```python
class AgentConfig(BaseModel):
    """Core agent configuration."""
    name: str = Field(..., description="Agent name")
    purpose: str = Field(..., description="Agent purpose statement")
    agent_occurrence_id: str = Field(  # NEW
        default="default",
        description="Unique ID for this runtime occurrence (for multi-instance deployments)"
    )
    # ... rest of fields
```

**File**: Runtime initialization (wherever AgentConfig is loaded)

```python
# Load config
config = AgentConfig.from_env()  # or from file

# Pass occurrence_id to TaskManager
task_manager = TaskManager(
    max_active_tasks=config.max_active_tasks,
    time_service=time_service,
    agent_occurrence_id=config.agent_occurrence_id  # NEW
)

# Pass occurrence_id to ThoughtManager
thought_manager = ThoughtManager(
    time_service=time_service,
    max_active_thoughts=50,
    default_channel_id=config.default_channel_id,
    agent_occurrence_id=config.agent_occurrence_id  # NEW
)

# Pass occurrence_id to BaseObserver
observer = DiscordObserver(
    on_observe=...,
    bus_manager=...,
    agent_id=config.agent_id,
    agent_occurrence_id=config.agent_occurrence_id,  # NEW
    # ... other params
)
```

**Environment Variable Support**:
```bash
# .env or docker-compose.yml
AGENT_OCCURRENCE_ID=api-instance-1

# Or for Kubernetes
AGENT_OCCURRENCE_ID=api-pod-${POD_NAME}
```

**Testing**:
- ✅ Verify occurrence_id loads from config
- ✅ Verify occurrence_id propagates to all managers
- ✅ Verify default value ("default") works for single-instance deployments

**Effort**: 1 hour

---

### Phase 7: Testing & Validation (Priority: CRITICAL)

#### 7.1: Unit Tests

**New test files**:
- `tests/test_multi_occurrence_persistence.py` - Verify occurrence filtering in all persistence functions
- `tests/test_multi_occurrence_isolation.py` - Verify two TaskManagers with different IDs don't interfere
- `tests/test_multi_occurrence_safety.py` - Verify cross-occurrence update prevention

**Example test**:
```python
def test_occurrence_isolation_in_task_activation():
    """Verify two occurrences don't activate each other's tasks."""
    # Setup
    time_service = get_mock_time_service()

    # Create two task managers with different occurrence IDs
    manager_a = TaskManager(
        max_active_tasks=10,
        time_service=time_service,
        agent_occurrence_id="occurrence-a"
    )
    manager_b = TaskManager(
        max_active_tasks=10,
        time_service=time_service,
        agent_occurrence_id="occurrence-b"
    )

    # Manager A creates a pending task
    task_a = manager_a.create_task(
        description="Task from A",
        channel_id="test-channel",
        priority=1
    )
    assert task_a.agent_occurrence_id == "occurrence-a"
    assert task_a.status == TaskStatus.PENDING

    # Manager B should not see or activate Manager A's task
    activated_by_b = manager_b.activate_pending_tasks()
    assert activated_by_b == 0, "Manager B should not activate Manager A's tasks"

    # Verify task_a is still pending
    task_a_check = persistence.get_task_by_id(task_a.task_id, "occurrence-a")
    assert task_a_check.status == TaskStatus.PENDING

    # Manager A can activate its own task
    activated_by_a = manager_a.activate_pending_tasks()
    assert activated_by_a == 1, "Manager A should activate its own task"
```

**Effort**: 3-4 hours

#### 7.2: Integration Tests

**Test scenario**: Run two API instances against shared SQLite database
```python
@pytest.mark.integration
async def test_dual_api_instances():
    """Run two API instances with different occurrence_ids against same DB."""
    db_path = "/tmp/test_multi_occurrence.db"

    # Start instance 1
    config_1 = AgentConfig(
        name="TestAgent",
        purpose="Testing",
        agent_occurrence_id="api-instance-1"
    )
    adapter_1 = APIAdapter(config_1, db_path=db_path)
    await adapter_1.start()

    # Start instance 2
    config_2 = AgentConfig(
        name="TestAgent",
        purpose="Testing",
        agent_occurrence_id="api-instance-2"
    )
    adapter_2 = APIAdapter(config_2, db_path=db_path)
    await adapter_2.start()

    # Send message to instance 1
    response_1 = await adapter_1.handle_message(
        channel_id="test-channel",
        content="Hello instance 1",
        author_id="user-1"
    )
    task_1_id = response_1.task_id

    # Send message to instance 2
    response_2 = await adapter_2.handle_message(
        channel_id="test-channel",
        content="Hello instance 2",
        author_id="user-2"
    )
    task_2_id = response_2.task_id

    # Verify instance 1 only sees its own task
    tasks_1 = persistence.get_all_tasks("api-instance-1", db_path)
    assert len(tasks_1) == 1
    assert tasks_1[0].task_id == task_1_id

    # Verify instance 2 only sees its own task
    tasks_2 = persistence.get_all_tasks("api-instance-2", db_path)
    assert len(tasks_2) == 1
    assert tasks_2[0].task_id == task_2_id

    # Cleanup
    await adapter_1.stop()
    await adapter_2.stop()
```

**Effort**: 2-3 hours

#### 7.3: QA Runner Tests

**New test module**: `tools/qa_runner.py` - Add `multi_occurrence` module

```python
async def test_multi_occurrence_isolation():
    """QA test for multi-occurrence API deployment."""
    # Test that two API instances with different occurrence_ids
    # can handle requests concurrently without interference
    pass
```

**Effort**: 1 hour

---

## Edge Cases & Risks

### 1. **Scheduler Service** (scheduled_tasks table)

**Issue**: Should scheduler run once globally or per-occurrence?

**Recommendation**:
- **Option A (Recommended)**: Run scheduler on ONE occurrence only (e.g., occurrence_id = "scheduler")
- **Option B**: Add occurrence_id to scheduled_tasks and let each occurrence manage its own schedules

**Migration needed**: Phase 1 already includes `ALTER TABLE scheduled_tasks ADD COLUMN agent_occurrence_id`

### 2. **Telemetry & Audit Logs**

**Issue**: Current service_correlations and audit_log tables are global

**Recommendation**:
- **DO NOT** add occurrence_id to audit logs (want global audit trail)
- **DO** add occurrence_id to service_correlations for per-instance metrics
- Update telemetry queries to optionally filter by occurrence_id

**Migration**:
```sql
ALTER TABLE service_correlations ADD COLUMN agent_occurrence_id TEXT NOT NULL DEFAULT 'default';
CREATE INDEX IF NOT EXISTS idx_correlations_occurrence ON service_correlations(agent_occurrence_id);
```

### 3. **Graph Memory (graph_nodes, graph_edges)**

**Issue**: Should memory be per-occurrence or shared?

**Recommendation**:
- **Shared memory** - All occurrences share IDENTITY/ENVIRONMENT/LOCAL scopes
- No occurrence_id needed in graph tables
- Memory is global knowledge base, not per-occurrence

### 4. **WA Certificates (wa_cert table)**

**Issue**: Should WA certs be per-occurrence?

**Recommendation**:
- **Shared WA certs** - Single agent identity across all occurrences
- No occurrence_id needed
- All occurrences authenticate as the same agent

### 5. **Channel-Scoped Tasks**

**Critical**: `get_active_task_for_channel()` currently assumes one active task per channel globally

**With multi-occurrence**:
- Each occurrence can have ONE active task per channel
- Prevents race conditions where two instances try to respond to same message

**Query becomes**:
```sql
SELECT * FROM tasks
WHERE channel_id = ?
  AND status = 'ACTIVE'
  AND agent_occurrence_id = ?  -- NEW
ORDER BY created_at DESC
LIMIT 1
```

### 6. **Migration of Existing Data**

**Issue**: What happens to tasks/thoughts created before migration?

**Solution**:
- All existing rows get `agent_occurrence_id = 'default'`
- Single-instance deployments continue using `occurrence_id = 'default'`
- No behavioral change for existing deployments

---

## Rollout Strategy

### Step 1: Development & Testing (Branch: feature/multi-occurrence)
- Implement Phases 1-6
- Run full test suite
- QA runner validation

### Step 2: Staging Deployment
- Deploy to staging with `occurrence_id = "default"`
- Verify no behavioral changes
- Monitor for 24 hours

### Step 3: Multi-Occurrence Testing
- Deploy 2-3 API instances to staging with different occurrence_ids
- Send concurrent traffic
- Monitor for conflicts/errors
- Verify isolation

### Step 4: Production Rollout
- Deploy migration to production (adds columns, backwards compatible)
- Restart existing instances with `occurrence_id = "default"` (no change)
- Gradually add new API instances with unique occurrence_ids
- Monitor queue metrics, task activation, response times

### Step 5: Documentation
- Update deployment docs with multi-occurrence configuration
- Add Kubernetes/Docker Compose examples
- Document occurrence_id naming conventions

---

## Success Criteria

✅ **Functional**:
- Two API instances can run against same SQLite database
- Each instance processes only its own tasks/thoughts
- No cross-occurrence interference observed
- Channel-scoped task lookups work correctly per-occurrence

✅ **Performance**:
- No significant overhead from occurrence filtering (indexes mitigate)
- Response times remain under 1s
- Memory usage stays under 4GB per instance

✅ **Safety**:
- Cross-occurrence updates are blocked
- Existing single-instance deployments continue working
- Migration is reversible

✅ **Testing**:
- 100% test coverage for new occurrence filtering code
- Integration tests pass for dual-instance scenario
- QA runner validates multi-occurrence isolation

---

## Timeline

| Phase | Description | Effort | Dependencies |
|-------|-------------|--------|--------------|
| 1 | Schema Migration | 1-2h | None |
| 2 | Domain Models | 0.5h | Phase 1 |
| 3 | Persistence API | 3-4h | Phase 2 |
| 4 | Queue Services | 2-3h | Phase 3 |
| 5 | Observer/Adapter | 2-3h | Phase 3, 4 |
| 6 | Runtime Config | 1h | None (parallel) |
| 7 | Testing | 6-8h | Phase 1-6 complete |

**Total Development**: 16-21 hours
**Testing & QA**: 6-8 hours
**Documentation**: 2-3 hours

**Grand Total**: ~24-32 hours (~3-4 days)

---

## Conclusion

**Verdict**: ✅ **FEASIBLE AND RECOMMENDED**

The multi-occurrence architecture is:
- ✅ **Architecturally sound** - Clean separation of concerns
- ✅ **Backwards compatible** - Existing deployments unaffected
- ✅ **Safe** - Strong isolation guarantees
- ✅ **Testable** - Clear unit and integration test boundaries
- ✅ **Performant** - Minimal overhead with proper indexing

**Key Success Factors**:
1. Thorough testing of occurrence isolation
2. Proper index creation for performance
3. Safety checks in cross-cutting functions (get_active_task_for_channel, set_task_updated_info_flag)
4. Clear documentation for deployment configurations

**Risks**:
- Low risk if phases followed sequentially
- Critical path: Phase 3 (Persistence API) must be correct
- Edge case: Scheduler service needs decision on global vs per-occurrence

**Recommendation**: Proceed with implementation following the phased plan above.
