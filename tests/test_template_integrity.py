"""The template ledger says things that nothing used to check.

Every template carries a `stewardship.creator_ledger_entry` naming a creator, a
public-key fingerprint and a signature, and `pre-approved-templates.json` carries
a SHA-256 per template under a root signature. The setup API reads that ledger and
surfaces it to the user as provenance (adapters/api/routes/setup/helpers.py).

Nothing verified any of it. `test_agent_templates.py` checks schema -- a name and
description exist, permitted actions are valid -- and stops. So the manifest went
on naming `ally` for the whole life of the rename to `default.yaml`, stopped
naming datum, test and he-300-benchmark entirely, and let every checksum fall
behind the files, with no test going red. That is how an edited template reaches
a user under an approval that covers a different file.

The signature was never the broken part: it verified correctly the whole time,
over a stale set. A signature over the wrong contents is exactly as useless as no
signature, and only a checksum test can tell the difference -- which is what these
are for. Regenerate with tools/dev/regen_template_manifest.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
import pathlib

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[1]
TEMPLATES = REPO / "ciris_engine" / "ciris_templates"
MANIFEST = REPO / "pre-approved-templates.json"

_MAN = json.loads(MANIFEST.read_text(encoding="utf-8"))
_FILES = sorted(TEMPLATES.glob("*.yaml"))


def _sha(p: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test_each_template_matches_its_approved_checksum(path: pathlib.Path) -> None:
    """A template whose bytes have moved since approval is not the approved one."""
    entry = _MAN["templates"].get(path.stem)
    assert entry is not None, f"{path.stem} ships but the manifest does not name it"
    assert entry["checksum"] == _sha(path), (
        f"{path.stem} has been edited since it was signed -- "
        "regenerate with tools/dev/regen_template_manifest.py"
    )


def test_the_manifest_names_exactly_what_ships() -> None:
    """Catches both halves of the ally->default rename: an entry for a file that
    no longer exists, and files shipping under no entry at all."""
    named, shipped = set(_MAN["templates"]), {p.stem for p in _FILES}
    assert named == shipped, (
        f"listed but absent: {sorted(named - shipped)}; "
        f"shipped but unlisted: {sorted(shipped - named)}"
    )


def test_the_root_signature_verifies() -> None:
    """Over the templates object as recorded, using the convention the generator
    signs with: compact JSON, keys sorted."""
    nacl_signing = pytest.importorskip("nacl.signing", reason="pynacl not installed")
    payload = json.dumps(_MAN["templates"], sort_keys=True, separators=(",", ":")).encode()
    nacl_signing.VerifyKey(base64.b64decode(_MAN["root_public_key"])).verify(
        payload, base64.b64decode(_MAN["root_signature"])
    )


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.stem)
def test_each_ledger_points_at_the_key_that_signed_the_manifest(path: pathlib.Path) -> None:
    """A ledger fingerprint naming some other key is unfalsifiable provenance: the
    reader cannot tell a rotation from a forgery. Templates were shipped for a
    long time claiming a key that had no relationship to anything in the repo."""
    led = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("stewardship", {}).get(
        "creator_ledger_entry", {}
    )
    fp = led.get("public_key_fingerprint")
    if fp is None:
        pytest.skip(f"{path.stem} carries no creator ledger")
    root = base64.b64decode(_MAN["root_public_key"])
    assert fp == "sha256:" + hashlib.sha256(root).hexdigest(), (
        f"{path.stem} names a key that did not sign the manifest"
    )
