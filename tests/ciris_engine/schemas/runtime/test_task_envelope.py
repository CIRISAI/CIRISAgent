"""Schema tests for the task-scoped authorization envelope (CIRISAgent#938, Phase 1).

Covers the two properties the schema is responsible for:

1. blanket-allow is unrepresentable — no wildcard token, no "None means any",
   no free-form pattern anywhere on a grant axis;
2. absence of an envelope evaluates to denial, never to "unconstrained".

Plus attenuation (narrows, never widens) and the ``ToolInvocationSubject``
shapes that must be impossible to construct.
"""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    DeploymentScope,
    EnvelopeIssuer,
    EnvelopeIssuerKind,
    EnvelopeWideningError,
    EnvironmentTier,
    IssuedCredential,
    RequesterAuthorization,
    TargetAuthKind,
    TargetRoot,
    TaskEnvelope,
    ToolCallOrigin,
    ToolCapability,
    ToolInvocationSubject,
    envelope_permits_capability,
    envelope_permits_tool,
)

DEPLOYMENT = DeploymentScope(
    environment_tier=EnvironmentTier.PRODUCTION,
    agent_id="echo-speculative",
    template="echo",
    agent_occurrence_id="default",
)


def make_envelope(**overrides) -> TaskEnvelope:
    kwargs = dict(
        envelope_id="env_1",
        task_id="task_1",
        issued_at="2026-07-30T00:00:00+00:00",
        issuer=EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED),
        deployment=DEPLOYMENT,
        granted_tools=frozenset({"weather", "discord_ban_user", "self_help"}),
        capabilities=ALL_TOOL_CAPABILITIES,
    )
    kwargs.update(overrides)
    return TaskEnvelope(**kwargs)


# ---------------------------------------------------------------- round trip


def test_envelope_round_trips_through_json():
    """The envelope survives the persist path (model_dump(mode="json") -> validate)."""
    envelope = make_envelope(
        requester=RequesterAuthorization(user_id="u-42", role=UserRole.OBSERVER, channel_id="c-1"),
    )
    dumped = envelope.model_dump(mode="json")
    assert isinstance(dumped["granted_tools"], list)  # frozenset -> list on the wire
    restored = TaskEnvelope.model_validate(dumped)
    assert restored == envelope
    assert restored.granted_tools == envelope.granted_tools
    assert restored.capabilities == envelope.capabilities


def test_envelope_is_frozen():
    envelope = make_envelope()
    with pytest.raises(ValidationError):
        envelope.granted_tools = frozenset({"anything"})


def test_envelope_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        make_envelope(allow_all=True)


def test_agent_occurrence_id_comes_from_deployment():
    envelope = make_envelope()
    assert envelope.agent_occurrence_id == "default"


# ------------------------------------------------- blanket allow is unrepresentable


@pytest.mark.parametrize("bad", ["*", "**", "sql_*", "?", "a*b", ""])
def test_granted_tools_rejects_every_pattern_shape(bad):
    """There is no spelling of "all tools" that the grant axis accepts."""
    with pytest.raises(ValidationError):
        make_envelope(granted_tools=frozenset({bad}))


def test_capability_enum_has_no_wildcard_member():
    values = {c.value for c in ToolCapability}
    assert "*" not in values
    assert not any("*" in v for v in values)
    assert not any(v.lower() in {"all", "any"} for v in values)


def test_no_allow_all_style_field_exists():
    """A boolean escape hatch is the shape this failure usually takes."""
    forbidden = {"allow_all", "unrestricted", "bypass", "sandbox_mode", "wildcard", "allow"}
    assert forbidden.isdisjoint(set(TaskEnvelope.model_fields))


def test_complete_enumeration_is_the_only_way_to_grant_everything():
    """`ALL_TOOL_CAPABILITIES` is a literal enumeration, not a wildcard token."""
    envelope = make_envelope(capabilities=ALL_TOOL_CAPABILITIES)
    dumped = envelope.model_dump(mode="json")
    assert sorted(dumped["capabilities"]) == sorted(c.value for c in ToolCapability)
    # It is diffable: adding a member changes the serialized envelope.
    assert len(dumped["capabilities"]) == len(ToolCapability)


