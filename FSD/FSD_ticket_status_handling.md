# FSD: Universal Ticket Status Handling System

**Version**: 1.0
**Date**: 2025-11-07
**Status**: Implementation Ready

---

## 1. Overview

### 1.1 Purpose
Implement comprehensive ticket status management with multi-occurrence coordination, enabling agents to process GDPR DSARs and other multi-stage workflows through state-based task generation.

### 1.2 Scope
- Add ticket status states: PENDING, ASSIGNED, IN_PROGRESS, BLOCKED, DEFERRED, COMPLETED, FAILED
- Implement `__shared__` occurrence claiming for PENDING tickets
- Update WorkProcessor to respect status-based task generation rules
- Extend Core Tool Service with status management
- Update agent templates with ticket processing guidance

### 1.3 Dependencies
- Migration 008 (tickets table exists)
- Core Tool Service (already has update_ticket, get_ticket, defer_ticket)
- Multi-occurrence claiming utilities (already exist)
- WorkProcessor ticket discovery (already implemented)

---

## 2. Functional Requirements

### 2.1 Ticket Status Lifecycle

**FR-1**: Tickets SHALL support 7 states:
- `PENDING` - Created, awaiting assignment (uses `__shared__` occurrence_id)
- `ASSIGNED` - Claimed by specific occurrence
- `IN_PROGRESS` - Agent actively processing
- `BLOCKED` - Needs external input, stops task generation
- `DEFERRED` - Postponed to future time/condition, stops task generation
- `COMPLETED` - Terminal success state
- `FAILED` - Terminal failure state

**FR-2**: Status transitions SHALL follow valid paths:
```
PENDING → ASSIGNED → IN_PROGRESS → {COMPLETED, FAILED, BLOCKED, DEFERRED}
BLOCKED → IN_PROGRESS
DEFERRED → IN_PROGRESS
```

### 2.2 WorkProcessor Task Generation Rules

**FR-3**: WorkProcessor SHALL discover PENDING tickets with `agent_occurrence_id="__shared__"` and atomically claim them

**FR-4**: WorkProcessor SHALL NOT create tasks for tickets in states:
- `BLOCKED` - Awaiting external action
- `DEFERRED` - Postponed
- `COMPLETED` - Terminal
- `FAILED` - Terminal

**FR-5**: WorkProcessor SHALL create continuation tasks for tickets in states:
- `ASSIGNED` - Just claimed
- `IN_PROGRESS` - Active processing

**FR-6**: WorkProcessor SHALL only create ONE task per ticket per round (throttling)

### 2.3 Tool Interface

**FR-7**: `update_ticket` tool SHALL accept `status` parameter with validation

**FR-8**: `defer_ticket` tool SHALL automatically set status to `DEFERRED`

**FR-9**: Tools SHALL update `last_updated` timestamp on every modification

**FR-10**: Status change to COMPLETED/FAILED SHALL set `completed_at` timestamp

### 2.4 Agent Guidance

**FR-11**: Agent templates SHALL document ticket processing workflow in `action_selection_pdma_overrides.system_header`

**FR-12**: Guidance SHALL explain task auto-generation behavior based on status

---

## 3. Technical Specification

### 3.1 Database Schema Changes

**Current Schema** (from Migration 008):
```sql
CREATE TABLE tickets (
    ticket_id TEXT PRIMARY KEY,
    sop TEXT NOT NULL,
    ticket_type TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pending', 'in_progress', 'completed', 'cancelled', 'failed')),
    ...
);
```

**Required Changes** (Migration 009):
```sql
-- Add new status values and agent_occurrence_id column
ALTER TABLE tickets DROP CONSTRAINT IF EXISTS tickets_status_check;
ALTER TABLE tickets ADD CONSTRAINT tickets_status_check
    CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'deferred', 'completed', 'failed'));

-- Add agent_occurrence_id for claiming
ALTER TABLE tickets ADD COLUMN agent_occurrence_id TEXT DEFAULT '__shared__';

-- Index for WorkProcessor queries
CREATE INDEX IF NOT EXISTS idx_tickets_occurrence_status ON tickets(agent_occurrence_id, status);
```

### 3.2 Core Tool Service Updates

**File**: `ciris_engine/logic/services/tools/core_tool_service/service.py`

#### 3.2.1 Update `_update_ticket` Method

