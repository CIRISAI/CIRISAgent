"""WA deferral resolutions are signed, and verification fails closed (#944).

The `signature` on a resolved deferral used to be
``f"api_{user_id}_{timestamp}"`` — an identifier and a clock reading. It
carried no key material, proved possession of nothing, and was forgeable by
anything able to write the row. Two sibling sites recorded the empty string
under the comment "Would be signed by the WA".

Worse, the signature and the ``signed_at`` it commits to were never written
down at all: ``resolve_deferral`` stored four fields and dropped the rest, so
after-the-fact verification was not merely unwired but impossible.

That record is the human-authority decision governing the agent's most
consequential actions, and under #938 it is the budget-issuance event. So these
tests assert the properties an approval has to have to be evidence rather than
a claim: it verifies, it cannot be lifted onto another deferral or another
verdict, the post-quantum half is real rather than decorative, the owner
binding cannot be asserted at will, and anything unverifiable is refused rather
than assumed good.

These run against the **real** persist substrate — a real Engine with real
Ed25519 and real ML-DSA-65 seeds — not a crypto double. A test that stubs the
signature check cannot tell you the control works.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Iterator

import pytest

from ciris_engine.logic.services.infrastructure.authentication.service import AuthenticationService
from ciris_engine.schemas.services.authority_core import (
    DeferralResponse,
    DeferralVerification,
    deferral_resolution_payload,
    deferral_resolution_record,
    is_unverifiable_legacy_signature,
)

DEFERRAL_ID = "defer_abc123"
SIGNED_AT = "2026-08-01T12:00:00+00:00"
WA_ID = "wa-2026-08-01-ABC123"


def _response(**over: Any) -> DeferralResponse:
    base = dict(approved=True, reason="looks fine", modified_time=None, wa_id=WA_ID, signature="")
    base.update(over)
    return DeferralResponse(**base)  # type: ignore[arg-type]


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Any]:
    """A real persist Engine with both signing seeds, wired as the process engine.

    Mirrors the agent's own bootstrap (`persistence/db/core.py`): 32 raw bytes
    per seed is the whole of persist's LocalSigner interface.
    """
    import ciris_engine.logic.persistence.models.graph as graph_mod
    from ciris_engine.logic.persistence._substrate import Engine, reset_engine  # type: ignore[import-untyped]
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    (tmp_path / "local_signing.seed").write_bytes(os.urandom(32))
    (tmp_path / "local_pqc_signing.seed").write_bytes(os.urandom(32))

    prior_engine, prior_dsn = graph_mod._engine, graph_mod._engine_dsn
    reset_engine()  # persist pins a process singleton; un-pin any prior fixture's
    dsn = f"sqlite:///{tmp_path}/t.db"
    real = Engine(
        dsn,
        "test-key",
        local_key_id="test-key",
        local_key_path=str(tmp_path / "local_signing.seed"),
        local_pqc_key_id="test-key",
        local_pqc_key_path=str(tmp_path / "local_pqc_signing.seed"),
    )
    set_persist_engine(real, dsn=dsn)
    try:
        yield real
    finally:
        graph_mod._engine, graph_mod._engine_dsn = prior_engine, prior_dsn


@pytest.fixture
def auth() -> AuthenticationService:
    """The real service methods. The deferral path uses no service state — it
    goes to the persist engine — so no start()/db is needed to exercise it."""
    return object.__new__(AuthenticationService)


class TestLegacyPlaceholders:
    @pytest.mark.parametrize(
        "sig",
        [
            "",
            "   ",
            "api_admin_2026-07-31T02:32:57+00:00",  # the exact f-string form
            "api_wa-2026-01-01-AAAAAA_2026-08-01T00:00:00Z",
        ],
    )
    def test_recognised_as_unverifiable(self, sig: str) -> None:
        assert is_unverifiable_legacy_signature(sig) is True

    def test_a_real_signature_is_not_mistaken_for_legacy(self) -> None:
        assert is_unverifiable_legacy_signature(base64.b64encode(b"\x01" * 64).decode()) is False


class TestSignAndVerify:
    @pytest.mark.asyncio
    async def test_a_signed_resolution_verifies(self, auth: AuthenticationService, engine: Any) -> None:
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is True

    @pytest.mark.asyncio
    async def test_signing_records_everything_verification_needs(
        self, auth: AuthenticationService, engine: Any
    ) -> None:
        """The #944 defect was that this material existed and was then dropped."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert signed.signed_at == SIGNED_AT
        assert signed.signing_key_id == engine.local_derived_key_id()
        assert signed.signature and signed.signature_pqc

    @pytest.mark.asyncio
    async def test_the_post_quantum_half_is_real(self, auth: AuthenticationService, engine: Any) -> None:
        """ML-DSA-65 is 3309 bytes (FIPS 204 final). A placeholder would not be.

        The maintainer's requirement is a post-quantum signing chain; this is
        the assertion that would fail if the PQC half were decorative.
        """
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert signed.signature_pqc is not None
        assert len(base64.b64decode(signed.signature_pqc)) == 3309
        assert len(base64.b64decode(signed.signature)) == 64  # Ed25519

    @pytest.mark.asyncio
    async def test_signature_is_not_a_rendering_of_the_inputs(self, auth: AuthenticationService, engine: Any) -> None:
        """The old value contained the user id and timestamp verbatim."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert WA_ID not in signed.signature
        assert SIGNED_AT not in signed.signature
        assert not signed.signature.startswith("api_")

    @pytest.mark.asyncio
    async def test_flipping_the_verdict_invalidates(self, auth: AuthenticationService, engine: Any) -> None:
        """The signature commits to the decision, not merely to its existence."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(approved=True), SIGNED_AT)
        signed.approved = False
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_editing_the_guidance_invalidates(self, auth: AuthenticationService, engine: Any) -> None:
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(reason="approved for $5"), SIGNED_AT)
        signed.reason = "approved for $5000"
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_reassigning_the_deciding_authority_invalidates(
        self, auth: AuthenticationService, engine: Any
    ) -> None:
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        signed.wa_id = "wa-2026-08-01-SOMEONE"
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_cannot_be_replayed_onto_another_deferral(self, auth: AuthenticationService, engine: Any) -> None:
        """Why deferral_id is inside the payload."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert await auth.verify_deferral_resolution("defer_other", signed, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_cannot_be_lifted_onto_another_moment(self, auth: AuthenticationService, engine: Any) -> None:
        """Why signed_at is inside the payload."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, "2027-01-01T00:00:00+00:00") is False


