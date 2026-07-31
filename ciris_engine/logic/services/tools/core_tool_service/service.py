"""
Core Tool Service - Provides core system tools for agents.

Implements ToolService protocol to expose core tools:
- Secrets management (RECALL_SECRET, UPDATE_SECRETS_FILTER)
- Ticket management (UPDATE_TICKET, GET_TICKET, DEFER_TICKET)
- Agent guidance (SELF_HELP)

Tickets are NOT a service - they're a coordination mechanism that sits above services.
Tools provide the agent-facing interface for ticket updates during task execution.
"""

import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.utils.jsondict_helpers import get_str
from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import (
    ToolDMAGuidance,
    ToolDocumentation,
    ToolExecutionResult,
    ToolExecutionStatus,
    ToolGotcha,
    ToolInfo,
    ToolParameterSchema,
    ToolResult,
    UsageExample,
)
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.budget_envelope import (
    PROPOSAL_METADATA_KEY,
    PROPOSAL_TICKET_STATUS,
    REQUESTED_BUDGET_METADATA_KEY,
    RESERVED_TICKET_METADATA_KEYS,
    RequestedBudget,
    TicketProposal,
    is_unapproved_proposal,
)
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.core.secrets import SecretContext
from ciris_engine.schemas.types import JSONDict

# ToolParameters is a JSONDict for flexible parameter passing
ToolParameters = JSONDict

logger = logging.getLogger(__name__)

# Error message constants to avoid duplication
ERROR_TICKET_ID_REQUIRED = "ticket_id (str) is required"
ERROR_FILTER_NOT_EXPOSED = "Filter operations not currently exposed"

# --- create_ticket: proposal defaults -------------------------------------
DEFAULT_PROPOSAL_SOP = "AGENT_PROPOSAL"
DEFAULT_PROPOSAL_TICKET_TYPE = "proposal"
DEFAULT_PROPOSAL_EMAIL = "agent-proposal@local"

# --- create_ticket: runaway bound ------------------------------------------
# An agent that can create tasks can create infinite tasks. Two bounds, both
# fail with an explicit error rather than silently dropping the proposal:
#   * per originating task — catches a single task stuck in a propose loop
#   * per rolling window   — catches runaway spread across many tasks
# Both counters are in-process and reset on restart; see FSD/BUDGET_ENVELOPE.md
# "what this does NOT do".
MAX_PROPOSALS_PER_TASK = 3
MAX_PROPOSALS_PER_WINDOW = 20
PROPOSAL_WINDOW_SECONDS = 3600.0


