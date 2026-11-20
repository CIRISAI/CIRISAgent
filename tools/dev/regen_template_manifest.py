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

    python3 tools/dev/regen_template_manifest.py            # rebuild and sign (retired classical root)
    python3 tools/dev/regen_template_manifest.py --check    # verify, write nothing
    python3 tools/dev/regen_template_manifest.py --sign-hybrid \
        --server-bin <ciris-server> --usb <holder usb dir> [--key-id A1|B1|C1] [--module <ykcs11.so>]

--sign-hybrid is the release step that PRE-APPROVES the shipped templates (Eric, 2026-11-20: "the template
ships pre-approved"). An accord holder signs, on their own machine with keys never leaving it, the
statement the agent's boot check verifies (identity_profile._signed_statement_bytes: domain
ciris.template_manifest.v1, the manifest's sha256 and size, the signer), through ciris-server's
`accord sign-bytes` exactly as regen_accord_manifest.py does. The result is pre-approved-templates.hybrid.json.
A shipped template whose bytes match a hybrid-signed manifest gets its identity base link at first boot with
no Wise Authority step; a custom or modified template still asks a WA.

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
HYBRID = REPO / "pre-approved-templates.hybrid.json"
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


def check_hybrid() -> int:
    """The hybrid pre-approval, structurally: the signer is an accord holder and the doc is over these bytes.

    The signature itself is verified by the agent at boot, against the holder's record in the directory
    (identity_profile.verified_template_manifest); here only what can be checked without an engine.
    """
    sys.path.insert(0, str(REPO))
    from ciris_engine.logic.context.identity_profile import TEMPLATE_MANIFEST_DOMAIN
    from ciris_engine.logic.utils.accord_manifest_hybrid import ACCORD_MANIFEST_SIGNERS

    if not HYBRID.exists():
        print(f"NOT PRE-APPROVED: no {HYBRID.name}: shipped templates would ask a Wise Authority for their base link")
        return 1
    body = MANIFEST.read_bytes()
    try:
        doc = json.loads(HYBRID.read_text(encoding="utf-8"))
    except ValueError:
        print(f"FAIL: {HYBRID.name} is not JSON")
        return 1
    bad = []
    if doc.get("signer_key_id") not in ACCORD_MANIFEST_SIGNERS:
        bad.append(f"signer {doc.get('signer_key_id')!r} is not an accord holder {ACCORD_MANIFEST_SIGNERS}")
    if doc.get("domain") != TEMPLATE_MANIFEST_DOMAIN:
        bad.append(f"domain {doc.get('domain')!r} is not {TEMPLATE_MANIFEST_DOMAIN}")
    if doc.get("manifest_size") != len(body) or doc.get("manifest_sha256") != hashlib.sha256(body).hexdigest():
        bad.append("the signature is over a different manifest (size or sha256 differs): re-run --sign-hybrid")
    if not (doc.get("ed25519_sig") and doc.get("ml_dsa_65_sig")):
        bad.append("a signature half is missing")
    for line in bad:
        print(f"FAIL: {line}")
    if not bad:
        print(f"pre-approved by {doc['signer_key_id']} over {len(body)} bytes (verified at boot against the holder record)")
    return 1 if bad else 0


def _opt(name: str) -> str | None:
    if name in sys.argv:
        i = sys.argv.index(name)
        if len(sys.argv) > i + 1:
            return sys.argv[i + 1]
    return None


def sign_hybrid() -> int:
    """Rebuild the manifest from the templates on disk and have an accord holder pre-approve it.

    The keys never pass through Python (ciris-server's `accord sign-bytes` opens the holder's YubiKey and USB
    halves). This side freezes the bytes, has the holder sign the 32-byte statement digest, checks the returned
    digest, and writes the hybrid doc the agent verifies. Any failure restores the previous files.
    """
    import subprocess
    import tempfile

    sys.path.insert(0, str(REPO))
    from ciris_engine.logic.context.identity_profile import TEMPLATE_MANIFEST_DOMAIN, _signed_statement_bytes
    from ciris_engine.logic.utils.accord_manifest_hybrid import ACCORD_MANIFEST_SIGNERS

    server_bin, usb = _opt("--server-bin"), _opt("--usb")
    key_id = _opt("--key-id") or "A1"
    if key_id not in ACCORD_MANIFEST_SIGNERS:
        print(f"FAIL: {key_id!r} is not an accord holder {ACCORD_MANIFEST_SIGNERS}")
        return 1
    if not server_bin or not usb:
        print("usage: regen_template_manifest.py --sign-hybrid --server-bin <ciris-server> --usb <dir> [--key-id A1|B1|C1]")
        return 1
    prior_manifest = MANIFEST.read_bytes() if MANIFEST.exists() else None
    prior_hybrid = HYBRID.read_bytes() if HYBRID.exists() else None

    def restore(why: str) -> int:
        if prior_manifest is None:
            MANIFEST.unlink(missing_ok=True)
        else:
            MANIFEST.write_bytes(prior_manifest)
        if prior_hybrid is None:
            HYBRID.unlink(missing_ok=True)
        else:
            HYBRID.write_bytes(prior_hybrid)
        print(f"FAIL: {why}; the previous files are restored")
        return 1

    templates = collect()
    # The retired 2025 classical root's fields are not carried: nothing accepts them (100% PQC, 2.20.0).
    body = (
        json.dumps(
            {
                "version": "1.0",
                "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "templates": templates,
            },
            indent=2,
        )
        + "\n"
    ).encode("utf-8")
    MANIFEST.write_bytes(body)
    HYBRID.unlink(missing_ok=True)
    signed = _signed_statement_bytes(body, key_id)
    print(f"manifest frozen: {len(templates)} templates, {len(body)} bytes, sha256 {hashlib.sha256(body).hexdigest()}")
    print(f"{key_id} signs sha256(JCS(statement)) = {signed.hex()}")
    print(f"{key_id} signs next: enter the YubiKey PIN and touch the key when asked", file=sys.stderr)
    tmp = tempfile.NamedTemporaryFile(prefix="template-statement-", suffix=".bin", delete=False)
    tmp.write(signed)
    tmp.close()
    statement_path = pathlib.Path(tmp.name)
    cmd = [server_bin, "accord", "sign-bytes", "--key-id", key_id, "--usb", usb, "--in", str(statement_path)]
    for flag in ("--module", "--piv-slot"):
        val = _opt(flag)
        if val:
            cmd += [flag, val]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return restore(f"could not run the signer ({type(exc).__name__})")
    finally:
        statement_path.unlink(missing_ok=True)
    if proc.returncode != 0:
        return restore(f"the signer exited {proc.returncode}")
    try:
        out = json.loads(proc.stdout)
        out_key_id, got = out["key_id"], out["sha256"]
        ed_b64, pqc_b64 = out["ed25519_signature_base64"], out["mldsa65_signature_base64"]
    except (ValueError, KeyError, TypeError):
        return restore("the signer's output is not the expected JSON")
    if out_key_id != key_id:
        return restore(f"the signer signed as {out_key_id!r}, not {key_id}")
    if got != hashlib.sha256(signed).hexdigest() or MANIFEST.read_bytes() != body:
        return restore("the signed bytes are not the frozen manifest's statement")
    HYBRID.write_text(
        json.dumps(
            {
                "domain": TEMPLATE_MANIFEST_DOMAIN,
                "signer_key_id": key_id,
                "manifest_size": len(body),
                "manifest_sha256": hashlib.sha256(body).hexdigest(),
                "ed25519_sig": ed_b64,
                "ml_dsa_65_sig": pqc_b64,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if check_hybrid() != 0:
        return restore("the written pre-approval does not check")
    print(f"done: commit {MANIFEST.name} and {HYBRID.name}")
    return 0


if __name__ == "__main__":
    if "--sign-hybrid" in sys.argv:
        sys.exit(sign_hybrid())
    if "--check-hybrid" in sys.argv:
        sys.exit(check_hybrid())
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    sys.exit(check() if ap.parse_args().check else regen())