class TestVerificationFailsClosed:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sig", ["", "api_admin_2026-07-31T02:32:57+00:00"])
    async def test_legacy_records_are_refused_not_accepted(
        self, auth: AuthenticationService, engine: Any, sig: str
    ) -> None:
        """Readable and clearly unverified — never silently treated as signed."""
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, _response(signature=sig), SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_forged_signature_is_refused(self, auth: AuthenticationService, engine: Any) -> None:
        forged = _response(signature=base64.b64encode(b"\x00" * 64).decode())
        forged.signing_key_id = engine.local_derived_key_id()
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, forged, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_signature_without_an_attributable_key_is_refused(
        self, auth: AuthenticationService, engine: Any
    ) -> None:
        """A signature nobody can attribute to a key is not evidence."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        signed.signing_key_id = None
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_unknown_signing_key_is_refused(self, auth: AuthenticationService, engine: Any) -> None:
        """Neither the local signer nor anything in the federation directory."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        signed.signing_key_id = "agent-nosuchkey"
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_verification_is_refused_when_the_substrate_is_absent(
        self, auth: AuthenticationService, engine: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No substrate means no check — which must read as refusal, not as pass."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", None)
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False


class TestOwnerBinding:
    """The owner's CEG federation identity is the root of authority — what signs
    the delegation letting the agent operate at all. The resolution names it so
    an approval chains there rather than standing on a second, ad-hoc key."""

    @pytest.mark.asyncio
    async def test_owner_is_resolved_from_the_directory_not_asserted(
        self, auth: AuthenticationService, engine: Any
    ) -> None:
        """An unprovisioned node honestly records no owner rather than inventing one."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert signed.owner_key_id == json.loads(engine.owner_of_json(engine.local_derived_key_id()))

    @pytest.mark.asyncio
    async def test_a_claimed_owner_the_directory_does_not_confirm_is_refused(
        self, auth: AuthenticationService, engine: Any
    ) -> None:
        """Without this the owner field is decoration an attacker fills in."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is True
        signed.owner_key_id = "owner-i-made-up"
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False


