#!/usr/bin/env python3
"""After a long-jump upgrade, did the agent's IDENTITY survive?

Booting is not the test. The failure that reached users boots GREEN: both
listeners answer 200, the incidents log holds nothing above INFO, and the
pre-existing owner simply cannot log in. Reproduced 2.7.9 → 2.9.14 — `wa_cert`
comes back empty and the only rows in the store are freshly-minted adapter
observers (`apiplatform_observer`, `wallet_observer`, …). 2.7.9 predates the
substrate, so its users lived in the old Python tables and nothing carries them
across.

A health check cannot see that. It is a fresh install wearing the old data
directory's clothes, and every signal says success.

So this asserts the thing a health check cannot: a human-owned WA certificate is
still present after the upgrade. Adapter observers do not count — they are minted
at every boot, so counting them would make this pass on an empty store, which is
exactly the state it exists to catch.

Exit 0 = an owner survived SOMEWHERE on disk. Exit 1 = the operator is locked out
of a healthy-looking agent.

"Somewhere" is deliberate: this asserts the credentials still EXIST, which is what
makes the failure recoverable. Whether the running code can READ them is a
separate question, and conflating the two is exactly the error that made me
report data loss when the rows were intact in a file nothing opened.
"""

from __future__ import annotations

import argparse
import glob
import sqlite3
import sys
from pathlib import Path

#: Certs the agent mints for itself on every boot. Their presence proves nothing
#: about upgrade fidelity; only a human-owned cert does.
MINTED_SUFFIXES = ("_observer",)
MINTED_NAMES = {"CIRIS System Authority"}


def human_certs(db: Path) -> tuple[list[str], list[str]]:
    """(human-owned names, all names) from a wa_cert table, tolerant of shape."""
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = [r[0] for r in conn.execute("select name from wa_cert") if r[0]]
    except sqlite3.Error:
        return [], []
    human = [
        n for n in rows
        if not n.endswith(MINTED_SUFFIXES) and n not in MINTED_NAMES
    ]
    return human, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--home", default="/tmp/fixture", help="CIRIS_HOME the agent booted against")
    args = ap.parse_args()

    # BOTH databases, because which one holds wa_cert is version-dependent —
    # that is the whole bug. 2.7.x's auth store took an explicit db_path and the
    # caller passed the AUDIT database, so `wa_cert` lives in ciris_audit.db
    # there; 2.9.x reads the persist engine, backed by ciris_engine.db. Looking
    # in only one is how I first misdiagnosed this as data loss: engine.wa_cert
    # was empty and the owner was sitting untouched in the audit file.
    dbs = [
        Path(p)
        for pattern in ("ciris_engine.db", "ciris_audit.db")
        for p in glob.glob(f"{args.home}/**/{pattern}", recursive=True)
    ]
    if not dbs:
        print(f"::error::No ciris_engine.db under {args.home} — the fixture did not "
              f"unpack, so this job proved nothing. Failing rather than reporting a pass.")
        return 1

    for db in dbs:
        human, allnames = human_certs(db)
        print(f"{db}: {len(allnames)} cert(s) — {allnames[:8]}")
        if human:
            print(f"owner survived the upgrade: {human[0]}")
            return 0

    print("::error::FAILURE MODE 2 — no human-owned WA cert survived the upgrade.")
    print("::error::The agent reports healthy and the pre-existing operator cannot log in.")
    print("::error::Only self-minted adapter observers are present, which is the signature")
    print("::error::of a fresh install over an old data directory rather than an upgrade.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
