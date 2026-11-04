#!/usr/bin/env python3
"""Every string the pinned ciris-client asks for must be in the agent's bundle.

The app does not load strings from the client library. It reads
``ciris_engine/data/localized/{lang}.json`` and its apps/ mirrors, so a key the
client adds renders raw until it is merged here. check_localization_sync.py
can't see that: its reference check scans commonMain Kotlin, which moved to
CIRISClient. 2.19.0 and 2.19.1 shipped 417 raw keys on every platform, including
every device-claim screen ("nav.surface.owned_agents", "mobile.owned_agents_claim").

This reads the client's published ``ciris-client-<pin>-localization.zip``, the
same pin requirements.txt holds (CIRIS_CLIENT_VERSION / CIRIS_CLIENT_RELEASE_TAG
override it, as in tools/fetch_client_artifacts.py).

    python tools/dev/check_client_strings.py                # check: exit 1 on a missing key
    python tools/dev/check_client_strings.py --merge        # add what's missing, every locale

``--merge`` only adds. A value already in the bundle is never replaced, and
``prompts.*`` is skipped: the prompts are the agent's own, not the client's.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "ciris_engine" / "data" / "localized"
MIRRORS = [
    ROOT / "apps" / "android" / "src" / "main" / "assets" / "localization",
    ROOT / "apps" / "ios" / "iosApp" / "localization",
    ROOT / "apps" / "ios" / "Resources" / "app" / "localization",
]
REPO = "CIRISAI/CIRISClient"
#: Top-level sections the agent owns outright.
AGENT_OWNED = ("prompts", "_meta")


def flatten(tree: Dict[str, object], prefix: str = "") -> Dict[str, object]:
    out: Dict[str, object] = {}
    for key, value in tree.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten(value, name))
        else:
            out[name] = value
    return out


def missing_keys(client: Dict[str, object], bundle: Dict[str, object]) -> List[str]:
    """Keys the client defines and the bundle doesn't, agent-owned sections aside."""
    have = flatten(bundle)
    return sorted(k for k in flatten(client) if k not in have and k.split(".")[0] not in AGENT_OWNED)


def merge_missing(client: Dict[str, object], bundle: Dict[str, object]) -> int:
    """Add the client's missing keys to `bundle` in place. Returns how many were added."""
    added = 0

    def walk(src: Dict[str, object], dst: Dict[str, object], top: bool) -> None:
        nonlocal added
        for key, value in src.items():
            if top and key in AGENT_OWNED:
                continue
            if key not in dst:
                dst[key] = value
                added += len(flatten(value)) if isinstance(value, dict) else 1
            elif isinstance(value, dict) and isinstance(dst[key], dict):
                walk(value, dst[key], False)

    walk(client, bundle, True)
    return added


def client_version() -> str:
    override = os.environ.get("CIRIS_CLIENT_VERSION", "").strip()
    if override:
        return override
    found = re.search(r"^ciris-client==([0-9.]+)", (ROOT / "requirements.txt").read_text(encoding="utf-8"), re.MULTILINE)
    if not found:
        raise SystemExit("no ciris-client pin in requirements.txt")
    return found.group(1)


def fetch_client_bundle(version: str, into: Path) -> Path:
    tag = os.environ.get("CIRIS_CLIENT_RELEASE_TAG", "").strip() or f"v{version}"
    subprocess.run(
        ["gh", "release", "download", tag, "--repo", REPO, "--pattern", "*-localization.zip", "--dir", str(into)],
        check=True,
    )
    with zipfile.ZipFile(next(into.glob("*-localization.zip"))) as archive:
        archive.extractall(into / "x")
    return into / "x" / "localization"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--merge", action="store_true", help="add missing keys to every locale and mirror")
    args = parser.parse_args()

    version = client_version()
    with tempfile.TemporaryDirectory() as tmp:
        client_dir = fetch_client_bundle(version, Path(tmp))
        locales = sorted(p for p in client_dir.glob("*.json") if p.name != "manifest.json")
        total = 0
        for path in locales:
            client = json.loads(path.read_text(encoding="utf-8"))
            target = BUNDLE / path.name
            bundle = json.loads(target.read_text(encoding="utf-8"))
            if args.merge:
                added = merge_missing(client, bundle)
                if added:
                    target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                total += added
            else:
                total += len(missing_keys(client, bundle))
                if path.name == "en.json":
                    for key in missing_keys(client, bundle)[:20]:
                        print(f"  missing from en.json: {key}")
        if args.merge:
            for mirror in MIRRORS:
                for path in locales:
                    shutil.copyfile(BUNDLE / path.name, mirror / path.name)
            print(f"merged {total} key(s) from ciris-client {version} across {len(locales)} locale(s) and {len(MIRRORS)} mirror(s)")
            return 0

    if total:
        print(
            f"FAIL: {total} key(s) in ciris-client {version} are missing from {BUNDLE.relative_to(ROOT)} "
            "(they render raw in the app). Fix: python tools/dev/check_client_strings.py --merge"
        )
        return 1
    print(f"OK: every ciris-client {version} string is in the bundle ({len(locales)} locales)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