class TestHybridDowngrade:
    @pytest.mark.asyncio
    async def test_stripping_the_pqc_half_does_not_yield_a_forgery(
        self, auth: AuthenticationService, engine: Any
    ) -> None:
        """Documents the downgrade honestly: dropping the ML-DSA-65 half falls
        back to Ed25519, so it still requires the classical key. It buys an
        attacker nothing today; it is the reason the PQC half is bound to the
        classical one rather than standing alone."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        signed.signature_pqc = None
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is True

        signed.approved = False  # still cannot alter the decision
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False


class TestCrossOccurrenceVerification:
    """#944 residual: a resolution signed by a SIBLING occurrence resolves here
    only through the federation directory (`lookup_public_key`), and the
    directory holds the signer's key only because edge-init calls
    ``engine.register_self_federation_key(...)`` (edge_runtime.py). Without
    that registration, cross-occurrence verification fails CLOSED — correct,
    but it means every multi-occurrence approval reads as unverified. These
    two tests pin both halves: closed without the registration, open with it.
    """

    class _SiblingOccurrenceEngine:
        """The verifying occurrence: same shared persist corpus (all calls
        delegate to the real engine), but a DIFFERENT local signing identity —
        so `_signing_pubkeys`' local fast path misses and the signer must
        resolve from the federation directory, exactly as on a sibling."""

        def __init__(self, real: Any) -> None:
            self._real = real

        def local_derived_key_id(self) -> str:
            return "sibling-occurrence-key"

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    @pytest.mark.asyncio
    async def test_unregistered_signer_fails_closed_on_a_sibling(
        self, auth: AuthenticationService, engine: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No directory row -> the sibling refuses. This is the #944 residual
        shape a deployment is in when edge-init never ran its registration."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", self._SiblingOccurrenceEngine(engine))
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_registered_signer_verifies_on_a_sibling(
        self, auth: AuthenticationService, engine: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """After the edge-init registration (the 5-arg self-registration path,
        same call edge_runtime.py makes at boot), the sibling verifies."""
        signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
        engine.register_self_federation_key("agent", "test-key", None, None, None)

        import ciris_engine.logic.persistence.models.graph as graph_mod

        monkeypatch.setattr(graph_mod, "_engine", self._SiblingOccurrenceEngine(engine))
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is True


class TestCanonicalPayload:
    @pytest.mark.asyncio
    async def test_signer_and_verifier_share_one_definition(
        self, auth: AuthenticationService, engine: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Neither path may build its canonical bytes inline.

        This assertion used to read
        ``payload(id, resp, at) == payload(id, resp, at)`` — the same call
        twice. That is a tautology over a deterministic function: it holds no
        matter how the signer and verifier are written, so it could not fail
        and proved nothing. (SonarCloud python:S5863 flagged it, correctly.)

        The property that actually matters is the one the docstring always
        claimed: ``sign_task``/``verify_task_signature`` each build their dict
        inline and drifted apart silently, and this pair must not.

        So perturb the single shared definition. If BOTH paths route through
        it, they move together and a sign -> verify round-trip still succeeds.
        If either path built its own bytes, they diverge and verification
        fails. The second assertion proves the perturbation was load-bearing
        rather than a no-op — without it, a patch that silently failed to
        apply would still let the first assertion pass.
        """
        original = AuthenticationService._deferral_canonical_bytes

        def perturbed(deferral_id: str, response: DeferralResponse, signed_at: str) -> bytes:
            return b"PERTURBED::" + original(deferral_id, response, signed_at)

        with monkeypatch.context() as mp:
            mp.setattr(AuthenticationService, "_deferral_canonical_bytes", staticmethod(perturbed))
            signed = await auth.sign_deferral_resolution(DEFERRAL_ID, _response(), SIGNED_AT)
            assert (
                await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is True
            ), "signer and verifier disagreed under a shared perturbation — one of them builds its own bytes"

        # Outside the context the real definition is restored. The perturbation
        # must have reached the bytes that were signed: a signature produced
        # under it cannot verify against the real definition.
        assert (
            await auth.verify_deferral_resolution(DEFERRAL_ID, signed, SIGNED_AT) is False
        ), "the perturbation was a no-op, so the assertion above was vacuous"

    def test_payload_commits_to_every_decision_bearing_field(self) -> None:
        payload = deferral_resolution_payload(DEFERRAL_ID, _response(), SIGNED_AT)
        assert set(payload) == {"deferral_id", "approved", "reason", "wa_id", "signed_at"}


class TestStoredRecord:
    """What resolve_deferral writes onto the task context."""

    def test_the_original_four_fields_are_preserved(self) -> None:
        """There is deployed data; existing readers must keep working."""
        record = deferral_resolution_record(_response(), "2026-08-01T13:00:00+00:00", DeferralVerification.UNSIGNED)
        assert record["approved"] is True
        assert record["reason"] == "looks fine"
        assert record["resolved_by"] == WA_ID
        assert record["resolved_at"] == "2026-08-01T13:00:00+00:00"

    def test_the_verification_material_survives(self) -> None:
        """The #944 defect exactly: these were built and then thrown away."""
        resp = _response(signature="c2ln")
        resp.signed_at = SIGNED_AT
        resp.signature_pqc = "cHFj"
        resp.signing_key_id = "agent-abc"
        resp.owner_key_id = "owner-xyz"
        record = deferral_resolution_record(resp, "2026-08-01T13:00:00+00:00", DeferralVerification.VERIFIED)
        assert record["signature"] == "c2ln"
        assert record["signed_at"] == SIGNED_AT
        assert record["signature_pqc"] == "cHFj"
        assert record["signing_key_id"] == "agent-abc"
        assert record["owner_key_id"] == "owner-xyz"
        assert record["verification"] == "verified"

    def test_unsigned_and_failed_are_distinguishable(self) -> None:
        """A migration gap and an attack must never render identically."""
        assert DeferralVerification.UNSIGNED.value != DeferralVerification.FAILED.value
        assert DeferralVerification.UNSIGNED.value != DeferralVerification.VERIFIED.value
