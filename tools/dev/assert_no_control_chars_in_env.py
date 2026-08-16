#!/usr/bin/env python3
"""Fail if any path the agent resolved contains a control character.

WHY THIS ASSERTION AND NOT "DID IT BOOT". The agent booting proves nothing on
its own: in the 2.9.19 case boot 1 was always clean and boot 2 was broken, so a
liveness check passed for three consecutive releases while a user could not
start the product at all.

What actually failed was a PATH carrying a form feed:

    OSError: [WinError 123] ... 'C:\\Users\\x0cranc\\ciris\\data'

`.env` applies POSIX escape processing inside double quotes, so `\\f` + `ranc`
became one control character. A control character is not legal in a Windows
path — WinError 123 is the OS saying exactly that — so finding one anywhere in
the resolved config is unambiguous evidence of the defect, with no judgement
call about whether the value "looks right".

Checked in BOTH directions, because the two halves disagreed and each one alone
would have passed at some point in this bug's history:

  * the RAW `.env` on disk — catches a writer that failed to escape;
  * the value as the CONFIG LAYER returns it — catches a reader that mangles a
    correctly-written file, which is what the env sync did.

Exit 0 = clean. Exit 1 = a control character reached a path, with the variable
named and the offending byte identified. The VALUE is never printed: it is user
data, and on a public CI artifact it would be a home directory path.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

#: Keys whose value names a filesystem path. Both spellings on purpose — the
#: wizard writes `SECRETS_DB_PATH`/`AUDIT_LOG_PATH` while the config layer reads
#: `CIRIS_SECRETS_DB_PATH`/`CIRIS_AUDIT_DB_PATH`, and a list built from either
#: side alone covers half the keys.
PATH_KEYS = (
    "CIRIS_HOME",
    "CIRIS_DATA_DIR",
    "CIRIS_DB_PATH",
    "CIRIS_SECRETS_DB_PATH",
    "CIRIS_AUDIT_DB_PATH",
    "SECRETS_DB_PATH",
    "AUDIT_LOG_PATH",
    "CIRIS_LOG_DIR",
    "CIRIS_AGENT_ROOT",
)


def _offenders(value: str) -> list[str]:
    return sorted({hex(ord(c)) for c in value if ord(c) < 32})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", required=True, help="CIRIS_HOME for this run")
    ap.add_argument("--label", default="", help="boot1 / boot2, for the message")
    args = ap.parse_args()

    tag = f"[{args.label}] " if args.label else ""
    env_path = Path(args.home) / ".env"
    failures: list[str] = []

    # ── 1. the file on disk ────────────────────────────────────────────────
    if not env_path.exists():
        print(f"{tag}::error::no .env at the resolved home — setup did not complete")
        return 1

    raw = env_path.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key in PATH_KEYS and (bad := _offenders(val)):
            failures.append(f"{key}: control character(s) {bad} in the RAW .env line")

    # ── 2. what the config layer hands back ────────────────────────────────
    # The half that matters more: the env sync produced a correct file and then
    # un-escaped it on read, so a disk-only check passed while users were broken.
    try:
        from ciris_engine.logic.config.env_utils import get_env_var, load_env_file

        load_env_file(str(env_path))
        for key in PATH_KEYS:
            val = get_env_var(key)
            if val and (bad := _offenders(val)):
                failures.append(f"{key}: control character(s) {bad} AS READ by the config layer")
    except Exception as exc:  # pragma: no cover - import shape varies by install
        print(f"{tag}::warning::could not read through the config layer ({type(exc).__name__})")

    if failures:
        print(f"{tag}::error::a path carried a control character — this is the WinError 123 defect")
        for f in failures:
            print(f"  {f}")
        print(
            "  Cause: .env applies POSIX escape processing inside double quotes, so a Windows "
            "path like C:\\Users\\franc becomes C:\\Users<FF>ranc. Writers must escape "
            "(env_line/env_quoted) or emit forward slashes (env_path_value); readers must "
            "repair (repair_dotenv_escapes)."
        )
        return 1

    print(f"{tag}all path values clean — no control characters on disk or as read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
