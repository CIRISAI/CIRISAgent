"""Regenerate ETHICS_TEXT_EXPECTED_HASHES in constants.py from the files on disk.

The pins are a startup fail-safe: a mismatch is a RuntimeError, so every edit
to an ethics-text file must ship with the pin for that file in the same commit.
Every edition in ``CORPUS_EDITIONS`` is pinned -- the default (constitution_ethics
1.3) and the research control (accord 1.2b) -- its polyglot pair plus every
``localized/<prefix>_<lang>.txt`` that exists. A locale is pinned only once the
lane has written its file, i.e. once that locale is complete.

This writes the dict in place and prints what changed. It does NOT touch
seed/accord_manifest.json or its signature -- the manifest covers the polyglot
and localized files and is signed by the root key; regenerating it is a
separate, deliberate step (see tools/dev/regen_accord_manifest.py).

    python3 tools/dev/regen_accord_pins.py [--check]

--check exits 1 if any pin would change (nothing is written).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "ciris_engine" / "data"
CONSTANTS = ROOT / "ciris_engine" / "logic" / "utils" / "constants.py"

_EDITION = re.compile(
    r'"(?P<name>[^"]+)":\s*CorpusEdition\(\s*polyglot="(?P<polyglot>[^"]+)",\s*'
    r'compressed="(?P<compressed>[^"]+)",\s*localized_prefix="(?P<prefix>[^"]+)",?\s*\)'
)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def editions(src: str) -> List[Tuple[str, str, str, str]]:
    """``(name, polyglot, compressed, localized_prefix)`` for every edition,
    read from the CORPUS_EDITIONS source (no import: importing constants runs
    the very integrity checks a stale pin fails)."""
    found = [(m["name"], m["polyglot"], m["compressed"], m["prefix"]) for m in _EDITION.finditer(src)]
    if not found:
        raise SystemExit("CORPUS_EDITIONS not found in constants.py")
    return found


def pinned_files(src: str) -> Dict[str, Path]:
    files: Dict[str, Path] = {}
    for _name, polyglot, compressed, prefix in editions(src):
        files[polyglot] = DATA / polyglot
        files[compressed] = DATA / compressed
        for p in sorted((DATA / "localized").glob(f"{prefix}_*.txt")):
            files[p.name] = p
    missing = [n for n, p in files.items() if not p.is_file()]
    if missing:
        raise SystemExit(f"cannot pin files that do not exist: {missing}")
    return files


def main() -> int:
    check_only = "--check" in sys.argv
    src = CONSTANTS.read_text(encoding="utf-8")
    m = re.search(r"ETHICS_TEXT_EXPECTED_HASHES: Dict\[str, str\] = \{\n(.*?)\n\}", src, re.S)
    if not m:
        print("ETHICS_TEXT_EXPECTED_HASHES not found", file=sys.stderr)
        return 1
    current = dict(re.findall(r'"([^"]+)":\s*"([0-9a-f]{64})"', m.group(1)))
    files = pinned_files(src)
    changed = []
    lines = []
    for name, p in files.items():
        h = sha(p)
        if current.get(name) != h:
            changed.append(name)
        lines.append(f'    "{name}": "{h}",')
    stale = sorted(set(current) - set(files))
    if not check_only:
        new_block = "ETHICS_TEXT_EXPECTED_HASHES: Dict[str, str] = {\n" + "\n".join(lines) + "\n}"
        CONSTANTS.write_text(src[: m.start()] + new_block + src[m.end() :], encoding="utf-8")
    verb = "would change" if check_only else "changed"
    print(
        f"pinned {len(files)} files; {len(changed)} pin(s) {verb}; "
        f"{len(stale)} stale entr{'y' if len(stale) == 1 else 'ies'} dropped"
    )
    for n in changed:
        print(f"  {verb}: {n}")
    for n in stale:
        print(f"  dropped: {n}")
    return 1 if check_only and (changed or stale) else 0


if __name__ == "__main__":
    raise SystemExit(main())
