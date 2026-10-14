"""The partnership wire pair (CIRISAgent#1251, CC 4.4.3.5.3 ``ratified_pair``).

Every stream write emits the grant half's content (the per-user consent:stream
row) and the SIGNED accept half, sharing one ``bilateral_pair_id``. Checked
three ways: the shape against a recording fake; the wiring (every stream write
emits, the steward decision is named); and the signature against the REAL
substrate in a subprocess, because a fake cannot show that persist signs it.
"""

import json
import subprocess
import sys
import textwrap
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.services.governance.consent import attestation as att
from ciris_engine.logic.services.governance.consent.attestation import (
    PartnershipGrantState,
    build_partnership_grant_input,
    emit_partnership_pair,
)
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream

USER = "google:1234567890"
AGENT_KEY = "agent-key-abc123"
OWNER_KEY = "owner-key-def456"


def _status(stream: ConsentStream = ConsentStream.PARTNERED) -> ConsentStatus:
    now = datetime.now(timezone.utc)
    return ConsentStatus(
        user_id=USER,
        stream=stream,
        categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE],
        granted_at=now,
        expires_at=now + timedelta(days=14) if stream == ConsentStream.TEMPORARY else None,
        last_modified=now,
        impact_score=0.0,
        attribution_count=0,
    )


class RecordingEngine:
    def __init__(self, owner=OWNER_KEY, reject_attested=False):
        self.local = []
        self.emitted = []
        self._owner = owner
        self._reject_attested = reject_attested

    def attestation_upsert_local(self, payload):
        self.local.append(json.loads(payload))
        return "stream-row-1"

    def emit_attestation_self(self, payload):
        body = json.loads(payload)
        if self._reject_attested and "attested_key_id" in body:
            raise ValueError("federation_invalid_argument")
        self.emitted.append(body)
        return f"accept-row-{len(self.emitted)}"

    def owner_of_json(self, key_id):
        assert key_id == AGENT_KEY
        return json.dumps(self._owner)


@pytest.fixture
def engine(monkeypatch):
    eng = RecordingEngine()
    monkeypatch.setattr(att, "_resolve_engine", lambda: eng)
    monkeypatch.setattr(att, "_resolve_attesting_key_id", lambda: AGENT_KEY)
    monkeypatch.delenv("CIRIS_CONSENT_CEG_ATTESTATIONS", raising=False)
    return eng


