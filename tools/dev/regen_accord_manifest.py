"""Rebuild seed/accord_manifest.json from disk and re-sign it with the root key.

WHAT THE MANIFEST IS FOR. `ACCORD_EXPECTED_HASHES` in constants.py is a
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
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ciris_engine" / "data"
LOCALIZED = DATA / "localized"
MANIFEST = ROOT / "seed" / "accord_manifest.json"
SIG = MANIFEST.with_suffix(".sig")


def manifest_files() -> dict[str, Path]:
    """Everything the agent loads as canon, in a stable order."""
    files: dict[str, Path] = {
        "accord_1.2b_POLYGLOT.txt": DATA / "accord_1.2b_POLYGLOT.txt",
        "accord_1.2b_POLYGLOT_compressed.txt": DATA / "accord_1.2b_POLYGLOT_compressed.txt",
    }
    for p in sorted(LOCALIZED.glob("accord_1.2b_*.txt")):
        files[p.name] = p
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
        "version": prev.get("version", "1.2b"),
        "files": {
            name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for name, p in manifest_files().items()
        },
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
    for name, rec in doc["files"].items():
        p = manifest_files().get(name)
        if p is None:
            bad.append(f"{name}: named by the manifest but not on disk")
        elif hashlib.sha256(p.read_bytes()).hexdigest() != rec["sha256"]:
            bad.append(f"{name}: hash differs from the manifest")
    # Verify with `cryptography`, the same library the agent's own startup check
    # uses (logic/utils/constants.py), not PyNaCl. PyNaCl is only needed to SIGN
    # -- which happens on a key holder's machine -- and requiring it to *check*
    # made this guard fail in CI with ModuleNotFoundError, reported as "manifest
    # is stale or unsigned". A verification path that cannot run is not a check.
    import base64

    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    pub = json.loads((ROOT / "seed" / "root_pub.json").read_text(encoding="utf-8"))["pubkey"]
    raw = base64.urlsafe_b64decode(pub + "=" * (-len(pub) % 4))
    try:
        Ed25519PublicKey.from_public_bytes(raw).verify(SIG.read_bytes(), MANIFEST.read_bytes())
        print(f"signature ok over {len(doc['files'])} files")
    except InvalidSignature:
        bad.append("signature does NOT verify against seed/root_pub.json")
    for b in bad:
        print(f"  {b}")
    return 1 if bad else 0


def main() -> int:
    if "--check" in sys.argv:
        return check()
    sys.path.insert(0, str(ROOT))
    from tools.generate_template_manifest import load_root_private_key

    body = build()
    MANIFEST.write_bytes(body)
    SIG.write_bytes(load_root_private_key().sign(body).signature)
    n = len(json.loads(body.decode())["files"])
    print(f"manifest rebuilt over {n} files and re-signed ({len(body)} bytes)")
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
