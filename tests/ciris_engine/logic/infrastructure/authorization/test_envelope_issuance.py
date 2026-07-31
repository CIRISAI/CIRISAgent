"""Issuance tests for the task envelope (CIRISAgent#938, Phase 1).

The issuance model under test: an envelope resolves from
``(environment tier, agent role/template, enabled tools, requester
authorization)`` — **not** from the task's purpose. By default it is identical
for every task in a deployment; it is bound per task for attribution and for
future narrowing, not because the grant differs.
"""

import pathlib
from typing import List

import pytest

from ciris_engine.logic.infrastructure.authorization import deployment as deployment_mod
from ciris_engine.logic.infrastructure.authorization.enabled_tools import (
    cached_enabled_tools,
    prime_enabled_tools,
    register_tool_name_source,
    reset_enabled_tools_cache,
)
from ciris_engine.logic.infrastructure.authorization.envelope_issuer import (
    attach_envelope_to_task,
    attenuate_envelope,
    issue_authority_envelope,
    issue_deployment_envelope,
    issue_deployment_envelope_from_cache,
    issue_task_envelope_best_effort,
)
from ciris_engine.logic.infrastructure.authorization.envelope_reader import resolve_task_envelope
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext
from ciris_engine.schemas.runtime.task_envelope import (
    ALL_TOOL_CAPABILITIES,
    EnvelopeIssuerKind,
    EnvelopeWideningError,
    EnvironmentTier,
    IssuedCredential,
    RequesterAuthorization,
    TargetAuthKind,
    TargetRoot,
    TaskEnvelope,
    ToolCapability,
)

DEPLOYMENT_TOOLS = [
    "self_help",
    "weather",  # context_enrichment provider — auto-runs, cannot be pre-declared
    "discord_ban_user",  # consequential — must be in every echo envelope
    "ha_integration",
    "sql_query",
]


class StubToolInfo:
    def __init__(self, name: str) -> None:
        self.name = name


class StubToolSource:
    """Minimal ``ToolNameSource``."""

    def __init__(self, names: List[str]) -> None:
        self.names = names
        self.calls = 0

    async def get_all_tool_info(self, handler_name: str = "default") -> List[StubToolInfo]:
        self.calls += 1
        return [StubToolInfo(n) for n in self.names]


@pytest.fixture(autouse=True)
def clean_enabled_tools():
    reset_enabled_tools_cache()
    yield
    reset_enabled_tools_cache()


@pytest.fixture
def clean_env(monkeypatch):
    for var in ("CIRIS_ENV", "CIRIS_AGENT_ID", "CIRIS_TEMPLATE"):
        monkeypatch.delenv(var, raising=False)
    yield monkeypatch


def make_task(task_id: str = "task_1") -> Task:
    return Task(
        task_id=task_id,
        channel_id="c-1",
        agent_occurrence_id="default",
        description="Respond to message from @someone",
        status=TaskStatus.ACTIVE,
        created_at="2026-07-30T00:00:00+00:00",
        updated_at="2026-07-30T00:00:00+00:00",
        context=TaskContext(channel_id="c-1", user_id="u-1", correlation_id="corr-1"),
    )


# --------------------------------------------------- deployment tier resolution


def test_environment_tier_defaults_to_development_not_production(clean_env):
    """An unlabelled deployment must not inherit production standing."""
    assert deployment_mod.resolve_environment_tier() is EnvironmentTier.DEVELOPMENT


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("prod", EnvironmentTier.PRODUCTION),
        ("production", EnvironmentTier.PRODUCTION),
        ("qa", EnvironmentTier.QA),
        ("dev", EnvironmentTier.DEVELOPMENT),
        ("local", EnvironmentTier.LOCAL),
        ("nonsense", EnvironmentTier.DEVELOPMENT),
    ],
)
def test_environment_tier_resolution(clean_env, raw, expected):
    clean_env.setenv("CIRIS_ENV", raw)
    assert deployment_mod.resolve_environment_tier() is expected


def test_deployment_scope_carries_the_four_knowable_coordinates(clean_env):
    clean_env.setenv("CIRIS_ENV", "prod")
    clean_env.setenv("CIRIS_AGENT_ID", "echo-speculative")
    clean_env.setenv("CIRIS_TEMPLATE", "echo")
    scope = deployment_mod.resolve_deployment_scope("occurrence-2")
    assert scope.environment_tier is EnvironmentTier.PRODUCTION
    assert scope.agent_id == "echo-speculative"
    assert scope.template == "echo"
    assert scope.agent_occurrence_id == "occurrence-2"


