#!/usr/bin/env python3
"""Block node key material from ever being committed.

WHY THIS EXISTS, AND WHY detect-private-key DID NOT DO IT

124 files under ``identity/`` were tracked in this repo and 122 reached main:
61 ``<alias>.master.key`` (32 raw bytes each), 61 sealed
``<alias>.ed25519.seed.blob``, and 2 ML-DSA-65 PQC seeds. Three separate
protections were in place and all three were structurally incapable of seeing
them:

  ``detect-private-key``  substring-matches a fixed blacklist of PEM armor —
                          ``BEGIN RSA PRIVATE KEY``, ``BEGIN OPENSSH PRIVATE
                          KEY``, and so on. CIRIS key material carries no
                          header and no armor, so there is nothing to match.
                          The hook was not misconfigured; it is scoped to a
                          format this project does not use.

  ``check-added-large-files``  fires at 250 KB. A master key is 32 bytes.

  ``.gitignore``          had no rule for the path (now it does) — and a
                          .gitignore is not a gate anyway: it is inert for
                          files that are ALREADY tracked, which is precisely
                          why these persisted across releases once added.

Each of those checks a FORMAT or a SIZE. The actual invariant is a PATH:
nothing under ``identity/`` or ``keys/`` may be committed, whatever it contains
and however small it is. That is what this hook enforces, and it fails on
``git add -f`` too, which .gitignore does not.

A node MINTS its identity (persist's ``create_identity_if_missing``) at boot.
There is no case where a checkout should carry one.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, List

# Directories that hold key material. Anything under these is refused.
FORBIDDEN_DIRS = ("identity/", "keys/")

# Suffixes that are key material wherever they appear, so moving the directory
# does not quietly move the exposure with it.
FORBIDDEN_SUFFIXES = (
    ".master.key",
    ".ed25519.seed.blob",
    ".tpmplugin_seal",
    ".pqc.seed",
)

# Test fixtures need to name these shapes without tripping the hook.
ALLOWED_PREFIXES = ("tests/", "docs/")


def offending_paths(paths: Iterable[str]) -> List[str]:
    bad: List[str] = []
    for raw in paths:
        p = raw.replace("\\", "/").lstrip("./")
        if p.startswith(ALLOWED_PREFIXES):
            continue
        if p.startswith(FORBIDDEN_DIRS) or p.endswith(FORBIDDEN_SUFFIXES):
            bad.append(p)
    return bad


def main(argv: List[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    bad = offending_paths(args)
    if not bad:
        return 0

    print("BLOCKED: node key material must never be committed.\n")
    for p in bad:
        size = ""
        try:
            size = f"  ({Path(p).stat().st_size} bytes)"
        except OSError:
            pass
        print(f"  - {p}{size}")
    print(
        "\nThese are private keys. Committing one compromises it the moment it is\n"
        "pushed, and deleting the file afterwards does not remove it from history.\n"
        "\n"
        "detect-private-key does not catch these: it looks for PEM armor\n"
        "('BEGIN ... PRIVATE KEY'), and CIRIS stores raw 32-byte keys and sealed\n"
        "binary blobs with no header at all.\n"
        "\n"
        "FIX: unstage them —\n"
        "    git restore --staged " + " ".join(bad[:3]) + ("\n" if len(bad) <= 3 else " …\n") + "\n"
        "A node mints its own identity at boot (create_identity_if_missing).\n"
        "A checkout should never carry one."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
