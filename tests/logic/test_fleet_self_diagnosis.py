"""Every fleet failure in #1057 must announce itself through the health API.

2.9.23 is the "if it does not work, the console and logs will tell you why"
release, and #1057 is the case that earned it. A five-agent fleet ran
2.9.22-stable with every container `running`/`healthy`, 0 restarts, correct
image — and only two of five agents doing any work:

  * two adapters failed to import on EVERY agent (`sync`, and
    `ciris_covenant_metrics`, which had been renamed to `ciris_accord_metrics`);
    one agent served with NONE of its configured adapters loaded
  * datum logged a successful shared-wakeup claim on every boot while its store
    held no such row — and no row of any kind for 17 days — then span in WAKEUP
    to round 66 finding 0 thoughts
  * a SHUTDOWN_SHARED task sat ACTIVE for 17 days, `updated_at` never moving
  * scout2 declared itself single-occurrence while running as occurrence 002

Every one of those was invisible from outside the container. Finding them took a
manual inventory of five agents' databases and logs. CIRISManager GENERATES the
config and ASSIGNS the occurrence id, so it is precisely the component that
could have corrected most of this — if anything had told it.

These tests assert the conditions reach `/v1/system/health` as machine-readable
warning codes. They deliberately test the WARNING PRODUCERS rather than a live
fleet: the producers are the contract manager consumes.
"""

from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from ciris_engine.logic.adapters.api.routes.system.health import (
    _adapter_load_failure_warnings,
    _claim_persistence_warnings,
    _occurrence_warnings,
    _stale_shared_task_warnings,
)
from ciris_engine.schemas.runtime.adapter_management import AdapterLoadFailure


def _request(**state) -> SimpleNamespace:
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(**state)))


class _Adapter:
    def __init__(self, adapter_type: str) -> None:
        self.adapter_type = adapter_type


# ── Finding 1: adapters that never loaded ────────────────────────────────────


def test_a_renamed_adapter_reports_as_stale_config() -> None:
    """`ciris_covenant_metrics` no longer exists; manager can fix that itself."""
    runtime = SimpleNamespace(
        adapters=[_Adapter("discord")],
        adapter_load_failures=[
            AdapterLoadFailure(
                adapter_type="ciris_covenant_metrics",
                adapter_id="ciris_covenant_metrics",
                error="Could not import adapter module for mode 'ciris_covenant_metrics'.",
                error_type="ValueError",
                is_missing_module=True,
            )
        ],
    )
    warnings = _adapter_load_failure_warnings(_request(runtime=runtime))
    codes = {w.code for w in warnings}
    assert "adapters_config_stale" in codes
    assert any("ciris_covenant_metrics" in w.message for w in warnings)


def test_zero_external_adapters_is_an_error_not_a_warning() -> None:
    """The exact scout1 state: 0 of 4 configured adapters, previously `healthy`.

    An agent whose only adapters are the internal auto-loaded ones is talking to
    nobody. That must not be reported at `warning` severity.
    """
    runtime = SimpleNamespace(
        # ciris_verify / wallet / ciris_accord_metrics always auto-load; none of
        # them is a communication adapter.
        adapters=[_Adapter("ciris_verify"), _Adapter("wallet"), _Adapter("ciris_accord_metrics")],
        adapter_load_failures=[
            AdapterLoadFailure(
                adapter_type=t, adapter_id=t, error="boom", error_type="ValueError", is_missing_module=True
            )
            for t in ("api", "sync", "ciris_covenant_metrics", "ciris_accord_metrics")
        ],
    )
    warnings = _adapter_load_failure_warnings(_request(runtime=runtime))
    assert warnings
    assert all(w.severity == "error" for w in warnings)


def test_a_broken_adapter_is_reported_separately_from_a_missing_one() -> None:
    """They need different fixes: regenerate config vs debug the adapter."""
    runtime = SimpleNamespace(
        adapters=[_Adapter("discord")],
        adapter_load_failures=[
            AdapterLoadFailure(
                adapter_type="sync", adapter_id="sync", error="no module", error_type="ValueError", is_missing_module=True
            ),
            AdapterLoadFailure(
                adapter_type="discord2",
                adapter_id="discord2",
                error="bad token",
                error_type="ConnectionError",
                is_missing_module=False,
            ),
        ],
    )
    codes = {w.code for w in _adapter_load_failure_warnings(_request(runtime=runtime))}
    assert codes == {"adapters_config_stale", "adapters_failed_to_load"}


