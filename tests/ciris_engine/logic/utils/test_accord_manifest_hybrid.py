"""The accord manifest's A1 hybrid signature, checked once the engine is up (Eric 2026-11-08, via CC)."""

import base64
import json
import shutil

import pytest

from ciris_engine.logic.utils import constants
from ciris_engine.logic.utils.accord_manifest_hybrid import verify_accord_manifest_hybrid


class _Engine:
    """Strict bound hybrid: ed over msg, pqc 'signature' = b"pqc:" + msg + ed_sig."""

    def __init__(self, record):
        self.record = record

    def lookup_public_key(self, key_id):
        return json.dumps(self.record) if self.record and key_id == "A1" else None

    def verify_hybrid(self, msg, ed_b64, pqc_b64, ed_pub, pqc_pub, policy):
        assert policy == "strict"
        ed = base64.b64decode(ed_b64)
        if ed != b"ed:" + msg[:8] or base64.b64decode(pqc_b64) != b"pqc:" + msg + ed:
            raise ValueError("bad signature")


A1 = {"pubkey_ed25519_base64": "ZWQ=", "pubkey_ml_dsa_65_base64": "cHFj"}


def _seed(tmp_path, signer="A1", tamper=False):
    for f in constants.ACCORD_SEED_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    msg = (tmp_path / "accord_manifest.json").read_bytes()
    ed = b"ed:" + msg[:8]
    pqc = b"pqc:" + msg + ed
    doc = {"signer_key_id": signer, "ed25519_sig": base64.b64encode(ed).decode(), "ml_dsa_65_sig": base64.b64encode(pqc).decode()}
    (tmp_path / "accord_manifest.hybrid.json").write_text(json.dumps(doc))
    if tamper:
        (tmp_path / "accord_manifest.json").write_bytes(msg + b" ")
    return tmp_path


def test_none_shipped_yet_is_not_a_failure() -> None:
    assert verify_accord_manifest_hybrid(_Engine(A1)) is False


def test_an_a1_hybrid_signature_verifies(tmp_path) -> None:
    assert verify_accord_manifest_hybrid(_Engine(A1), _seed(tmp_path)) is True


def test_a_changed_manifest_stops_startup(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="HYBRID MANIFEST SIGNATURE FAILED"):
        verify_accord_manifest_hybrid(_Engine(A1), _seed(tmp_path, tamper=True))


def test_a_signer_outside_the_pinned_set_stops_startup(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="not a pinned"):
        verify_accord_manifest_hybrid(_Engine(A1), _seed(tmp_path, signer="B9"))


def test_a1_without_its_ml_dsa_half_stops_startup(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="no ML-DSA-65 half"):
        verify_accord_manifest_hybrid(_Engine({"pubkey_ed25519_base64": "ZWQ="}), _seed(tmp_path))