# ---------------------------------------------------------------- enabled tools


async def test_enabled_tools_resolve_from_the_registry():
    source = StubToolSource(DEPLOYMENT_TOOLS)
    resolved = await prime_enabled_tools(source)
    assert resolved == frozenset(DEPLOYMENT_TOOLS)
    assert cached_enabled_tools() == frozenset(DEPLOYMENT_TOOLS)


async def test_registered_source_is_used_when_none_is_passed():
    register_tool_name_source(StubToolSource(DEPLOYMENT_TOOLS))
    assert await prime_enabled_tools() == frozenset(DEPLOYMENT_TOOLS)


async def test_registry_failure_keeps_the_previous_grant():
    """A transient registry error must not silently shrink every envelope."""

    class Flaky(StubToolSource):
        async def get_all_tool_info(self, handler_name: str = "default"):
            raise RuntimeError("registry down")

    await prime_enabled_tools(StubToolSource(DEPLOYMENT_TOOLS))
    assert await prime_enabled_tools(Flaky([]), force=True) == frozenset(DEPLOYMENT_TOOLS)


async def test_empty_registry_sweep_keeps_the_previous_grant():
    """An empty sweep almost always means adapters have not registered yet."""
    await prime_enabled_tools(StubToolSource(DEPLOYMENT_TOOLS))
    assert await prime_enabled_tools(StubToolSource([]), force=True) == frozenset(DEPLOYMENT_TOOLS)


async def test_cache_ttl_avoids_a_registry_sweep_per_task():
    source = StubToolSource(DEPLOYMENT_TOOLS)
    await prime_enabled_tools(source)
    await prime_enabled_tools(source)
    await prime_enabled_tools(source)
    assert source.calls == 1
    await prime_enabled_tools(source, force=True)
    assert source.calls == 2


# ------------------------------------------------------------------- issuance


async def test_issuance_grants_every_enabled_tool_enumerated(clean_env):
    """The default grant is the deployment's enabled set, written out in full."""
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource(DEPLOYMENT_TOOLS))
    assert envelope.granted_tools == frozenset(DEPLOYMENT_TOOLS)
    # Enumerated, not wildcarded: every name is literal and present.
    for name in DEPLOYMENT_TOOLS:
        assert envelope.permits_tool(name)
    assert "*" not in envelope.granted_tools


async def test_issuance_includes_consequential_and_auto_run_tools(clean_env):
    """Kick/ban and context-enrichment providers must be in every envelope.

    We cannot know at creation whether a message is a greeting or CSAM; the
    task that needs the ban is exactly the one that could not have declared it.
    Auto-run enrichment providers cannot be declared in advance at all.
    """
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource(DEPLOYMENT_TOOLS))
    assert envelope.permits_tool("discord_ban_user")
    assert envelope.permits_tool("weather")
    assert envelope.permits_tool("ha_integration")


async def test_issuance_is_identical_for_every_task_in_a_deployment(clean_env):
    """Task purpose is not an input, so two different tasks get the same grant."""
    source = StubToolSource(DEPLOYMENT_TOOLS)
    a = await issue_deployment_envelope(task_id="task_a", tool_source=source)
    b = await issue_deployment_envelope(task_id="task_b", tool_source=source)
    assert a.granted_tools == b.granted_tools
    assert a.capabilities == b.capabilities
    assert a.deployment == b.deployment
    # Bound per task for attribution, with distinct ids.
    assert a.task_id != b.task_id
    assert a.envelope_id != b.envelope_id


async def test_issuance_records_the_requester(clean_env):
    envelope = await issue_deployment_envelope(
        task_id="task_1",
        requester=RequesterAuthorization(user_id="u-9", channel_id="c-1", source_ref="msg-3"),
        tool_source=StubToolSource(DEPLOYMENT_TOOLS),
    )
    assert envelope.requester.user_id == "u-9"
    assert envelope.requester.source_ref == "msg-3"
    assert envelope.issuer.kind is EnvelopeIssuerKind.DEPLOYMENT_RESOLVED
    assert envelope.issuer.issuer_id is None


