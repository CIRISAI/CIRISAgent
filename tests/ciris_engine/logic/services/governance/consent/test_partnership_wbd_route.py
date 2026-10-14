"""PARTNERED is a data-management record; a non-steward request goes to the steward via WBD (#1251).

End to end over the REAL deferral path: a real persist Engine, a real
ServiceRegistry + WiseBus, and the real WiseAuthorityService that the
``/v1/wa/deferrals/{id}/resolve`` route calls. Nothing here is a parallel
mechanism - the consent service only creates the task, hands a DeferralContext
to ``WiseBus.send_deferral``, and applies the answer ``resolve_deferral`` gives it.

Each behaviour has its negative: a non-steward request changes NOTHING until
answered; a refusal writes nothing; a steward's own request defers nothing; a
resolution the consent service cannot apply is refused, leaving it pending.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.logic.services.governance.consent import ConsentService, StewardDeferralUnavailableError
from ciris_engine.logic.services.governance.consent import service as consent_service_module
from ciris_engine.logic.services.governance.consent.attestation import PartnershipGrantState, PartnershipPairEmission
from ciris_engine.logic.services.governance.consent.partnership import (
    DEFERRAL_KIND_KEY,
    PARTNERED_STREAM_KIND,
    SHARED_OCCURRENCE_ID,
    partnership_task_prefix,
)
from ciris_engine.logic.services.governance.wise_authority import WiseAuthorityService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    ConsentRequest,
    ConsentStatus,
    ConsentStream,
    PartnershipRequestStatus,
)
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority_core import DeferralResponse, WARole

USER = "discord:4815162342"
STEWARD_WA = "wa-2026-10-11-STEWRD"
CATEGORIES = [ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE]


@pytest.fixture
def time_service():
    return TimeService()


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    os.unlink(db_path)
    yield db_path
    for ext in ("", "-wal", "-shm"):
        if os.path.exists(db_path + ext):
            os.unlink(db_path + ext)


@pytest_asyncio.fixture
async def wired(temp_db, time_service, monkeypatch):
    """Real engine + registry + WiseBus + WA service + consent service, wired as ServiceInitializer does."""
    import ciris_engine.logic.persistence.models.graph as graph_mod
    from ciris_engine.logic.persistence._substrate import Engine, reset_engine  # type: ignore[import-untyped]
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    prior_engine, prior_dsn = graph_mod._engine, graph_mod._engine_dsn
    reset_engine()
    set_persist_engine(Engine(f"sqlite:///{temp_db}", "test-key"), dsn=f"sqlite:///{temp_db}")

    auth = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
    await auth.start()
    auth.get_wa = AsyncMock(
        return_value=MagicMock(wa_id=STEWARD_WA, role=WARole.AUTHORITY, active=True, created_at=time_service.now())
    )

    wa = WiseAuthorityService(time_service=time_service, auth_service=auth, db_path=temp_db)
    await wa.start()
    registry = ServiceRegistry()
    registry.register_service(
        service_type=ServiceType.WISE_AUTHORITY,
        provider=wa,
        priority=Priority.HIGH,
        capabilities=["send_deferral", "get_pending_deferrals", "resolve_deferral"],
    )
    consent = ConsentService(time_service=time_service, wise_bus=WiseBus(registry, time_service))
    wa.attach_consent_service(consent)

    # Record every wire-pair emission instead of needing a signing key here;
    # the emission itself is covered against a fake and the REAL engine below.
    emissions: List[dict] = []

    def record(status, *, user_key_id=None, decided_by=None, deferral_id=None):
        emissions.append(
            {"stream": status.stream, "user_id": status.user_id, "decided_by": decided_by, "deferral_id": deferral_id}
        )
        return PartnershipPairEmission(bilateral_pair_id="pair", grant_state=PartnershipGrantState.KEYLESS_USER)

    monkeypatch.setattr(consent_service_module, "emit_partnership_pair", record)
    try:
        yield {"consent": consent, "wa": wa, "emissions": emissions}
    finally:
        await wa.stop()
        await auth.stop()
        graph_mod._engine, graph_mod._engine_dsn = prior_engine, prior_dsn


def _partnered(user_id: str = USER) -> ConsentRequest:
    return ConsentRequest(user_id=user_id, stream=ConsentStream.PARTNERED, categories=CATEGORIES, reason="I want this")


async def _temporary_baseline(consent: ConsentService) -> ConsentStatus:
    return await consent.grant_consent(
        ConsentRequest(user_id=USER, stream=ConsentStream.TEMPORARY, categories=[ConsentCategory.INTERACTION])
    )


async def _only_pending(wa: WiseAuthorityService):
    pending = await wa.get_pending_deferrals()
    assert len(pending) == 1, pending
    return pending[0]


def _resolution(approved: bool) -> DeferralResponse:
    return DeferralResponse(approved=approved, reason="steward's answer", wa_id=STEWARD_WA, signature="")


class TestNonStewardRequestIsDeferred:
    @pytest.mark.asyncio
    async def test_creates_one_wbd_deferral_and_changes_nothing(self, wired):
        consent, wa, emissions = wired["consent"], wired["wa"], wired["emissions"]
        before = await _temporary_baseline(consent)
        emissions.clear()

        returned = await consent.grant_consent(_partnered(), channel_id=f"api_{USER}")

        # The user's CURRENT stream comes back, and nothing was written or emitted.
        assert returned.stream == ConsentStream.TEMPORARY
        assert (await consent.get_consent(USER)).stream == ConsentStream.TEMPORARY
        assert (await consent.get_consent(USER)).last_modified == before.last_modified
        assert emissions == []

        # One deferral, on the shared namespace the WA listing reads, tagged as a consent request.
        deferral = await _only_pending(wa)
        assert deferral.task_id.startswith(partnership_task_prefix(USER))
        assert deferral.context[DEFERRAL_KIND_KEY] == PARTNERED_STREAM_KIND
        assert deferral.context["user_id"] == USER
        assert deferral.context["categories"] == "interaction,preference"
        assert deferral.user_id == USER
        assert await consent.get_partnership_request_status(USER) == PartnershipRequestStatus.PENDING

    @pytest.mark.asyncio
    async def test_asking_again_while_open_does_not_defer_twice(self, wired):
        consent, wa = wired["consent"], wired["wa"]
        await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        await consent.grant_consent(_partnered())
        await _only_pending(wa)

    @pytest.mark.asyncio
    async def test_task_is_never_agent_work(self, wired):
        """Created DEFERRED, so no processor can pick it up as a PENDING task."""
        from ciris_engine.logic.persistence.models.tasks import get_task_by_id_any_occurrence

        consent, wa = wired["consent"], wired["wa"]
        await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        task = get_task_by_id_any_occurrence((await _only_pending(wa)).task_id)
        assert task is not None
        assert task.status.value == "deferred"
        assert task.agent_occurrence_id == SHARED_OCCURRENCE_ID

    @pytest.mark.asyncio
    async def test_no_deferral_path_fails_loud_and_writes_nothing(self, time_service, monkeypatch):
        consent = ConsentService(time_service=time_service)  # no wise_bus
        consent.get_consent = AsyncMock(side_effect=consent_service_module.ConsentNotFoundError("none"))
        monkeypatch.setattr(consent_service_module, "find_open_partnership_task", lambda _u: None)
        added = []
        monkeypatch.setattr("ciris_engine.logic.persistence.models.tasks.add_task", added.append)
        with pytest.raises(StewardDeferralUnavailableError):
            await consent.grant_consent(_partnered())
        assert added == []

    @pytest.mark.asyncio
    async def test_undelivered_deferral_fails_loud(self, time_service, monkeypatch):
        bus = MagicMock()
        bus.send_deferral = AsyncMock(return_value=False)
        consent = ConsentService(time_service=time_service, wise_bus=bus)
        consent.get_consent = AsyncMock(side_effect=consent_service_module.ConsentNotFoundError("none"))
        monkeypatch.setattr(consent_service_module, "find_open_partnership_task", lambda _u: None)
        added = []
        monkeypatch.setattr("ciris_engine.logic.persistence.models.tasks.add_task", added.append)
        with pytest.raises(StewardDeferralUnavailableError):
            await consent.grant_consent(_partnered())
        assert bus.send_deferral.await_count == 1


class TestStewardAnswers:
    @pytest.mark.asyncio
    async def test_approval_writes_partnered_and_emits_the_pair(self, wired):
        consent, wa, emissions = wired["consent"], wired["wa"], wired["emissions"]
        await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        deferral = await _only_pending(wa)
        emissions.clear()

        assert await wa.resolve_deferral(deferral.deferral_id, _resolution(approved=True)) is True

        status = await consent.get_consent(USER)
        assert status.stream == ConsentStream.PARTNERED
        assert status.categories == CATEGORIES
        assert emissions == [
            {
                "stream": ConsentStream.PARTNERED,
                "user_id": USER,
                "decided_by": STEWARD_WA,
                "deferral_id": deferral.deferral_id,
            }
        ]
        assert await wa.get_pending_deferrals() == []
        assert await consent.get_partnership_request_status(USER) == PartnershipRequestStatus.PARTNERED

    @pytest.mark.asyncio
    async def test_decision_is_recorded_on_the_deferral(self, wired):
        from ciris_engine.logic.persistence.models.tasks import get_task_raw_context

        consent, wa = wired["consent"], wired["wa"]
        await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        deferral = await _only_pending(wa)
        await wa.resolve_deferral(deferral.deferral_id, _resolution(approved=True))

        resolution = get_task_raw_context(deferral.task_id)["deferral"]["resolution"]
        assert resolution["approved"] is True
        assert resolution["resolved_by"] == STEWARD_WA

    @pytest.mark.asyncio
    async def test_approval_creates_no_agent_guidance_task(self, wired):
        """The effect is the stream write; there is no thought to resume."""
        from ciris_engine.logic.persistence.models.tasks import get_all_tasks

        consent, wa = wired["consent"], wired["wa"]
        await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        deferral = await _only_pending(wa)
        await wa.resolve_deferral(deferral.deferral_id, _resolution(approved=True))

        for occurrence in ("default", SHARED_OCCURRENCE_ID):
            assert not [t for t in get_all_tasks(occurrence) if t.description.startswith("[WA GUIDANCE]")]

    @pytest.mark.asyncio
    async def test_refusal_leaves_the_stream_unchanged(self, wired):
        consent, wa, emissions = wired["consent"], wired["wa"], wired["emissions"]
        before = await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        deferral = await _only_pending(wa)
        emissions.clear()

        assert await wa.resolve_deferral(deferral.deferral_id, _resolution(approved=False)) is True

        after = await consent.get_consent(USER)
        assert after.stream == ConsentStream.TEMPORARY
        assert after.last_modified == before.last_modified
        assert emissions == []
        assert await wa.get_pending_deferrals() == []
        assert await consent.get_partnership_request_status(USER) == PartnershipRequestStatus.NONE

    @pytest.mark.asyncio
    async def test_users_later_choice_outranks_a_stale_approval(self, wired):
        """The steward decides whether to retain the user; never overrides the user's later choice."""
        consent, wa, emissions = wired["consent"], wired["wa"], wired["emissions"]
        await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        deferral = await _only_pending(wa)
        await consent.grant_consent(
            ConsentRequest(user_id=USER, stream=ConsentStream.ANONYMOUS, categories=[ConsentCategory.RESEARCH])
        )
        emissions.clear()

        assert await wa.resolve_deferral(deferral.deferral_id, _resolution(approved=True)) is True

        assert (await consent.get_consent(USER)).stream == ConsentStream.ANONYMOUS
        assert emissions == []

    @pytest.mark.asyncio
    async def test_unapplicable_resolution_is_refused_and_stays_pending(self, wired):
        """No consent service attached: the answer cannot be applied, so it is not recorded either."""
        consent, wa = wired["consent"], wired["wa"]
        await _temporary_baseline(consent)
        await consent.grant_consent(_partnered())
        deferral = await _only_pending(wa)
        wa._consent_service = None

        assert await wa.resolve_deferral(deferral.deferral_id, _resolution(approved=True)) is False

        assert (await consent.get_consent(USER)).stream == ConsentStream.TEMPORARY
        assert (await _only_pending(wa)).deferral_id == deferral.deferral_id

    @pytest.mark.asyncio
    async def test_ordinary_deferrals_are_untouched(self, wired, time_service):
        """A deferral that is not a consent request never reaches the consent service."""
        from ciris_engine.logic.persistence.models.tasks import add_task
        from ciris_engine.logic.utils.task_thought_factory import create_task
        from ciris_engine.schemas.services.authority_core import DeferralRequest

        consent, wa = wired["consent"], wired["wa"]
        consent.apply_steward_partnership_decision = AsyncMock()
        task = create_task(
            description="ordinary", channel_id="c", agent_occurrence_id="default", correlation_id="corr-ordinary"
        )
        add_task(task)
        deferral_id = await wa.send_deferral(
            DeferralRequest(
                task_id=task.task_id, thought_id="t", reason="r", defer_until=datetime.now(timezone.utc), context={}
            )
        )
        assert await wa.resolve_deferral(deferral_id, _resolution(approved=True)) is True
        consent.apply_steward_partnership_decision.assert_not_awaited()


