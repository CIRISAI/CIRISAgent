"""Task-scoped authorization envelope (CIRISAgent#938, Phase 1).

The defect this addresses: privilege in the agent is **identity-scoped, not
task-scoped**. One runtime holds one identity with one privilege set for the
lifetime of the process, and a task borrows the whole identity for its
duration. ``TaskEnvelope`` is the missing subject — the authorization scope of
*one task*, bound to a task id and living exactly as long as that task.

**Issuance resolves from the deployment, not from the task's purpose.**
We cannot know a task's type at creation. For ally deployments every task is a
generic assistant task; an inbound message may be someone saying hello or
someone sharing CSAM, and the task that needs ``discord_ban_user`` is exactly
the one that could not have declared that need in advance. What *is* knowable
at issuance is the environment tier, the agent's role/template, the set of
tools this deployment actually enabled, and the requester's authorization. The
envelope resolves from those four, and is therefore **identical for every task
in a deployment by default**. It stays bound per task for attribution and for
future narrowing, not because the grant differs.

**This module is schema only. It contains no enforcement.** Nothing here is
called on the tool-execution path; the predicates below exist so that Phase 2
(#905 Ask 1 — gate ``ToolBus.execute_tool``) has something to key on. See
``FSD/TASK_ENVELOPE.md``.

Two schema-level properties:

1. **Blanket-allow is unrepresentable.** There is no wildcard member of
   :class:`ToolCapability`, no ``allow_all`` flag, no free-form pattern field,
   and no "``None`` means unrestricted" state. "Every enabled tool is granted"
   is expressed as the *resolved, explicitly enumerated* set of tool names the
   deployment actually enabled — an enumerated set that happens to be complete
   is auditable and diffable; ``allow: ["*"]`` is not. The single bounded
   exception is :attr:`TargetRoot.include_subdomains`, documented there.
2. **Absence of an envelope is denial.** The module-level predicates
   (:func:`envelope_permits_capability`, :func:`envelope_permits_tool`) take
   ``Optional[TaskEnvelope]`` and return ``False`` for ``None``. There is no
   code path in which "no envelope" evaluates to "unconstrained".
"""

from __future__ import annotations

import re
from enum import Enum
from typing import FrozenSet, Iterable, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ciris_engine.schemas.api.auth import UserRole


