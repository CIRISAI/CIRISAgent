"""Regenerate ACCORD_EXPECTED_HASHES in constants.py from the files on disk.

The pins are a startup fail-safe: a mismatch is a RuntimeError, so every edit
to an accord text must ship with the pin for that file in the same commit.
This writes the dict in place and prints what changed. It does NOT touch
seed/accord_manifest.json or its signature -- the manifest covers the polyglot
and braided files and is signed by the root key; regenerating it is a
separate, deliberate step (see tools/dev/regen_accord_manifest.py).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ciris_engine" / "data"
CONSTANTS = ROOT / "ciris_engine" / "logic" / "utils" / "constants.py"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    src = CONSTANTS.read_text(encoding="utf-8")
    m = re.search(r"ACCORD_EXPECTED_HASHES: Dict\[str, str\] = \{\n(.*?)\n\}", src, re.S)
    if not m:
        print("ACCORD_EXPECTED_HASHES not found", file=sys.stderr)
        return 1
    current = dict(re.findall(r'"([^"]+)":\s*"([0-9a-f]{64})"', m.group(1)))
    files = {
        "accord_1.2b_POLYGLOT.txt": DATA / "accord_1.2b_POLYGLOT.txt",
        "accord_1.2b_POLYGLOT_compressed.txt": DATA / "accord_1.2b_POLYGLOT_compressed.txt",
    }
    for p in sorted((DATA / "localized").glob("accord_1.2b_*.txt")):
        files[p.name] = p
    changed = []
    lines = []
    for name, p in files.items():
        h = sha(p)
        if current.get(name) != h:
            changed.append(name)
        lines.append(f'    "{name}": "{h}",')
    new_block = "ACCORD_EXPECTED_HASHES: Dict[str, str] = {\n" + "\n".join(lines) + "\n}"
    CONSTANTS.write_text(src[: m.start()] + new_block + src[m.end():], encoding="utf-8")
    stale = sorted(set(current) - set(files))
    print(f"pinned {len(files)} files; {len(changed)} pin(s) changed; {len(stale)} stale entr{'y' if len(stale)==1 else 'ies'} dropped")
    for n in changed:
        print(f"  changed: {n}")
    for n in stale:
        print(f"  dropped: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
