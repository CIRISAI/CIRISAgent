"""Choose the upgrade fixture the long-jump job boots against.

Reads a JSON array of GitHub artifacts and prints the name of the OLDEST
unexpired ``upgrade-fixture-*`` captured by this agent version or an earlier
one. A fixture captured by a newer version holds migrations this code does not
ship, so booting it tests a downgrade, not an upgrade. Prints nothing when no
fixture qualifies; the workflow fails loudly on an empty name.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_FIXTURE = re.compile(r"^upgrade-fixture-(\d+)\.(\d+)\.(\d+)-")
_VERSION = re.compile(r'^CIRIS_VERSION\s*=\s*"(\d+)\.(\d+)\.(\d+)', re.MULTILINE)
_CONSTANTS = Path(__file__).resolve().parents[2] / "ciris_engine" / "constants.py"


def current_version(constants: Path = _CONSTANTS) -> Tuple[int, int, int]:
    match = _VERSION.search(constants.read_text(encoding="utf-8"))
    if match is None:
        raise SystemExit(f"CIRIS_VERSION not found in {constants}")
    major, minor, patch = (int(part) for part in match.groups())
    return (major, minor, patch)


def fixture_version(name: str) -> Optional[Tuple[int, int, int]]:
    match = _FIXTURE.match(name)
    if match is None:
        return None
    major, minor, patch = (int(part) for part in match.groups())
    return (major, minor, patch)


def pick(artifacts: List[Dict[str, Any]], version: Tuple[int, int, int]) -> Optional[str]:
    eligible = []
    for artifact in artifacts:
        name = artifact.get("name", "")
        captured = fixture_version(name)
        if captured is None or artifact.get("expired", True):
            continue
        if captured > version:
            print(f"skipping {name}: captured by a newer version than {'.'.join(map(str, version))}", file=sys.stderr)
            continue
        eligible.append(artifact)
    if not eligible:
        return None
    return str(min(eligible, key=lambda a: a.get("created_at", ""))["name"])


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print("usage: pick_upgrade_fixture.py <artifacts.json>", file=sys.stderr)
        return 2
    artifacts = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    name = pick(artifacts, current_version())
    if name:
        print(name)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