async def test_issuance_declares_the_full_effect_class_set_enumerated(clean_env):
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource(DEPLOYMENT_TOOLS))
    assert envelope.capabilities == ALL_TOOL_CAPABILITIES
    assert len(envelope.capabilities) == len(ToolCapability)


async def test_cold_registry_yields_an_empty_grant_not_an_implicit_everything(clean_env, caplog):
    """Fail-closed: nothing observed means nothing granted, loudly."""
    envelope = await issue_deployment_envelope(task_id="task_1")
    assert envelope.granted_tools == frozenset()
    assert envelope.permits_tool("weather") is False
    assert any("EMPTY tool grant" in rec.message for rec in caplog.records)


def test_sync_issuance_uses_the_primed_cache(clean_env):
    import asyncio

    asyncio.run(prime_enabled_tools(StubToolSource(DEPLOYMENT_TOOLS)))
    envelope = issue_deployment_envelope_from_cache(task_id="task_1")
    assert envelope.granted_tools == frozenset(DEPLOYMENT_TOOLS)


def test_sync_issuance_cold_cache_is_empty_and_warns(clean_env, caplog):
    envelope = issue_deployment_envelope_from_cache(task_id="task_1")
    assert envelope.granted_tools == frozenset()
    assert any("EMPTY tool grant" in rec.message for rec in caplog.records)


# ------------------------------------------------------------ authority issuance


def test_authority_issuance_requires_a_named_authority(clean_env):
    with pytest.raises(ValueError, match="requires a named authority"):
        issue_authority_envelope(
            task_id="task_1",
            issuer_kind=EnvelopeIssuerKind.DEPLOYMENT_RESOLVED,
            issuer_id="wa-1",
            granted_tools=[],
            capabilities=[],
        )


def test_authority_issuance_can_declare_roots_and_credentials(clean_env):
    envelope = issue_authority_envelope(
        task_id="task_1",
        issuer_kind=EnvelopeIssuerKind.WISE_AUTHORITY,
        issuer_id="wa-root",
        granted_tools=["sql_query"],
        capabilities=[ToolCapability.WRITE_TARGET],
        target_roots=(TargetRoot(scheme="postgresql", host="db.internal"),),
        credentials=(
            IssuedCredential(
                credential_ref="pg_dsn_ref", target_host="db.internal", auth_kind=TargetAuthKind.CONNECTION_STRING
            ),
        ),
    )
    assert envelope.issuer.kind is EnvelopeIssuerKind.WISE_AUTHORITY
    assert envelope.issuer.issuer_id == "wa-root"
    assert envelope.credential_for("db.internal") is not None


# ---------------------------------------------------------- binding & lifetime


async def test_envelope_binds_to_its_task_and_is_readable_back(clean_env):
    task = make_task()
    envelope = await issue_deployment_envelope(
        task_id=task.task_id, tool_source=StubToolSource(DEPLOYMENT_TOOLS)
    )
    attach_envelope_to_task(task, envelope)
    assert resolve_task_envelope(task) == envelope
    assert task.context.envelope.task_id == task.task_id


async def test_envelope_cannot_be_attached_to_a_different_task(clean_env):
    task = make_task("task_1")
    other = await issue_deployment_envelope(task_id="task_2", tool_source=StubToolSource(DEPLOYMENT_TOOLS))
    with pytest.raises(ValueError, match="is bound to task"):
        attach_envelope_to_task(task, other)


def test_task_without_an_envelope_resolves_to_none_which_is_denial():
    assert resolve_task_envelope(make_task()) is None
    assert resolve_task_envelope(None) is None


def test_best_effort_issuance_binds_and_never_drops_the_task(clean_env):
    import asyncio

    asyncio.run(prime_enabled_tools(StubToolSource(DEPLOYMENT_TOOLS)))
    task = make_task()
    issue_task_envelope_best_effort(task)
    assert task.context.envelope is not None
    assert task.context.envelope.granted_tools == frozenset(DEPLOYMENT_TOOLS)


# -------------------------------------------------------------- multi-occurrence


async def test_envelope_records_the_owning_occurrence(clean_env):
    envelope = await issue_deployment_envelope(
        task_id="task_1", agent_occurrence_id="occurrence-3", tool_source=StubToolSource(DEPLOYMENT_TOOLS)
    )
    assert envelope.deployment.agent_occurrence_id == "occurrence-3"
    assert envelope.agent_occurrence_id == "occurrence-3"


