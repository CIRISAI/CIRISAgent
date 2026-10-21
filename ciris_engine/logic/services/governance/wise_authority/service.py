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
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType, TaskStatus
from ciris_engine.schemas.runtime.models import TaskContext
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import (
    AuthorizationDecision,
    AuthorizationDenialReason,
    DeferralApprovalContext,
    DeferralRequest,
    DeferralResponse,
    DeferralVerification,
    GuidanceRequest,
    GuidanceResponse,
    WAPermission,
    WARole,
    deferral_resolution_record,
    is_unverifiable_legacy_signature,
    scope_grants,
)
from ciris_engine.schemas.services.context import GuidanceContext
from ciris_engine.schemas.services.core import ServiceStatus

logger = logging.getLogger(__name__)

# Actions an AUTHORITY may never take: minting is the one privilege reserved to
# ROOT, because a WA able to mint WAs can manufacture its own jurisdiction and
# every downstream scope check becomes advisory.
MINTING_ACTIONS = frozenset({"mint_wa", "create_wa", "bootstrap_root"})

# The complete set an OBSERVER may take. Unchanged from the original role gate —
# hoisted out of the function body only so the two gates read as data.
OBSERVER_ACTIONS = frozenset({"read", "send_message", "observe", "get_status"})


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

        # REDACTED. `db_path` is a full DSN in a Postgres deployment, password
        # included, and this line wrote it in cleartext to /app/logs/latest.log
        # on EVERY boot — a file `qa_runner pull-logs` collects into support
        # bundles by design, so the credential travelled off-host with them.
        # Found on live production containers.
        #
        # The helper already existed and the `[DB_INIT]` logger three lines
        # earlier was already using it correctly; this call site simply did not.
        from ciris_engine.logic.persistence.db.core import _redact_dsn

        logger.info(f"Consolidated WA Service initialized with DB: {_redact_dsn(str(self.db_path))}")

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
            "authorize",
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
        from ciris_engine.logic.infrastructure.authorization.tool_approval import (
            TOOL_APPROVAL_DETAIL_KEY,
            TOOL_APPROVAL_DETAIL_MAX_CHARS,
        )

        ui_context: Dict[str, str] = {
            "task_description": (description[:500] if description else ""),
        }
        # Add deferral-specific context fields (converted to strings for UI)
        deferral_context = deferral_info.get("context", {})
        if isinstance(deferral_context, dict):
            for key, value in deferral_context.items():
                if value is None:
                    continue
                # The tool-approval detail (CIRISAgent#942) is a JSON document the
                # approval screen parses to show WHAT is being approved. Clipping
                # it at the generic 200-char UI budget would truncate it into
                # unparseable JSON, and the human would be back to approving a
                # sentence. It has its own cap, applied where it is encoded.
                limit = TOOL_APPROVAL_DETAIL_MAX_CHARS if key == TOOL_APPROVAL_DETAIL_KEY else 200
                ui_context[key] = str(value)[:limit]
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

    @staticmethod
    def _held_scopes(wa: object) -> List[str]:
        """The WA's scope list, normalized, never raising.

        ``WACertificate.scopes`` decodes ``scopes_json`` on every access, and the
        rows behind it are known to carry historical shapes — see
        ``persistence/stores/authentication_store.py``, where a doubly-encoded
        ``scopes`` column yields a *string* where the schema promises a list.
        A scope set that fails to decode must resolve to "no scopes", never to
        "unknown, so allow": this gate is the thing standing between a broad
        authority and a decision it has no jurisdiction over, and it is the one
        place where a parse failure absolutely must not widen access.
        """
        try:
            raw = wa.scopes  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover - defensive; malformed scopes_json
            return []
        if isinstance(raw, str) or not isinstance(raw, (list, tuple, set, frozenset)):
            return []
        return [str(scope) for scope in raw]

    async def authorize(self, wa_id: str, action: str, resource: Optional[str] = None) -> AuthorizationDecision:
        """Decide whether a WA may take ``action`` on ``resource``, inspectably.

        Two gates, in order. Both must pass.

        **Gate 1 — role.** What kind of decision may this WA make at all?
        ROOT everything, AUTHORITY everything but minting, OBSERVER a fixed read
        set. Unchanged from what shipped.

        **Gate 2 — scope.** Does this WA hold jurisdiction over *this* resource?
        This gate is new, and it is finding F1 (NULLWORKS RC3, MULTI-AUTH-01).
        Before it, ``check_authorization`` accepted a ``resource`` argument and
        never read it, so an AUTHORITY minted to adjudicate one domain
        adjudicated every domain. Routing or domain affinity is not
        decision-specific human jurisdiction; a powerful authority holding no
        scope for the decision in front of it has to be refused.

        ROOT skips gate 2 deliberately. ROOT is the recovery path — the identity
        you authenticate as when scopes are wrong, a certificate was minted
        badly, or the domain taxonomy itself needs repair. A gate that can lock
        out the operator who repairs gates is a gate that gets disabled.

        **What ``resource=None`` means, and why it is not a denial.**

        "No resource specified" is *not* the same fact as "no scope required".
        It means the **caller** did not say what is at stake. Silence is
        under-specification, not evidence of harmlessness, so nothing here
        invents a resource to check against or reads the omission as a grant of
        domain jurisdiction.

        But denying on silence would deny essentially every caller alive today:
        the protocol defaults ``resource`` to ``None``, ``request_approval``
        pulls it from ``context.metadata`` where it is usually absent, and the
        Discord adapter never sets it. Shipping that would take the deferral
        path down on the first call, and a control that gets reverted the
        morning after it lands protects nothing. So:

            resource is None  ->  the decision rests on the role gate alone,
                                  exactly as it did before this change. Never
                                  weaker than what shipped; never stronger.

        What *is* different is that the omission is no longer invisible. The
        returned decision carries ``scope_enforced=False`` and says so in
        ``message``, so a caller that skipped naming its resource is findable in
        logs and assertable in tests, instead of being indistinguishable from a
        scope check that actually ran and passed. Every such call site is a bug
        in the caller, and this is the field that lets us enumerate them before
        tightening the default.
        """
        wa = await self.auth_service.get_wa(wa_id)
        if not wa:
            return AuthorizationDecision(
                allowed=False,
                reason=AuthorizationDenialReason.WA_NOT_FOUND,
                message=f"No WA certificate found for '{wa_id}'",
                wa_id=wa_id,
                action=action,
                resource=resource,
            )

        role = wa.role
        held_scopes = self._held_scopes(wa)

        # --- Gate 1: role ----------------------------------------------------
        if role == WARole.ROOT:
            return AuthorizationDecision(
                allowed=True,
                message=f"ROOT '{wa_id}' is unconditionally authorized for '{action}' (recovery path)",
                wa_id=wa_id,
                role=role,
                action=action,
                resource=resource,
                held_scopes=held_scopes,
            )

        if role == WARole.AUTHORITY:
            role_allows = action not in MINTING_ACTIONS
        else:  # OBSERVER
            role_allows = action in OBSERVER_ACTIONS

        if not role_allows:
            return AuthorizationDecision(
                allowed=False,
                reason=AuthorizationDenialReason.ROLE_FORBIDS_ACTION,
                message=f"Role {role.value} may not perform '{action}'",
                wa_id=wa_id,
                role=role,
                action=action,
                resource=resource,
                held_scopes=held_scopes,
            )

        # --- Gate 2: resource scope ------------------------------------------
        if resource is None:
            return AuthorizationDecision(
                allowed=True,
                message=(
                    f"Role {role.value} permits '{action}'; caller named no resource, "
                    "so no jurisdiction check was possible (role gate only)"
                ),
                wa_id=wa_id,
                role=role,
                action=action,
                resource=None,
                scope_enforced=False,
                held_scopes=held_scopes,
            )

        required_scope = f"{action}:{resource}"
        if not any(scope_grants(scope, action, resource) for scope in held_scopes):
            return AuthorizationDecision(
                allowed=False,
                reason=AuthorizationDenialReason.SCOPE_ABSENT,
                message=(
                    f"Role {role.value} permits '{action}', but WA '{wa_id}' holds no scope "
                    f"covering resource '{resource}'. Required: a scope granting '{required_scope}'; "
                    f"held: {held_scopes}"
                ),
                wa_id=wa_id,
                role=role,
                action=action,
                resource=resource,
                scope_enforced=True,
                required_scope=required_scope,
                held_scopes=held_scopes,
            )

        return AuthorizationDecision(
            allowed=True,
            message=f"WA '{wa_id}' holds scope for '{action}' on '{resource}'",
            wa_id=wa_id,
            role=role,
            action=action,
            resource=resource,
            scope_enforced=True,
            required_scope=required_scope,
            held_scopes=held_scopes,
        )

    async def check_authorization(self, wa_id: str, action: str, resource: Optional[str] = None) -> bool:
        """Check if a WA is authorized for an action on a resource.

        Boolean face of :meth:`authorize`, kept because it is the protocol
        signature every adapter implements. The reasoning is not thrown away
        when it collapses to a bool — a denial is logged with the scope that was
        demanded and the scopes the WA actually held, because "an approval was
        refused and nobody could see why" is the condition that let this gate
        stay decorative for as long as it did. Callers that need the reasoning
        as a value should call :meth:`authorize` directly.
        """
        decision = await self.authorize(wa_id, action, resource)

        if not decision.allowed:
            logger.warning(
                "WA authorization DENIED [%s]: %s",
                decision.reason.value if decision.reason else "unspecified",
                decision.message,
            )
        elif not decision.scope_enforced:
            # INFO, not WARNING: this is the behaviour that already shipped, so
            # it is not itself an incident, and check_authorization sits on the
            # deferral path where a per-call warning would train operators to
            # filter the log. The fact is carried structurally on the decision
            # for anything that wants to assert on it.
            logger.info(
                "WA authorization allowed WITHOUT a jurisdiction check (caller named no resource): %s",
                decision.message,
            )

        return decision.allowed

    async def request_approval(self, action: str, context: DeferralApprovalContext) -> bool:
        """Request approval for an action - may defer to human.

        Returns True if immediately approved (e.g., requester is ROOT),
        False if deferred to human WA.
        """
        # Check if requester can self-approve.
        #
        # Uses authorize() rather than check_authorization() so the *reason* for
        # a refusal survives into the deferral below. A human opening this
        # deferral needs to know whether it reached them because the requester's
        # role forbids the action outright or because the requester is a real
        # authority who simply holds no jurisdiction over this resource — those
        # are different situations and they want different answers.
        resource = context.metadata.get("resource") if context.metadata else None
        decision = await self.authorize(context.requester_id, action, resource)

        if decision.allowed:
            logger.info(f"Action {action} auto-approved for {context.requester_id}: {decision.message}")
            return True

        logger.info(
            "Action %s not self-approvable for %s [%s]: %s",
            action,
            context.requester_id,
            decision.reason.value if decision.reason else "unspecified",
            decision.message,
        )

        # Create a deferral for human approval
        deferral_context = {
            "action": action,
            "requester": context.requester_id,
            "authorization_denial_reason": decision.reason.value if decision.reason else "unspecified",
        }
        if decision.required_scope:
            deferral_context["required_scope"] = decision.required_scope
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

            # Routed through persist substrate (CIRISAgent#763).
            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.persistence.models.tasks import _persist_row_to_task, _task_to_persist_payload

            engine = get_persist_engine()
            if engine is None:
                raise RuntimeError("persist engine not initialized — cannot send deferral")

            raw = engine.task_get(deferral.task_id)
            if raw is None:
                logger.error(f"Task {deferral.task_id} not found for deferral")
                raise ValueError(f"Task {deferral.task_id} not found")

            row = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(row, dict):
                logger.error(f"Task {deferral.task_id} returned non-dict row")
                raise ValueError(f"Task {deferral.task_id} not found")

            existing_task = _persist_row_to_task(row)
            existing_context: Dict[str, object] = {}
            ctx = row.get("context")
            if isinstance(ctx, str):
                try:
                    parsed_ctx = json.loads(ctx)
                    if isinstance(parsed_ctx, dict):
                        existing_context = parsed_ctx
                except json.JSONDecodeError:
                    existing_context = {}
            elif isinstance(ctx, dict):
                existing_context = dict(ctx)

            existing_context["deferral"] = {
                "deferral_id": deferral_id,
                "thought_id": deferral.thought_id,
                "reason": deferral.reason,
                "defer_until": deferral.defer_until.isoformat() if deferral.defer_until else None,
                "requires_wa_approval": True,
                "context": deferral.context or {},
                "created_at": self._now().isoformat(),
            }

            # Build an upsert payload preserving every field while flipping
            # status + replacing context. We can't use task_update_status
            # because that wouldn't carry the deferral metadata into
            # context_json.
            payload = _task_to_persist_payload(existing_task)
            payload["status"] = TaskStatus.DEFERRED.value
            payload["context"] = existing_context
            payload["updated_at"] = self._now().isoformat()
            engine.task_upsert(json.dumps(payload))

            logger.info(f"Task {deferral.task_id} marked as deferred - visible via /v1/wa/deferrals API")

            return deferral_id
        except Exception as e:
            logger.error(f"Failed to send deferral: {e}")
            raise

    async def get_pending_deferrals(self, wa_id: Optional[str] = None) -> List[PendingDeferral]:
        """Get pending deferrals from the tasks table.

        Routed through persist substrate (CIRISAgent#763); paginates
        DEFERRED tasks across all occurrences via task_list, since
        deferrals can originate from any occurrence and WAs review
        them globally.
        """
        result: List[PendingDeferral] = []

        try:
            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.persistence.models.tasks import _list_with_filter

            engine = get_persist_engine()
            if engine is None:
                logger.error("persist engine not initialized — cannot get pending deferrals")
                return []

            # Persist's task_list filter is equality on agent_occurrence_id,
            # which would force one query per occurrence. Iterate the known
            # set: "default", "__shared__", and any other occurrence_ids we
            # discover. For now, fetch from both the default and shared
            # namespaces (production has at most a handful of occurrences;
            # WA tooling lists deferrals from all of them by design).
            seen_task_ids: set[str] = set()
            deferred_tasks = []
            for occurrence_id in ("default", "__shared__"):
                try:
                    deferred_tasks.extend(
                        _list_with_filter({"status": TaskStatus.DEFERRED.value, "agent_occurrence_id": occurrence_id})
                    )
                except Exception as inner_e:
                    logger.warning(f"Failed to list deferred tasks for occurrence {occurrence_id}: {inner_e}")

            # Sort by updated_at DESC to match legacy ordering.
            deferred_tasks.sort(key=lambda t: getattr(t, "updated_at", ""), reverse=True)

            for task in deferred_tasks:
                if task.task_id in seen_task_ids:
                    continue
                seen_task_ids.add(task.task_id)

                # Re-extract context_json shape that _parse_deferral_context expects.
                # _persist_row_to_task collapses context onto the TaskContext model
                # which drops the deferral metadata; reconstruct a dict from the
                # raw persist row for parsing.
                raw = engine.task_get(task.task_id)
                if raw is None:
                    continue
                row = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(row, dict):
                    continue
                context_json = row.get("context")

                _, deferral_info = self._parse_deferral_context(context_json)
                priority_str = self._priority_to_string(task.priority)
                ui_context = self._build_ui_context(task.description, deferral_info)

                deferral = self._create_pending_deferral(
                    task_id=task.task_id,
                    channel_id=task.channel_id,
                    updated_at=task.updated_at,
                    deferral_info=deferral_info,
                    priority_str=priority_str,
                    ui_context=ui_context,
                    description=task.description,
                )
                result.append(deferral)

        except Exception as e:
            logger.error(f"Failed to get pending deferrals from database: {e}")
            return []

        return result

    async def _verify_resolution(self, deferral_id: str, response: DeferralResponse) -> DeferralVerification:
        """Classify a resolution's signature before anything acts on it (#944).

        Three outcomes, because two would force a lie about one of them:

        - ``VERIFIED``  — signature checks out against the signing key, and the
          owner binding agrees with the federation directory.
        - ``UNSIGNED``  — no signature, or one of the pre-#944 placeholder forms
          (``""`` / ``api_{user}_{ts}``). Deployed rows look like this. They are
          recorded as unverified and allowed through, because refusing them
          would break resolution of every deferral written before signing
          existed. They are never recorded as verified.
        - ``FAILED``    — a signature is present and does not check out, or
          cannot be checked. The caller refuses.

        The gap this leaves is worth stating plainly: an attacker who can write
        the row can also clear the signature and land in ``UNSIGNED``. Closing
        that means refusing unsigned resolutions outright, which is a data
        migration, not a code change. What is closed here is the weaker but
        real hole — a *forged* or *altered* signed resolution now cannot be
        acted on, and the record says which of the three it was.
        """
        if not response.signature or is_unverifiable_legacy_signature(response.signature):
            logger.warning(
                "Deferral %s carries no verifiable signature — recording as unverified (pre-#944 record)",
                deferral_id,
            )
            return DeferralVerification.UNSIGNED

        if not response.signed_at:
            # The canonical payload commits to signed_at; without it there is
            # nothing to rebuild the signature against.
            logger.error("Deferral %s has a signature but no signed_at — cannot verify", deferral_id)
            return DeferralVerification.FAILED

        try:
            ok = await self.auth_service.verify_deferral_resolution(deferral_id, response, response.signed_at)
        except Exception:
            logger.exception("Verification of deferral %s raised — refusing", deferral_id)
            return DeferralVerification.FAILED

        return DeferralVerification.VERIFIED if ok else DeferralVerification.FAILED

    async def resolve_deferral(self, deferral_id: str, response: DeferralResponse) -> bool:
        """Resolve a deferral by creating a new guidance task.

        When a deferral is resolved:
        1. Signature is verified — a signed-but-invalid resolution is refused
        2. Original deferred task is marked COMPLETED with outcome
        3. New guidance TASK is created (not just a thought) to ensure proper billing
        4. New task copies context from original and includes WA guidance
        5. New task is PENDING and ready for normal processing

        This ensures:
        - New billing cycle starts (new task = new credit charge)
        - Original task/thought history preserved
        - Proper task resumption flow
        """
        # Fail closed BEFORE any mutation (#944). A resolution that presents a
        # signature which does not verify must not complete the task, must not
        # create the guidance task, and must not spend the budget that #938
        # attaches to it.
        verification = await self._verify_resolution(deferral_id, response)
        if verification is DeferralVerification.FAILED:
            logger.error("Refusing deferral %s: signature present but did not verify", deferral_id)
            return False

        try:
            # Routed through persist substrate (CIRISAgent#763).
            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.persistence.models.tasks import (
                _list_with_filter,
                _persist_row_to_task,
                _task_to_persist_payload,
            )
            from ciris_engine.logic.utils.task_thought_factory import create_task

            engine = get_persist_engine()
            if engine is None:
                logger.error("persist engine not initialized — cannot resolve deferral")
                return False

            # Extract task_id from deferral_id
            # Format can be either defer_{task_id} or defer_{task_id}_{timestamp}
            task_id: Optional[str] = None
            if deferral_id.startswith("defer_"):
                parts = deferral_id.split("_", 2)
                if len(parts) == 2:
                    task_id = parts[1]
                elif len(parts) >= 3:
                    without_prefix = deferral_id[6:]
                    last_underscore = without_prefix.rfind("_")
                    if last_underscore > 0:
                        potential_timestamp = without_prefix[last_underscore + 1 :]
                        try:
                            float(potential_timestamp)
                            task_id = without_prefix[:last_underscore]
                        except ValueError:
                            task_id = without_prefix
                    else:
                        task_id = without_prefix
                else:
                    task_id = deferral_id[6:]
            else:
                # Fall back to scanning deferred tasks for deferral_id in context.
                matched: Optional[str] = None
                for occ in ("default", "__shared__"):
                    candidates = _list_with_filter({"status": TaskStatus.DEFERRED.value, "agent_occurrence_id": occ})
                    for cand in candidates:
                        raw = engine.task_get(cand.task_id)
                        if raw is None:
                            continue
                        row = json.loads(raw) if isinstance(raw, str) else raw
                        ctx_raw = row.get("context") if isinstance(row, dict) else None
                        ctx_str = json.dumps(ctx_raw) if isinstance(ctx_raw, dict) else (ctx_raw or "")
                        if f'"deferral_id":"{deferral_id}"' in ctx_str:
                            matched = cand.task_id
                            break
                    if matched:
                        break
                if not matched:
                    logger.error(f"Deferral {deferral_id} not found")
                    return False
                task_id = matched

            # Load the deferred task via persist.
            raw = engine.task_get(task_id)
            if raw is None:
                logger.error(f"Task {task_id} not found or not deferred")
                return False
            row = json.loads(raw) if isinstance(raw, str) else raw
            if not isinstance(row, dict) or row.get("status") != TaskStatus.DEFERRED.value:
                logger.error(f"Task {task_id} not found or not deferred")
                return False

            existing_task = _persist_row_to_task(row)
            original_task_id = existing_task.task_id
            channel_id = existing_task.channel_id
            original_description = existing_task.description
            priority = existing_task.priority
            agent_occurrence_id = existing_task.agent_occurrence_id

            context: Dict[str, object] = {}
            ctx_raw = row.get("context")
            if isinstance(ctx_raw, dict):
                context = dict(ctx_raw)
            elif isinstance(ctx_raw, str) and ctx_raw:
                try:
                    parsed = json.loads(ctx_raw)
                    if isinstance(parsed, dict):
                        context = parsed
                except json.JSONDecodeError:
                    pass

            # Add resolution to deferral info in the original task. This now
            # carries the signature and the `signed_at` it commits to (#944):
            # without them stored, verifying an approval after the fact was not
            # merely unwired but impossible, because the material to check
            # against was discarded at write time.
            deferral_info = context.get("deferral")
            if isinstance(deferral_info, dict):
                deferral_info["resolution"] = deferral_resolution_record(
                    response, self._now().isoformat(), verification
                )

            # Mark original deferred task as COMPLETED with outcome
            # Use TaskOutcome schema: status, summary, actions_taken, memories_created, errors
            if response.approved:
                outcome_data = {
                    "status": "success",
                    "summary": f"Deferral approved by WA {response.wa_id}: {response.reason}",
                    "actions_taken": ["Deferred to WA", f"Approved by {response.wa_id}"],
                    "memories_created": [],
                    "errors": [],
                }
            else:
                outcome_data = {
                    "status": "failure",
                    "summary": f"Deferral rejected by WA {response.wa_id}: {response.reason}",
                    "actions_taken": ["Deferred to WA", f"Rejected by {response.wa_id}"],
                    "memories_created": [],
                    "errors": [f"Rejection reason: {response.reason}"],
                }

            # Update the deferred task → completed, with outcome + updated context.
            now_iso = self._now().isoformat()
            update_payload = _task_to_persist_payload(existing_task)
            update_payload["status"] = TaskStatus.COMPLETED.value
            update_payload["context"] = context
            update_payload["outcome"] = outcome_data
            update_payload["updated_at"] = now_iso
            try:
                engine.task_upsert(json.dumps(update_payload))
            except Exception:
                logger.exception("Failed to update original task %s", task_id)
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

                # Update context with new correlation_id to avoid UNIQUE constraint violation
                guidance_context_dict["correlation_id"] = correlation_id

                # Inherit preferred_language from the original deferred task so
                # the WA-guidance follow-up task continues the same locale as
                # the user's original interaction. Without this, a Spanish
                # user's WA-resolved task would create an English-locale
                # guidance task, breaking the locale-coherent reasoning chain
                # the localization helper depends on.
                original_preferred_language: Optional[str] = None
                try:
                    from ciris_engine.logic.persistence.models.tasks import get_task_by_id

                    original_task = get_task_by_id(original_task_id, agent_occurrence_id)
                    if original_task is not None:
                        # Prefer the top-level field (Task is record of truth);
                        # fall back to context for older records.
                        original_preferred_language = getattr(original_task, "preferred_language", None) or (
                            getattr(original_task.context, "preferred_language", None)
                            if original_task.context is not None
                            else None
                        )
                except Exception as exc:
                    logger.debug(
                        f"WA guidance task: could not load original task {original_task_id} "
                        f"for preferred_language inheritance: {exc}"
                    )

                # Resolve via the centralized chain (explicit > user > channel > env)
                # so the guidance task always lands with a known locale, even
                # when the original task lookup fails.
                from ciris_engine.logic.utils.localization import resolve_language_for_new_task

                resolved_language = resolve_language_for_new_task(
                    explicit_lang=original_preferred_language,
                )

                # Build TaskContext from the guidance context dict
                ctx_user_id = context.get("user_id")
                ctx_user_id_str: Optional[str] = str(ctx_user_id) if ctx_user_id else None
                task_context = TaskContext(
                    channel_id=channel_id,
                    user_id=ctx_user_id_str,
                    correlation_id=correlation_id,
                    parent_task_id=original_task_id,
                    agent_occurrence_id=agent_occurrence_id,
                    preferred_language=resolved_language,
                )

                # Create new task description incorporating WA guidance
                new_description = f"[WA GUIDANCE] Original: {original_description}\n\nWA Response: {response.reason}"

                # Use factory to create new guidance task
                guidance_task = create_task(
                    description=new_description,
                    channel_id=channel_id,
                    agent_occurrence_id=agent_occurrence_id,
                    correlation_id=correlation_id,
                    time_service=self._time_service,
                    status=TaskStatus.PENDING,
                    priority=priority if priority is not None else 5,
                    user_id=ctx_user_id_str,
                    parent_task_id=original_task_id,
                    context=task_context,
                )

                # CIRISAgent#942: when this deferral was raised by the approval
                # gate, issue the guidance task a WISE_AUTHORITY envelope naming
                # the approved tool. This is issuance, not widening — TaskEnvelope
                # stays frozen and no existing envelope is touched; a new task
                # legitimately gets a newly issued envelope.
                self._attach_tool_approval_envelope(
                    guidance_context_dict=guidance_context_dict,
                    deferral_info=deferral_info,
                    guidance_task_id=guidance_task.task_id,
                    agent_occurrence_id=agent_occurrence_id,
                    wa_id=response.wa_id,
                )

                # Persist the new guidance task via the substrate.
                guidance_payload = {
                    "task_id": guidance_task.task_id,
                    "channel_id": guidance_task.channel_id,
                    "agent_occurrence_id": guidance_task.agent_occurrence_id,
                    "description": guidance_task.description,
                    "status": guidance_task.status.value,
                    "priority": guidance_task.priority,
                    "created_at": guidance_task.created_at,
                    "updated_at": guidance_task.updated_at,
                    "parent_task_id": guidance_task.parent_task_id,
                    "context": guidance_context_dict,
                }
                engine.task_upsert(json.dumps(guidance_payload))

                logger.info(f"Created new guidance task {guidance_task.task_id} for resolved deferral {deferral_id}")

            logger.info(
                f"Deferral {deferral_id} {'approved' if response.approved else 'rejected'} by {response.wa_id}, "
                f"original task {task_id} completed, new guidance task created"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to resolve deferral: {e}")
            return False

    # ========== Tool-Approval Envelope Issuance (CIRISAgent#942) ==========

    def _attach_tool_approval_envelope(
        self,
        *,
        guidance_context_dict: Dict[str, object],
        deferral_info: object,
        guidance_task_id: str,
        agent_occurrence_id: str,
        wa_id: str,
    ) -> None:
        """Mint the approval envelope for a ``[WA GUIDANCE]`` task and bind it.

        Completes the loop the approval gate opens. The gate
        (``ThoughtProcessor._enforce_tool_approval``) denies an approval-requiring
        tool and defers, carrying the tool name in the deferral context. A human
        approves through the WA panel that already ships. Here we issue the
        follow-up task a ``WISE_AUTHORITY`` envelope whose ``granted_tools`` names
        exactly that tool, so the re-run of the pipeline passes the gate.

        ``granted_tools`` is deliberately **narrow** — only the approved tool, not
        the deployment's enabled set. A union would silently approve every *other*
        ``requires_approval`` tool for this task, which is precisely the widening
        the design forbids. Ordinary tools are unaffected because the gate only
        consults the envelope for approval-requiring tools.

        ``capabilities`` is left empty on purpose: this envelope is an approval
        token for one named tool, not a resolved effect-class summary, and
        claiming effect classes it did not resolve would be a false declaration.

        Provenance is ``issuer_id=wa_id``. Note what that is and is not: it is the
        identifier of the resolving Wise Authority, and the cryptographic binding
        lives on ``DeferralResponse.signature`` (an Ed25519 signature produced
        server-side by ``AuthenticationService.sign_as_wa``, persisted by
        CIRISAgent#944). It is **not** the owner's post-quantum CEG federation
        identity: that identity is minted by the substrate's node self-claim and
        the Python side explicitly recognises and skips those rows
        (``persistence/stores/authentication_store.py``), so no owner key material
        is reachable in this process. Chaining approvals to the owner's PQC fedID
        requires that identity to be exposed by the substrate first; deliberately
        not faked here, because a second invented signer is exactly what the
        dry297 series removed.

        Best-effort and fully defensive: any failure leaves the guidance task with
        no approval envelope, so the gate denies again on the re-run. That is the
        fail-closed direction — a broken issuance can never turn into a grant.
        """
        from ciris_engine.logic.infrastructure.authorization.tool_approval import pending_tool_from_deferral_context

        if not isinstance(deferral_info, dict):
            return
        approved_tool = pending_tool_from_deferral_context(deferral_info.get("context"))
        if approved_tool is None:
            return

        try:
            from ciris_engine.logic.infrastructure.authorization.envelope_issuer import issue_authority_envelope
            from ciris_engine.schemas.runtime.task_envelope import EnvelopeIssuerKind

            envelope = issue_authority_envelope(
                task_id=guidance_task_id,
                issuer_kind=EnvelopeIssuerKind.WISE_AUTHORITY,
                issuer_id=wa_id,
                granted_tools=frozenset({approved_tool}),
                capabilities=frozenset(),
                agent_occurrence_id=agent_occurrence_id,
                time_service=self._time_service,
            )
        except Exception as exc:
            logger.error(
                "CIRISAgent#942: failed to issue tool-approval envelope for tool %r on guidance "
                "task %s (WA %s): %s. The guidance task proceeds WITHOUT the approval, so the "
                "approval gate will deny and defer again — never a bypass.",
                approved_tool,
                guidance_task_id,
                wa_id,
                exc,
            )
            return

        guidance_context_dict["envelope"] = envelope.model_dump(mode="json")
        logger.info(
            "CIRISAgent#942: WA %s approved tool %r; issued envelope %s to guidance task %s",
            wa_id,
            approved_tool,
            envelope.envelope_id,
            guidance_task_id,
        )

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
        # Get counts via the persist substrate (CIRISAgent#763).
        pending_deferrals_count = 0
        resolved_deferrals_count = 0

        try:
            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.persistence.models.tasks import _list_with_filter

            engine = get_persist_engine()
            if engine is not None:
                # Pending = currently DEFERRED across known occurrences.
                for occ in ("default", "__shared__"):
                    pending_deferrals_count += len(
                        _list_with_filter({"status": TaskStatus.DEFERRED.value, "agent_occurrence_id": occ})
                    )
                # Resolved = task whose context_json contains "resolution".
                # No SQL JSON predicate via persist; scan each occurrence's
                # tasks once and Python-filter. Bounded by total occurrence
                # task volume; acceptable for status-page cardinality.
                for occ in ("default", "__shared__"):
                    for task in _list_with_filter({"agent_occurrence_id": occ}):
                        raw = engine.task_get(task.task_id)
                        if raw is None:
                            continue
                        row = json.loads(raw) if isinstance(raw, str) else raw
                        ctx = row.get("context") if isinstance(row, dict) else None
                        ctx_str = json.dumps(ctx) if isinstance(ctx, dict) else (ctx or "")
                        if '"resolution":' in ctx_str:
                            resolved_deferrals_count += 1
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
        # Get deferral counts via the persist substrate (CIRISAgent#763).
        total_deferrals_count = 0
        resolved_deferrals_count = 0

        try:
            from ciris_engine.logic.persistence.models.graph import get_persist_engine
            from ciris_engine.logic.persistence.models.tasks import _list_with_filter

            engine = get_persist_engine()
            if engine is not None:
                for occ in ("default", "__shared__"):
                    for task in _list_with_filter({"agent_occurrence_id": occ}):
                        raw = engine.task_get(task.task_id)
                        if raw is None:
                            continue
                        row = json.loads(raw) if isinstance(raw, str) else raw
                        ctx = row.get("context") if isinstance(row, dict) else None
                        ctx_str = json.dumps(ctx) if isinstance(ctx, dict) else (ctx or "")
                        if '"deferral":' in ctx_str:
                            total_deferrals_count += 1
                        if '"resolution":' in ctx_str:
                            resolved_deferrals_count += 1
        except Exception as e:
            logger.error(f"Error getting deferral counts: {e}")

        return {
            # v1.4.3 specified metrics - exact names from telemetry taxonomy
            "wise_authority_deferrals_total": float(total_deferrals_count),
            "wise_authority_deferrals_resolved": float(resolved_deferrals_count),
            "wise_authority_guidance_requests": float(self._guidance_provided_count),
            "wise_authority_uptime_seconds": self._calculate_uptime(),
        }