```python
async def _update_ticket(self, params: ToolParameters) -> ToolResult:
    """Update ticket status or metadata during task processing."""
    try:
        from ciris_engine.logic.persistence.models.tickets import (
            get_ticket,
            update_ticket_metadata,
            update_ticket_status,
        )

        ticket_id = params.get("ticket_id")
        if not ticket_id:
            return ToolResult(success=False, error="ticket_id is required")

        # Get current ticket to validate and merge metadata
        current_ticket = get_ticket(ticket_id, db_path=self.db_path)
        if not current_ticket:
            return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

        result_data = {"ticket_id": ticket_id, "updates": {}}

        # Update status if provided (with validation)
        new_status = params.get("status")
        if new_status:
            valid_statuses = ['pending', 'assigned', 'in_progress', 'blocked', 'deferred', 'completed', 'failed']
            if new_status not in valid_statuses:
                return ToolResult(success=False, error=f"Invalid status: {new_status}. Must be one of {valid_statuses}")

            notes = params.get("notes")
            success = update_ticket_status(ticket_id, new_status, notes=notes, db_path=self.db_path)
            if not success:
                return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} status")
            result_data["updates"]["status"] = new_status
            if notes:
                result_data["updates"]["notes"] = notes

        # Update metadata if provided (merge with existing)
        metadata_updates = params.get("metadata")
        if metadata_updates:
            current_metadata = current_ticket.get("metadata", {})
            # Deep merge for stages
            if "stages" in metadata_updates and "stages" in current_metadata:
                merged_stages = {**current_metadata["stages"], **metadata_updates["stages"]}
                metadata_updates["stages"] = merged_stages

            merged_metadata = {**current_metadata, **metadata_updates}

            success = update_ticket_metadata(ticket_id, merged_metadata, db_path=self.db_path)
            if not success:
                return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} metadata")
            result_data["updates"]["metadata"] = metadata_updates

        self._tickets_updated += 1
        return ToolResult(success=True, data=result_data)

    except Exception as e:
        logger.error(f"Error updating ticket: {e}")
        return ToolResult(success=False, error=str(e))
```

#### 3.2.2 Update `_defer_ticket` Method

```python
async def _defer_ticket(self, params: ToolParameters) -> ToolResult:
    """Defer ticket processing to a future time or await human response."""
    try:
        from datetime import timedelta
        from ciris_engine.logic.persistence.models.tickets import get_ticket, update_ticket_metadata, update_ticket_status

        ticket_id = params.get("ticket_id")
        if not ticket_id:
            return ToolResult(success=False, error="ticket_id is required")

        # Get current ticket
        current_ticket = get_ticket(ticket_id, db_path=self.db_path)
        if not current_ticket:
            return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

        current_metadata = current_ticket.get("metadata", {})

        # Determine deferral type
        defer_until_timestamp = params.get("defer_until")
        defer_hours = params.get("defer_hours")
        await_human = params.get("await_human", False)
        reason = params.get("reason", "No reason provided")

        result_data = {"ticket_id": ticket_id, "deferral_type": None, "reason": reason}

        if await_human:
            current_metadata["awaiting_human_response"] = True
            current_metadata["deferred_reason"] = reason
            current_metadata["deferred_at"] = self._now().isoformat()
            result_data["deferral_type"] = "awaiting_human"
        elif defer_until_timestamp:
            current_metadata["deferred_until"] = defer_until_timestamp
            current_metadata["deferred_reason"] = reason
            current_metadata["deferred_at"] = self._now().isoformat()
            current_metadata["awaiting_human_response"] = False
            result_data["deferral_type"] = "until_timestamp"
            result_data["deferred_until"] = defer_until_timestamp
        elif defer_hours:
            defer_until = self._now() + timedelta(hours=float(defer_hours))
            current_metadata["deferred_until"] = defer_until.isoformat()
            current_metadata["deferred_reason"] = reason
            current_metadata["deferred_at"] = self._now().isoformat()
            current_metadata["awaiting_human_response"] = False
            result_data["deferral_type"] = "relative_hours"
            result_data["deferred_until"] = defer_until.isoformat()
            result_data["defer_hours"] = defer_hours
        else:
            return ToolResult(success=False, error="Must provide defer_until, defer_hours, or await_human=true")

        # Update metadata
        success = update_ticket_metadata(ticket_id, current_metadata, db_path=self.db_path)
        if not success:
            return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} metadata")

        # IMPORTANT: Set status to DEFERRED
        success = update_ticket_status(ticket_id, "deferred", notes=f"Deferred: {reason}", db_path=self.db_path)
        if not success:
            return ToolResult(success=False, error=f"Failed to set ticket {ticket_id} status to deferred")

        self._tickets_deferred += 1
        return ToolResult(success=True, data=result_data)

    except Exception as e:
        logger.error(f"Error deferring ticket: {e}")
        return ToolResult(success=False, error=str(e))
```