def test_target_root_rejects_host_patterns():
    with pytest.raises(ValidationError):
        TargetRoot(scheme="https", host="*.example.com")
    with pytest.raises(ValidationError):
        TargetRoot(scheme="https", host="*")
    with pytest.raises(ValidationError):
        TargetRoot(scheme="https", host="example.com", path_prefix="/a/*")


def test_include_subdomains_is_the_one_bounded_widening_affordance():
    root = TargetRoot(scheme="https", host="example.com", include_subdomains=True)
    # It is a boolean under a named parent host — it cannot name another host.
    assert root.host == "example.com"
    assert root.include_subdomains is True


def test_credential_ref_rejects_patterns():
    with pytest.raises(ValidationError):
        IssuedCredential(credential_ref="secret_*", target_host="example.com", auth_kind=TargetAuthKind.BEARER_TOKEN)


# ------------------------------------------------------- absence means denial


def test_absent_envelope_denies_every_tool():
    assert envelope_permits_tool(None, "weather") is False
    assert envelope_permits_tool(None, "anything_at_all") is False


def test_absent_envelope_denies_every_capability():
    for capability in ToolCapability:
        assert envelope_permits_capability(None, capability) is False


def test_empty_grant_permits_nothing():
    """An empty set is not "unrestricted" — it is the deny-all envelope."""
    envelope = make_envelope(granted_tools=frozenset(), capabilities=frozenset())
    assert envelope.permits_tool("weather") is False
    assert envelope_permits_tool(envelope, "weather") is False
    for capability in ToolCapability:
        assert envelope.declares_capability(capability) is False


def test_present_envelope_permits_only_what_it_names():
    envelope = make_envelope()
    assert envelope_permits_tool(envelope, "weather") is True
    assert envelope_permits_tool(envelope, "tmux") is False


# ------------------------------------------------------------- consequential tools


def test_consequential_tools_are_grantable_and_not_schema_denied():
    """Kick/ban must be in every echo envelope.

    The control on consequential tools is the conscience layer plus
    Wisdom-Based Deferral (``ToolDMAGuidance(requires_approval=True)``), which
    judges the specific content. The envelope must not preempt it — so nothing
    in the schema may refuse to carry these.
    """
    envelope = make_envelope(
        granted_tools=frozenset({"discord_ban_user", "discord_timeout_user", "reddit_remove_content"}),
        capabilities=frozenset({ToolCapability.MODERATE_CHANNEL}),
    )
    assert envelope.permits_tool("discord_ban_user") is True
    assert envelope.declares_capability(ToolCapability.MODERATE_CHANNEL) is True


def test_write_public_namespace_is_a_distinct_capability_class():
    assert ToolCapability.WRITE_PUBLIC_NAMESPACE in ToolCapability
    assert ToolCapability.WRITE_PUBLIC_NAMESPACE.value == "write:public-namespace"


# ------------------------------------------------------ credential scoping (Phase 3)


def test_credential_must_bind_to_a_declared_target_root():
    with pytest.raises(ValidationError, match="not a declared target root"):
        make_envelope(
            target_roots=(TargetRoot(scheme="https", host="a.example.com"),),
            credentials=(
                IssuedCredential(
                    credential_ref="tok_a", target_host="b.example.com", auth_kind=TargetAuthKind.BEARER_TOKEN
                ),
            ),
        )


def test_credential_lookup_is_closed_world():
    envelope = make_envelope(
        target_roots=(TargetRoot(scheme="https", host="a.example.com"),),
        credentials=(
            IssuedCredential(credential_ref="tok_a", target_host="a.example.com", auth_kind=TargetAuthKind.BEARER_TOKEN),
        ),
    )
    assert envelope.credential_for("a.example.com").credential_ref == "tok_a"
    assert envelope.credential_for("A.EXAMPLE.COM").credential_ref == "tok_a"
    assert envelope.credential_for("b.example.com") is None