class ToolCapability(str, Enum):
    """Classes of effect an envelope declares.

    Deliberately a closed enumeration with **no wildcard member**: an envelope
    can name capability classes, it cannot say "all of them" in one token.

    This axis is a coarse *effect-class summary* of the envelope, resolved
    alongside :attr:`TaskEnvelope.granted_tools`. It is **not** a second tool
    gate — Phase 2 keys on the enumerated tool set, because there is no
    tool -> class registry today and inferring one would deny legitimate,
    deployment-enabled tools. Its named consumer is Phase 4 (#905 Ask 3),
    whose central rule is "referral may expand the read surface; it may never
    expand the credential surface or the write surface" — a rule that needs
    read/write/credential to be distinguishable. It also participates in
    :meth:`TaskEnvelope.attenuate`'s subset check today.

    Each member is grounded in tools that exist in this codebase; the
    parenthetical names are illustrative, not an authoritative mapping.
    """

    OBSERVE_LOCAL = "observe:local"
    """Read agent-local state (``self_help``, ``get_ticket``, ``recall_secret``,
    ``session_logs``, ``model_usage``)."""

    OBSERVE_CHANNEL = "observe:channel"
    """Read the conversation surface the task originated on (``reddit_observe``,
    Discord history, ``imsg``/``bluebubbles`` reads)."""

    OBSERVE_NETWORK = "observe:network"
    """Outbound *read* (``weather``, ``local_places``, ``blogwatcher``,
    ``goplaces``, web search). Includes the ``context_enrichment=True``
    providers that auto-run during context gathering."""

    COMMUNICATE_CHANNEL = "communicate:channel"
    """Emit into the task's own channel (``voice_call``, adapter send paths)."""

    MODERATE_CHANNEL = "moderate:channel"
    """Act on the moderated surface: timeout, kick, ban, delete
    (``discord_timeout_user``, ``discord_ban_user``, ``reddit_remove_content``).
    Consequential by construction and present in every echo-template envelope —
    the control on these is the conscience layer and Wisdom-Based Deferral
    (``ToolDMAGuidance(requires_approval=True)``), which judges the specific
    content. The envelope does not, and must not, preempt that judgement."""

    WRITE_LOCAL = "write:local"
    """Write agent-local state (``update_ticket``, ``obsidian``, ``bear_notes``,
    ``apple_notes``, ``session_logs`` writes)."""

    WRITE_TARGET = "write:target"
    """Authenticated write to an external target (``notion``, ``trello``,
    ``sql_anonymize_user``, ``sql_delete_user``)."""

    WRITE_PUBLIC_NAMESPACE = "write:public-namespace"
    """Publish into a **shared external namespace** — a package registry, a
    public repository, a public forum post (``reddit_submit_post``, package
    publish). Kept as its own class because it is the effect class #905 argues
    the registry-write case under, and because Phase 4 must be able to say
    "referral never expands *this*"."""

    CONTROL_DEVICE = "control:device"
    """Actuate a physical device (``ha_integration``, ``openhue``, ``sonoscli``,
    ``spotify_player``, ``camsnap``)."""

    SPEND_FUNDS = "spend:funds"
    """Move money or incur a purchase obligation (wallet adapter, ``ordercli``)."""

    MANAGE_SELF = "manage:self"
    """Change the agent's own runtime: adapter lifecycle, config,
    ``update_secrets_filter``, ``skill_creator``."""

    EXECUTE_CODE = "execute:code"
    """Run caller-supplied code or an opaque command (``tmux``, ``mcporter``,
    ``coding_agent``, arbitrary ``sql_query``). The broad-surface class #905
    names as the thing that makes credential-scope checks bypassable."""


ALL_TOOL_CAPABILITIES: FrozenSet[ToolCapability] = frozenset(ToolCapability)
"""Every declared effect class, enumerated.

The default resolution for a CIRISAgent deployment that declares no narrower
set. This is a *complete enumeration*, not a wildcard: it is a literal list of
members that changes visibly in a diff when a member is added, and a narrower
deployment or vertical (CIRISMedical, CIRISFinancial) resolves a strict subset.
"""


class EnvironmentTier(str, Enum):
    """Deployment environment. One of the four things knowable at issuance."""

    PRODUCTION = "production"
    QA = "qa"
    DEVELOPMENT = "development"
    LOCAL = "local"


class EnvelopeIssuerKind(str, Enum):
    """Who minted an envelope. Never model-authored."""

    DEPLOYMENT_RESOLVED = "deployment_resolved"
    """Resolved deterministically from (environment tier, agent role/template,
    enabled tools, requester authorization) at task creation."""

    WISE_AUTHORITY = "wise_authority"
    """Issued explicitly by a WA against a WA identity."""

    NODE_OWNER = "node_owner"
    """Issued explicitly by the node owner (boot provisioning, operator action)."""

    SYSTEM_COMPONENT = "system_component"
    """Issued to a named, code-declared component for one unit of non-model work
    — a DSAR erasure request, an operator connector setup. Bound to that unit's
    id rather than to a reasoning task, and granting exactly the tools the
    component's code actually calls. These paths would otherwise be denied on
    day one by a fail-closed gate, which would take GDPR erasure with them."""


class TargetAuthKind(str, Enum):
    """How a credential is presented to its target."""

    BEARER_TOKEN = "bearer_token"
    BASIC_AUTH = "basic_auth"
    API_KEY_HEADER = "api_key_header"
    OAUTH_ACCESS_TOKEN = "oauth_access_token"
    MUTUAL_TLS = "mutual_tls"
    CONNECTION_STRING = "connection_string"