async def test_envelope_survives_the_persist_context_round_trip(clean_env):
    """The envelope rides in the task row, so it survives restart and is
    visible to every occurrence sharing the database."""
    from ciris_engine.logic.persistence.models.tasks import _persist_row_to_task, _task_to_persist_payload

    task = make_task()
    envelope = await issue_deployment_envelope(
        task_id=task.task_id, agent_occurrence_id="occurrence-2", tool_source=StubToolSource(DEPLOYMENT_TOOLS)
    )
    attach_envelope_to_task(task, envelope)

    payload = _task_to_persist_payload(task)
    assert "envelope" in payload["context"]

    restored = _persist_row_to_task(payload)
    assert restored.context.envelope == envelope


def test_corrupt_persisted_envelope_decodes_to_denial_not_to_permission(caplog):
    from ciris_engine.logic.persistence.models.tasks import _decode_envelope

    assert _decode_envelope({"not": "an envelope"}, "task_1") is None
    assert _decode_envelope("garbage", "task_1") is None
    assert any("treating as no envelope (deny)" in rec.message for rec in caplog.records)


# --------------------------------------------------------------- attenuation API


async def test_attenuate_envelope_helper_narrows(clean_env):
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource(DEPLOYMENT_TOOLS))
    narrowed = attenuate_envelope(envelope, granted_tools={"self_help"})
    assert narrowed.granted_tools == frozenset({"self_help"})
    assert narrowed.attenuated_from == envelope.envelope_id


async def test_attenuate_envelope_helper_cannot_widen(clean_env):
    envelope = await issue_deployment_envelope(task_id="task_1", tool_source=StubToolSource(["self_help"]))
    with pytest.raises(EnvelopeWideningError):
        attenuate_envelope(envelope, granted_tools={"self_help", "tmux"})


def test_no_narrowing_policy_ships_for_cirisagent():
    """Attenuation is available; CIRISAgent deliberately does not use it.

    The verticals with typed tasks (CIRISMedical, CIRISFinancial) are where
    narrowing is meaningful. If this assertion ever fails, a narrowing policy
    has been introduced and it needs its own justification and tests.
    """
    import subprocess

    repo_root = next(
        parent
        for parent in pathlib.Path(__file__).resolve().parents
        if (parent / "ciris_engine").is_dir() and (parent / "tests").is_dir()
    )
    result = subprocess.run(
        ["grep", "-rn", "attenuate_envelope(", "ciris_engine/"],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    callers = [
        line
        for line in result.stdout.splitlines()
        if "envelope_issuer.py" not in line and "def attenuate_envelope" not in line
    ]
    assert callers == [], f"a narrowing policy was introduced without justification: {callers}"


# ------------------------------------ the one reasoning-loop write path


async def test_conscience_style_read_modify_write_preserves_the_envelope(clean_env):
    """`updated_status_conscience.py:140` writes a task row from *inside* the
    reasoning loop.

    It reads the row with `_persist_row_to_task`, flips
    `updated_info_available`, and writes it back with
    `_task_to_persist_payload`. That is a task-row write reachable from the
    conscience layer, and the envelope must survive it byte-for-byte — a
    conscience silently dropping a task's authorization would look identical to
    a task that never had one, and under Phase 2 would deny every subsequent
    tool call on that task.

    This is also the weakest link in Phase 1's issuance story: the mint guard is
    on the issuer, not on the write. See FSD/TASK_ENVELOPE.md §2.
    """
    from ciris_engine.logic.persistence.models.tasks import _persist_row_to_task, _task_to_persist_payload

    task = make_task()
    envelope = await issue_deployment_envelope(
        task_id=task.task_id, tool_source=StubToolSource(DEPLOYMENT_TOOLS)
    )
    attach_envelope_to_task(task, envelope)

    # Exactly what the conscience does.
    row = _task_to_persist_payload(task)
    reloaded = _persist_row_to_task(row)
    reloaded.updated_info_available = False
    written_back = _task_to_persist_payload(reloaded)
    final = _persist_row_to_task(written_back)

    assert final.context is not None
    assert final.context.envelope == envelope
    assert final.context.envelope.granted_tools == frozenset(DEPLOYMENT_TOOLS)