# ------------------------------------------------------------------- issuer


def test_deployment_resolved_issuer_must_not_name_an_issuer_id():
    with pytest.raises(ValidationError):
        EnvelopeIssuer(kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED, issuer_id="wa-1")


@pytest.mark.parametrize("kind", [EnvelopeIssuerKind.WISE_AUTHORITY, EnvelopeIssuerKind.NODE_OWNER])
def test_authority_issuers_require_an_issuer_id(kind):
    with pytest.raises(ValidationError):
        EnvelopeIssuer(kind=kind)
    with pytest.raises(ValidationError):
        EnvelopeIssuer(kind=kind, issuer_id="   ")
    assert EnvelopeIssuer(kind=kind, issuer_id="wa-1").issuer_id == "wa-1"


# --------------------------------------------------------------- attenuation


def test_attenuation_narrows_tools():
    envelope = make_envelope()
    narrowed = envelope.attenuate(
        envelope_id="env_2",
        issued_at="2026-07-30T00:01:00+00:00",
        granted_tools=frozenset({"self_help"}),
    )
    assert narrowed.granted_tools == frozenset({"self_help"})
    assert narrowed.task_id == envelope.task_id
    assert narrowed.attenuated_from == "env_1"
    # The original is untouched.
    assert envelope.granted_tools == frozenset({"weather", "discord_ban_user", "self_help"})


def test_attenuation_narrows_capabilities():
    envelope = make_envelope()
    narrowed = envelope.attenuate(
        envelope_id="env_2",
        issued_at="t",
        capabilities=frozenset({ToolCapability.OBSERVE_LOCAL}),
    )
    assert narrowed.capabilities == frozenset({ToolCapability.OBSERVE_LOCAL})


def test_attenuation_cannot_widen_tools():
    envelope = make_envelope()
    with pytest.raises(EnvelopeWideningError, match="would add tools"):
        envelope.attenuate(
            envelope_id="env_2",
            issued_at="t",
            granted_tools=frozenset({"weather", "tmux"}),
        )


def test_attenuation_cannot_widen_capabilities():
    envelope = make_envelope(capabilities=frozenset({ToolCapability.OBSERVE_LOCAL}))
    with pytest.raises(EnvelopeWideningError, match="would add capabilities"):
        envelope.attenuate(
            envelope_id="env_2",
            issued_at="t",
            capabilities=frozenset({ToolCapability.OBSERVE_LOCAL, ToolCapability.EXECUTE_CODE}),
        )


def test_attenuation_cannot_add_target_roots_or_credentials():
    envelope = make_envelope()
    with pytest.raises(EnvelopeWideningError, match="would add target roots"):
        envelope.attenuate(
            envelope_id="env_2",
            issued_at="t",
            target_roots=(TargetRoot(scheme="https", host="evil.example.com"),),
        )
    with pytest.raises(EnvelopeWideningError, match="would add credentials"):
        envelope.attenuate(
            envelope_id="env_2",
            issued_at="t",
            credentials=(
                IssuedCredential(
                    credential_ref="tok", target_host="evil.example.com", auth_kind=TargetAuthKind.BEARER_TOKEN
                ),
            ),
        )


def test_attenuation_omitted_axis_does_not_widen():
    envelope = make_envelope()
    narrowed = envelope.attenuate(envelope_id="env_2", issued_at="t")
    assert narrowed.granted_tools == envelope.granted_tools
    assert narrowed.capabilities == envelope.capabilities


def test_no_widening_entry_point_exists_on_the_model():
    """There is no counterpart to attenuate()."""
    surface = {name for name in dir(TaskEnvelope) if not name.startswith("_")}
    assert "attenuate" in surface
    for forbidden in ("widen", "amplify", "grant", "extend", "escalate", "add_tool", "add_capability"):
        assert forbidden not in surface