class ToolCallOrigin(str, Enum):
    """Where a tool invocation entered the bus from.

    Set by CIRIS code at the call site, never by the model. It exists so
    Phase 2 can tell a model-selected tool call apart from an
    operator-initiated or governance-service-initiated one instead of silently
    treating them alike.
    """

    REASONING = "reasoning"
    """The H3ERE reasoning loop selected this action (``ToolHandler``)."""

    CONTEXT_ENRICHMENT = "context_enrichment"
    """A ``context_enrichment=True`` provider auto-running during context
    gathering. Not model-selected — the pipeline runs it before the model has
    chosen anything."""

    GOVERNANCE_SERVICE = "governance_service"
    """A governance service acting on a statutory obligation (DSAR)."""

    OPERATOR_API = "operator_api"
    """An authenticated operator drove this through the API surface."""

    ADAPTER_LIFECYCLE = "adapter_lifecycle"
    """Adapter bootstrap/teardown (connector registration, health probes)."""


_TASK_BOUND_ORIGINS: FrozenSet[ToolCallOrigin] = frozenset(
    {ToolCallOrigin.REASONING, ToolCallOrigin.CONTEXT_ENRICHMENT}
)
"""Origins that run inside a task and therefore carry task identity."""

_TOOL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]*$")
_HOST_RE = re.compile(r"^[a-z0-9]([a-z0-9\-.]*[a-z0-9])?$")


class DeploymentScope(BaseModel):
    """What was knowable about the deployment when the envelope was issued.

    These four coordinates — plus the requester — are the *entire* resolution
    input. Task purpose is deliberately absent.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    environment_tier: EnvironmentTier = Field(..., description="production / qa / development / local")
    agent_id: str = Field(..., description="Agent identifier this deployment runs")
    template: str = Field(..., description="Agent role/template (echo, scout, datum, ...)")
    agent_occurrence_id: str = Field("default", description="Runtime occurrence that owns the bound task")


class RequesterAuthorization(BaseModel):
    """Authorization of the principal whose request created the task.

    Reuses the existing :class:`~ciris_engine.schemas.api.auth.UserRole` RBAC
    vocabulary rather than minting a parallel role enum.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: Optional[str] = Field(None, description="Originating principal, when there is one")
    role: UserRole = Field(UserRole.OBSERVER, description="Requester's role; OBSERVER is the floor")
    channel_id: Optional[str] = Field(None, description="Channel the request arrived on")
    source_ref: Optional[str] = Field(None, description="Originating message/correlation id")
    is_wise_authority: bool = Field(False, description="Requester is a recognised WA on this deployment")