class CoreToolService(BaseService, ToolService):
    """Service providing core system tools (secrets, tickets, guidance)."""

    def __init__(
        self,
        secrets_service: SecretsService,
        time_service: TimeServiceProtocol,
        db_path: Optional[str] = None,
    ) -> None:
        """Initialize with secrets service, time service, and optional db path.

        Args:
            secrets_service: Service for secrets management
            time_service: Service for time operations
            db_path: Optional database path override. When None (default),
                    uses current config (_test_db_path or essential_config).
                    When provided, uses this specific path for all operations.
        """
        super().__init__(time_service=time_service)
        self.secrets_service = secrets_service
        # Store db_path for persistence calls - None means use current config
        self._db_path = db_path
        self.adapter_name = "core_tools"

        # v1.4.3 metrics tracking
        self._secrets_retrieved = 0
        self._secrets_stored = 0
        self._tickets_updated = 0
        self._tickets_retrieved = 0
        self._tickets_deferred = 0
        self._tickets_proposed = 0
        self._proposals_rate_limited = 0
        # Runaway bound state (in-process; see MAX_PROPOSALS_PER_* above)
        self._proposals_by_task: Dict[str, int] = {}
        self._proposal_timestamps: Deque[float] = deque()
        self._metrics_tracking: Dict[str, float] = {}  # For custom metric tracking
        self._tool_executions = 0
        self._tool_failures = 0

    @property
    def db_path(self) -> Optional[str]:
        """Get database path for persistence operations.

        Returns the stored db_path if provided during initialization,
        otherwise None to use current config (_test_db_path or essential_config).
        """
        return self._db_path

    def _track_metric(self, metric_name: str, default: float = 0.0) -> float:
        """Track a metric with default value."""
        return self._metrics_tracking.get(metric_name, default)

    def get_service_type(self) -> ServiceType:
        """Get service type."""
        return ServiceType.TOOL

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "recall_secret",
            "update_secrets_filter",
            "self_help",
            "create_ticket",
            "update_ticket",
            "get_ticket",
            "defer_ticket",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are available."""
        return self.secrets_service is not None

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        self._dependencies.add("SecretsService")

    async def is_healthy(self) -> bool:
        """Check if service is healthy.

        SecretsToolService is stateless and always healthy if instantiated.
        """
        return True

    async def execute_tool(self, tool_name: str, parameters: ToolParameters) -> ToolExecutionResult:
        """Execute a tool and return the result."""
        self._track_request()  # Track the tool execution
        self._tool_executions += 1

        if tool_name == "recall_secret":
            result = await self._recall_secret(parameters)
        elif tool_name == "update_secrets_filter":
            result = await self._update_secrets_filter(parameters)
        elif tool_name == "self_help":
            result = await self._self_help(parameters)
        elif tool_name == "create_ticket":
            result = await self._create_ticket(parameters)
        elif tool_name == "update_ticket":
            result = await self._update_ticket(parameters)
        elif tool_name == "get_ticket":
            result = await self._get_ticket(parameters)
        elif tool_name == "defer_ticket":
            result = await self._defer_ticket(parameters)
        else:
            self._tool_failures += 1  # Unknown tool is a failure!
            result = ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        if not result.success:
            self._tool_failures += 1  # Track failed executions
            self._track_error(Exception(result.error or "Tool execution failed"))

        return ToolExecutionResult(
            tool_name=tool_name,
            status=ToolExecutionStatus.COMPLETED if result.success else ToolExecutionStatus.FAILED,
            success=result.success,
            data=result.data,
            error=result.error,
            correlation_id=f"secrets_{tool_name}_{self._now().timestamp()}",
        )

    async def _recall_secret(self, params: ToolParameters) -> ToolResult:
        """Recall a secret by UUID."""
        try:
            secret_uuid_val = get_str(params, "secret_uuid", "")
            purpose = params.get("purpose", "No purpose specified")
            decrypt = params.get("decrypt", False)

            if not secret_uuid_val:
                return ToolResult(success=False, error="secret_uuid is required")

            # Retrieve the secret
            if decrypt:
                value = await self.secrets_service.retrieve_secret(secret_uuid_val)
                if value is None:
                    return ToolResult(success=False, error=f"Secret {secret_uuid_val} not found")
                self._secrets_retrieved += 1  # Track successful retrieval
                result_data = {"value": value, "decrypted": True}
            else:
                # Just verify it exists
                # Just check if it exists by trying to retrieve
                value = await self.secrets_service.retrieve_secret(secret_uuid_val)
                if value is None:
                    return ToolResult(success=False, error=f"Secret {secret_uuid_val} not found")
                self._secrets_retrieved += 1  # Track successful retrieval
                result_data = {"exists": True, "decrypted": False}

            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error recalling secret: {e}")
            return ToolResult(success=False, error=str(e))

    async def _update_secrets_filter(self, params: ToolParameters) -> ToolResult:
        """Update secrets filter configuration."""
        try:
            operation = params.get("operation")
            if not operation:
                return ToolResult(success=False, error="operation is required")

            result_data = {"operation": operation}

            if operation == "add_pattern":
                pattern = params.get("pattern")
                if not pattern:
                    return ToolResult(success=False, error="pattern is required for add_pattern")

                # Filter operations not directly accessible - would need to be exposed
                return ToolResult(success=False, error=ERROR_FILTER_NOT_EXPOSED)

            elif operation == "remove_pattern":
                pattern = params.get("pattern")
                if not pattern:
                    return ToolResult(success=False, error="pattern is required for remove_pattern")

                # Filter operations not directly accessible
                return ToolResult(success=False, error=ERROR_FILTER_NOT_EXPOSED)

            elif operation == "list_patterns":
                # Filter operations not directly accessible
                patterns: List[Any] = []
                result_data.update({"patterns": patterns})

            elif operation == "enable":
                # Filter operations not directly accessible
                return ToolResult(success=False, error=ERROR_FILTER_NOT_EXPOSED)

            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")

            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error updating secrets filter: {e}")
            return ToolResult(success=False, error=str(e))

    async def _self_help(self, parameters: ToolParameters) -> ToolResult:
        """Access the agent experience document.

        Resolves relative to the installed ``ciris_engine`` package so the
        path works on both dev tree and installed wheels (was a CWD-relative
        ``docs/agent_experience.md`` lookup in 2.8.4 and earlier — broke on
        every wheel install because docs/ is outside the package).
        """
        try:
            # parents[4] walks up from this file to the ciris_engine package
            # root, where data/agent_experience.txt lives.
            experience_path = Path(__file__).resolve().parents[4] / "data" / "agent_experience.txt"
            rel_source = "ciris_engine/data/agent_experience.txt"

            if not experience_path.exists():
                return ToolResult(success=False, error=f"Agent experience document not found at {rel_source}")

            content = experience_path.read_text()

            return ToolResult(success=True, data={"content": content, "source": rel_source, "length": len(content)})

        except Exception as e:
            logger.error(f"Error reading experience document: {e}")
            return ToolResult(success=False, error=str(e))

    def _validate_ticket_id(self, params: ToolParameters) -> Optional[str]:
        """Validate and extract ticket_id from parameters.

        Returns:
            ticket_id if valid, None otherwise
        """
        ticket_id = params.get("ticket_id")
        if not ticket_id or not isinstance(ticket_id, str):
            return None
        return ticket_id

    def _parse_metadata_json(
        self, metadata_updates: Any, start_time: float
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Parse metadata updates, handling JSON strings from CLI/mock LLM.

        Args:
            metadata_updates: Raw metadata updates (dict or JSON string)
            start_time: Timer start for debug logging

        Returns:
            Tuple of (parsed_metadata, error_message). One will be None.
        """
        import json
        import time

        # Handle JSON string from command-line tools (mock LLM, CLI)
        if isinstance(metadata_updates, str):
            try:
                metadata_updates = json.loads(metadata_updates)
                logger.debug(
                    f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s PARSED_JSON metadata_updates={metadata_updates}"
                )
            except json.JSONDecodeError as e:
                return None, f"metadata must be valid JSON: {e}"

        if not isinstance(metadata_updates, dict):
            return None, "metadata must be a dictionary or valid JSON string"

        return metadata_updates, None

    def _merge_single_stage(
        self,
        merged_stages: dict[str, Any],
        stage_name: str,
        stage_data: Any,
        start_time: float,
    ) -> None:
        """Merge a single stage into the merged_stages dict in place.

        Args:
            merged_stages: Dictionary of merged stages (modified in place)
            stage_name: Name of the stage to merge
            stage_data: Data for the stage
            start_time: Timer start for debug logging
        """
        import time

        logger.debug(
            f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s MERGING_STAGE stage={stage_name} data={stage_data}"
        )

        if not isinstance(stage_data, dict):
            return

        if stage_name in merged_stages and isinstance(merged_stages[stage_name], dict):
            # Merge existing stage
            before = merged_stages[stage_name].copy()
            merged_stages[stage_name] = {**merged_stages[stage_name], **stage_data}
            logger.debug(
                f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s MERGED_STAGE "
                f"stage={stage_name} before={before} after={merged_stages[stage_name]}"
            )
        else:
            # New stage
            merged_stages[stage_name] = stage_data
            logger.debug(
                f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s NEW_STAGE stage={stage_name} data={stage_data}"
            )

    def _merge_stage_metadata(
        self, current_metadata: dict[str, Any], metadata_updates: dict[str, Any], start_time: float
    ) -> dict[str, Any]:
        """Deep merge stage metadata, preserving existing stage data.

        Args:
            current_metadata: Current ticket metadata
            metadata_updates: New metadata to merge
            start_time: Timer start for debug logging

        Returns:
            Merged metadata dictionary
        """
        import time

        # Shallow merge first
        merged_metadata: dict[str, Any] = {**current_metadata, **metadata_updates}

        # Deep merge for 'stages' key only
        if "stages" not in metadata_updates:
            return merged_metadata

        merged_stages: dict[str, Any] = {**current_metadata.get("stages", {})}
        stages_updates = metadata_updates.get("stages", {})

        logger.debug(
            f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s DEEP_MERGE_STAGES "
            f"base_stages={list(merged_stages.keys())} update_stages={list(stages_updates.keys())}"
        )

        if isinstance(stages_updates, dict):
            for stage_name, stage_data in stages_updates.items():
                self._merge_single_stage(merged_stages, stage_name, stage_data, start_time)
            merged_metadata["stages"] = merged_stages

        return merged_metadata

    def _update_ticket_status_only(
        self, ticket_id: str, new_status: Any, params: ToolParameters, result_data: dict[str, Any]
    ) -> Optional[ToolResult]:
        """Update ticket status and add to result data.

        Args:
            ticket_id: Ticket ID to update
            new_status: New status value
            params: Tool parameters (for notes)
            result_data: Result dictionary to update

        Returns:
            ToolResult with error if update fails, None if successful
        """
        from ciris_engine.logic.persistence.models.tickets import update_ticket_status

        if not isinstance(new_status, str):
            return ToolResult(success=False, error="status must be a string")

        notes = params.get("notes")
        notes_str = str(notes) if notes is not None else None
        success = update_ticket_status(ticket_id, new_status, notes=notes_str)

        if not success:
            return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} status")

        result_data["updates"]["status"] = new_status
        if notes:
            result_data["updates"]["notes"] = notes

        return None

    def _update_ticket_metadata_only(
        self,
        ticket_id: str,
        current_ticket: dict[str, Any],
        metadata_updates: Any,
        result_data: dict[str, Any],
        start_time: float,
    ) -> Optional[ToolResult]:
        """Update ticket metadata with deep merge for stages.

        Args:
            ticket_id: Ticket ID to update
            current_ticket: Current ticket data
            metadata_updates: New metadata to merge
            result_data: Result dictionary to update
            start_time: Timer start for debug logging

        Returns:
            ToolResult with error if update fails, None if successful
        """
        import time

        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        logger.debug(
            f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s METADATA_UPDATE_START metadata_updates={metadata_updates}"
        )

        # Parse JSON if needed
        parsed_metadata, error = self._parse_metadata_json(metadata_updates, start_time)
        if error:
            return ToolResult(success=False, error=error)

        metadata_updates = parsed_metadata

        # Get current metadata
        current_metadata = current_ticket.get("metadata", {})
        if not isinstance(current_metadata, dict):
            current_metadata = {}

        logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s BEFORE_MERGE current={current_metadata}")

        # Deep merge with special handling for stages
        merged_metadata = self._merge_stage_metadata(current_metadata, metadata_updates, start_time)

        logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s AFTER_MERGE merged={merged_metadata}")

        # Update database
        success = update_ticket_metadata(ticket_id, merged_metadata)
        logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s DB_UPDATE_RESULT success={success}")

        if not success:
            return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} metadata")

        result_data["updates"]["metadata"] = metadata_updates
        return None

    @staticmethod
    def _reserved_keys_in(metadata_updates: Any) -> List[str]:
        """Return any reserved authorization keys present in a metadata update.

        Handles both dict and JSON-string forms, because ``_update_ticket``
        accepts a JSON string from CLI-shaped callers and would otherwise let a
        reserved key through as text.
        """
        candidate = metadata_updates
        if isinstance(candidate, str):
            import json as _json

            try:
                candidate = _json.loads(candidate)
            except (ValueError, TypeError):
                return []
        if not isinstance(candidate, dict):
            return []
        return sorted(RESERVED_TICKET_METADATA_KEYS.intersection(candidate.keys()))

    async def _update_ticket(self, params: ToolParameters) -> ToolResult:
        """Update ticket status or metadata during task processing."""
        import time

        start_time = time.time()

        try:
            from ciris_engine.logic.persistence.models.tickets import get_ticket

            # Validate ticket_id
            ticket_id = self._validate_ticket_id(params)
            if not ticket_id:
                return ToolResult(success=False, error=ERROR_TICKET_ID_REQUIRED)

            logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s START ticket_id={ticket_id}")

            # Get current ticket to validate and merge metadata
            current_ticket = get_ticket(ticket_id)
            if not current_ticket:
                return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

            # --- Authorization guards (#938) -------------------------------
            # 1. Reserved metadata keys carry the human-issued grant and the
            #    spend ledger. update_ticket is otherwise an arbitrary metadata
            #    write primitive, so without this the agent could mint its own
            #    budget grant. Refuse loudly rather than silently stripping.
            reserved = self._reserved_keys_in(params.get("metadata"))
            if reserved:
                logger.warning(
                    f"[UPDATE_TICKET] REFUSED reserved-key write on {ticket_id}: {reserved}",
                )
                return ToolResult(
                    success=False,
                    error=(
                        f"Refusing update: metadata keys {reserved} are reserved for human-issued "
                        f"authorization and cannot be written by the agent."
                    ),
                )

            # 2. A proposal must not promote itself into an executing ticket.
            #    Promotion is the human's decision; the agent may only withdraw
            #    its own proposal (cancel), which narrows and never widens.
            new_status_raw = params.get("status")
            if is_unapproved_proposal(current_ticket) and new_status_raw:
                requested_status = str(new_status_raw)
                if requested_status not in (PROPOSAL_TICKET_STATUS, "cancelled"):
                    logger.warning(
                        f"[UPDATE_TICKET] REFUSED self-promotion of proposal {ticket_id} "
                        f"to status={requested_status}",
                    )
                    return ToolResult(
                        success=False,
                        error=(
                            f"Refusing update: ticket {ticket_id} is a proposal. Only a human can move it "
                            f"out of proposal state. You may cancel it, but you cannot approve it."
                        ),
                    )

            logger.debug(
                f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s FETCHED current_metadata={current_ticket.get('metadata', {})}"
            )

            result_data: dict[str, Any] = {"ticket_id": ticket_id, "updates": {}}

            # Update status if provided
            new_status = params.get("status")
            if new_status:
                error_result = self._update_ticket_status_only(ticket_id, new_status, params, result_data)
                if error_result:
                    return error_result

            # Update metadata if provided
            metadata_updates = params.get("metadata")
            if metadata_updates:
                error_result = self._update_ticket_metadata_only(
                    ticket_id, current_ticket, metadata_updates, result_data, start_time
                )
                if error_result:
                    return error_result

            self._tickets_updated += 1
            logger.debug(f"[UPDATE_TICKET] T+{time.time()-start_time:.3f}s COMPLETE result={result_data}")
            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error updating ticket: {e}")
            return ToolResult(success=False, error=str(e))

    # ------------------------------------------------------------------
    # create_ticket — the agent's proposal channel (#938)
    # ------------------------------------------------------------------

    def _check_proposal_rate_limit(self, origin_task_id: Optional[str]) -> Optional[str]:
        """Enforce the runaway bound. Returns an error string when over budget.

        Two independent caps. The per-task cap is the one that matters in
        practice (a task looping on propose); the window cap catches runaway
        spread across many tasks.
        """
        now = self._now().timestamp()

        # Evict timestamps outside the rolling window.
        while self._proposal_timestamps and now - self._proposal_timestamps[0] > PROPOSAL_WINDOW_SECONDS:
            self._proposal_timestamps.popleft()

        if len(self._proposal_timestamps) >= MAX_PROPOSALS_PER_WINDOW:
            self._proposals_rate_limited += 1
            return (
                f"Proposal rate limit reached: {MAX_PROPOSALS_PER_WINDOW} proposals in the last "
                f"{int(PROPOSAL_WINDOW_SECONDS / 60)} minutes. Wait, or ask a human to act on the "
                f"proposals already open."
            )

        if origin_task_id:
            count = self._proposals_by_task.get(origin_task_id, 0)
            if count >= MAX_PROPOSALS_PER_TASK:
                self._proposals_rate_limited += 1
                return (
                    f"Proposal limit reached for this task: {MAX_PROPOSALS_PER_TASK} proposals already "
                    f"created from task {origin_task_id}. Consolidate the work into an existing "
                    f"proposal instead of opening another."
                )
        return None

    def _record_proposal(self, origin_task_id: Optional[str]) -> None:
        """Record a successful proposal against both runaway counters."""
        self._proposal_timestamps.append(self._now().timestamp())
        if origin_task_id:
            self._proposals_by_task[origin_task_id] = self._proposals_by_task.get(origin_task_id, 0) + 1

    @staticmethod
    def _parse_requested_budget(params: ToolParameters) -> Tuple[Optional[RequestedBudget], Optional[str]]:
        """Parse the optional requested budget. Returns (budget, error).

        A *request* carries no authority whatsoever — see RequestedBudget's
        docstring for why it is structurally unassignable to a GrantedBudget.
        """
        amount_raw = params.get("requested_budget_amount")
        currency = params.get("requested_budget_currency")
        purpose = params.get("requested_budget_purpose")

        provided = [v for v in (amount_raw, currency, purpose) if v is not None]
        if not provided:
            return None, None
        if len(provided) != 3:
            return None, (
                "A requested budget needs all of requested_budget_amount, "
                "requested_budget_currency and requested_budget_purpose."
            )

        try:
            amount = Decimal(str(amount_raw))
        except (InvalidOperation, ValueError, TypeError):
            return None, f"requested_budget_amount is not a number: {amount_raw!r}"

        try:
            justification = params.get("requested_budget_justification")
            budget = RequestedBudget(
                requested_amount=amount,
                requested_currency=str(currency),
                purpose=str(purpose),
                justification=str(justification) if justification is not None else None,
            )
        except Exception as e:
            return None, f"Invalid requested budget: {e}"
        return budget, None

    async def _create_ticket(self, params: ToolParameters) -> ToolResult:
        """Propose a new ticket. Creates it in PROPOSAL state — never executing.

        The proposal is written with status ``proposed``, which is not one of the
        statuses WorkProcessor discovers, so no Task is generated from it. A
        human must move it to ``pending`` (and, for spend, issue a budget grant)
        before any work happens.
        """
        try:
            from ciris_engine.logic.persistence.models.tickets import create_ticket

            goal_description = params.get("goal_description")
            if not goal_description or not isinstance(goal_description, str):
                return ToolResult(success=False, error="goal_description (str) is required")

            # Provenance. task_id is injected by ToolHandler._build_tool_params;
            # it is advisory-only here (it labels the proposal, it does not
            # authorize anything) so a model-authored value cannot escalate.
            origin_task_id = params.get("task_id")
            origin_task_id = str(origin_task_id) if origin_task_id else None
            origin_thought_id = params.get("thought_id")
            origin_thought_id = str(origin_thought_id) if origin_thought_id else None

            # Runaway bound
            rate_error = self._check_proposal_rate_limit(origin_task_id)
            if rate_error:
                logger.warning(f"[CREATE_TICKET] Rate limited: {rate_error}")
                return ToolResult(success=False, error=rate_error)

            # Requested budget (optional). Requesting is not granting.
            requested_budget, budget_error = self._parse_requested_budget(params)
            if budget_error:
                return ToolResult(success=False, error=budget_error)

            # The agent may not write reserved metadata keys — those carry the
            # grant and the spend ledger. Refuse loudly rather than stripping.
            supplied_metadata = params.get("metadata")
            metadata: Dict[str, Any] = {}
            if isinstance(supplied_metadata, dict):
                reserved = RESERVED_TICKET_METADATA_KEYS.intersection(supplied_metadata.keys())
                if reserved:
                    return ToolResult(
                        success=False,
                        error=(
                            f"Refusing to create ticket: metadata keys {sorted(reserved)} are reserved for "
                            f"human-issued authorization and cannot be set by the agent."
                        ),
                    )
                metadata = dict(supplied_metadata)

            now = self._now()
            ticket_id = f"PROP-{uuid.uuid4().hex[:12].upper()}"

            proposal = TicketProposal(
                origin_task_id=origin_task_id,
                origin_thought_id=origin_thought_id,
                proposed_at=now,
                proposed_by="agent",
                goal_description=goal_description,
            )
            metadata[PROPOSAL_METADATA_KEY] = proposal.model_dump(mode="json")
            if requested_budget is not None:
                metadata[REQUESTED_BUDGET_METADATA_KEY] = requested_budget.model_dump(mode="json")

            priority_raw = params.get("priority", 5)
            try:
                priority = int(priority_raw)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                priority = 5
            priority = max(1, min(10, priority))

            sop = params.get("sop") or DEFAULT_PROPOSAL_SOP
            ticket_type = params.get("ticket_type") or DEFAULT_PROPOSAL_TICKET_TYPE
            contact_email = params.get("contact_email") or DEFAULT_PROPOSAL_EMAIL
            notes = params.get("notes")

            created = create_ticket(
                ticket_id=ticket_id,
                sop=str(sop),
                ticket_type=str(ticket_type),
                email=str(contact_email),
                status=PROPOSAL_TICKET_STATUS,
                priority=priority,
                submitted_at=now,
                metadata=metadata,
                notes=str(notes) if notes else None,
                automated=True,
                correlation_id=origin_task_id,
            )
            if not created:
                return ToolResult(success=False, error="Failed to create proposal ticket")

            self._record_proposal(origin_task_id)
            self._tickets_proposed += 1

            result_data: Dict[str, Any] = {
                "ticket_id": ticket_id,
                "status": PROPOSAL_TICKET_STATUS,
                "is_proposal": True,
                "will_execute": False,
                "goal_description": goal_description,
                "origin_task_id": origin_task_id,
                "requested_budget": (metadata.get(REQUESTED_BUDGET_METADATA_KEY) if requested_budget else None),
                "next_step": (
                    "This is a PROPOSAL and will not run. A human must approve it. "
                    + (
                        "The requested budget is a request, not an authorization — no spend is "
                        "possible until a Wise Authority grants a budget on this ticket."
                        if requested_budget
                        else "A human must move it to 'pending' for work to begin."
                    )
                ),
            }
            logger.info(
                f"[CREATE_TICKET] Proposal {ticket_id} created (origin_task={origin_task_id}, "
                f"requested_budget={'yes' if requested_budget else 'no'})"
            )
            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error creating proposal ticket: {e}")
            return ToolResult(success=False, error=str(e))

    async def _get_ticket(self, params: ToolParameters) -> ToolResult:
        """Retrieve current ticket state during task processing."""
        try:
            from ciris_engine.logic.persistence.models.tickets import get_ticket

            ticket_id = params.get("ticket_id")
            if not ticket_id or not isinstance(ticket_id, str):
                return ToolResult(success=False, error=ERROR_TICKET_ID_REQUIRED)

            # Use self._db_path to respect provided path or current config
            ticket = get_ticket(ticket_id)
            if not ticket:
                return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

            self._tickets_retrieved += 1
            return ToolResult(success=True, data=ticket)

        except Exception as e:
            logger.error(f"Error retrieving ticket: {e}")
            return ToolResult(success=False, error=str(e))

    async def _defer_ticket(self, params: ToolParameters) -> ToolResult:
        """Defer ticket processing to a future time or await human response.

        Automatically sets ticket status to 'deferred' to prevent WorkProcessor
        from creating new tasks until the deferral condition is resolved.
        """
        try:
            from datetime import timedelta

            from ciris_engine.logic.persistence.models.tickets import (
                get_ticket,
                update_ticket_metadata,
                update_ticket_status,
            )

            ticket_id = params.get("ticket_id")
            if not ticket_id or not isinstance(ticket_id, str):
                return ToolResult(success=False, error=ERROR_TICKET_ID_REQUIRED)

            # Get current ticket - use self._db_path to respect provided path or current config
            current_ticket = get_ticket(ticket_id)
            if not current_ticket:
                return ToolResult(success=False, error=f"Ticket {ticket_id} not found")

            current_metadata = current_ticket.get("metadata", {})
            if not isinstance(current_metadata, dict):
                current_metadata = {}

            # Determine deferral type
            defer_until_timestamp = params.get("defer_until")  # ISO8601 timestamp
            defer_hours = params.get("defer_hours")  # Relative hours
            await_human = params.get("await_human", False)  # Wait for human response
            reason = params.get("reason", "No reason provided")

            result_data = {"ticket_id": ticket_id, "deferral_type": None, "reason": reason}

            if await_human:
                # Mark as awaiting human response
                current_metadata["awaiting_human_response"] = True
                current_metadata["deferred_reason"] = reason
                current_metadata["deferred_at"] = self._now().isoformat()
                result_data["deferral_type"] = "awaiting_human"

            elif defer_until_timestamp:
                # Defer until specific timestamp
                current_metadata["deferred_until"] = defer_until_timestamp
                current_metadata["deferred_reason"] = reason
                current_metadata["deferred_at"] = self._now().isoformat()
                current_metadata["awaiting_human_response"] = False
                result_data["deferral_type"] = "until_timestamp"
                result_data["deferred_until"] = defer_until_timestamp

            elif defer_hours:
                # Defer for relative hours
                if not isinstance(defer_hours, (int, float)):
                    return ToolResult(success=False, error="defer_hours must be a number")
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

            # Update ticket status to 'deferred' (prevents task generation)
            status_success = update_ticket_status(ticket_id, "deferred", notes=f"Deferred: {reason}")
            if not status_success:
                return ToolResult(success=False, error=f"Failed to update ticket {ticket_id} status to deferred")

            # Update ticket metadata
            success = update_ticket_metadata(ticket_id, current_metadata)
            if not success:
                return ToolResult(success=False, error=f"Failed to defer ticket {ticket_id}")

            self._tickets_deferred += 1
            result_data["status_updated"] = "deferred"
            return ToolResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Error deferring ticket: {e}")
            return ToolResult(success=False, error=str(e))

    async def get_available_tools(self) -> List[str]:
        """Get list of available tool names."""
        return [
            "recall_secret",
            "update_secrets_filter",
            "self_help",
            "create_ticket",
            "update_ticket",
            "get_ticket",
            "defer_ticket",
        ]

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""
        if tool_name == "recall_secret":
            return ToolInfo(
                name="recall_secret",
                description="Recall a stored secret by UUID",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "secret_uuid": {"type": "string", "description": "UUID of the secret to recall"},
                        "purpose": {"type": "string", "description": "Why the secret is needed (for audit)"},
                        "decrypt": {
                            "type": "boolean",
                            "description": "Whether to decrypt the secret value",
                            "default": False,
                        },
                    },
                    required=["secret_uuid", "purpose"],
                ),
                category="security",
                when_to_use="When you need to retrieve a previously stored secret value",
            )
        elif tool_name == "update_secrets_filter":
            return ToolInfo(
                name="update_secrets_filter",
                description="Update secrets detection filter configuration",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "operation": {
                            "type": "string",
                            "enum": ["add_pattern", "remove_pattern", "list_patterns", "enable"],
                            "description": "Operation to perform",
                        },
                        "pattern": {"type": "string", "description": "Pattern for add/remove operations"},
                        "pattern_type": {"type": "string", "enum": ["regex", "exact"], "default": "regex"},
                        "enabled": {"type": "boolean", "description": "For enable operation"},
                    },
                    required=["operation"],
                ),
                category="security",
                when_to_use="When you need to modify how secrets are detected",
            )
        elif tool_name == "self_help":
            return ToolInfo(
                name="self_help",
                description="Access your experience document for guidance",
                parameters=ToolParameterSchema(type="object", properties={}, required=[]),
                category="knowledge",
                when_to_use="When you need guidance on your capabilities or best practices",
            )
        elif tool_name == "create_ticket":
            return ToolInfo(
                name="create_ticket",
                description=(
                    "Propose a new ticket for work you cannot do now. Creates it in PROPOSAL state — "
                    "it will NOT run until a human approves it."
                ),
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "goal_description": {
                            "type": "string",
                            "description": "What the work is and why it is needed",
                        },
                        "sop": {
                            "type": "string",
                            "description": f"SOP identifier (default '{DEFAULT_PROPOSAL_SOP}')",
                        },
                        "ticket_type": {
                            "type": "string",
                            "description": f"Ticket type (default '{DEFAULT_PROPOSAL_TICKET_TYPE}')",
                        },
                        "priority": {
                            "type": "integer",
                            "description": "Priority 1-10 (default 5)",
                        },
                        "contact_email": {
                            "type": "string",
                            "description": "Contact email for the proposal, if a human should be reached",
                        },
                        "notes": {"type": "string", "description": "Optional notes for the reviewing human"},
                        "metadata": {
                            "type": "object",
                            "description": "Additional metadata. Reserved authorization keys are refused.",
                        },
                        "requested_budget_amount": {
                            "type": "number",
                            "description": "Spend amount you are REQUESTING (not granting). Requires currency+purpose.",
                        },
                        "requested_budget_currency": {
                            "type": "string",
                            "description": "Currency of the requested budget, e.g. USDC",
                        },
                        "requested_budget_purpose": {
                            "type": "string",
                            "description": "What the requested budget would be spent on",
                        },
                        "requested_budget_justification": {
                            "type": "string",
                            "description": "Why this spend is warranted",
                        },
                    },
                    required=["goal_description"],
                ),
                category="workflow",
                when_to_use=(
                    "When work needs to happen that you cannot or should not do in this task — "
                    "especially when it needs money. Proposing is how you ask; it is not how you act."
                ),
                documentation=ToolDocumentation(
                    quick_start=(
                        "create_ticket opens a PROPOSAL. It does not start work and does not spend "
                        "anything. A human reviews it and decides."
                    ),
                    detailed_instructions="""
## What this tool does and does not do

`create_ticket` writes a ticket with status `proposed`. The work processor only
picks up tickets in `pending`, `assigned` or `in_progress`, so **a proposal never
becomes a running task by itself**. A human must move it forward.

## Requesting a budget

If the work needs money, include `requested_budget_amount`,
`requested_budget_currency` and `requested_budget_purpose`.

**Requesting is not granting.** The amount you name is recorded as a request and
carries no authority. Spend tools stay closed until a Wise Authority issues a
*granted* budget on the ticket, which happens outside your reasoning entirely.
You cannot approve your own proposal, and there is no parameter, metadata key or
tool sequence that lets you try.

When a budget is granted, spend on that ticket is bounded by whichever is
tighter: what was granted, or the deployment's own spending envelope.

## Limits

You may open at most 3 proposals from one task, and 20 per hour overall. Past
that the tool fails with an explicit message. If you hit it, consolidate into a
proposal you already opened rather than opening another.
""",
                    examples=[
                        UsageExample(
                            title="Propose follow-up work",
                            description="Work that belongs in its own task",
                            code='{"goal_description": "Migrate the archived DSAR exports to cold storage", "priority": 4}',
                        ),
                        UsageExample(
                            title="Propose work that needs money",
                            description="Request a budget; a human decides whether to grant it",
                            code=(
                                '{"goal_description": "Pay the data-broker opt-out fee for this DSAR", '
                                '"requested_budget_amount": 25, "requested_budget_currency": "USDC", '
                                '"requested_budget_purpose": "Opt-out processing fee", '
                                '"requested_budget_justification": "Required to complete the erasure request"}'
                            ),
                        ),
                    ],
                    gotchas=[
                        ToolGotcha(
                            title="A proposal does not run",
                            description=(
                                "Creating a ticket does not start the work. Do not assume the task is "
                                "underway, and do not tell a user it is."
                            ),
                            severity="warning",
                        ),
                        ToolGotcha(
                            title="A requested budget is not money you have",
                            description=(
                                "Naming an amount does not authorize it. Spend remains denied until a "
                                "human grants a budget on this ticket."
                            ),
                            severity="error",
                        ),
                        ToolGotcha(
                            title="Reserved metadata keys are refused",
                            description=(
                                "Metadata keys carrying authorization (the granted budget and the spend "
                                "ledger) cannot be written by you. Attempting it fails the call."
                            ),
                            severity="error",
                        ),
                    ],
                ),
                dma_guidance=ToolDMAGuidance(
                    when_not_to_use=(
                        "Don't propose work you can simply do now, and don't open a second proposal for "
                        "something you already proposed. Don't use a proposal to imply work has started."
                    ),
                    ethical_considerations=(
                        "A proposal asks a human to spend attention, and a budget request asks them to "
                        "spend money. Be honest and specific about what is needed and why, state the "
                        "smallest amount that actually suffices, and be clear with the user that the "
                        "work is proposed rather than underway."
                    ),
                    prerequisite_actions=[
                        "Check whether the work can be completed in the current task",
                        "get_ticket / review open proposals before opening another",
                    ],
                    followup_actions=[
                        "Tell the user the work is proposed and awaiting human approval",
                    ],
                    min_confidence=0.7,
                    # Deliberately False. A proposal has no external effect: it writes a row no
                    # processor picks up and notifies no one. Gating the request behind approval
                    # would be circular — the proposal exists in order to ask — and would turn
                    # every ask into a human interrupt. The human decision point is the budget
                    # grant, which is enforced deterministically at the spend path.
                    requires_approval=False,
                ),
            )
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
                            "enum": [
                                "pending",
                                "assigned",
                                "in_progress",
                                "blocked",
                                "deferred",
                                "completed",
                                "cancelled",
                                "failed",
                            ],
                            "description": "New ticket status",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Metadata updates (merged with existing metadata)",
                        },
                        "notes": {"type": "string", "description": "Optional notes about the update"},
                    },
                    required=["ticket_id"],
                ),
                category="workflow",
                when_to_use="When processing a ticket task and need to record progress or results",
                documentation=ToolDocumentation(
                    quick_start="Use update_ticket to record progress on multi-stage tasks. "
                    "Metadata is deep-merged so you can update just the fields you need.",
                    detailed_instructions="""
## Ticket Metadata Structure

Tickets support structured metadata for tracking multi-stage workflows:

```json
{
  "stages": {
    "stage_name": {
      "status": "in_progress|completed|failed",
      "result": "any data from this stage",
      "error": "error message if failed"
    }
  },
  "custom_field": "any other data you need"
}
```

## Deep Merge Behavior

When you update metadata, it's deep-merged with existing metadata:
- Top-level keys are merged (new keys added, existing preserved)
- The `stages` object is specially handled: each stage is merged individually
- This means you can update one stage without losing others

## Status Transitions

Valid status values and when to use them:
- `in_progress`: Active work happening
- `blocked`: Waiting on external dependency
- `deferred`: Intentionally delayed (use defer_ticket instead)
- `completed`: Successfully finished
- `failed`: Unrecoverable error occurred
""",
                    examples=[
                        UsageExample(
                            title="Update stage progress",
                            description="Record completion of a processing stage",
                            code='{"ticket_id": "TKT-123", "metadata": {"stages": {"validation": {"status": "completed", "result": "all checks passed"}}}}',
                        ),
                        UsageExample(
                            title="Mark ticket blocked",
                            description="Indicate ticket is waiting on external input",
                            code='{"ticket_id": "TKT-123", "status": "blocked", "notes": "Waiting for user to provide API key"}',
                        ),
                    ],
                    gotchas=[
                        ToolGotcha(
                            title="Don't use for deferrals",
                            description="Use defer_ticket instead of setting status='deferred' directly. "
                            "defer_ticket properly sets up the deferral metadata and prevents task generation.",
                            severity="warning",
                        ),
                        ToolGotcha(
                            title="Metadata must be JSON",
                            description="If passing metadata as a string (from CLI), it must be valid JSON. "
                            "The tool will attempt to parse JSON strings automatically.",
                            severity="info",
                        ),
                    ],
                ),
                dma_guidance=ToolDMAGuidance(
                    when_not_to_use="Don't use to mark tickets as deferred - use defer_ticket instead",
                    prerequisite_actions=["get_ticket to verify current state if unsure"],
                    followup_actions=["get_ticket to verify update was applied if critical"],
                ),
            )
        elif tool_name == "get_ticket":
            return ToolInfo(
                name="get_ticket",
                description="Retrieve current ticket state during task processing",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={"ticket_id": {"type": "string", "description": "Ticket ID to retrieve"}},
                    required=["ticket_id"],
                ),
                category="workflow",
                when_to_use="When you need to check current ticket status, metadata, or stage progress",
            )
        elif tool_name == "defer_ticket":
            return ToolInfo(
                name="defer_ticket",
                description="Defer ticket processing to future time or await human response",
                parameters=ToolParameterSchema(
                    type="object",
                    properties={
                        "ticket_id": {"type": "string", "description": "Ticket ID to defer"},
                        "defer_until": {"type": "string", "description": "ISO8601 timestamp to defer until"},
                        "defer_hours": {"type": "number", "description": "Hours to defer (relative)"},
                        "await_human": {
                            "type": "boolean",
                            "description": "Wait for human response (blocks task generation)",
                        },
                        "reason": {"type": "string", "description": "Reason for deferral (for audit/transparency)"},
                    },
                    required=["ticket_id", "reason"],
                ),
                category="workflow",
                when_to_use="When ticket needs human input or must wait for external event/time",
                documentation=ToolDocumentation(
                    quick_start="Use defer_ticket when you cannot proceed without human input "
                    "or need to wait for a specific time. Choose ONE of: await_human, defer_until, or defer_hours.",
                    detailed_instructions="""
## Deferral Types

You must specify exactly ONE of these options:

1. **await_human=true**: Use when you need human input to proceed
   - Ticket stays deferred until human responds
   - No automatic reactivation

2. **defer_hours**: Use for relative time delays
   - Specify hours as a number (can be decimal, e.g., 0.5 for 30 minutes)
   - System will reactivate ticket after the time passes

3. **defer_until**: Use for specific time targets
   - Provide ISO8601 timestamp (e.g., "2024-01-15T09:00:00Z")
   - Useful for scheduling at specific times

## What Happens When You Defer

1. Ticket status is automatically set to 'deferred'
2. Metadata is updated with deferral details
3. WorkProcessor stops generating new tasks for this ticket
4. Ticket will be reactivated when condition is met

## Reason Field

Always provide a clear reason - this appears in audit logs and helps
humans understand why the ticket was deferred.
""",
                    examples=[
                        UsageExample(
                            title="Wait for human input",
                            description="Defer until user provides missing information",
                            code='{"ticket_id": "TKT-123", "await_human": true, "reason": "Need user to specify which database to use"}',
                        ),
                        UsageExample(
                            title="Delay for rate limiting",
                            description="Wait 1 hour before retrying API call",
                            code='{"ticket_id": "TKT-123", "defer_hours": 1, "reason": "API rate limit hit, waiting for quota reset"}',
                        ),
                        UsageExample(
                            title="Schedule for business hours",
                            description="Wait until specific time",
                            code='{"ticket_id": "TKT-123", "defer_until": "2024-01-15T09:00:00Z", "reason": "Scheduling for business hours"}',
                        ),
                    ],
                    gotchas=[
                        ToolGotcha(
                            title="Choose only one deferral type",
                            description="Specify exactly ONE of: await_human, defer_until, or defer_hours. "
                            "Providing none or multiple will cause an error.",
                            severity="error",
                        ),
                        ToolGotcha(
                            title="Reason is required",
                            description="Always provide a reason for audit trail and human understanding. "
                            "Vague reasons like 'waiting' are not helpful.",
                            severity="warning",
                        ),
                    ],
                ),
                dma_guidance=ToolDMAGuidance(
                    when_not_to_use="Don't defer just to avoid work - only defer when genuinely blocked",
                    ethical_considerations="Be transparent about why you're deferring. "
                    "Users should understand what's blocking progress.",
                    prerequisite_actions=["Exhaust other options first - can you proceed without human input?"],
                ),
            )
        return None

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get information about all available tools."""
        tools = []
        for tool_name in await self.get_available_tools():
            tool_info = await self.get_tool_info(tool_name)
            if tool_info:
                tools.append(tool_info)
        return tools

    async def validate_parameters(self, tool_name: str, parameters: ToolParameters) -> bool:
        """Validate parameters for a tool."""
        if tool_name == "recall_secret":
            return "secret_uuid" in parameters and "purpose" in parameters
        elif tool_name == "update_secrets_filter":
            operation = parameters.get("operation")
            if not operation:
                return False
            if operation in ["add_pattern", "remove_pattern"]:
                return "pattern" in parameters
            return True
        elif tool_name == "self_help":
            return True  # No parameters required
        elif tool_name == "create_ticket":
            return "goal_description" in parameters
        elif tool_name == "update_ticket":
            return "ticket_id" in parameters
        elif tool_name == "get_ticket":
            return "ticket_id" in parameters
        elif tool_name == "defer_ticket":
            return "ticket_id" in parameters and "reason" in parameters
        return False

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of an async tool execution."""
        # Secrets tools execute synchronously
        return None

    async def list_tools(self) -> List[str]:
        """List available tools - required by ToolServiceProtocol."""
        return await self.get_available_tools()

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool - required by ToolServiceProtocol."""
        tool_info = await self.get_tool_info(tool_name)
        if tool_info:
            return tool_info.parameters
        return None

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get base capabilities
        capabilities = super().get_capabilities()

        # Add custom metadata using model_copy
        if capabilities.metadata:
            capabilities.metadata = capabilities.metadata.model_copy(
                update={"adapter": self.adapter_name, "tool_count": 6}
            )

        return capabilities

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect tool service specific metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate success rate
        success_rate = 0.0
        if self._request_count > 0:
            success_rate = (self._request_count - self._error_count) / self._request_count

        # Add tool-specific metrics
        metrics.update(
            {
                "tool_executions": float(self._request_count),
                "tool_errors": float(self._error_count),
                "success_rate": success_rate,
                "secrets_retrieved": float(self._secrets_retrieved),
                "tickets_updated": float(self._tickets_updated),
                "tickets_retrieved": float(self._tickets_retrieved),
                "tickets_deferred": float(self._tickets_deferred),
                "audit_events_generated": float(self._request_count),  # Each execution generates an audit event
                "available_tools": 6.0,  # recall_secret, update_secrets_filter, self_help, update_ticket, get_ticket, defer_ticket
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """Get all metrics including base, custom, and v1.4.3 specific.

        Returns:
            Dict with all metrics including tool-specific and v1.4.3 metrics
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        current_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = max(0.0, (current_time - self._start_time).total_seconds())

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "core_tool_invocations": float(self._request_count),
                "core_tool_uptime_seconds": uptime_seconds,
                "secrets_retrieved": float(self._secrets_retrieved),
                "secrets_stored": 0.0,  # This service only retrieves, never stores
                "tickets_updated": float(self._tickets_updated),
                "tickets_retrieved": float(self._tickets_retrieved),
                "tickets_deferred": float(self._tickets_deferred),
                # Backwards compatibility aliases for unit tests
                "tickets_updated_total": float(self._tickets_updated),
                "tickets_deferred_total": float(self._tickets_deferred),
                "tools_enabled": 6.0,  # recall_secret, update_secrets_filter, self_help, update_ticket, get_ticket, defer_ticket
            }
        )

        return metrics

    # get_telemetry() removed - use get_metrics() from BaseService instead
