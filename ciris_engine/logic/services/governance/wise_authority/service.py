"""
Wise Authority Service - Authorization and Guidance

This service handles:
- Authorization checks (what can you do?)
- Decision deferrals to humans
- Guidance for complex situations
- Permission management

Authentication (who are you?) is handled by AuthenticationService.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union

from ciris_engine.logic.config import get_sqlite_db_full_path
from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType, TaskStatus
from ciris_engine.schemas.runtime.models import TaskContext
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import (
    DeferralApprovalContext,
    DeferralRequest,
    DeferralResponse,
    GuidanceRequest,
    GuidanceResponse,
    WAPermission,
    WARole,
)
from ciris_engine.schemas.services.context import GuidanceContext
from ciris_engine.schemas.services.core import ServiceStatus

logger = logging.getLogger(__name__)


class WiseAuthorityService(BaseService, WiseAuthorityServiceProtocol):
    """
    Wise Authority Service for authorization and guidance.

    Handles:
    - Authorization checks
    - Decision deferrals
    - Guidance requests
    - Permission management
    """

    def __init__(
        self, time_service: TimeServiceProtocol, auth_service: AuthenticationService, db_path: Optional[str] = None
    ) -> None:
        """Initialize the WA authorization service."""
        # Initialize BaseService with time service
        super().__init__(time_service=time_service)

        # Use configured database if not specified
        self.db_path = db_path or get_sqlite_db_full_path()

        # Store injected services
        self.auth_service = auth_service

        # Metrics tracking
        self._guidance_provided_count = 0
        self._queries_handled_count = 0

        # All deferrals and guidance are persisted in the database

        logger.info(f"Consolidated WA Service initialized with DB: {self.db_path}")

    def _get_placeholder(self) -> str:
        """Get the appropriate parameter placeholder for the current dialect."""
        return get_adapter().placeholder()

    def _get_context_json_like_clause(self) -> str:
        """Get the appropriate LIKE clause for context_json based on dialect."""
        adapter = get_adapter()
        placeholder = self._get_placeholder()
        if adapter.is_postgresql():
            return f"context_json::text LIKE {placeholder}"
        else:
            return f"context_json LIKE {placeholder}"

    async def _on_start(self) -> None:
        """Custom startup logic for WA service."""
        # Bootstrap if needed
        await self.auth_service.bootstrap_if_needed()

        # Deferrals are persisted in the thoughts table with status='deferred'
        # They can be queried via get_pending_deferrals()

    async def _on_stop(self) -> None:
        """Custom cleanup logic for WA service."""
        pass

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            # Authorization
            "check_authorization",
            "request_approval",
            # Guidance
            "get_guidance",
            # Deferrals
            "send_deferral",
            "get_pending_deferrals",
            "resolve_deferral",
            # Permissions
            "grant_permission",
            "revoke_permission",
            "list_permissions",
        ]

    # ========== Deferral Helper Methods ==========

    def _parse_deferral_context(
        self, context_json: Optional[Union[str, Dict[str, object]]]
    ) -> tuple[Dict[str, object], Dict[str, object]]:
        """Parse context JSON and extract deferral info.

        Args:
            context_json: JSON string or dict containing context data
                         (PostgreSQL jsonb returns dict directly)

        Returns:
            Tuple of (context_dict, deferral_info_dict)
        """
        context: Dict[str, object] = {}
        deferral_info: Dict[str, object] = {}
        if context_json:
            try:
                # Handle both string JSON and pre-parsed dict (PostgreSQL jsonb)
                if isinstance(context_json, dict):
                    context = context_json
                else:
                    context = json.loads(context_json)
                deferral_info = context.get("deferral", {})  # type: ignore[assignment]
            except (json.JSONDecodeError, TypeError):
                pass
        return context, deferral_info

    def _priority_to_string(self, priority: Optional[int]) -> str:
        """Convert integer priority to string representation.

        Args:
            priority: Integer priority value (can be None or string from DB)

        Returns:
            String priority: 'high', 'medium', or 'low'
        """
        priority_int = int(priority) if priority else 0
        if priority_int > 5:
            return "high"
        elif priority_int > 0:
            return "medium"
        return "low"

    def _build_ui_context(self, description: Optional[str], deferral_info: Dict[str, object]) -> Dict[str, str]:
        """Build UI context dictionary from description and deferral info.

        Args:
            description: Task description
            deferral_info: Dictionary containing deferral-specific data

        Returns:
            Dictionary with string keys and values for UI display
        """
        ui_context: Dict[str, str] = {
            "task_description": (description[:500] if description else ""),
        }
        # Add deferral-specific context fields (converted to strings for UI)
        deferral_context = deferral_info.get("context", {})
        if isinstance(deferral_context, dict):
            for key, value in deferral_context.items():
                if value is not None:
                    ui_context[key] = str(value)[:200]
        # Include original message if available
        original_message = deferral_info.get("original_message")
        if original_message:
            ui_context["original_message"] = str(original_message)[:500]
        return ui_context

    def _create_pending_deferral(
        self,
        task_id: str,
        channel_id: str,
        updated_at: Optional[str],
        deferral_info: Dict[str, object],
        priority_str: str,
        ui_context: Dict[str, str],
        description: Optional[str],
    ) -> PendingDeferral:
        """Create a PendingDeferral object from parsed data.

        Args:
            task_id: The task ID
            channel_id: Channel where deferral originated
            updated_at: Timestamp of last update
            deferral_info: Parsed deferral information
            priority_str: String priority ('high', 'medium', 'low')
            ui_context: UI-formatted context dictionary
            description: Task description

        Returns:
            PendingDeferral object
        """
        deferral_id = str(deferral_info.get("deferral_id", f"defer_{task_id}"))
        thought_id = str(deferral_info.get("thought_id", ""))
        reason = str(deferral_info.get("reason", description or ""))[:200]

        deferral_context = deferral_info.get("context", {})
        user_id = deferral_context.get("user_id") if isinstance(deferral_context, dict) else None

        created_at_dt = datetime.fromisoformat(updated_at.replace(" ", "T")) if updated_at else self._now()
        timeout_dt = created_at_dt + timedelta(days=7)

        return PendingDeferral(
            deferral_id=deferral_id,
            created_at=created_at_dt,
            deferred_by="ciris_agent",
            task_id=task_id,
            thought_id=thought_id,
            reason=reason,
            channel_id=channel_id,
            user_id=str(user_id) if user_id else None,
            priority=priority_str,
            assigned_wa_id=None,
            requires_role=None,
            status="pending",
            question=reason,
            context=ui_context,
            timeout_at=timeout_dt.isoformat(),
        )

    # ========== Authorization Operations ==========

    async def check_authorization(self, wa_id: str, action: str, resource: Optional[str] = None) -> bool:
        """Check if a WA is authorized for an action on a resource.

        Simple role-based authorization:
        - ROOT: Can do everything
        - AUTHORITY: Can approve/reject deferrals, provide guidance (no minting)
        - OBSERVER: Can only read and send messages
        """
        wa = await self.auth_service.get_wa(wa_id)
        if not wa:
            return False

        # Check role permissions
        if wa.role == WARole.ROOT:
            # Root can do anything
            return True
        elif wa.role == WARole.AUTHORITY:
            # Authority can do most things except mint WAs
            return action not in ["mint_wa", "create_wa", "bootstrap_root"]
        else:  # wa.role == WARole.OBSERVER
            # Observer can only read and send messages
            return action in ["read", "send_message", "observe", "get_status"]

    async def request_approval(self, action: str, context: DeferralApprovalContext) -> bool:
        """Request approval for an action - may defer to human.

        Returns True if immediately approved (e.g., requester is ROOT),
        False if deferred to human WA.
        """
        # Check if requester can self-approve
        can_self_approve = await self.check_authorization(
            context.requester_id, action, context.metadata.get("resource") if context.metadata else None
        )

        if can_self_approve:
            logger.info(f"Action {action} auto-approved for {context.requester_id}")
            return True

        # Create a deferral for human approval
        deferral_context = {
            "action": action,
            "requester": context.requester_id,
        }
        # Flatten action params into context
        for key, value in context.action_params.items():
            deferral_context[f"param_{key}"] = str(value)

        deferral = DeferralRequest(
            task_id=context.task_id,
            thought_id=context.thought_id,
            reason=f"Action '{action}' requires human approval",
            defer_until=(
                self._time_service.now() + timedelta(hours=24)
                if self._time_service
                else datetime.now() + timedelta(hours=24)
            ),
            context=deferral_context,
        )

        deferral_id = await self.send_deferral(deferral)
        logger.info(f"Created deferral {deferral_id} for action {action}")
        return False

    async def grant_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Grant a permission to a WA.

        In our simplified model, permissions are role-based.
        This method could be used to promote a WA to a higher role.
        """
        # For beta, we don't support dynamic permission grants
        # Permissions are determined by role
        _ = permission  # Unused in current implementation
        _ = resource  # Unused in current implementation
        logger.warning(
            "grant_permission called but permissions are role-based. " "Use update_wa to change roles instead."
        )
        return False

    async def revoke_permission(self, wa_id: str, permission: str, resource: Optional[str] = None) -> bool:
        """Revoke a permission from a WA.

        In our simplified model, permissions are role-based.
        This method could be used to demote or deactivate a WA.
        """
        # For beta, we don't support dynamic permission revocation
        # Permissions are determined by role
        _ = permission  # Unused in current implementation
        _ = resource  # Unused in current implementation
        logger.warning(
            "revoke_permission called but permissions are role-based. "
            "Use update_wa to change roles or revoke_wa to deactivate."
        )
        return False

    async def list_permissions(self, wa_id: str) -> List[WAPermission]:
        """List all permissions for a WA.

        Returns permissions based on the WA's role.
        """
        wa = await self.auth_service.get_wa(wa_id)
        if not wa:
            return []

        # Define role-based permissions
        role_permissions = {
            WARole.ROOT: ["*"],  # Root can do everything
            WARole.AUTHORITY: [
                "read",
                "write",
                "approve_deferrals",
                "provide_guidance",
                "manage_tasks",
                "access_audit",
                "manage_memory",
            ],
            WARole.OBSERVER: ["read", "send_message", "observe"],
        }

        permissions = role_permissions.get(wa.role, [])

        # Convert to WAPermission objects for protocol compliance
        return [
            WAPermission(
                permission_id=f"{wa.wa_id}_{perm}",
                wa_id=wa.wa_id,
                permission_type="role_based",
                permission_name=perm,
                resource=None,
                granted_by="system",
                granted_at=wa.created_at,
                expires_at=None,
                metadata={"role": wa.role.value},
            )
            for perm in permissions
        ]

    # ========== Deferral Operations ==========

    async def send_deferral(self, deferral: DeferralRequest) -> str:
        """Send a deferral to appropriate WA.

        Stores the deferral in the tasks table by updating the task status to 'deferred'
        and storing deferral metadata in context_json.
        """
        try:
            # Generate deferral ID
            timestamp = self._time_service.timestamp() if self._time_service else datetime.now().timestamp()
            deferral_id = f"defer_{deferral.task_id}_{timestamp}"

            import json

            conn = get_db_connection(db_path=self.db_path)
            cursor = conn.cursor()

            # Get existing task to preserve context
            placeholder = self._get_placeholder()
            cursor.execute(
                f"""
                SELECT context_json, priority FROM tasks
                WHERE task_id = {placeholder}
            """,
                (deferral.task_id,),
            )

            row = cursor.fetchone()
            if not row:
                logger.error(f"Task {deferral.task_id} not found for deferral")
                conn.close()
                raise ValueError(f"Task {deferral.task_id} not found")

            existing_context = {}
            if row[0]:
                try:
                    existing_context = json.loads(row[0])
                except json.JSONDecodeError:
                    pass

            # Add deferral information to context
            existing_context["deferral"] = {
                "deferral_id": deferral_id,
                "thought_id": deferral.thought_id,
                "reason": deferral.reason,
                "defer_until": deferral.defer_until.isoformat() if deferral.defer_until else None,
                "requires_wa_approval": True,  # Always true when sent to WA
                "context": deferral.context or {},
                "created_at": self._now().isoformat(),
            }

            # Update task status to deferred
            cursor.execute(
                f"""
                UPDATE tasks
                SET status = 'deferred',
                    context_json = {placeholder},
                    updated_at = {placeholder}
                WHERE task_id = {placeholder}
            """,
                (json.dumps(existing_context), self._now().isoformat(), deferral.task_id),
            )

            conn.commit()
            conn.close()

            logger.info(f"Task {deferral.task_id} marked as deferred - visible via /v1/wa/deferrals API")

            return deferral_id
        except Exception as e:
            logger.error(f"Failed to send deferral: {e}")
            raise

    async def get_pending_deferrals(self, wa_id: Optional[str] = None) -> List[PendingDeferral]:
        """Get pending deferrals from the tasks table."""
        result: List[PendingDeferral] = []

        try:
            conn = get_db_connection(db_path=self.db_path)
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT task_id, channel_id, description, priority, created_at, updated_at, context_json
                FROM tasks
                WHERE status = 'deferred'
                ORDER BY updated_at DESC
            """
            )

            for row in cursor.fetchall():
                # Handle both dict (PostgreSQL RealDictCursor) and tuple (SQLite) row formats
                if isinstance(row, dict):
                    task_id = row["task_id"]
                    channel_id = row["channel_id"]
                    description = row["description"]
                    priority = row["priority"]
                    updated_at = row["updated_at"]
                    context_json = row["context_json"]
                else:
                    task_id, channel_id, description, priority, _, updated_at, context_json = row

                _, deferral_info = self._parse_deferral_context(context_json)
                priority_str = self._priority_to_string(priority)
                ui_context = self._build_ui_context(description, deferral_info)

                deferral = self._create_pending_deferral(
                    task_id=task_id,
                    channel_id=channel_id,
                    updated_at=updated_at,
                    deferral_info=deferral_info,
                    priority_str=priority_str,
                    ui_context=ui_context,
                    description=description,
                )
                result.append(deferral)

            conn.close()

        except Exception as e:
            logger.error(f"Failed to get pending deferrals from database: {e}")
            return []

        return result

    async def resolve_deferral(self, deferral_id: str, response: DeferralResponse) -> bool:
        """Resolve a deferral by creating a new guidance task.

        When a deferral is resolved:
        1. Original deferred task is marked COMPLETED with outcome
        2. New guidance TASK is created (not just a thought) to ensure proper billing
        3. New task copies context from original and includes WA guidance
        4. New task is PENDING and ready for normal processing

        This ensures:
        - New billing cycle starts (new task = new credit charge)
        - Original task/thought history preserved
        - Proper task resumption flow
        """
        try:
            from ciris_engine.logic.utils.task_thought_factory import create_task

            conn = get_db_connection(db_path=self.db_path)
            cursor = conn.cursor()

            # Extract task_id from deferral_id
            # Format can be either defer_{task_id} or defer_{task_id}_{timestamp}
            if deferral_id.startswith("defer_"):
                parts = deferral_id.split("_", 2)  # Split into at most 3 parts
                if len(parts) == 2:
                    # Simple format: defer_{task_id}
                    task_id = parts[1]
                elif len(parts) >= 3:
                    # Timestamp format: defer_{task_id}_{timestamp}
                    # The task_id might contain underscores, so we need to handle that
                    # Remove 'defer_' prefix and find the last underscore for timestamp
                    without_prefix = deferral_id[6:]  # Remove 'defer_'
                    last_underscore = without_prefix.rfind("_")
                    if last_underscore > 0:
                        # Check if the part after last underscore looks like a timestamp
                        potential_timestamp = without_prefix[last_underscore + 1 :]
                        try:
                            float(potential_timestamp)  # Timestamps are floats
                            task_id = without_prefix[:last_underscore]
                        except ValueError:
                            # Not a timestamp, so the whole thing is the task_id
                            task_id = without_prefix
                    else:
                        task_id = without_prefix
                else:
                    # Shouldn't happen, but handle it
                    task_id = deferral_id[6:]  # Remove 'defer_' prefix
            else:
                # Try to find by deferral_id in context
                like_clause = self._get_context_json_like_clause()
                cursor.execute(
                    f"""
                    SELECT task_id, context_json
                    FROM tasks
                    WHERE status = 'deferred'
                    AND {like_clause}
                """,
                    (f'%"deferral_id":"{deferral_id}"%',),
                )

                row = cursor.fetchone()
                if row:
                    task_id = row[0]
                else:
                    logger.error(f"Deferral {deferral_id} not found")
                    conn.close()
                    return False

            # Get existing task details
            placeholder = self._get_placeholder()
            cursor.execute(
                f"""
                SELECT task_id, channel_id, description, priority, context_json, agent_occurrence_id
                FROM tasks
                WHERE task_id = {placeholder} AND status = 'deferred'
            """,
                (task_id,),
            )

            row = cursor.fetchone()
            if not row:
                logger.error(f"Task {task_id} not found or not deferred")
                conn.close()
                return False

            # Handle both dict (PostgreSQL) and tuple (SQLite) row formats
            if isinstance(row, dict):
                original_task_id = row["task_id"]
                channel_id = row["channel_id"]
                original_description = row["description"]
                priority = row["priority"]
                context_json = row["context_json"]
                agent_occurrence_id = row["agent_occurrence_id"]
            else:
                original_task_id, channel_id, original_description, priority, context_json, agent_occurrence_id = row

            # Parse existing context
            context = {}
            if context_json:
                try:
                    # Handle both string JSON and pre-parsed dict (PostgreSQL jsonb)
                    if isinstance(context_json, dict):
                        context = context_json
                    else:
                        context = json.loads(context_json)
                except json.JSONDecodeError:
                    pass

            # Add resolution to deferral info in the original task
            if "deferral" in context:
                context["deferral"]["resolution"] = {
                    "approved": response.approved,
                    "reason": response.reason,
                    "resolved_by": response.wa_id,
                    "resolved_at": self._now().isoformat(),
                }

            # Mark original deferred task as COMPLETED with outcome
            if response.approved:
                outcome = f"Resolved by WA {response.wa_id}: Approved"
            else:
                outcome = f"Rejected by WA {response.wa_id}: {response.reason}"

            cursor.execute(
                f"""
                UPDATE tasks
                SET status = 'completed',
                    context_json = {placeholder},
                    outcome = {placeholder},
                    updated_at = {placeholder}
                WHERE task_id = {placeholder}
            """,
                (json.dumps(context), outcome, self._now().isoformat(), task_id),
            )

            if cursor.rowcount == 0:
                logger.error(f"Failed to update original task {task_id}")
                conn.close()
                return False

            logger.info(f"Marked original deferred task {task_id} as COMPLETED with outcome")

            # If approved, create a NEW guidance task
            if response.approved and response.reason:
                # Track guidance provided via deferral resolution
                self._guidance_provided_count += 1

                # Create new context for guidance task - copy from original and add guidance
                guidance_context_dict = context.copy()
                guidance_context_dict["wa_guidance"] = response.reason
                guidance_context_dict["original_task_id"] = original_task_id
                guidance_context_dict["resolved_deferral_id"] = deferral_id

                # Always generate a NEW correlation_id for the guidance task
                # Tasks have a unique index on (agent_occurrence_id, correlation_id)
                # so reusing the original would cause a constraint violation
                import uuid
                correlation_id = str(uuid.uuid4())

                # Store original correlation_id in context for linkage/tracing
                if "correlation_id" in context:
                    guidance_context_dict["original_correlation_id"] = context["correlation_id"]

                # Build TaskContext from the guidance context dict
                task_context = TaskContext(
                    channel_id=channel_id,
                    user_id=context.get("user_id"),
                    correlation_id=correlation_id,
                    parent_task_id=original_task_id,
                    agent_occurrence_id=agent_occurrence_id,
                )

                # Create new task description incorporating WA guidance
                new_description = (
                    f"[WA GUIDANCE] Original: {original_description}\n\n"
                    f"WA Response: {response.reason}"
                )

                # Use factory to create new guidance task
                guidance_task = create_task(
                    description=new_description,
                    channel_id=channel_id,
                    agent_occurrence_id=agent_occurrence_id,
                    correlation_id=correlation_id,
                    time_service=self._time_service,
                    status=TaskStatus.PENDING,
                    priority=priority if priority is not None else 5,
                    user_id=context.get("user_id"),
                    parent_task_id=original_task_id,
                    context=task_context,
                )

                # Add the guidance task to database
                # We need to manually insert since we're already in a transaction
                task_json = {
                    "task_id": guidance_task.task_id,
                    "channel_id": guidance_task.channel_id,
                    "agent_occurrence_id": guidance_task.agent_occurrence_id,
                    "description": guidance_task.description,
                    "status": guidance_task.status.value,
                    "priority": guidance_task.priority,
                    "created_at": guidance_task.created_at,
                    "updated_at": guidance_task.updated_at,
                    "parent_task_id": guidance_task.parent_task_id,
                    "context_json": json.dumps(guidance_context_dict),
                }

                cursor.execute(
                    f"""
                    INSERT INTO tasks (
                        task_id, channel_id, agent_occurrence_id, description,
                        status, priority, created_at, updated_at, parent_task_id, context_json
                    ) VALUES (
                        {placeholder}, {placeholder}, {placeholder}, {placeholder},
                        {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}
                    )
                    """,
                    (
                        task_json["task_id"],
                        task_json["channel_id"],
                        task_json["agent_occurrence_id"],
                        task_json["description"],
                        task_json["status"],
                        task_json["priority"],
                        task_json["created_at"],
                        task_json["updated_at"],
                        task_json["parent_task_id"],
                        task_json["context_json"],
                    ),
                )

                logger.info(
                    f"Created new guidance task {guidance_task.task_id} for resolved deferral {deferral_id}"
                )

            conn.commit()
            conn.close()

            logger.info(
                f"Deferral {deferral_id} {'approved' if response.approved else 'rejected'} by {response.wa_id}, "
                f"original task {task_id} completed, new guidance task created"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to resolve deferral: {e}")
            return False

    # ========== Guidance Operations ==========

    async def fetch_guidance(self, context: GuidanceContext) -> Optional[str]:
        """Fetch guidance from a Wise Authority for a given context.

        This is the WiseBus-compatible method that adapters call.
        Guidance comes ONLY from authorized Wise Authorities - never
        generated by the system.
        """
        try:
            # Track wisdom query
            self._queries_handled_count += 1

            # Log the guidance request
            logger.info(f"Guidance requested for thought {context.thought_id}: {context.question}")

            # Check if we have any stored guidance for this context
            # In the full implementation, this would query the database
            # for guidance provided by WAs through the API or other channels

            # Guidance is provided by WAs through the API, not generated by this service
            # Returns None when no WA has provided guidance - this is the correct behavior

            logger.debug(f"No WA guidance available yet for thought {context.thought_id}")
            return None

        except Exception as e:
            logger.error(f"Failed to fetch guidance: {e}", exc_info=True)
            return None

    async def get_guidance(self, request: GuidanceRequest) -> GuidanceResponse:
        """Get guidance for a situation (Protocol method).

        This wraps fetch_guidance to comply with the protocol.
        """
        # Convert GuidanceRequest to GuidanceContext for internal use
        timestamp = self._time_service.timestamp() if self._time_service else datetime.now().timestamp()
        context = GuidanceContext(
            thought_id=f"guidance_{timestamp}",
            task_id=f"guidance_task_{timestamp}",
            question=request.context,
            ethical_considerations=[],  # Could extract from options
            domain_context={
                "urgency": request.urgency,
                "options": ", ".join(request.options) if request.options else "",
                "recommendation": request.recommendation or "",
            },
        )

        # Use the existing fetch_guidance method
        guidance = await self.fetch_guidance(context)

        if guidance:
            # Track guidance provided
            self._guidance_provided_count += 1

            # Audit log guidance observation
            if hasattr(self, "_audit_service") and self._audit_service:
                from ciris_engine.schemas.audit.core import EventPayload

                event_data = EventPayload(
                    action="observe",
                    service_name="wise_authority",
                    user_id="system",
                    result="guidance_provided",
                )
                await self._audit_service.log_event(event_type="guidance_observation", event_data=event_data)

            # Parse the guidance response (assuming it's structured)
            return GuidanceResponse(
                selected_option=None,  # Would be parsed from guidance
                custom_guidance=guidance,
                reasoning="Guidance provided by Wise Authority",
                wa_id="unknown",  # Would come from the actual WA
                signature="",  # Would be signed by the WA
            )
        else:
            # Audit log no guidance available
            if hasattr(self, "_audit_service") and self._audit_service:
                from ciris_engine.schemas.audit.core import EventPayload

                event_data = EventPayload(
                    action="observe",
                    service_name="wise_authority",
                    user_id="system",
                    result="no_guidance",
                )
                await self._audit_service.log_event(event_type="guidance_observation", event_data=event_data)

            # No guidance available
            return GuidanceResponse(
                selected_option=None,
                custom_guidance=None,
                reasoning="No Wise Authority guidance available yet",
                wa_id="system",
                signature="",
            )

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        # Get counts from database
        pending_deferrals_count = 0
        resolved_deferrals_count = 0

        try:
            conn = get_db_connection(db_path=self.db_path)
            cursor = conn.cursor()

            # Count pending deferrals (deferred tasks)
            cursor.execute(
                """
                SELECT COUNT(*) FROM tasks
                WHERE status = 'deferred'
            """
            )
            pending_deferrals_count = cursor.fetchone()[0]

            # Count resolved deferrals (tasks with resolution in context)
            like_clause = self._get_context_json_like_clause()
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM tasks
                WHERE {like_clause}
            """,
                ('%"resolution":%',),
            )
            resolved_deferrals_count = cursor.fetchone()[0]

            conn.close()
        except Exception as e:
            logger.error(f"Error getting deferral counts: {e}")

        return ServiceStatus(
            service_name="WiseAuthorityService",
            service_type="governance_service",
            is_healthy=self._started,
            uptime_seconds=self._calculate_uptime(),
            last_error=self._last_error,
            metrics={
                "pending_deferrals": float(pending_deferrals_count),
                "resolved_deferrals": float(resolved_deferrals_count),
                "total_deferrals": float(pending_deferrals_count + resolved_deferrals_count),
            },
            last_health_check=self._last_health_check,
        )

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.WISE_AUTHORITY

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        return self.auth_service is not None

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        self._dependencies.add("AuthenticationService")
        self._dependencies.add("GraphAuditService")
        self._dependencies.add("SecretsService")

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect service-specific metrics for v1.4.3 API."""
        # Get deferral counts from database
        total_deferrals_count = 0
        resolved_deferrals_count = 0

        try:
            conn = get_db_connection(db_path=self.db_path)
            cursor = conn.cursor()

            like_clause = self._get_context_json_like_clause()

            # Count total deferrals - tasks that have or had deferral context
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM tasks
                WHERE {like_clause}
            """,
                ('%"deferral":%',),
            )
            total_deferrals_count = cursor.fetchone()[0]

            # Count resolved deferrals (tasks with resolution in context)
            cursor.execute(
                f"""
                SELECT COUNT(*) FROM tasks
                WHERE {like_clause}
            """,
                ('%"resolution":%',),
            )
            resolved_deferrals_count = cursor.fetchone()[0]

            conn.close()
        except Exception as e:
            logger.error(f"Error getting deferral counts: {e}")

        return {
            # v1.4.3 specified metrics - exact names from telemetry taxonomy
            "wise_authority_deferrals_total": float(total_deferrals_count),
            "wise_authority_deferrals_resolved": float(resolved_deferrals_count),
            "wise_authority_guidance_requests": float(self._guidance_provided_count),
            "wise_authority_uptime_seconds": self._calculate_uptime(),
        }