class TargetRoot(BaseModel):
    """A declared root of the task's reachable surface.

    A root is the *origin* of reachability, not a pattern: scheme + literal
    host + literal path prefix. There is no host pattern field, so
    ``*.example.com`` and ``*`` cannot be written. The one bounded widening
    affordance is :attr:`include_subdomains`, a boolean under an already-named
    host — it can only expand within one parent domain and cannot reach an
    unrelated host.

    Phase 1 does not populate target roots for CIRISAgent (nothing declares
    them yet). They are consumed *today* by the credential-binding invariant on
    :class:`TaskEnvelope`, and are Phase 4's (#905 Ask 3) primary input.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scheme: str = Field(..., description="URI scheme, e.g. https")
    host: str = Field(..., description="Literal lowercase host. No patterns.")
    port: Optional[int] = Field(None, ge=1, le=65535, description="Explicit port, if pinned")
    path_prefix: str = Field("/", description="Literal path prefix this root covers")
    include_subdomains: bool = Field(
        False,
        description=(
            "Extend this root to subdomains of `host`. The only wildcard-like "
            "affordance in the schema, deliberately bounded to one named parent "
            "domain (see class docstring)."
        ),
    )

    @field_validator("scheme")
    @classmethod
    def _validate_scheme(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in {"https", "http", "postgresql", "mysql", "sqlite", "ssh", "file"}:
            raise ValueError(f"unsupported target-root scheme: {v!r}")
        return v

    @field_validator("host")
    @classmethod
    def _validate_host(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("target-root host must not be empty")
        if "*" in v or "?" in v:
            raise ValueError(f"target-root host must be a literal host, not a pattern: {v!r}")
        if not _HOST_RE.match(v):
            raise ValueError(f"invalid target-root host: {v!r}")
        return v

    @field_validator("path_prefix")
    @classmethod
    def _validate_path_prefix(cls, v: str) -> str:
        if not v.startswith("/"):
            raise ValueError("path_prefix must start with '/'")
        if "*" in v or "?" in v:
            raise ValueError(f"path_prefix must be a literal prefix, not a pattern: {v!r}")
        return v


class IssuedCredential(BaseModel):
    """A credential issued *to this envelope*, for one declared target.

    Carries a **reference** into the secrets store, never a secret value. The
    binding to ``target_host`` is what makes #905 Ask 2 ("deny when the agent
    authenticates against a target for which the envelope holds no issued
    credential") decidable without target enumeration: the closed world is the
    set of credentials actually issued here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    credential_ref: str = Field(..., description="Opaque handle into the secrets store. NEVER a secret value.")
    target_host: str = Field(..., description="Literal host this credential may be presented to")
    auth_kind: TargetAuthKind = Field(..., description="How the credential is presented")

    @field_validator("credential_ref")
    @classmethod
    def _validate_ref(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("credential_ref must not be empty")
        if "*" in v:
            raise ValueError("credential_ref must be a literal handle, not a pattern")
        return v

    @field_validator("target_host")
    @classmethod
    def _validate_target_host(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or "*" in v or "?" in v:
            raise ValueError(f"credential target_host must be a literal host: {v!r}")
        return v


class EnvelopeIssuer(BaseModel):
    """Provenance of an envelope. Set by the issuance path, never by the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EnvelopeIssuerKind = Field(..., description="Which issuance path minted this")
    issuer_id: Optional[str] = Field(
        None,
        description=(
            "WA id / owner id for explicitly issued envelopes. Required for "
            "WISE_AUTHORITY and NODE_OWNER; must be absent for DEPLOYMENT_RESOLVED."
        ),
    )

    @model_validator(mode="after")
    def _validate_issuer(self) -> "EnvelopeIssuer":
        if self.kind is EnvelopeIssuerKind.DEPLOYMENT_RESOLVED:
            if self.issuer_id is not None:
                raise ValueError("DEPLOYMENT_RESOLVED envelopes must not name an issuer_id")
        elif not (self.issuer_id or "").strip():
            raise ValueError(f"{self.kind.value} envelopes require a non-empty issuer_id")
        return self


_NON_TASK_ISSUERS: FrozenSet[EnvelopeIssuerKind] = frozenset({EnvelopeIssuerKind.SYSTEM_COMPONENT})
"""Issuer kinds whose envelopes bind to a non-reasoning unit of work.

Kept as a set so the anti-laundering check in :class:`ToolInvocationSubject`
stays one membership test: a component subject may only carry an envelope
issued by one of these, and a task subject may never carry one of these.
"""


class EnvelopeWideningError(ValueError):
    """Raised when an attenuation request would grant more than it holds."""


class TaskEnvelope(BaseModel):
    """The authorization scope of exactly one task.

    Immutable (``frozen=True``). Narrowing produces a new envelope via
    :meth:`attenuate`; there is no widening method and no mutable field, so an
    envelope cannot grow after issuance.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, defer_build=True)

    envelope_id: str = Field(..., description="Unique envelope identifier")
    task_id: str = Field(
        ...,
        description=(
            "The unit of work this envelope is bound to, and whose lifetime it shares. "
            "A reasoning task id for DEPLOYMENT_RESOLVED/WA/owner envelopes; the "
            "component's own work-unit id (a DSAR request id, an operator action id) "
            "for SYSTEM_COMPONENT envelopes."
        ),
    )
    issued_at: str = Field(..., description="ISO8601 issuance timestamp")
    issuer: EnvelopeIssuer = Field(..., description="Who minted this envelope")
    deployment: DeploymentScope = Field(..., description="Deployment coordinates the grant resolved from")
    requester: RequesterAuthorization = Field(
        default_factory=RequesterAuthorization, description="Authorization of the principal that caused the task"
    )
    attenuated_from: Optional[str] = Field(None, description="envelope_id this was narrowed from, if any")

    granted_tools: FrozenSet[str] = Field(
        default_factory=frozenset,
        description=(
            "The resolved, explicitly enumerated set of tool names this envelope grants. "
            "For CIRISAgent this is every tool the deployment enabled. Pattern entries are "
            "rejected — 'everything' is spelled out, never abbreviated to a wildcard."
        ),
    )
    capabilities: FrozenSet[ToolCapability] = Field(
        default_factory=frozenset,
        description="Declared effect classes. Closed enum, no wildcard. Summary axis, not a tool gate.",
    )
    target_roots: Tuple[TargetRoot, ...] = Field(
        default_factory=tuple, description="Declared roots of the task's reachable surface (Phase 4 input)"
    )
    credentials: Tuple[IssuedCredential, ...] = Field(
        default_factory=tuple,
        description="Credentials issued to this envelope, each bound to a declared root (Phase 3 input)",
    )

    @property
    def agent_occurrence_id(self) -> str:
        """Occurrence that owns the bound task."""
        return self.deployment.agent_occurrence_id

    # ---------------------------------------------------------------- validators

    @field_validator("envelope_id", "task_id", "issued_at")
    @classmethod
    def _validate_required_str(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must be a non-empty string")
        return v

    @field_validator("granted_tools")
    @classmethod
    def _validate_granted_tools(cls, v: FrozenSet[str]) -> FrozenSet[str]:
        for name in v:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("granted_tools entries must be non-empty tool names")
            if not _TOOL_NAME_RE.match(name):
                raise ValueError(
                    f"granted_tools entry {name!r} is not a literal tool name. "
                    "Wildcards and patterns are not representable in a TaskEnvelope; "
                    "enumerate the resolved set instead."
                )
        return v

    @model_validator(mode="after")
    def _validate_envelope(self) -> "TaskEnvelope":
        # Every issued credential must be bound to a declared target root.
        # This is what keeps credentials envelope-scoped rather than
        # identity-held (#905 Ask 2's provisioning-side correction), and it is
        # enforced at issuance today, not deferred to a later phase.
        declared_hosts = {root.host for root in self.target_roots}
        for cred in self.credentials:
            if cred.target_host not in declared_hosts:
                raise ValueError(
                    f"credential {cred.credential_ref!r} targets {cred.target_host!r}, "
                    "which is not a declared target root of this envelope"
                )
        return self

    # ---------------------------------------------------------------- predicates
    #
    # Read-only. NOT wired into any execution path in Phase 1 — Phase 2 (#905
    # Ask 1) is what calls these from the bus gate.

    def permits_tool(self, tool_name: str) -> bool:
        """True iff this envelope's resolved grant names ``tool_name``.

        Deliberately *not* "returns True when the set is empty" — an empty
        grant permits nothing. There is no "unrestricted" state.
        """
        return tool_name in self.granted_tools

    def declares_capability(self, capability: ToolCapability) -> bool:
        """True iff this envelope declares the effect class ``capability``."""
        return capability in self.capabilities

    def credential_for(self, target_host: str) -> Optional[IssuedCredential]:
        """The credential issued to this envelope for ``target_host``, if any."""
        host = target_host.strip().lower()
        for cred in self.credentials:
            if cred.target_host == host:
                return cred
        return None

    # ---------------------------------------------------------------- attenuation

    def attenuate(
        self,
        *,
        envelope_id: str,
        issued_at: str,
        granted_tools: Optional[Iterable[str]] = None,
        capabilities: Optional[Iterable[ToolCapability]] = None,
        target_roots: Optional[Tuple[TargetRoot, ...]] = None,
        credentials: Optional[Tuple[IssuedCredential, ...]] = None,
    ) -> "TaskEnvelope":
        """Return a strictly narrower envelope for the same task.

        Every argument must be a subset of what this envelope already holds;
        anything else raises :class:`EnvelopeWideningError`. Omitting an
        argument keeps the current value (it never widens). There is no
        corresponding widening operation anywhere in this module.

        CIRISAgent ships **no narrowing policy** — nothing calls this in the
        product path. It exists because the typed-task verticals
        (CIRISMedical, CIRISFinancial) know task purpose at creation and can
        narrow meaningfully. See ``FSD/TASK_ENVELOPE.md``.
        """
        new_tools = self.granted_tools if granted_tools is None else frozenset(granted_tools)
        new_caps = self.capabilities if capabilities is None else frozenset(capabilities)
        new_roots = self.target_roots if target_roots is None else tuple(target_roots)
        new_creds = self.credentials if credentials is None else tuple(credentials)

        if not new_tools <= self.granted_tools:
            raise EnvelopeWideningError(f"attenuate would add tools {sorted(new_tools - self.granted_tools)}")
        if not new_caps <= self.capabilities:
            raise EnvelopeWideningError(
                f"attenuate would add capabilities {sorted(c.value for c in new_caps - self.capabilities)}"
            )
        extra_roots = set(new_roots) - set(self.target_roots)
        if extra_roots:
            raise EnvelopeWideningError(f"attenuate would add target roots {sorted(r.host for r in extra_roots)}")
        extra_creds = set(new_creds) - set(self.credentials)
        if extra_creds:
            raise EnvelopeWideningError(
                f"attenuate would add credentials {sorted(c.credential_ref for c in extra_creds)}"
            )

        return TaskEnvelope(
            envelope_id=envelope_id,
            task_id=self.task_id,
            issued_at=issued_at,
            issuer=self.issuer,
            deployment=self.deployment,
            requester=self.requester,
            attenuated_from=self.envelope_id,
            granted_tools=new_tools,
            capabilities=new_caps,
            target_roots=new_roots,
            credentials=new_creds,
        )


def envelope_permits_tool(envelope: Optional[TaskEnvelope], tool_name: str) -> bool:
    """Fail-closed by-name predicate. A ``None`` envelope is a **denial**."""
    if envelope is None:
        return False
    return envelope.permits_tool(tool_name)


def envelope_permits_capability(envelope: Optional[TaskEnvelope], capability: ToolCapability) -> bool:
    """Fail-closed capability predicate. A ``None`` envelope is a **denial**."""
    if envelope is None:
        return False
    return envelope.declares_capability(capability)


class ToolInvocationSubject(BaseModel):
    """The subject a tool-call authorization decision is made *about*.

    ``ToolBus.execute_tool`` takes one of these so that the enforcement point
    can see who is asking. Today the bus only records it; Phase 2 keys the gate
    on it. Every field is set by CIRIS code at the call site — none of it is
    model-authored.

    The validators make three shapes unrepresentable:

    * a task-bound subject without task **and** thought identity — the exact
      blindness #938 is about;
    * a task-bound subject carrying a ``SYSTEM_COMPONENT`` envelope, i.e. the
      reasoning path borrowing a governance component's grant;
    * a component subject carrying a *task's* envelope, i.e. the reasoning path
      laundering itself as a system caller.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, defer_build=True)

    origin: ToolCallOrigin = Field(..., description="Where this invocation entered the bus from")
    handler_name: str = Field(..., description="Calling handler/component name, for telemetry and routing")
    agent_occurrence_id: str = Field("default", description="Occurrence making the call")
    task_id: Optional[str] = Field(None, description="Task identity (task-bound origins only)")
    thought_id: Optional[str] = Field(None, description="Thought identity (task-bound origins only)")
    envelope: Optional[TaskEnvelope] = Field(
        None,
        description=(
            "The resolved envelope for `task_id`, if one was issued. None means "
            "DENY under Phase 2 — it never means 'unconstrained'."
        ),
    )
    component: Optional[str] = Field(
        None, description="For non-task-bound origins: the component that initiated the call"
    )

    @property
    def is_task_bound(self) -> bool:
        """True for origins that run inside a task (reasoning, context enrichment)."""
        return self.origin in _TASK_BOUND_ORIGINS

    @model_validator(mode="after")
    def _validate_subject(self) -> "ToolInvocationSubject":
        if self.origin in _TASK_BOUND_ORIGINS:
            if not self.task_id or not self.thought_id:
                raise ValueError(f"a {self.origin.value} tool invocation must carry both task_id and thought_id")
            if self.component is not None:
                raise ValueError(f"a {self.origin.value} tool invocation must not name a component")
            if self.envelope is not None:
                if self.envelope.issuer.kind in _NON_TASK_ISSUERS:
                    raise ValueError(
                        f"a {self.origin.value} tool invocation must not carry a "
                        f"{self.envelope.issuer.kind.value} envelope — that grant belongs to a component, not a task"
                    )
                if self.envelope.task_id != self.task_id:
                    raise ValueError("envelope.task_id does not match the subject's task_id")
        else:
            if self.task_id or self.thought_id:
                raise ValueError(f"{self.origin.value} invocations are not task-bound; task/thought id must be absent")
            if not (self.component or "").strip():
                raise ValueError(f"{self.origin.value} invocations must name the initiating component")
            if self.envelope is not None and self.envelope.issuer.kind not in _NON_TASK_ISSUERS:
                raise ValueError(
                    f"{self.origin.value} invocations must not carry a "
                    f"{self.envelope.issuer.kind.value} envelope — a component cannot borrow a task's grant"
                )
        return self

    @classmethod
    def for_task(
        cls,
        *,
        task_id: str,
        thought_id: str,
        handler_name: str,
        origin: ToolCallOrigin = ToolCallOrigin.REASONING,
        agent_occurrence_id: str = "default",
        envelope: Optional[TaskEnvelope] = None,
    ) -> "ToolInvocationSubject":
        """Subject for a tool call made on behalf of a task.

        ``origin`` distinguishes a model-selected action (``REASONING``) from a
        ``context_enrichment=True`` provider that the pipeline auto-ran
        (``CONTEXT_ENRICHMENT``). Both are task-bound; only the first is
        model-selected.
        """
        if origin not in _TASK_BOUND_ORIGINS:
            raise ValueError(f"{origin.value} is not a task-bound origin; use for_component()")
        return cls(
            origin=origin,
            handler_name=handler_name,
            agent_occurrence_id=agent_occurrence_id,
            task_id=task_id,
            thought_id=thought_id,
            envelope=envelope,
        )

    @classmethod
    def for_component(
        cls,
        *,
        origin: ToolCallOrigin,
        component: str,
        handler_name: str = "default",
        agent_occurrence_id: str = "default",
        envelope: Optional[TaskEnvelope] = None,
    ) -> "ToolInvocationSubject":
        """Subject for a non-task, non-model-authored caller.

        ``envelope`` must be a ``SYSTEM_COMPONENT`` grant when present — the
        narrow, code-declared tool list that component actually calls. Passing
        one is strongly preferred over passing ``None``: absence is a denial to
        Phase 2, and for the DSAR erasure path that denial is a GDPR failure.
        """
        if origin in _TASK_BOUND_ORIGINS:
            raise ValueError("use for_task() for task-bound invocations")
        return cls(
            origin=origin,
            handler_name=handler_name,
            agent_occurrence_id=agent_occurrence_id,
            component=component,
            envelope=envelope,
        )

    def describe(self) -> str:
        """Short, log-safe description of the subject."""
        env = self.envelope.envelope_id if self.envelope else "no-envelope"
        if self.is_task_bound:
            return f"{self.origin.value} task={self.task_id} thought={self.thought_id} envelope={env}"
        return f"{self.origin.value} component={self.component} envelope={env}"


__all__ = [
    "ALL_TOOL_CAPABILITIES",
    "DeploymentScope",
    "EnvelopeIssuer",
    "EnvelopeIssuerKind",
    "EnvelopeWideningError",
    "EnvironmentTier",
    "IssuedCredential",
    "RequesterAuthorization",
    "TargetAuthKind",
    "TargetRoot",
    "TaskEnvelope",
    "ToolCallOrigin",
    "ToolCapability",
    "ToolInvocationSubject",
    "envelope_permits_capability",
    "envelope_permits_tool",
]
