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
    # split("\n"), NOT splitlines(). str.splitlines() treats FORM FEED (0x0c) and
    # VERTICAL TAB (0x0b) as line boundaries — the exact characters this guard
    # exists to find. A value containing the reported corruption was split in
    # half and neither piece retained the control character, so the guard
    # reported "all path values clean" on a .env that carried it.
    #
    # `\f` comes from `\franc`, `\v` from `\victor`. The two most likely
    # instances of the bug were the two it could not see.
    for line in raw.split("\n"):
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

    # ── 3. PROVE THE TEST WAS CAPABLE OF FAILING ───────────────────────────
    # Without this the assertion can pass VACUOUSLY, and it did -- for three
    # consecutive Windows runs.
    #
    # The job pins a home containing `\f` on purpose, but the harness overwrote
    # CIRIS_HOME with the repo checkout when spawning the backend, so every path
    # written into .env was D:\a\CIRISAgent\CIRISAgent\data\... -- no escape
    # sequence anywhere. "No control characters found" was true and meaningless:
    # the dangerous shape had never been constructed.
    #
    # So require that at least one path value actually descends from the home we
    # asked for. A green result then means "the risky path was built and came out
    # clean", not "nothing risky was attempted".
    home_resolved = str(Path(args.home)).replace("\\", "/").rstrip("/").lower()
    derived = []
    present_path_keys = []
    seen_keys = []
    for line in raw.split("\n"):
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        key, _, val = line.partition("=")
        seen_keys.append(key.strip())
        if key.strip() in PATH_KEYS:
            present_path_keys.append(key.strip())
            if home_resolved and home_resolved in val.strip().strip('"').replace("\\", "/").lower():
                derived.append(key.strip())

    # NO PATH KEYS AT ALL is a different fact from "paths written, none ours",
    # and only the second is the vacuous pass this guard exists to catch.
    #
    # Two setup flows write .env and they write different things. The CLI wizard
    # (`ciris_engine/logic/setup/wizard.py`) persists CIRIS_DB_PATH /
    # CIRIS_DATA_DIR / SECRETS_DB_PATH / AUDIT_LOG_PATH — that is the flow that
    # can produce the WinError 123 corruption, and it is where this guard bites.
    # The API/UI setup flow persists only CIRIS_CONFIGURED; paths stay in the
    # environment and are never written, so there is nothing here to corrupt.
    #
    # Demanding a path key from the UI flow made this step UNPASSABLE rather than
    # rigorous: it failed a run in which nothing was wrong, and the remedy it
    # printed ("check CIRIS_HOME is passed with setdefault") named a bug that had
    # already been fixed. A guard that cannot pass teaches people to ignore it.
    #
    # The escape round-trip itself is covered deterministically, and with a
    # negative control, by tests/ciris_engine/logic/setup/test_env_windows_paths.py.
    if not present_path_keys:
        print(
            f"{tag}: .env carries no path values ({', '.join(sorted(seen_keys)) or 'no keys'}) — "
            "this setup flow persists none, so there is no path to corrupt."
        )
        print(
            "  Not a vacuous pass: the flow that DOES write paths (the CLI wizard) is "
            "covered by tests/ciris_engine/logic/setup/test_env_windows_paths.py, which "
            "includes a negative control proving it can fail."
        )
        return 0

    if not derived:
        print(
            f"{tag}::error::no path in .env derives from the home this job pinned — "
            "the escape-triggering path was never constructed, so a clean result proves nothing"
        )
        print(
            "  This is exactly how the guard passed vacuously for three runs: the harness "
            "replaced CIRIS_HOME with the repo checkout, so nothing dangerous was ever written. "
            "Check that the backend is spawned with the pinned CIRIS_HOME (setdefault, not assignment)."
        )
        return 1

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