def test_attenuation_repeats_monotonically():
    envelope = make_envelope()
    once = envelope.attenuate(envelope_id="e2", issued_at="t", granted_tools=frozenset({"weather", "self_help"}))
    twice = once.attenuate(envelope_id="e3", issued_at="t", granted_tools=frozenset({"self_help"}))
    assert twice.granted_tools == frozenset({"self_help"})
    with pytest.raises(EnvelopeWideningError):
        twice.attenuate(envelope_id="e4", issued_at="t", granted_tools=frozenset({"weather"}))


# ------------------------------------------------------- ToolInvocationSubject


def test_task_bound_subject_requires_task_and_thought_identity():
    """The exact blindness #938 names must be unrepresentable."""
    with pytest.raises(ValidationError, match="must carry both task_id and thought_id"):
        ToolInvocationSubject(origin=ToolCallOrigin.REASONING, handler_name="ToolHandler")
    with pytest.raises(ValidationError):
        ToolInvocationSubject(origin=ToolCallOrigin.REASONING, handler_name="ToolHandler", task_id="t1")
    with pytest.raises(ValidationError):
        ToolInvocationSubject(origin=ToolCallOrigin.CONTEXT_ENRICHMENT, handler_name="ctx")


def test_component_subject_cannot_carry_a_task_envelope():
    """A system caller cannot launder itself as a task, or vice versa."""
    envelope = make_envelope()
    with pytest.raises(ValidationError, match="must not carry a task envelope"):
        ToolInvocationSubject(
            origin=ToolCallOrigin.GOVERNANCE_SERVICE,
            handler_name="default",
            component="DSAR",
            envelope=envelope,
        )
    with pytest.raises(ValidationError, match="task/thought id must be absent"):
        ToolInvocationSubject(
            origin=ToolCallOrigin.OPERATOR_API, handler_name="default", component="api", task_id="t1"
        )


def test_component_subject_must_name_the_component():
    with pytest.raises(ValidationError, match="must name the initiating component"):
        ToolInvocationSubject(origin=ToolCallOrigin.OPERATOR_API, handler_name="default")


def test_envelope_task_id_must_match_the_subject():
    envelope = make_envelope(task_id="task_1")
    with pytest.raises(ValidationError, match="does not match"):
        ToolInvocationSubject.for_task(
            task_id="task_OTHER", thought_id="th_1", handler_name="ToolHandler", envelope=envelope
        )


def test_subject_constructors_route_correctly():
    with pytest.raises(ValueError, match="not a task-bound origin"):
        ToolInvocationSubject.for_task(
            task_id="t", thought_id="th", handler_name="h", origin=ToolCallOrigin.OPERATOR_API
        )
    with pytest.raises(ValueError, match="use for_task"):
        ToolInvocationSubject.for_component(origin=ToolCallOrigin.REASONING, component="x")


def test_subject_describe_is_log_safe():
    envelope = make_envelope()
    reasoning = ToolInvocationSubject.for_task(
        task_id="task_1", thought_id="th_1", handler_name="ToolHandler", envelope=envelope
    )
    assert "task=task_1" in reasoning.describe()
    assert "envelope=env_1" in reasoning.describe()

    unauthorized = ToolInvocationSubject.for_task(task_id="task_1", thought_id="th_1", handler_name="ToolHandler")
    assert "no-envelope" in unauthorized.describe()

    component = ToolInvocationSubject.for_component(origin=ToolCallOrigin.GOVERNANCE_SERVICE, component="DSAR")
    assert "component=DSAR" in component.describe()


def test_context_enrichment_is_task_bound_but_distinct_from_reasoning():
    """Auto-run enrichment providers are not model-selected; the origin says so."""
    subject = ToolInvocationSubject.for_task(
        task_id="t", thought_id="th", handler_name="context", origin=ToolCallOrigin.CONTEXT_ENRICHMENT
    )
    assert subject.is_task_bound is True
    assert subject.origin is not ToolCallOrigin.REASONING