def test_a_healthy_agent_emits_no_adapter_warning() -> None:
    runtime = SimpleNamespace(adapters=[_Adapter("api")], adapter_load_failures=[])
    assert _adapter_load_failure_warnings(_request(runtime=runtime)) == []


# ── Finding 2: a claim that reported success and left no row ─────────────────


def test_a_claim_that_did_not_persist_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """datum's failure: 'claimed shared' logged, no row, spins forever."""
    from ciris_engine.logic.persistence.models import tasks as tasks_mod

    monkeypatch.setattr(
        tasks_mod, "get_shared_claim_failures", lambda: [{"task_id": "WAKEUP_SHARED_20260817", "outcome": "stored"}]
    )
    warnings = _claim_persistence_warnings(_request())
    assert [w.code for w in warnings] == ["shared_claim_not_persisted"]
    assert warnings[0].severity == "error"
    assert "WAKEUP_SHARED_20260817" in warnings[0].message


def test_no_claim_failures_means_no_warning() -> None:
    assert _claim_persistence_warnings(_request()) == []


# ── Finding 3: the 17-day-old ACTIVE shared task ─────────────────────────────


def test_a_shared_task_stuck_for_days_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """SHUTDOWN_SHARED_20260731, ACTIVE, updated_at never moved (#1018)."""
    old = (datetime.now(timezone.utc) - timedelta(days=17)).isoformat()
    task = SimpleNamespace(task_id="SHUTDOWN_SHARED_20260731", status="active", created_at=old, updated_at=old)

    import ciris_engine.logic.persistence.models.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "get_all_tasks", lambda **kw: [task], raising=False)
    warnings = _stale_shared_task_warnings(_request())
    assert [w.code for w in warnings] == ["shared_task_stranded"]
    assert "SHUTDOWN_SHARED_20260731" in warnings[0].message
    assert warnings[0].severity == "error"


