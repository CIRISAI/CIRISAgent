#!/usr/bin/env python3
"""Rebuild and sign pre-approved-templates.json from the templates on disk.

Replaces four near-identical generators (tools/generate_template_manifest.py,
tools/templates/generate_manifest.py, tools/templates/generate-template-manifest.py,
tools/dev/generate-template-manifest.py). Each carried its own hardcoded dict of
template names, and that is precisely how the manifest drifted: when ally.yaml was
renamed default.yaml the dicts were not updated, so the manifest went on naming a
template that no longer existed and stopped naming three that did. This one globs
the directory and reads each description from the template itself, so a rename or
an addition cannot silently fall out of coverage.

The signed payload is unchanged from the generator this supersedes -- the compact
sort_keys JSON of the templates object -- so existing signatures stay checkable.

    python3 tools/dev/regen_template_manifest.py            # rebuild and sign
    python3 tools/dev/regen_template_manifest.py --check    # verify, write nothing

--check exits 0 when the manifest covers every template with a matching checksum
and a signature that verifies, 1 when it does not, and 2 when it cannot tell
(pynacl absent) -- "cannot verify" and "verified bad" must never be reported the
same way.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "ciris_engine" / "ciris_templates"
MANIFEST = REPO / "pre-approved-templates.json"
# Location of the 32-byte ed25519 signing key, supplied by the operator. Kept out
# of the source so the tool carries no assumption about where a steward keeps it.
KEY_ENV = "CIRIS_ROOT_WA_KEY"


def collect() -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for p in sorted(TEMPLATES.glob("*.yaml")):
        doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        out[p.stem] = {
            "checksum": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest(),
            "description": doc.get("description") or f"{p.stem} template",
        }
    return out


def payload(templates: dict) -> bytes:
    return json.dumps(templates, sort_keys=True, separators=(",", ":")).encode("utf-8")


def check() -> int:
    if not MANIFEST.exists():
        print("FAIL: no manifest")
        return 1
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    live, recorded = collect(), man.get("templates", {})
    ok = True
    for name in sorted(set(live) | set(recorded)):
        if name not in recorded:
            print(f"FAIL: {name} ships but the manifest does not name it")
            ok = False
        elif name not in live:
            print(f"FAIL: the manifest names {name}, which does not exist")
            ok = False
        elif recorded[name]["checksum"] != live[name]["checksum"]:
            print(f"FAIL: {name} checksum does not match the file")
            ok = False
    try:
        from nacl.exceptions import BadSignatureError
        from nacl.signing import VerifyKey
    except ImportError:
        print("CANNOT VERIFY: pynacl is not installed -- signature unchecked")
        return 2
    try:
        VerifyKey(base64.b64decode(man["root_public_key"])).verify(
            payload(recorded), base64.b64decode(man["root_signature"])
        )
        print(f"signature verifies under {man['root_public_key']}")
    except (BadSignatureError, KeyError, ValueError) as exc:
        print(f"FAIL: signature does not verify ({type(exc).__name__})")
        ok = False
    print("OK" if ok else "manifest is stale")
    return 0 if ok else 1


def regen() -> int:
    from nacl.signing import SigningKey

    env = os.environ.get(KEY_ENV)
    if not env:
        print(f"FAIL: set {KEY_ENV} to the path of the 32-byte root signing key")
        return 1
    key = pathlib.Path(env).expanduser()
    if not key.is_file():
        print(f"FAIL: {KEY_ENV} does not point at a file")
        return 1
    raw = key.read_bytes()
    if len(raw) != 32:
        print(f"FAIL: signing key is {len(raw)} bytes, expected 32")
        return 1
    sk = SigningKey(raw)
    templates = collect()
    pub = base64.b64encode(sk.verify_key.encode()).decode("ascii")
    prev = json.loads(MANIFEST.read_text(encoding="utf-8")).get("root_public_key") if MANIFEST.exists() else None
    if prev and prev != pub:
        print(f"NOTE: attesting key changes {prev} -> {pub}")
    MANIFEST.write_text(
        json.dumps(
            {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "root_public_key": pub,
                "templates": templates,
                "root_signature": base64.b64encode(sk.sign(payload(templates)).signature).decode("ascii"),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in templates:
        print(f"  {name}: {templates[name]['checksum'][7:19]}...")
    print(f"signed {len(templates)} templates under {pub}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    sys.exit(check() if ap.parse_args().check else regen())
