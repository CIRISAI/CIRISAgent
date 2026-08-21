"""Contracts the F1 gate and the LLM ladder actually depend on.

Three defects shipped on this branch and were caught by mypy, not by tests:

    health.py    `auth` was never a parameter          -> NameError on EVERY /v1/system/health
    wa.py        `_decision.authorized`                -> AttributeError whenever a domain WAS set
    wa.py        `_pd.metadata`                        -> field does not exist on PendingDeferral

They share one cause. The suites for both features drive helper functions with
duck-typed fixtures (``SimpleNamespace``, ``Mock``), and a duck answers to any
attribute you ask it for. ``mock.authorized`` is a truthy Mock; so is
``mock.metadata``. The fixture cannot disagree with the code, so the code was
never checked against the real thing.

These tests assert against the REAL Pydantic models and the REAL handler
signature, so a rename upstream fails here instead of in production.
"""

import inspect
from typing import get_type_hints

import pytest
from pydantic import ValidationError

from ciris_engine.logic.adapters.api.routes.system.health import get_system_health
from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import AuthorizationDecision


class TestHealthStaysReachableWithoutCredentials:
    """/v1/system/health is the container healthcheck target.

    docker-compose*.yml probes it with a bare `curl -f` and no Authorization
    header. If auth ever becomes REQUIRED here, every healthcheck fails, the
    container is marked unhealthy, and autoheal restarts it — a self-inflicted
    outage that looks like an app crash.
    """

    def test_handler_accepts_an_auth_argument(self) -> None:
        params = inspect.signature(get_system_health).parameters
        assert "auth" in params, (
            "get_system_health references `auth` to decide whether the caller may be handed "
            "LLM-settings links. It must arrive as a parameter; a free name is a NameError on "
            "every health request."
        )

    def test_auth_is_optional_so_an_unauthenticated_probe_still_works(self) -> None:
        hint = get_type_hints(get_system_health, include_extras=True).get("auth")
        assert "Optional" in str(hint) or "None" in str(
            hint
        ), f"auth must be Optional so an anonymous probe resolves to None; got {hint!r}"

    @pytest.mark.asyncio
    async def test_identifying_the_caller_cannot_fail_the_endpoint(self) -> None:
        """The dependency must not require an auth service to exist.

        OptionalAuthDep looked right and was wrong: it resolves optional_auth,
        whose nested Depends(get_auth_service) raises 500 when
        app.state.auth_service is missing. app.py's supported standalone path
        calls create_app() with no runtime, which skips _initialize_app_state
        entirely — so /v1/system/health would have 500'd before the handler
        ran, in exactly the uninitialized state it exists to REPORT, and the
        container healthcheck probing it would have failed.
        """
        from types import SimpleNamespace

        from ciris_engine.logic.adapters.api.routes.system.health import _identify_caller

        no_service = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
        assert await _identify_caller(no_service, None) is None

        wrong_type = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(auth_service="nope")))
        assert await _identify_caller(wrong_type, None) is None

    def test_health_binds_the_failure_proof_dependency(self) -> None:
        """Assert on what the handler USES, not on what its comments mention."""
        from ciris_engine.logic.adapters.api.routes.system.health import _identify_caller

        default = inspect.signature(get_system_health).parameters["auth"].default
        assert getattr(default, "dependency", None) is _identify_caller, (
            "health must resolve its caller through _identify_caller. OptionalAuthDep "
            "hard-depends on get_auth_service, which 500s when the auth service is absent — "
            f"health must degrade to 'unidentified caller', never to an error. got {default!r}"
        )


class TestAuthorizationDecisionFieldNames:
    """The jurisdiction gate reads these by name; extra='forbid' gives no slack."""

    def test_the_field_is_allowed_not_authorized(self) -> None:
        assert "allowed" in AuthorizationDecision.model_fields
        assert "authorized" not in AuthorizationDecision.model_fields, (
            "If this ever becomes `authorized`, update routes/wa.py — reading the wrong name "
            "raises AttributeError precisely when a domain IS set, i.e. exactly on the MEDICAL "
            "deferrals the F1 gate exists to stop."
        )

    def test_the_gate_reads_reason_and_required_scope(self) -> None:
        for f in ("reason", "required_scope", "scope_enforced"):
            assert f in AuthorizationDecision.model_fields, f"routes/wa.py logs {f} on denial"

    def test_a_typo_cannot_pass_silently(self) -> None:
        with pytest.raises(ValidationError):
            AuthorizationDecision(
                authorized=True,  # type: ignore[call-arg]
                message="m",
                wa_id="wa-1",
                action="resolve_deferrals",
            )


class TestPendingDeferralCarriesTheDomain:
    def test_context_exists_and_metadata_does_not(self) -> None:
        assert "context" in PendingDeferral.model_fields
        assert "metadata" not in PendingDeferral.model_fields, (
            "routes/wa.py once read `_pd.metadata` as a fallback for domain_hint. It never "
            "existed; the branch was dead and would have raised had it been reached."
        )

    def test_context_defaults_to_a_dict_so_get_is_always_safe(self) -> None:
        pd = PendingDeferral(
            deferral_id="d1",
            created_at=__import__("datetime").datetime.now(),
            deferred_by="agent",
            task_id="t1",
            thought_id="th1",
            reason="r",
        )
        assert pd.context == {}
        assert pd.context.get("domain_hint") is None, "the gate calls .get() without a None guard"

    def test_a_domain_hint_survives_the_round_trip(self) -> None:
        pd = PendingDeferral(
            deferral_id="d1",
            created_at=__import__("datetime").datetime.now(),
            deferred_by="agent",
            task_id="t1",
            thought_id="th1",
            reason="r",
            context={"domain_hint": "medical"},
        )
        assert pd.context.get("domain_hint") == "medical"


class TestProvidersWithoutScopesStillAnswerHonestly:
    """Wise authority is a multi-provider bus.

    The Discord adapter authorizes by guild role and has no CIRIS scopes to
    report. The protocol's default authorize() must give it a usable decision
    without inventing a scope it never checked.
    """

    @pytest.mark.asyncio
    async def test_default_authorize_reports_scope_not_enforced(self) -> None:
        from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityServiceProtocol

        class RoleOnlyProvider:
            async def check_authorization(self, wa_id, action, resource=None):
                return wa_id == "trusted"

            authorize = WiseAuthorityServiceProtocol.authorize

        provider = RoleOnlyProvider()

        granted = await provider.authorize("trusted", "resolve_deferrals", "medical")
        assert isinstance(granted, AuthorizationDecision)
        assert granted.allowed is True
        assert granted.reason is None
        assert (
            granted.scope_enforced is False
        ), "A provider that never looked at scopes must not claim it enforced them."

        refused = await provider.authorize("stranger", "resolve_deferrals", "medical")
        assert refused.allowed is False
        assert refused.reason is not None
        assert refused.scope_enforced is False
