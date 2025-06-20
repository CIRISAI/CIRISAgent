import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ciris_engine.adapters.base import Service
from ciris_engine.protocols.services import AuditService as AuditServiceProtocol
from ciris_engine.schemas.foundational_schemas_v1 import HandlerActionType
from ciris_engine.schemas.audit_schemas_v1 import AuditLogEntry  # Import from schemas
from ciris_engine.schemas.protocol_schemas_v1 import ActionContext, AuditEntry, GuardrailCheckResult

logger = logging.getLogger(__name__)


class AuditService(AuditServiceProtocol):
    """Service for persisting audit log entries with buffering and rotation."""

    def __init__(
        self,
        log_path: str = "audit_logs.jsonl",
        rotation_size_mb: int = 100,
        retention_days: int = 90,
    ) -> None:
        # Configure retry settings for file operations
        retry_config = {
            "retry": {
                "global": {
                    "max_retries": 3,
                    "base_delay": 0.5,  # Shorter delays for file operations
                    "max_delay": 5.0,
                },
                "file_operation": {
                    "retryable_exceptions": (OSError, IOError, PermissionError),
                    "non_retryable_exceptions": (FileNotFoundError,),  # Don't retry if file doesn't exist
                }
            }
        }
        super().__init__(config=retry_config)
        
        self.log_path = Path(log_path)
        self.rotation_size_mb = rotation_size_mb
        self.retention_days = retention_days
        self._buffer: List[AuditLogEntry] = []
        self._flush_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        await super().start()
        
        # Use retry logic for initial file creation
        async def create_file() -> None:
            await asyncio.to_thread(self.log_path.touch, exist_ok=True)
        
        await self.retry_with_backoff(create_file)  # type: ignore[unused-coroutine]

    async def stop(self) -> None:
        # Flush any remaining buffered entries before stopping
        await self._flush_buffer()
        await super().stop()

    async def log_action(
        self,
        handler_action: HandlerActionType,
        context: ActionContext,
        outcome: Optional[str] = None,
    ) -> bool:
        """Log an action with context and outcome."""
        try:
            entry = AuditLogEntry(
                event_id=str(uuid.uuid4()),
                event_timestamp=datetime.now(timezone.utc).isoformat(),
                event_type=handler_action.value,
                originator_id=context.thought_id,
                target_id=context.task_id,
                event_summary=self._generate_summary(handler_action, context, outcome),  # Pass outcome
                event_payload={"thought_id": context.thought_id, "task_id": context.task_id, "handler_name": context.handler_name, "parameters": context.parameters},
                agent_template="default",
                round_number=0,
                thought_id=context.thought_id,
                task_id=context.task_id,
            )
            self._buffer.append(entry)
            if len(self._buffer) >= 100:  # Flush every 100 entries
                await self._flush_buffer()
            return True
        except Exception as e:
            logger.error(f"Failed to log action: {e}")
            return False

    async def log_event(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Log a general event (replaces EventLogService functionality)."""
        entry = AuditLogEntry(
            event_id=str(uuid.uuid4()),
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            originator_id=event_data.get("originator_id", "system"),
            target_id=event_data.get("target_id"),
            event_summary=event_data.get("summary", f"{event_type} event"),
            event_payload=event_data,
            agent_template=event_data.get("agent_template"),
            round_number=event_data.get("round_number"),
            thought_id=event_data.get("thought_id"),
            task_id=event_data.get("task_id"),
        )
        self._buffer.append(entry)
        if len(self._buffer) >= 100:  # Flush every 100 entries
            await self._flush_buffer()

    async def log_guardrail_event(self, guardrail_name: str, action_type: str, result: GuardrailCheckResult) -> None:
        """Log guardrail check events (specific helper for guardrail logging)."""
        event_data = {
            "guardrail_name": guardrail_name,
            "action_type": action_type,
            "result": {"allowed": result.allowed, "reason": result.reason, "risk_level": result.risk_level},
            "originator_id": "guardrail_system",
            "summary": f"Guardrail {guardrail_name} check for {action_type}"
        }
        await self.log_event("guardrail_check", event_data)

    async def query_audit_log(
        self,
    ) -> List[AuditLogEntry]:
        """Query audit logs with filters."""
        # Placeholder: implement log search logic as needed
        return []

    async def get_audit_trail(self, entity_id: str, limit: int = 100) -> List[AuditEntry]:
        """
        Get audit trail for an entity.
        
        Args:
            entity_id: ID of the entity to get audit trail for
            limit: Maximum number of audit entries
            
        Returns:
            List of audit entries as dictionaries
        """
        # For now, return a simple implementation
        # In a full implementation, this would search through audit logs
        # filtering by entity_id (could be thought_id, task_id, etc.)
        try:
            if not self.log_path.exists():
                return []
            
            entries: List[AuditEntry] = []
            with self.log_path.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry_dict = json.loads(line.strip())
                        # Check if this entry is related to the entity_id
                        if (entry_dict.get("originator_id") == entity_id or
                            entry_dict.get("thought_id") == entity_id or
                            entry_dict.get("task_id") == entity_id):
                            # Convert to AuditEntry
                            audit_entry = AuditEntry(
                                entry_id=entry_dict.get("event_id", str(uuid.uuid4())),
                                timestamp=datetime.fromisoformat(entry_dict.get("event_timestamp", datetime.now(timezone.utc).isoformat())),
                                entity_id=entity_id,
                                event_type=entry_dict.get("event_type", "unknown"),
                                actor=entry_dict.get("originator_id", "system"),
                                details=entry_dict,
                                outcome=entry_dict.get("event_summary")
                            )
                            entries.append(audit_entry)
                            if len(entries) >= limit:
                                break
                    except (json.JSONDecodeError, ValueError):
                        continue
            
            return entries[-limit:] if len(entries) > limit else entries
        except Exception as e:
            logger.error(f"Failed to get audit trail: {e}")
            return []

    def _write_entries(self, entries: List[AuditLogEntry]) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            for entry in entries:
                f.write(entry.model_dump_json() + "\n")

    async def _flush_buffer(self) -> None:
        """Flush buffered entries to disk with retry logic."""
        if not self._buffer:
            return
            
        entries_to_write = self._buffer.copy()
        self._buffer.clear()
        
        async def perform_flush() -> None:
            await self._perform_flush_operation(entries_to_write)
        
        await self.retry_with_backoff(perform_flush)  # type: ignore[unused-coroutine]

    async def _perform_flush_operation(self, entries_to_write: List[AuditLogEntry]) -> None:
        """Helper method for flush operation."""
        await asyncio.to_thread(self._write_entries, entries_to_write)
        if await self._should_rotate():
            await self._rotate_log()

    async def _should_rotate(self) -> bool:
        if not self.log_path.exists():
            return False
        size_mb = self.log_path.stat().st_size / (1024 * 1024)
        return size_mb >= self.rotation_size_mb

    async def _rotate_log(self) -> None:
        """Simple rotation: rename current log and start new."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        rotated = self.log_path.with_name(f"{self.log_path.stem}_{ts}.jsonl")
        async def perform_rotation() -> None:
            await asyncio.to_thread(self.log_path.rename, rotated)
        
        await self.retry_with_backoff(perform_rotation)  # type: ignore[unused-coroutine]

    def _generate_summary(
        self, handler_action: HandlerActionType, context: ActionContext, outcome: Optional[str] = None
    ) -> str:
        """Generate a summary including outcome if provided."""
        base_summary = f"{handler_action.value} action for thought {context.thought_id}"
        if outcome:
            return f"{base_summary} - {outcome}"
        return base_summary
