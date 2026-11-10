"""Emergency shutdown: works only with a valid hybrid signature from the seated WA (Eric, 2026-11-08).

Accord holders (A1/B1/C1) are refused: their emergency act is the accord halt.
"""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from ciris_engine.logic.adapters.api.routes import emergency
from ciris_engine.schemas.services.shutdown import WASignedCommand

OWNER = "owner-fedid-1"
NOW = datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc)


class _Engine:
    def __init__(self, records, owner=OWNER):
        self.records, self.owner = records, owner

    def local_derived_key_id(self):
        return "node-key"

    def owner_of_json(self, key_id):
        return json.dumps(self.owner)  # the substrate's owner_of_json: a JSON string, or null

    def lookup_public_key(self, key_id):
        rec = self.records.get(key_id)
        return json.dumps(rec) if rec else None

    def verify_hybrid(self, msg, ed_b64, pqc_b64, ed_pub, pqc_pub, policy):
        assert policy == "strict"
        ed = base64.b64decode(ed_b64)
        if ed != b"ed:" + ed_pub.encode() + msg[:16] or base64.b64decode(pqc_b64) != b"pqc:" + msg + ed:
            raise ValueError("bad signature")


def _rec(identity_type="user", pqc=True):
    r = {"pubkey_ed25519_base64": "ZWQ=", "identity_type": identity_type}
    if pqc:
        r["pubkey_ml_dsa_65_base64"] = "cHFj"
    return r


def _signed(signer=OWNER, issued=NOW, **over):
    cmd = WASignedCommand(
        command_id="c1", command_type="SHUTDOWN_NOW", signer_key_id=signer, issued_at=issued,
        reason="test", signature="", signature_pqc="",
    )
    msg = emergency.canonical_command_bytes(cmd)
    ed = b"ed:" + b"ZWQ=" + msg[:16]
    cmd = cmd.model_copy(update={"signature": base64.b64encode(ed).decode(),
                                 "signature_pqc": base64.b64encode(b"pqc:" + msg + ed).decode()})
    return cmd.model_copy(update=over)


def _owner_engine(owner_key, owner_rec=None):
    return _Engine({owner_key: owner_rec or _rec()}, owner=owner_key)


def test_the_seated_wa_with_a_valid_hybrid_signature_is_accepted() -> None:
    emergency.verify_command(_owner_engine(OWNER), _signed(), now=NOW)


def test_a_missing_pqc_half_is_refused() -> None:
    with pytest.raises(emergency.EmergencyRefused, match="Invalid signature"):
        emergency.verify_command(_owner_engine(OWNER), _signed(signature_pqc=""), now=NOW)


def test_a_changed_reason_is_refused() -> None:
    with pytest.raises(emergency.EmergencyRefused, match="Invalid signature"):
        emergency.verify_command(_owner_engine(OWNER), _signed(reason="other"), now=NOW)


def test_a_signer_without_an_ml_dsa_key_is_refused() -> None:
    with pytest.raises(emergency.EmergencyRefused, match="ML-DSA-65"):
        emergency.verify_command(_owner_engine(OWNER, _rec(pqc=False)), _signed(), now=NOW)


def test_a_valid_signature_from_someone_other_than_the_seated_wa_is_refused() -> None:
    eng = _Engine({OWNER: _rec(), "stranger": _rec()}, owner=OWNER)
    with pytest.raises(emergency.EmergencyRefused, match="seated Wise Authority"):
        emergency.verify_command(eng, _signed(signer="stranger"), now=NOW)


def test_an_unowned_node_accepts_no_one() -> None:
    eng = _Engine({OWNER: _rec()}, owner=None)
    with pytest.raises(emergency.EmergencyRefused, match="seated Wise Authority"):
        emergency.verify_command(eng, _signed(), now=NOW)


@pytest.mark.parametrize("holder", ["A1", "B1", "C1"])
def test_accord_holders_are_sent_to_the_halt(holder: str) -> None:
    eng = _Engine({holder: _rec("accord_holder")}, owner=holder)
    with pytest.raises(emergency.EmergencyRefused, match="accord halt"):
        emergency.verify_command(eng, _signed(signer=holder), now=NOW)


def test_an_accord_holder_record_under_another_name_is_sent_to_the_halt() -> None:
    eng = _Engine({OWNER: _rec("accord_holder")}, owner=OWNER)
    with pytest.raises(emergency.EmergencyRefused, match="accord halt"):
        emergency.verify_command(eng, _signed(), now=NOW)


def test_a_stale_command_is_refused() -> None:
    with pytest.raises(emergency.EmergencyRefused, match="5-minute"):
        emergency.verify_command(_owner_engine(OWNER), _signed(issued=NOW - timedelta(minutes=6)), now=NOW)
