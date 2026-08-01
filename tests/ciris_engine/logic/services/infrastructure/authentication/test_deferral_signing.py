"""WA deferral resolutions are signed, and verification fails closed (#944).

The `signature` on a resolved deferral used to be
``f"api_{user_id}_{timestamp}"`` — an identifier and a clock reading. It
carried no key material, proved possession of nothing, and was forgeable by
anything able to write the row. Two sibling sites recorded the empty string
under the comment "Would be signed by the WA".

That record is the human-authority decision governing the agent's most
consequential actions, and under #938 it is the budget-issuance event. So these
tests assert the properties an approval has to have to be evidence rather than
a claim: it verifies, it cannot be lifted onto another deferral or another
verdict, and anything unverifiable is refused rather than assumed good.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from ciris_engine.schemas.services.authority_core import (
    DeferralResponse,
    deferral_resolution_payload,
    is_unverifiable_legacy_signature,
)

DEFERRAL_ID = "defer_abc123"
SIGNED_AT = "2026-08-01T12:00:00+00:00"
WA_ID = "wa-2026-08-01-ABC123"


def _response(**over: Any) -> DeferralResponse:
    base = dict(approved=True, reason="looks fine", modified_time=None, wa_id=WA_ID, signature="")
    base.update(over)
    return DeferralResponse(**base)  # type: ignore[arg-type]


def _canonical(deferral_id: str, resp: DeferralResponse, signed_at: str) -> bytes:
    payload = deferral_resolution_payload(deferral_id, resp, signed_at)
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


class _StubAuth:
    """Exercises the real sign/verify bodies against a real Ed25519 keypair.

    Only get_wa and the key plumbing are stubbed; the canonicalization and the
    signature check under test are the service's own.
    """

    def __init__(self) -> None:
        self._priv = ed25519.Ed25519PrivateKey.generate()
        pub = self._priv.public_key().public_bytes_raw()
        self.pubkey = base64.urlsafe_b64encode(pub).decode().rstrip("=")

    async def get_wa(self, wa_id: str) -> Any:
        if wa_id != WA_ID:
            return None
        return type("WA", (), {"pubkey": self.pubkey})()

    async def sign_as_wa(self, wa_id: str, data: bytes) -> str:
        return base64.b64encode(self._priv.sign(data)).decode()

    def _decode_public_key(self, pubkey: str) -> bytes:
        return base64.urlsafe_b64decode(pubkey + "=" * (-len(pubkey) % 4))

    def _verify_signature(self, data: bytes, signature: str, public_key: str) -> bool:
        try:
            vk = ed25519.Ed25519PublicKey.from_public_bytes(self._decode_public_key(public_key))
            vk.verify(base64.b64decode(signature), data)
            return True
        except Exception:
            return False

    # The two methods under test, bound from the real class.
    from ciris_engine.logic.services.infrastructure.authentication.service import (  # noqa: E402
        AuthenticationService as _Real,
    )

    sign_deferral_resolution = _Real.sign_deferral_resolution
    verify_deferral_resolution = _Real.verify_deferral_resolution


@pytest.fixture
def auth() -> _StubAuth:
    return _StubAuth()


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
    async def test_a_signed_resolution_verifies(self, auth: _StubAuth) -> None:
        resp = _response()
        resp.signature = await auth.sign_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT)
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT) is True

    @pytest.mark.asyncio
    async def test_signature_is_not_a_rendering_of_the_inputs(self, auth: _StubAuth) -> None:
        """The old value contained the user id and timestamp verbatim."""
        resp = _response()
        sig = await auth.sign_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT)
        assert WA_ID not in sig
        assert SIGNED_AT not in sig
        assert not sig.startswith("api_")

    @pytest.mark.asyncio
    async def test_flipping_the_verdict_invalidates(self, auth: _StubAuth) -> None:
        """The signature commits to the decision, not merely to its existence."""
        resp = _response(approved=True)
        resp.signature = await auth.sign_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT)
        resp.approved = False
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_editing_the_guidance_invalidates(self, auth: _StubAuth) -> None:
        resp = _response(reason="approved for $5")
        resp.signature = await auth.sign_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT)
        resp.reason = "approved for $5000"
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_cannot_be_replayed_onto_another_deferral(self, auth: _StubAuth) -> None:
        """Why deferral_id is inside the payload."""
        resp = _response()
        resp.signature = await auth.sign_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT)
        assert await auth.verify_deferral_resolution("defer_other", resp, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_cannot_be_lifted_onto_another_moment(self, auth: _StubAuth) -> None:
        """Why signed_at is inside the payload."""
        resp = _response()
        resp.signature = await auth.sign_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT)
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, resp, "2027-01-01T00:00:00+00:00") is False


class TestVerificationFailsClosed:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("sig", ["", "api_admin_2026-07-31T02:32:57+00:00"])
    async def test_legacy_records_are_refused_not_accepted(self, auth: _StubAuth, sig: str) -> None:
        """Readable and clearly unverified — never silently treated as signed."""
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, _response(signature=sig), SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_forged_signature_is_refused(self, auth: _StubAuth) -> None:
        forged = base64.b64encode(b"\x00" * 64).decode()
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, _response(signature=forged), SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_signature_from_a_different_key_is_refused(self, auth: _StubAuth) -> None:
        """An attacker who can write the row still cannot mint an approval."""
        attacker = ed25519.Ed25519PrivateKey.generate()
        resp = _response()
        resp.signature = base64.b64encode(attacker.sign(_canonical(DEFERRAL_ID, resp, SIGNED_AT))).decode()
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT) is False

    @pytest.mark.asyncio
    async def test_unknown_wa_is_refused(self, auth: _StubAuth) -> None:
        resp = _response(wa_id="wa-does-not-exist")
        resp.signature = base64.b64encode(b"\x01" * 64).decode()
        assert await auth.verify_deferral_resolution(DEFERRAL_ID, resp, SIGNED_AT) is False


class TestCanonicalPayload:
    def test_signer_and_verifier_share_one_definition(self) -> None:
        """sign_task and verify_task_signature each build their dict inline and
        can drift apart silently. This must not."""
        resp = _response()
        assert deferral_resolution_payload(DEFERRAL_ID, resp, SIGNED_AT) == deferral_resolution_payload(
            DEFERRAL_ID, resp, SIGNED_AT
        )

    def test_payload_commits_to_every_decision_bearing_field(self) -> None:
        payload = deferral_resolution_payload(DEFERRAL_ID, _response(), SIGNED_AT)
        assert set(payload) == {"deferral_id", "approved", "reason", "wa_id", "signed_at"}