class TestPairShape:
    def test_one_bilateral_pair_id_across_both_halves(self, engine):
        emission = emit_partnership_pair(_status())

        assert len(engine.local) == 1 and len(engine.emitted) == 1
        stream_claim = engine.local[0]["attestation_envelope"]["claim"]
        accept = engine.emitted[0]
        accept_claim = accept["attestation_envelope"]["claim"]

        assert stream_claim["bilateral_pair_id"] == accept_claim["bilateral_pair_id"] == emission.bilateral_pair_id
        assert emission.accept_attestation_id == "accept-row-1"
        assert emission.stream_attestation_id == "stream-row-1"

    def test_accept_half_is_the_reserved_leaf_under_the_owner_binding(self, engine):
        emit_partnership_pair(_status())
        accept = engine.emitted[0]
        envelope = accept["attestation_envelope"]

        assert envelope["dimension"] == "consent:partnership_accept:v1"
        assert envelope["claim"]["half"] == "accept"
        assert envelope["claim"]["owner_key_id"] == OWNER_KEY
        assert envelope["claim"]["stream"] == "partnered"
        assert accept["cohort_scope"] == "self"
        assert accept["attestation_type"] == "scores"

    def test_accept_half_never_carries_the_raw_user_identifier(self, engine):
        emit_partnership_pair(_status())
        assert USER not in json.dumps(engine.emitted[0])

    def test_keyless_user_still_gets_the_accept_half(self, engine):
        emission = emit_partnership_pair(_status())
        assert emission.grant_state == PartnershipGrantState.KEYLESS_USER
        assert "attested_key_id" not in engine.emitted[0]
        assert emission.accept_attestation_id is not None

    def test_user_with_a_key_is_named_and_awaits_their_signature(self, engine):
        emission = emit_partnership_pair(_status(), user_key_id="user-key-1")
        assert emission.grant_state == PartnershipGrantState.AWAITING_USER_SIGNATURE
        assert engine.emitted[0]["attested_key_id"] == "user-key-1"

    def test_unregistered_user_key_falls_back_to_self_attested(self, monkeypatch):
        eng = RecordingEngine(reject_attested=True)
        monkeypatch.setattr(att, "_resolve_engine", lambda: eng)
        monkeypatch.setattr(att, "_resolve_attesting_key_id", lambda: AGENT_KEY)
        emission = emit_partnership_pair(_status(), user_key_id="not-in-federation-keys")
        assert emission.accept_attestation_id is not None
        assert "attested_key_id" not in eng.emitted[0]

    def test_every_stream_change_is_a_new_pair(self, engine):
        first = emit_partnership_pair(_status(ConsentStream.TEMPORARY))
        second = emit_partnership_pair(_status(ConsentStream.PARTNERED))
        assert first.bilateral_pair_id != second.bilateral_pair_id
        assert [e["attestation_envelope"]["claim"]["stream"] for e in engine.emitted] == ["temporary", "partnered"]

    def test_steward_decision_is_named_in_the_accept_half(self, engine):
        emit_partnership_pair(_status(), decided_by="wa-steward", deferral_id="defer_t_1")
        claim = engine.emitted[0]["attestation_envelope"]["claim"]
        assert claim["decided_by"] == "wa-steward"
        assert claim["deferral_id"] == "defer_t_1"

    def test_unclaimed_node_emits_with_no_owner(self, monkeypatch):
        eng = RecordingEngine(owner=None)
        monkeypatch.setattr(att, "_resolve_engine", lambda: eng)
        monkeypatch.setattr(att, "_resolve_attesting_key_id", lambda: AGENT_KEY)
        emit_partnership_pair(_status())
        assert eng.emitted[0]["attestation_envelope"]["claim"]["owner_key_id"] is None

    def test_emit_failure_never_raises(self, monkeypatch):
        broken = Mock()
        broken.attestation_upsert_local.side_effect = RuntimeError("down")
        broken.emit_attestation_self.side_effect = RuntimeError("down")
        broken.owner_of_json.return_value = "null"
        monkeypatch.setattr(att, "_resolve_engine", lambda: broken)
        monkeypatch.setattr(att, "_resolve_attesting_key_id", lambda: AGENT_KEY)
        emission = emit_partnership_pair(_status())
        assert emission.accept_attestation_id is None

    def test_kill_switch_emits_nothing(self, engine, monkeypatch):
        monkeypatch.setenv("CIRIS_CONSENT_CEG_ATTESTATIONS", "false")
        emission = emit_partnership_pair(_status())
        assert engine.local == [] and engine.emitted == []
        assert emission.accept_attestation_id is None

    def test_grant_half_shape_is_authored_by_the_user_key(self):
        grant = build_partnership_grant_input(_status(), "pair-1", "user-key-1", owner_key_id=OWNER_KEY)
        assert grant.attesting_key_id == "user-key-1"
        assert grant.attestation_envelope.dimension == "consent:partnership_grant:v1"
        assert grant.attestation_envelope.claim.bilateral_pair_id == "pair-1"
        assert grant.attestation_envelope.claim.half.value == "grant"