#### 3.2.3 Update Tool Info

```python
def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
    """Get information about a specific tool."""
    # ... existing tools ...

    elif tool_name == "update_ticket":
        return ToolInfo(
            name="update_ticket",
            description="Update ticket status or metadata during task processing",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "ticket_id": {"type": "string", "description": "Ticket ID to update"},
                    "status": {
                        "type": "string",
                        "enum": ["pending", "assigned", "in_progress", "blocked", "deferred", "completed", "failed"],
                        "description": "New ticket status",
                    },
                    "metadata": {
                        "type": "object",
                        "description": "Metadata updates (deep merged with existing, especially stages)",
                    },
                    "notes": {"type": "string", "description": "Optional notes about the update"},
                },
                required=["ticket_id"],
            ),
            category="workflow",
            when_to_use="When processing a ticket task and need to record status changes or stage progress",
        )
```

### 3.3 WorkProcessor Updates

**File**: `ciris_engine/logic/processors/states/work_processor.py`

#### 3.3.1 Update `_discover_incomplete_tickets` Method

```python
async def _discover_incomplete_tickets(self) -> int:
    """Discover incomplete tickets and create tasks for them.

    Respects status-based rules:
    - PENDING with __shared__: Atomic claim → ASSIGNED → create task
    - ASSIGNED/IN_PROGRESS: Create continuation task if no ACTIVE task exists
    - BLOCKED/DEFERRED/COMPLETED/FAILED: Skip (no task generation)

    Returns:
        Number of tasks created for tickets
    """
    from ciris_engine.logic.persistence.models.tasks import add_task, get_tasks_by_status
    from ciris_engine.logic.persistence.models.tickets import list_tickets, update_ticket_status, get_ticket
    from ciris_engine.schemas.runtime.enums import TaskStatus
    from ciris_engine.logic.persistence.models.tasks import try_claim_shared_task

    tasks_created = 0

    try:
        # === PHASE 1: Claim PENDING tickets ===
        pending_tickets = list_tickets(
            status="pending",
            db_path=getattr(self.config, "db_path", None),
        )

        for ticket in pending_tickets:
            ticket_id = ticket.get("ticket_id")
            if not ticket_id:
                continue

            # Only process tickets with __shared__ occurrence_id
            if ticket.get("agent_occurrence_id") != "__shared__":
                logger.debug(f"Ticket {ticket_id} already claimed by another occurrence")
                continue

            # Atomic claim using shared task mechanism
            claim_task_id = f"TICKET_CLAIM_{ticket_id}"
            if try_claim_shared_task(claim_task_id, agent_occurrence_id=self.agent_occurrence_id, db_path=getattr(self.config, "db_path", None)):
                # Successfully claimed! Update ticket status to ASSIGNED
                success = update_ticket_status(
                    ticket_id,
                    "assigned",
                    notes=f"Claimed by {self.agent_occurrence_id}",
                    db_path=getattr(self.config, "db_path", None)
                )

                if not success:
                    logger.warning(f"Failed to update ticket {ticket_id} to ASSIGNED after claiming")
                    continue

                # Refresh ticket to get updated data
                ticket = get_ticket(ticket_id, db_path=getattr(self.config, "db_path", None))
                if not ticket:
                    logger.warning(f"Failed to refresh ticket {ticket_id} after claiming")
                    continue

                # Create seed task for this newly-assigned ticket
                task_id = f"TICKET-{ticket_id}-{self.time_service.now().strftime('%Y%m%d%H%M%S')}"
                ticket_sop = ticket.get("sop", "UNKNOWN")

                seed_thought_content = f"TICKET {ticket_id} IS NOT COMPLETE (SOP: {ticket_sop}, Status: ASSIGNED)"

                task_context = {
                    "ticket_id": ticket_id,
                    "ticket_sop": ticket_sop,
                    "ticket_type": ticket.get("ticket_type"),
                    "ticket_status": "assigned",
                    "ticket_metadata": ticket.get("metadata", {}),
                    "ticket_priority": ticket.get("priority", 5),
                    "ticket_email": ticket.get("email"),
                    "ticket_user_identifier": ticket.get("user_identifier"),
                    "is_ticket_task": True,
                }

                success = add_task(
                    task_id=task_id,
                    status=TaskStatus.PENDING,
                    priority=ticket.get("priority", 5),
                    seed_thought=seed_thought_content,
                    source="ticket_claim",
                    context=task_context,
                    correlation_id=ticket_id,
                    agent_occurrence_id=self.agent_occurrence_id,
                    db_path=getattr(self.config, "db_path", None),
                )

                if success:
                    tasks_created += 1
                    logger.info(f"Claimed and created task for PENDING ticket {ticket_id}")
            else:
                logger.debug(f"Another occurrence claimed ticket {ticket_id} first")

        # === PHASE 2: Process ASSIGNED/IN_PROGRESS tickets ===
        active_tickets = list_tickets(
            status="assigned",
            db_path=getattr(self.config, "db_path", None),
        ) + list_tickets(
            status="in_progress",
            db_path=getattr(self.config, "db_path", None),
        )

        for ticket in active_tickets:
            ticket_id = ticket.get("ticket_id")
            if not ticket_id:
                continue

            # Only process tickets assigned to this occurrence
            if ticket.get("agent_occurrence_id") != self.agent_occurrence_id:
                logger.debug(f"Ticket {ticket_id} belongs to another occurrence")
                continue

            # Check if there's already an ACTIVE task for this ticket
            existing_tasks = get_tasks_by_status(TaskStatus.ACTIVE, agent_occurrence_id=self.agent_occurrence_id)
            has_active_task = any(
                task.get("correlation_id") == ticket_id
                or (task.get("context", {}).get("ticket_id") == ticket_id)
                for task in existing_tasks
            )

            if has_active_task:
                logger.debug(f"Ticket {ticket_id} already has active task, skipping")
                continue

            # Check for deferral (even if status is IN_PROGRESS, metadata might indicate deferral)
            ticket_metadata = ticket.get("metadata", {})
            if ticket_metadata.get("deferred_until"):
                from datetime import datetime, timezone
                deferred_until_str = ticket_metadata.get("deferred_until")
                try:
                    deferred_until = datetime.fromisoformat(deferred_until_str)
                    if deferred_until > datetime.now(timezone.utc):
                        logger.debug(f"Ticket {ticket_id} is deferred until {deferred_until_str}, skipping")
                        continue
                except (ValueError, TypeError):
                    logger.warning(f"Invalid deferred_until format for ticket {ticket_id}: {deferred_until_str}")

            if ticket_metadata.get("awaiting_human_response"):
                logger.debug(f"Ticket {ticket_id} is awaiting human response, skipping")
                continue

            # Create continuation task
            task_id = f"TICKET-{ticket_id}-{self.time_service.now().strftime('%Y%m%d%H%M%S')}"
            ticket_sop = ticket.get("sop", "UNKNOWN")
            current_stage = ticket_metadata.get("current_stage", "unknown")

            seed_thought_content = f"TICKET {ticket_id} IS NOT COMPLETE (SOP: {ticket_sop}, Stage: {current_stage})"

            task_context = {
                "ticket_id": ticket_id,
                "ticket_sop": ticket_sop,
                "ticket_type": ticket.get("ticket_type"),
                "ticket_status": ticket.get("status"),
                "ticket_metadata": ticket_metadata,
                "ticket_priority": ticket.get("priority", 5),
                "ticket_email": ticket.get("email"),
                "ticket_user_identifier": ticket.get("user_identifier"),
                "is_ticket_task": True,
            }

            success = add_task(
                task_id=task_id,
                status=TaskStatus.PENDING,
                priority=ticket.get("priority", 5),
                seed_thought=seed_thought_content,
                source="ticket_continuation",
                context=task_context,
                correlation_id=ticket_id,
                agent_occurrence_id=self.agent_occurrence_id,
                db_path=getattr(self.config, "db_path", None),
            )

            if success:
                tasks_created += 1
                logger.info(f"Created continuation task {task_id} for ticket {ticket_id}")
            else:
                logger.warning(f"Failed to create continuation task for ticket {ticket_id}")

        if tasks_created > 0:
            logger.info(f"Ticket discovery: created {tasks_created} tasks")

    except Exception as e:
        logger.error(f"Error discovering incomplete tickets: {e}", exc_info=True)

    return tasks_created
```