class TestStewardOwnRequest:
    @pytest.mark.asyncio
    async def test_applies_directly_with_no_deferral(self, wired):
        consent, wa, emissions = wired["consent"], wired["wa"], wired["emissions"]
        await _temporary_baseline(consent)
        emissions.clear()

        status = await consent.grant_consent(_partnered(), requester_is_steward=True)

        assert status.stream == ConsentStream.PARTNERED
        assert (await consent.get_consent(USER)).stream == ConsentStream.PARTNERED
        assert await wa.get_pending_deferrals() == []
        assert [e["stream"] for e in emissions] == [ConsentStream.PARTNERED]


class TestRouteStewardship:
    """The API route marks the requester a steward exactly when they may resolve deferrals."""

    @pytest.mark.parametrize(
        "role,expected", [("OBSERVER", False), ("ADMIN", False), ("AUTHORITY", True), ("SYSTEM_ADMIN", True)]
    )
    @pytest.mark.asyncio
    async def test_requester_is_steward_follows_resolve_permission(self, role, expected):
        from ciris_engine.logic.adapters.api.routes import consent as consent_routes
        from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS, AuthContext, UserRole

        user_role = UserRole(role)
        auth = AuthContext(
            user_id=USER,
            role=user_role,
            permissions=ROLE_PERMISSIONS.get(user_role, set()),
            authenticated_at=datetime.now(timezone.utc),
        )
        manager = MagicMock()
        manager.grant_consent = AsyncMock(return_value="ok")
        await consent_routes.grant_consent(_partnered(), auth, manager)
        assert manager.grant_consent.await_args.kwargs["requester_is_steward"] is expected
