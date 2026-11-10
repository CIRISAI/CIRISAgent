"""regen_accord_manifest.py --sign-hybrid: A1 signs on this machine through ciris-server.

The keys never reach Python, so these tests drive the wrapper with a fake
signer binary. What they hold: only the frozen manifest's own bytes, signed as
A1, get attached; the agent's startup check must accept them; and every failure
puts the previous manifest back, so the tree never fails to boot.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FROZEN = b'{"files":{},"signed_at":"2026-11-09T00:00:00Z"}\n'
OLD = b'{"files":{},"old":true}\n'
ED = base64.b64encode(b"e" * 64).decode()
PQC = base64.b64encode(b"p" * 3309).decode()


@pytest.fixture
def tool(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("regen_accord_manifest", ROOT / "tools/dev/regen_accord_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    manifest = tmp_path / "accord_manifest.json"
    manifest.write_bytes(OLD)
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    monkeypatch.setattr(mod, "HYBRID", manifest.with_name("accord_manifest.hybrid.json"))
    monkeypatch.setattr(mod, "build", lambda: FROZEN)
    monkeypatch.setattr(mod, "verify_in_scratch_home", lambda: 0)
    return mod


def _signer(tmp_path: Path, *, exit_code: int = 0, key_id: str = "", digest_of_input: bool = True) -> Path:
    script = tmp_path / "fake-ciris-server"
    script.write_text(
        f"""#!{sys.executable}
import hashlib, json, sys
args = sys.argv[1:]
assert args[:3] == ["accord", "sign-bytes", "--key-id"] and args[3] in ("A1", "B1", "C1"), args
data = open(args[args.index("--in") + 1], "rb").read()
digest = hashlib.sha256(data).hexdigest() if {digest_of_input!r} else "0" * 64
if {exit_code}:
    sys.exit({exit_code})
print(json.dumps({{"key_id": {key_id!r} or args[3], "sha256": digest,
                   "ed25519_signature_base64": {ED!r}, "mldsa65_signature_base64": {PQC!r}}}))
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _run(tool, monkeypatch, signer: Path, tmp_path: Path, *extra: str) -> int:
    monkeypatch.setattr(sys, "argv", ["x", "--sign-hybrid", "--server-bin", str(signer), "--usb", str(tmp_path), *extra])
    return tool.main()


def test_signed_frozen_bytes_are_attached(tool, monkeypatch, tmp_path):
    assert _run(tool, monkeypatch, _signer(tmp_path), tmp_path) == 0
    assert tool.MANIFEST.read_bytes() == FROZEN
    doc = json.loads(tool.HYBRID.read_text())
    assert doc == {
        "signer_key_id": "A1",
        "domain": "ciris.accord_manifest.v1",
        "manifest_sha256": hashlib.sha256(FROZEN).hexdigest(),
        "manifest_size": len(FROZEN),
        "ed25519_sig": ED,
        "ml_dsa_65_sig": PQC,
    }


@pytest.mark.parametrize(
    "kwargs",
    [{"exit_code": 3}, {"key_id": "B1"}, {"digest_of_input": False}],
    ids=["signer-fails", "wrong-signer", "other-bytes"],
)
def test_a_refused_signature_restores_the_previous_manifest(tool, monkeypatch, tmp_path, kwargs):
    assert _run(tool, monkeypatch, _signer(tmp_path, **kwargs), tmp_path) == 1
    assert tool.MANIFEST.read_bytes() == OLD
    assert not tool.HYBRID.exists()


def test_startup_check_refusal_restores_and_removes_the_signature(tool, monkeypatch, tmp_path):
    monkeypatch.setattr(tool, "verify_in_scratch_home", lambda: 1)
    assert _run(tool, monkeypatch, _signer(tmp_path), tmp_path) == 1
    assert tool.MANIFEST.read_bytes() == OLD
    assert not tool.HYBRID.exists()


def test_a_previous_hybrid_signature_comes_back_on_failure(tool, monkeypatch, tmp_path):
    tool.HYBRID.write_text('{"prior": true}\n')
    assert _run(tool, monkeypatch, _signer(tmp_path, exit_code=1), tmp_path) == 1
    assert tool.HYBRID.read_text() == '{"prior": true}\n'


def test_the_signer_is_handed_32_bytes_not_the_manifest(tool, monkeypatch, tmp_path):
    """The token's EdDSA refuses multi-KB inputs: A1 signs sha256(JCS(statement)) (CC 3.1.2 form)."""
    from ciris_adapters.ciris_verify.ffi_bindings import jcs_canonicalize

    seen = tmp_path / "seen"
    signer = _signer(tmp_path)
    signer.write_text(signer.read_text().replace(
        'data = open(args[args.index("--in") + 1], "rb").read()',
        f'data = open(args[args.index("--in") + 1], "rb").read(); open({str(seen)!r}, "wb").write(data)'))
    assert _run(tool, monkeypatch, signer, tmp_path) == 0
    statement = {
        "domain": "ciris.accord_manifest.v1",
        "manifest_sha256": hashlib.sha256(FROZEN).hexdigest(),
        "manifest_size": len(FROZEN),
        "signer_identity": "A1",
    }
    assert seen.read_bytes() == hashlib.sha256(jcs_canonicalize(statement)).digest()


def test_missing_arguments_change_nothing(tool, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["x", "--sign-hybrid"])
    assert tool.main() == 1
    assert tool.MANIFEST.read_bytes() == OLD


def test_another_holder_can_sign_with_key_id(tool, monkeypatch, tmp_path):
    assert _run(tool, monkeypatch, _signer(tmp_path), tmp_path, "--key-id", "B1") == 0
    assert json.loads(tool.HYBRID.read_text())["signer_key_id"] == "B1"


def test_a_non_holder_key_id_is_refused_before_the_token(tool, monkeypatch, tmp_path):
    assert _run(tool, monkeypatch, _signer(tmp_path), tmp_path, "--key-id", "wa-ROOT-00") == 1
    assert tool.MANIFEST.read_bytes() == OLD
