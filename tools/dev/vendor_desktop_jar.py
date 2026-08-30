#!/usr/bin/env python3
"""Copy the CIRIS Desktop uber-jar out of a downloaded `ciris-client` wheel.

The desktop app is built by CIRISAI/CIRISClient and published inside the
`ciris-client` PLATFORM wheels. This lifts it into `ciris_engine/desktop_app/`,
which is where `setup.py` looks to derive our wheel's platform tag, where
MANIFEST.in ships it from, and where `ciris_engine/desktop_launcher.py` globs
for it at runtime.

A script rather than an inline heredoc because the same three lines run in two
CI jobs (the wheel matrix and the Windows installer) on two shells, and an
inline `python - <<EOF` inside a `run:` block is indentation-sensitive in a way
that has bitten this workflow before.

Exits non-zero with a GitHub-annotated message on anything ambiguous. The
important case is the JAR-FREE universal wheel: `ciris-client` publishes a
3 MB `py3-none-any` wheel alongside the ~63 MB platform wheels so that Android
and other non-desktop targets do not carry 60 MB of Java. Downloading on a
host that resolves the universal wheel yields no jar at all, and that must fail
loudly here rather than produce a wheel with a silently missing desktop app.
"""

from __future__ import annotations

import glob
import os
import sys
import zipfile


def freshness_tail(client_version: str) -> str:
    """The part of the client version that appears in the jar's filename.

    Upstream names the jar for its OWN product version, not the wheel's:
    ciris-client 0.5.192 ships `CIRIS-linux-x64-1.5.192.jar`. Asserting the jar
    contains "0.5.192" therefore fails on every correct build. Compare on the
    `minor.patch` tail, which is shared and still moves on every release -- so a
    jar left over from an earlier client is still caught.
    """
    parts = client_version.split(".")
    return ".".join(parts[1:]) if len(parts) > 2 else client_version


def main(argv: list[str]) -> int:
    if len(argv) not in (3, 4):
        print(f"usage: {argv[0]} <wheel-dir> <dest-dir> [expected-client-version]", file=sys.stderr)
        return 2

    wheel_dir, dest_dir = argv[1], argv[2]
    expected = argv[3] if len(argv) == 4 else None

    wheels = sorted(glob.glob(os.path.join(wheel_dir, "*.whl")))
    if len(wheels) != 1:
        print(f"::error::expected exactly ONE client wheel in {wheel_dir}, got {wheels}")
        return 1
    wheel = wheels[0]

    with zipfile.ZipFile(wheel) as z:
        jars = [n for n in z.namelist() if n.endswith(".jar")]
        if not jars:
            print(
                f"::error::{os.path.basename(wheel)} contains no .jar. The universal "
                "(py3-none-any) ciris-client wheel is JAR-FREE by design; this job needs a "
                "PLATFORM wheel. Check what pip resolved for this runner."
            )
            return 1
        if len(jars) > 1:
            print(f"::error::expected exactly ONE jar in {os.path.basename(wheel)}, got {jars}")
            return 1

        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(jars[0]))
        with z.open(jars[0]) as src, open(dest, "wb") as out:
            out.write(src.read())

    size_mb = os.path.getsize(dest) / 1048576
    print(f"vendored {os.path.basename(dest)} ({size_mb:.1f} MB) from {os.path.basename(wheel)}")

    if expected:
        tail = freshness_tail(expected)
        if tail not in os.path.basename(dest):
            print(
                f"::error::{os.path.basename(dest)} does not carry the pinned client {expected} "
                f"(looked for {tail!r}) — this is a STALE artifact, not a fresh download"
            )
            return 1
        print(f"freshness ok: jar carries {tail} for pinned client {expected}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