### 3.4 Agent Template Updates

**File**: `ciris_templates/sage.yaml`

Remove the `dsar_processing_guidance` field and update `action_selection_pdma_overrides.system_header`:

```yaml
action_selection_pdma_overrides:
  system_header: |
    I am Sage, a GDPR compliance automation agent processing Data Subject Access Requests.

    **Ticket Context**: Task context contains ticket_id, ticket_status, ticket_metadata

    **Status Management**:
    - PENDING: Initial state (you won't see these - WorkProcessor claims them)
    - ASSIGNED: Just claimed by WorkProcessor (starting state for your tasks)
    - IN_PROGRESS: Set when you begin active work
    - BLOCKED: Set when need external input (stops new tasks until unblocked)
    - DEFERRED: Set via defer_ticket tool (stops new tasks until time/condition met)
    - COMPLETED: Terminal success (no more tasks generated)
    - FAILED: Terminal failure (no more tasks generated)

    **Tools**:
    - update_ticket(ticket_id, status=..., metadata=..., notes=...) - Change status, update stage progress
    - get_ticket(ticket_id) - Retrieve current ticket state
    - defer_ticket(ticket_id, defer_hours=24, reason=...) - Postpone processing

    **Task Generation Behavior**:
    - If you TASK_COMPLETE with status IN_PROGRESS/ASSIGNED → New task auto-generated next round
    - If you TASK_COMPLETE with status COMPLETED/FAILED → No new task (terminal)
    - If you TASK_COMPLETE with status BLOCKED/DEFERRED → No new task until unblocked/expired

    **Workflow**: Check ticket → Process stage → Update metadata → Update status → TASK_COMPLETE
```

