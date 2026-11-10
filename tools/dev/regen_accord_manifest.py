"""Rebuild seed/accord_manifest.json from disk and re-sign it with the root key.

WHAT THE MANIFEST IS FOR. `ETHICS_TEXT_EXPECTED_HASHES` in constants.py is a
fail-safe against a file changing under us; the manifest is the *signed*
record of what those hashes were when a Wise Authority last vouched for
them. A hash pin an attacker can edit is a pin an attacker can move, so the
manifest closes that loop (H11/M1) -- and it only closes it for files it
actually names.

It named four: the polyglot pair and two guides under names that do not
exist on disk any more (`CIRIS_COMPREHENSIVE_GUIDE.md`; the guides moved to
`localized/*.txt` in 2.8.5). The 29 localized accord texts -- the ones the
action-selection DMAs actually put in front of the model -- were covered by
nothing. This regenerates all of it from the files that ship.

The signature is raw Ed25519 over the manifest's EXACT BYTES
(constants.py `_verify_accord_manifest_signature`), so the JSON is written
LF-only with a trailing newline and signed exactly as written. Every file
named here must also be byte-exact in .gitattributes, or a Windows checkout
CRLFs it and the hash check fails -- `tests/logic/utils/
test_accord_manifest_line_endings.py` holds that line.

    python3 tools/dev/regen_accord_manifest.py [--check]

--check verifies the on-disk manifest and signature without writing.

A1 (the accord holder) signs on the holder's own machine, keys never leaving
the YubiKey and the USB drive:

    python3 tools/dev/regen_accord_manifest.py --sign-hybrid \
        --server-bin <ciris-server> --usb <A1 usb dir> [--module <ykcs11.so>]
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
# Import this checkout's ciris_engine, never an installed copy: the startup
# check and the statement it signs must be the ones this tree ships.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "ciris_engine" / "data"
LOCALIZED = DATA / "localized"
MANIFEST = DATA / "seed" / "accord_manifest.json"
SIG = MANIFEST.with_suffix(".sig")


def manifest_files() -> dict[str, Path]:
    """Everything the agent loads as canon, in a stable order."""
    # Every edition in constants.CORPUS_EDITIONS -- the served 1.3 and the 1.2b
    # research control -- by the same source read the pin tool uses.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    # A sibling script, not a package module: resolvable only via the sys.path entry above.
    from regen_accord_pins import pinned_files  # type: ignore[import-not-found]

    files: dict[str, Path] = dict(pinned_files((ROOT / "ciris_engine/logic/utils/constants.py").read_text("utf-8")))
    for name in ("CIRIS_COMPREHENSIVE_GUIDE.txt", "CIRIS_COMPREHENSIVE_GUIDE_MOBILE.txt"):
        p = LOCALIZED / name
        if p.exists():
            files[name] = p
    missing = [n for n, p in files.items() if not p.exists()]
    if missing:
        raise SystemExit(f"cannot manifest files that do not exist: {missing}")
    return files


def build() -> bytes:
    prev = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
    doc = {
        # The served edition (constants.DEFAULT_CORPUS_EDITION).
        "version": "1.3",
        "files": {name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for name, p in manifest_files().items()},
        "signed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "signer": prev.get("signer", "wa-ROOT-00"),
    }
    return (json.dumps(doc, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def check() -> int:
    if not MANIFEST.exists() or not SIG.exists():
        print("manifest or signature missing")
        return 1
    doc = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = []
    on_disk = manifest_files()
    # Coverage, not just consistency: a served file the manifest does not name
    # is a file nobody has vouched for (the 1.3 edition until its first re-sign).
    for name in sorted(set(on_disk) - set(doc["files"])):
        bad.append(f"{name}: on disk and pinned, but not named by the manifest")
    for name, rec in doc["files"].items():
        p = on_disk.get(name)
        if p is None:
            bad.append(f"{name}: named by the manifest but not on disk")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != rec["sha256"]:
            bad.append(f"{name}: hash differs from the manifest")
    if HYBRID.exists():
        # A1's bound hybrid signature supersedes the WA-root one. Its ML-DSA-65
        # half is verified by the agent at startup, against A1's federation
        # directory record (accord_manifest_hybrid.py); here, the file only.
        for b in bad:
            print(f"  {b}")
        if not bad:
            print(f"hashes ok over {len(doc['files'])} files; A1 hybrid signature present (verified at agent startup)")
        return 1 if bad else 0
    # Verify with `cryptography`, the same library the agent's own startup check
    # uses (logic/utils/constants.py), not PyNaCl. PyNaCl is only needed to SIGN
    # -- which happens on a key holder's machine -- and requiring it to *check*
    # made this guard fail in CI with ModuleNotFoundError, reported as "manifest
    # is stale or unsigned". A verification path that cannot run is not a check.
    import base64

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        # "Cannot verify" and "does not verify" are different claims, and this
        # said the second when it meant the first: a missing module was reported
        # as "manifest is stale or unsigned", which reads as tampering. Say what
        # is true and exit distinctly (2), so a caller can tell them apart.
        print("  cannot verify: `cryptography` is not installed (this is not a verdict on the signature)")
        return 2

    pub = json.loads((DATA / "seed" / "root_pub.json").read_text(encoding="utf-8"))["pubkey"]
    raw = base64.urlsafe_b64decode(pub + "=" * (-len(pub) % 4))
    try:
        Ed25519PublicKey.from_public_bytes(raw).verify(SIG.read_bytes(), MANIFEST.read_bytes())
        print(f"signature ok over {len(doc['files'])} files")
    except InvalidSignature:
        bad.append("signature does NOT verify against seed/root_pub.json")
    for b in bad:
        print(f"  {b}")
    return 1 if bad else 0


HYBRID = MANIFEST.with_name("accord_manifest.hybrid.json")


def prepare_hybrid(out_dir: pathlib.Path) -> int:
    """Write what A1 signs, for the ceremony device (A1 never sits on a build machine).

    Bound hybrid form (CC 5.3.2.4.3.1): Ed25519 over the manifest bytes, then
    ML-DSA-65 over the manifest bytes followed by that Ed25519 signature.
    """
    # Freeze the bytes A1 will sign: build once, write, and never rebuild
    # before --attach-hybrid (build() stamps signed_at). A stale hybrid file
    # would not cover these bytes, so it goes.
    MANIFEST.write_bytes(build())
    if HYBRID.exists():
        HYBRID.unlink()
    from ciris_engine.logic.utils.accord_manifest_hybrid import accord_manifest_signed_bytes

    out_dir.mkdir(parents=True, exist_ok=True)
    signed = accord_manifest_signed_bytes(MANIFEST.read_bytes(), "A1")
    (out_dir / "accord_manifest.signed.bin").write_bytes(signed)
    print(f"wrote {out_dir / 'accord_manifest.signed.bin'} (32 bytes: sha256 of the JCS statement, {signed.hex()})")
    print("sign it with A1: ed25519 over these bytes; ml-dsa-65 over these bytes || the ed25519 signature")
    print("then: regen_accord_manifest.py --attach-hybrid <ed25519_b64> <ml_dsa_65_b64>")
    return 0


def attach_hybrid(ed_b64: str, pqc_b64: str, signer: str = "A1") -> int:
    """Write the ceremony's two halves beside the manifest; the agent verifies them strict at startup."""
    for name, val in (("ed25519", ed_b64), ("ml-dsa-65", pqc_b64)):
        try:
            base64.b64decode(val, validate=True)
        except ValueError:
            print(f"FAIL: the {name} half is not base64")
            return 1
    from ciris_engine.logic.utils.accord_manifest_hybrid import accord_manifest_statement

    statement = accord_manifest_statement(MANIFEST.read_bytes(), signer)
    doc = {
        "signer_key_id": signer,
        "domain": statement["domain"],
        "manifest_sha256": statement["manifest_sha256"],
        "manifest_size": statement["manifest_size"],
        "ed25519_sig": ed_b64,
        "ml_dsa_65_sig": pqc_b64,
    }
    HYBRID.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {HYBRID}; the agent verifies it against {signer}'s directory record when the engine starts")
    return 0


