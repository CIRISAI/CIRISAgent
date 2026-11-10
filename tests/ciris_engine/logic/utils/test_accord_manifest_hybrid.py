"""The accord manifest's A1 hybrid signature, checked once the engine is up (Eric 2026-11-08, via CC)."""

import base64
import hashlib
import json
import shutil

import pytest

from ciris_engine.logic.utils import constants
from ciris_engine.logic.utils.accord_manifest_hybrid import (
    ACCORD_MANIFEST_DOMAIN,
    accord_manifest_signed_bytes,
    accord_manifest_statement,
    verify_accord_manifest_hybrid,
)


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


def _seed(tmp_path, signer="A1", tamper=False, signed_as=None, domain=ACCORD_MANIFEST_DOMAIN, raw_file=False):
    for f in constants.ACCORD_SEED_DIR.iterdir():
        shutil.copy(f, tmp_path / f.name)
    manifest = (tmp_path / "accord_manifest.json").read_bytes()
    msg = manifest if raw_file else accord_manifest_signed_bytes(manifest, signed_as or signer)
    ed = b"ed:" + msg[:8]
    pqc = b"pqc:" + msg + ed
    doc = {
        "signer_key_id": signer,
        "domain": domain,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "manifest_size": len(manifest),
        "ed25519_sig": base64.b64encode(ed).decode(),
        "ml_dsa_65_sig": base64.b64encode(pqc).decode(),
    }
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


def test_a1_signs_a_short_digest_statement_not_the_file(tmp_path) -> None:
    """The YubiKey's EdDSA refuses multi-KB inputs (CIRISVerify#113): the statement stays small."""
    from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize

    manifest = (constants.ACCORD_SEED_DIR / "accord_manifest.json").read_bytes()
    statement = accord_manifest_statement(manifest, "A1")
    assert statement == {
        "domain": ACCORD_MANIFEST_DOMAIN,
        "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
        "manifest_size": len(manifest),
        "signer_identity": "A1",
    }
    # CC 3.1.2 form: the signed bytes are sha256(JCS(statement)), 32 bytes.
    assert accord_manifest_signed_bytes(manifest, "A1") == hashlib.sha256(jcs_canonicalize(statement)).digest()


def test_a_signature_over_the_raw_file_is_refused(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="HYBRID MANIFEST SIGNATURE FAILED"):
        verify_accord_manifest_hybrid(_Engine(A1), _seed(tmp_path, raw_file=True))


def test_a_statement_naming_another_holder_is_refused(tmp_path) -> None:
    """signer_identity is inside the signed bytes: a B1 statement can't be passed off as A1's."""
    with pytest.raises(RuntimeError, match="HYBRID MANIFEST SIGNATURE FAILED"):
        verify_accord_manifest_hybrid(_Engine(A1), _seed(tmp_path, signed_as="B1"))


def test_a_different_domain_is_refused(tmp_path) -> None:
    with pytest.raises(RuntimeError, match="names domain"):
        verify_accord_manifest_hybrid(_Engine(A1), _seed(tmp_path, domain="ciris.locale_manifest.v2"))


def test_a_manifest_of_a_different_size_is_refused_before_hashing(tmp_path) -> None:
    seed = _seed(tmp_path)
    doc = json.loads((seed / "accord_manifest.hybrid.json").read_text())
    doc["manifest_size"] += 1
    (seed / "accord_manifest.hybrid.json").write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="signed for"):
        verify_accord_manifest_hybrid(_Engine(A1), seed)