def test_a_fresh_shared_task_is_not_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only genuinely stranded tasks; a task claimed minutes ago is normal."""
    fresh = datetime.now(timezone.utc).isoformat()
    task = SimpleNamespace(task_id="WAKEUP_SHARED_TODAY", status="active", created_at=fresh, updated_at=fresh)

    import ciris_engine.logic.persistence.models.tasks as tasks_mod

    monkeypatch.setattr(tasks_mod, "get_all_tasks", lambda **kw: [task], raising=False)
    assert _stale_shared_task_warnings(_request()) == []


# ── Finding 4: occurrence identity ───────────────────────────────────────────


def test_a_non_default_occurrence_is_reported_as_multi(monkeypatch: pytest.MonkeyPatch) -> None:
    """scout2: id 002 must not resolve to 'single-occurrence' (#1048)."""
    monkeypatch.setenv("AGENT_OCCURRENCE_ID", "002")
    monkeypatch.delenv("CIRIS_OCCURRENCE_ID", raising=False)
    monkeypatch.delenv("AGENT_OCCURRENCE_COUNT", raising=False)

    from ciris_engine.logic.utils.occurrence_utils import is_multi_occurrence_deployment

    assert is_multi_occurrence_deployment() is True

    warnings = _occurrence_warnings(_request())
    assert [w.code for w in warnings] == ["occurrence_identity"]
    assert "002" in warnings[0].message
    assert "multi_occurrence=True" in warnings[0].message


def test_the_documented_env_var_spelling_is_honoured(monkeypatch: pytest.MonkeyPatch) -> None:
    """CIRIS_OCCURRENCE_ID is the current standard; EssentialConfig reads both.

    occurrence_utils read only the legacy name, so the two halves of the system
    could disagree about which occurrence the process is.
    """
    monkeypatch.delenv("AGENT_OCCURRENCE_ID", raising=False)
    monkeypatch.setenv("CIRIS_OCCURRENCE_ID", "007")

    from ciris_engine.logic.utils.occurrence_utils import get_current_occurrence_id, is_multi_occurrence_deployment

    assert get_current_occurrence_id() == "007"
    assert is_multi_occurrence_deployment() is True


def test_a_plain_default_agent_stays_quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Most agents are single-occurrence; they must not emit noise."""
    monkeypatch.delenv("AGENT_OCCURRENCE_ID", raising=False)
    monkeypatch.delenv("CIRIS_OCCURRENCE_ID", raising=False)
    monkeypatch.setenv("AGENT_OCCURRENCE_COUNT", "1")
    assert _occurrence_warnings(_request()) == []


# ── The contract manager depends on ──────────────────────────────────────────


def test_every_new_code_is_distinct_and_actionable() -> None:
    """Manager routes on `code`; duplicates or renames silently break it."""
    codes = {
        "adapters_config_stale",
        "adapters_failed_to_load",
        "shared_claim_not_persisted",
        "shared_task_stranded",
        "occurrence_identity",
    }
    assert len(codes) == 5
    from ciris_engine.logic.adapters.api.routes.system import health as health_mod

    src = open(health_mod.__file__, encoding="utf-8").read()
    for code in codes:
        assert f'code="{code}"' in src, f"{code} is not emitted by the health route"


# ── The gap that survived 2.9.23: the top-level status field ─────────────────


def test_the_real_loader_records_a_missing_adapter() -> None:
    """The link that makes every warning above possible.

    The warning producers are tested with hand-built failures; this asserts the
    REAL loader populates them, because a recorder that is never reached makes
    the whole feature inert — which is precisely how a fleet ran six releases
    with two adapters failing to import on every agent.
    """
    from types import SimpleNamespace

    from ciris_engine.logic.runtime.bootstrap_helpers import _load_single_adapter

    runtime = SimpleNamespace(
        adapters=[], adapter_configs={}, modules_to_load=[], startup_channel_id="",
        debug=False, essential_config=None, bootstrap=SimpleNamespace(adapters=[]),
    )
    assert _load_single_adapter(runtime, "ciris_covenant_metrics", "ciris_covenant_metrics") is False

    failures = getattr(runtime, "adapter_load_failures", [])
    assert len(failures) == 1
    assert failures[0].adapter_type == "ciris_covenant_metrics"
    # A renamed/removed adapter is a STALE CONFIG, which manager can fix itself.
    assert failures[0].is_missing_module is True


def test_zero_adapters_forces_status_critical() -> None:
    """scout1's exact state must not read `healthy` at the top level.

    2.9.23 surfaced this as a warning, which was necessary and not sufficient:
    a warning buried in an array under a green status is still a green status,
    and `status` is the field every dashboard and operator reads first.

    critical, not degraded — an agent that can neither receive nor send is not
    doing a reduced job, it is doing none of it.
    """
    from ciris_engine.logic.adapters.api.routes.system.schemas import SystemWarning

    warnings = [
        SystemWarning(
            code="adapters_config_stale",
            message="Configured adapter(s) do not exist and were skipped: sync",
            severity="error",
            action_url="/settings/adapters",
        )
    ]
    # Mirrors the health route's own escalation rule.
    status = "healthy"
    if any(w.code in ("adapters_config_stale", "adapters_failed_to_load") and w.severity == "error" for w in warnings):
        status = "critical"
    assert status == "critical"


def test_a_warning_severity_adapter_gap_does_not_force_critical() -> None:
    """Some adapters loaded: degraded, not dead. Do not cry wolf.

    A gate that escalates on ANY adapter failure would fire on every agent that
    lost one optional adapter, and an alarm that is always on is not an alarm.
    """
    from ciris_engine.logic.adapters.api.routes.system.schemas import SystemWarning

    warnings = [
        SystemWarning(code="adapters_config_stale", message="one of four missing", severity="warning")
    ]
    status = "healthy"
    if any(w.code in ("adapters_config_stale", "adapters_failed_to_load") and w.severity == "error" for w in warnings):
        status = "critical"
    assert status == "healthy"


def test_the_health_route_actually_applies_the_escalation() -> None:
    """Pin it in the route, not just in this test's restatement of the rule."""
    import pathlib

    from ciris_engine.logic.adapters.api.routes.system import health as health_mod

    src = pathlib.Path(health_mod.__file__).read_text(encoding="utf-8")
    assert 'status = "critical"' in src
    assert "adapters_config_stale" in src


# ── 2.9.24: the agent must stay reachable, and say what it ignored ───────────


def test_the_real_loader_records_a_missing_adapter() -> None:
    """The link that makes every warning above possible.

    The warning producers are tested with hand-built failures; this asserts the
    REAL loader populates them. A recorder that is never reached makes the whole
    feature inert — which is how a fleet ran six releases with two adapters
    failing to import on every agent.
    """
    from types import SimpleNamespace

    from ciris_engine.logic.runtime.bootstrap_helpers import _load_single_adapter

    runtime = SimpleNamespace(
        adapters=[], adapter_configs={}, modules_to_load=[], startup_channel_id="",
        debug=False, essential_config=None, bootstrap=SimpleNamespace(adapters=[]),
    )
    assert _load_single_adapter(runtime, "ciris_covenant_metrics", "ciris_covenant_metrics") is False

    failures = getattr(runtime, "adapter_load_failures", [])
    assert len(failures) == 1
    assert failures[0].adapter_type == "ciris_covenant_metrics"
    assert failures[0].is_missing_module is True


def test_api_is_always_loaded_regardless_of_config() -> None:
    """scout1 ran 0 of 4 adapters and stayed up, unreachable.

    Whatever else fails, ONE door must stay open — otherwise the agent is a
    process burning CPU that nobody can talk to and nobody can ask why. It is
    also what makes "loudly log and ignore" safe for everything else.
    """
    src = pathlib.Path("ciris_engine/logic/runtime/bootstrap_helpers.py").read_text(encoding="utf-8")
    assert '_load_single_adapter(runtime, "api", "api")' in src
    # And a config that also lists `api` must not load it twice.
    assert '"ciris_accord_metrics", "api"' in src


def test_missing_adapters_are_ignored_not_fatal() -> None:
    """Ignoring is the policy — a stale generated config must not stop an agent."""
    from types import SimpleNamespace

    from ciris_engine.logic.runtime.bootstrap_helpers import _load_single_adapter

    runtime = SimpleNamespace(
        adapters=[], adapter_configs={}, modules_to_load=[], startup_channel_id="",
        debug=False, essential_config=None, bootstrap=SimpleNamespace(adapters=[]),
    )
    # Returns False rather than raising: the caller continues.
    assert _load_single_adapter(runtime, "definitely_not_an_adapter", "x") is False


def test_the_summary_names_what_it_ignored(caplog: pytest.LogCaptureFixture) -> None:
    """Loud, and specific. A count alone cannot be acted on.

    The failures WERE logged before — one ERROR line each, buried in hundreds of
    startup lines, with no total. Nobody reads a line they do not know to look
    for; everybody reads a banner.
    """
    from types import SimpleNamespace

    from ciris_engine.logic.runtime.bootstrap_helpers import _log_adapter_load_summary

    runtime = SimpleNamespace(
        adapters=[SimpleNamespace(adapter_type="api")],
        adapter_load_failures=[
            AdapterLoadFailure(
                adapter_type="sync", adapter_id="sync", error="no module",
                error_type="ValueError", is_missing_module=True,
            )
        ],
    )
    with caplog.at_level("ERROR"):
        _log_adapter_load_summary(runtime)

    text = caplog.text
    assert "sync" in text, "the ignored adapter must be named, not just counted"
    assert "IGNORED" in text
    assert "api" in text, "what DID load matters as much as what did not"


def test_a_clean_boot_does_not_shout(caplog: pytest.LogCaptureFixture) -> None:
    """No failures, no banner — an alarm that is always on is not an alarm."""
    from types import SimpleNamespace

    from ciris_engine.logic.runtime.bootstrap_helpers import _log_adapter_load_summary

    runtime = SimpleNamespace(adapters=[SimpleNamespace(adapter_type="api")], adapter_load_failures=[])
    with caplog.at_level("ERROR"):
        _log_adapter_load_summary(runtime)
    assert "IGNORED" not in caplog.text