class TestEveryStreamWriteEmits:
    """The accept half is emitted on every stream change and never withheld."""

    @pytest.fixture
    def service(self):
        from ciris_engine.logic.services.governance.consent import ConsentService
        from ciris_engine.logic.services.governance.consent.service import ConsentNotFoundError

        time_service = Mock()
        time_service.now.return_value = datetime(2026, 10, 13, tzinfo=timezone.utc)
        time_service.now_iso.return_value = "2026-10-13T00:00:00+00:00"
        svc = ConsentService(time_service=time_service)

        async def none(*_a, **_k):
            raise ConsentNotFoundError("none")

        svc.get_consent = none  # type: ignore[assignment]
        return svc

    @pytest.mark.parametrize("stream", [ConsentStream.TEMPORARY, ConsentStream.ANONYMOUS])
    @pytest.mark.asyncio
    async def test_grant_consent_emits(self, service, stream):
        from ciris_engine.schemas.consent.core import ConsentRequest

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"), patch(
            "ciris_engine.logic.services.governance.consent.service.emit_partnership_pair"
        ) as emit:
            await service.grant_consent(
                ConsentRequest(user_id=USER, stream=stream, categories=[ConsentCategory.RESEARCH])
            )
        emit.assert_called_once()
        assert emit.call_args.args[0].stream == stream

    @pytest.mark.asyncio
    async def test_update_consent_emits(self, service):
        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"), patch(
            "ciris_engine.logic.services.governance.consent.service.emit_partnership_pair"
        ) as emit:
            await service.update_consent(USER, ConsentStream.ANONYMOUS, [ConsentCategory.RESEARCH])
        emit.assert_called_once()

    @pytest.mark.asyncio
    async def test_deferred_request_emits_nothing(self, service, monkeypatch):
        """Negative: nothing reaches the wire before the steward answers."""
        from ciris_engine.logic.services.governance.consent import service as svc_mod
        from ciris_engine.schemas.consent.core import ConsentRequest

        bus = Mock()

        async def delivered(*_a, **_k):
            return True

        bus.send_deferral = delivered
        service._wise_bus = bus
        monkeypatch.setattr(svc_mod, "find_open_partnership_task", lambda _u: None)
        monkeypatch.setattr("ciris_engine.logic.persistence.models.tasks.add_task", lambda _t: _t.task_id)
        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node") as write, patch(
            "ciris_engine.logic.services.governance.consent.service.emit_partnership_pair"
        ) as emit:
            await service.grant_consent(
                ConsentRequest(user_id=USER, stream=ConsentStream.PARTNERED, categories=[ConsentCategory.INTERACTION])
            )
        emit.assert_not_called()
        write.assert_not_called()


# The real substrate. The engine is a process singleton, so this runs in a
# subprocess (same pattern as test_substrate_consent_contract.py).
_REAL_ENGINE_PROBE = textwrap.dedent(
    """
    import json, os, tempfile
    from datetime import datetime, timezone
    import ciris_server as cs
    from ciris_engine.logic.services.governance.consent import attestation as att
    from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "pair.db")
    for suffix in (".seed", ".pqc"):
        with open(db + suffix, "wb") as fh:
            fh.write(os.urandom(32))
    engine = cs.Engine(
        f"sqlite:///{db}", "pair-key",
        local_key_id="pair-key", local_key_path=db + ".seed",
        local_pqc_key_id="pair-key-pqc", local_pqc_key_path=db + ".pqc",
    )
    key = engine.register_self_federation_key("agent", "pair-key", None, None, None)
    att._resolve_engine = lambda: engine
    att._resolve_attesting_key_id = lambda: key

    now = datetime.now(timezone.utc)
    status = ConsentStatus(
        user_id="google:probe", stream=ConsentStream.PARTNERED,
        categories=[ConsentCategory.INTERACTION], granted_at=now, expires_at=None,
        last_modified=now, impact_score=0.0, attribution_count=0,
    )
    emission = att.emit_partnership_pair(status)
    rows = json.loads(engine.list_attestations_by(key))
    accept = [r for r in rows if r["attestation_id"] == emission.accept_attestation_id]
    print("RESULT:" + json.dumps({"emission": emission.model_dump(mode="json"), "accept": accept, "key": key}))
    """
)


@pytest.mark.timeout(240)
def test_accept_half_is_signed_by_the_agent_key_on_the_real_substrate():
    completed = subprocess.run([sys.executable, "-c", _REAL_ENGINE_PROBE], capture_output=True, text=True, timeout=220)
    assert completed.returncode == 0, f"stdout: {completed.stdout}\nstderr: {completed.stderr}"
    payload = next(
        (line[len("RESULT:") :] for line in completed.stdout.splitlines() if line.startswith("RESULT:")), None
    )
    assert payload is not None, completed.stdout
    result = json.loads(payload)

    emission = result["emission"]
    assert emission["accept_attestation_id"], "the real engine did not write the accept half"
    assert len(result["accept"]) == 1
    row = result["accept"][0]
    # Signed (hybrid) by THIS agent's key - not merely stored.
    assert row["attesting_key_id"] == result["key"]
    assert row["scrub_signature_classical"]
    assert row["scrub_signature_pqc"]
    envelope = row["attestation_envelope"]
    assert envelope["dimension"] == "consent:partnership_accept:v1"
    assert envelope["claim"]["bilateral_pair_id"] == emission["bilateral_pair_id"]
    assert emission["grant_state"] == "keyless_user"