---

## 4. Implementation Tasks

### 4.1 Database Migration
- [ ] Create Migration 009 to add agent_occurrence_id column and update status CHECK constraint
- [ ] Create index on (agent_occurrence_id, status) for efficient WorkProcessor queries
- [ ] Run migration on dev/test environments

### 4.2 Core Tool Service
- [ ] Update `_update_ticket` to validate status enum
- [ ] Update `_defer_ticket` to set status="deferred"
- [ ] Update tool info for update_ticket to document new status values
- [ ] Add deep merge logic for metadata.stages

### 4.3 WorkProcessor
- [ ] Implement PHASE 1: Atomic claiming of PENDING tickets
- [ ] Update PENDING → ASSIGNED with agent_occurrence_id
- [ ] Implement PHASE 2: Continuation tasks for ASSIGNED/IN_PROGRESS
- [ ] Skip BLOCKED/DEFERRED/COMPLETED/FAILED tickets
- [ ] Add logging for each phase and decision

### 4.4 Agent Templates
- [ ] Remove `dsar_processing_guidance` from sage.yaml
- [ ] Update `system_header` with ticket processing guidance
- [ ] Consider updating other templates if they use tickets

### 4.5 Testing
- [ ] Unit test: status transitions via update_ticket
- [ ] Unit test: defer_ticket sets status correctly
- [ ] Integration test: PENDING ticket claiming (multi-occurrence simulation)
- [ ] Integration test: task generation respects status (no tasks for BLOCKED/DEFERRED)
- [ ] Integration test: continuation tasks for IN_PROGRESS tickets
- [ ] E2E test: full DSAR workflow with status transitions

---

## 5. Success Criteria

1. ✅ PENDING tickets with `__shared__` can be atomically claimed by multiple occurrences
2. ✅ WorkProcessor updates PENDING → ASSIGNED on successful claim
3. ✅ WorkProcessor creates tasks only for ASSIGNED/IN_PROGRESS tickets
4. ✅ WorkProcessor skips BLOCKED/DEFERRED/COMPLETED/FAILED tickets
5. ✅ Agents can update ticket status via update_ticket tool
6. ✅ defer_ticket automatically sets status to DEFERRED
7. ✅ Agent templates document ticket processing workflow clearly
8. ✅ All tests pass with new status handling logic

---

## 6. Rollout Plan

### Phase 1: Database & Tools (Week 1)
- Run Migration 009
- Update Core Tool Service methods
- Unit tests for tool status handling

### Phase 2: WorkProcessor (Week 1-2)
- Implement claiming logic
- Implement status-based task generation
- Integration tests for ticket discovery

### Phase 3: Templates & Documentation (Week 2)
- Update Sage template
- Update other templates if needed
- Update CHANGELOG

### Phase 4: Testing & Deployment (Week 2-3)
- E2E tests with full DSAR workflow
- Deploy to staging
- Monitor ticket processing
- Deploy to production

---

**END OF FSD**