#: The startup check, run in a scratch home: the real engine resolves A1 and
#: verifies the hybrid signature exactly as every agent will at boot.
_SCRATCH_VERIFY = (
    "from ciris_engine.logic.persistence.db.core import initialize_database\n"
    "from ciris_engine.logic.persistence.models import graph as g\n"
    "from ciris_engine.logic.utils.accord_manifest_hybrid import verify_accord_manifest_hybrid\n"
    "import os\n"
    "initialize_database(db_path=os.environ['CIRIS_DB_PATH'])\n"
    "assert verify_accord_manifest_hybrid(g.get_persist_engine()) is True\n"
    "print('A1_HYBRID_VERIFIED')\n"
)

#: Every data-path key the agent resolves, pinned to the scratch home so the
#: check can never open the operator's live install (~/ciris/.env wins otherwise).
_DATA_PATH_KEYS = {
    "CIRIS_HOME": "",
    "CIRIS_DATA_DIR": "data",
    "CIRIS_DB_PATH": "data/ciris_engine.db",
    "SECRETS_DB_PATH": "data/secrets.db",
    "CIRIS_SECRETS_DB_PATH": "data/secrets.db",
    "AUDIT_LOG_PATH": "data/audit.jsonl",
    "CIRIS_AUDIT_DB_PATH": "data/audit.db",
    "CIRIS_LOG_DIR": "logs",
}


def verify_in_scratch_home() -> int:
    """Boot the engine in a throwaway home and run the startup hybrid check."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory(prefix="accord-a1-verify-") as home:
        env = dict(os.environ)
        for key, rel in _DATA_PATH_KEYS.items():
            env[key] = str(pathlib.Path(home) / rel) if rel else home
        env["CIRIS_FORCE_FIRST_RUN"] = "1"
        (pathlib.Path(home) / "data").mkdir()
        (pathlib.Path(home) / "logs").mkdir()
        proc = subprocess.run(
            [sys.executable, "-c", _SCRATCH_VERIFY], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300
        )
        db_in_scratch = (pathlib.Path(home) / "data" / "ciris_engine.db").exists()
        ok = proc.returncode == 0 and "A1_HYBRID_VERIFIED" in proc.stdout and db_in_scratch
        if not ok:
            print("FAIL: the startup check did not verify A1's signature in a scratch home")
            if not db_in_scratch:
                print("  (the engine did not open its database under the scratch home)")
            print("\n".join(proc.stderr.strip().splitlines()[-15:]))
            return 1
    print("verified: the agent's startup check resolves A1 and accepts both halves")
    return 0


def _opt(name: str) -> Optional[str]:
    if name in sys.argv:
        i = sys.argv.index(name)
        if len(sys.argv) > i + 1:
            return sys.argv[i + 1]
    return None


def sign_hybrid() -> int:
    """Sign the manifest with A1 on this machine, through ciris-server's sign-bytes verb.

    The keys never pass through Python: the server binary opens A1's Ed25519
    half on the YubiKey (PKCS#11) and unwraps the ML-DSA-65 half from the USB
    drive in memory, signs bound hybrid and self-verifies. This side freezes
    the bytes, has A1 sign a short statement of their digest, checks the returned digest, attaches, then re-runs the agent's
    own startup check in a scratch home. Any failure puts the previous
    manifest back, so the tree is never left in a state that fails to boot.
    """
    import subprocess

    server_bin, usb = _opt("--server-bin"), _opt("--usb")
    if not server_bin or not usb:
        print("usage: regen_accord_manifest.py --sign-hybrid --server-bin <ciris-server> --usb <dir> [--module <ykcs11.so>]")
        return 1
    prior_manifest = MANIFEST.read_bytes()
    prior_hybrid = HYBRID.read_bytes() if HYBRID.exists() else None

    def restore(why: str) -> int:
        MANIFEST.write_bytes(prior_manifest)
        if prior_hybrid is None:
            HYBRID.unlink(missing_ok=True)
        else:
            HYBRID.write_bytes(prior_hybrid)
        print(f"FAIL: {why}; the previous manifest is restored")
        return 1

    import tempfile

    from ciris_engine.logic.utils.accord_manifest_hybrid import accord_manifest_signed_bytes, accord_manifest_statement

    body = build()
    MANIFEST.write_bytes(body)
    HYBRID.unlink(missing_ok=True)
    print(f"manifest frozen: {len(body)} bytes, sha256 {hashlib.sha256(body).hexdigest()}")
    # A1 signs a short statement of the manifest's digest: the YubiKey's EdDSA
    # refuses multi-KB inputs (CKR_DATA_LEN_RANGE, CIRISVerify#113).
    statement = accord_manifest_statement(body, "A1")
    signed = accord_manifest_signed_bytes(body, "A1")
    digest = hashlib.sha256(signed).hexdigest()
    print(f"statement: {json.dumps(statement, sort_keys=True)}")
    print(f"A1 signs sha256(JCS(statement)) = {signed.hex()}")
    print("A1 signs next: enter the YubiKey PIN and touch the key when asked", file=sys.stderr)
    tmp = tempfile.NamedTemporaryFile(prefix="accord-statement-", suffix=".bin", delete=False)
    tmp.write(signed)
    tmp.close()
    statement_path = pathlib.Path(tmp.name)

    cmd = [server_bin, "accord", "sign-bytes", "--key-id", "A1", "--usb", usb, "--in", str(statement_path)]
    for flag in ("--module", "--piv-slot"):
        val = _opt(flag)
        if val:
            cmd += [flag, val]
    try:
        # stdin and stderr stay on the terminal for the PIN prompt; only the JSON comes back.
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return restore(f"could not run the signer ({type(exc).__name__})")
    finally:
        statement_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        return restore(f"the signer exited {proc.returncode}")
    try:
        out = json.loads(proc.stdout)
        key_id, got = out["key_id"], out["sha256"]
        ed_b64, pqc_b64 = out["ed25519_signature_base64"], out["mldsa65_signature_base64"]
    except (ValueError, KeyError, TypeError):
        return restore("the signer's output is not the expected JSON")
    if key_id != "A1":
        return restore(f"the signer signed as {key_id!r}, not A1")
    if got != digest or MANIFEST.read_bytes() != body:
        return restore("the signed bytes are not the frozen manifest's statement")
    if attach_hybrid(ed_b64, pqc_b64, signer="A1") != 0:
        return restore("the signature halves did not attach")
    if verify_in_scratch_home() != 0:
        return restore("the agent's startup check refused the signature")
    print("done: commit ciris_engine/data/seed/accord_manifest.json and accord_manifest.hybrid.json")
    return 0


def main() -> int:
    if "--sign-hybrid" in sys.argv:
        return sign_hybrid()
    if "--check" in sys.argv:
        return check()
    if "--prepare-hybrid" in sys.argv:
        i = sys.argv.index("--prepare-hybrid")
        return prepare_hybrid(pathlib.Path(sys.argv[i + 1]) if len(sys.argv) > i + 1 else ROOT / "accord-ceremony")
    if "--attach-hybrid" in sys.argv:
        i = sys.argv.index("--attach-hybrid")
        return attach_hybrid(sys.argv[i + 1], sys.argv[i + 2])
    # Signing key path comes from the operator, not from this source file.
    env = os.environ.get("CIRIS_ROOT_WA_KEY")
    if not env:
        print("FAIL: set CIRIS_ROOT_WA_KEY to the path of the 32-byte root signing key")
        return 1
    key = pathlib.Path(env).expanduser()
    if not key.is_file():
        print("FAIL: CIRIS_ROOT_WA_KEY does not point at a file")
        return 1
    raw = key.read_bytes()
    if len(raw) != 32:
        print(f"FAIL: signing key is {len(raw)} bytes, expected 32")
        return 1
    from nacl.signing import SigningKey

    body = build()
    MANIFEST.write_bytes(body)
    SIG.write_bytes(SigningKey(raw).sign(body).signature)
    n = len(json.loads(body.decode())["files"])
    print(f"manifest rebuilt over {n} files and re-signed ({len(body)} bytes)")
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
