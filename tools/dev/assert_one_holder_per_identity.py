#!/usr/bin/env python3
"""Fail if any provider identity is claimed by more than one live certificate.

WHY THIS EXISTS, AND WHY IT NEEDS NO GOOGLE.

On 2026-08-31 a fresh install signed in with Google, completed setup, and was
then locked out permanently:

    AMBIGUOUS provider identity — multiple live certs claim this account.
    Refusing to choose: picking one silently signs the human in with whichever
    rights that cert happens to carry.
    provider=google holders=2
    wa_ids=["wa-2026-08-31-227732", "wa-root-mooreericnyc-7hhypjexoo"]

Google failed on the ambiguity; local failed because an OAuth user has no
password. A closed door on both sides, on a first run.

CI did not catch it, and the reason is worth stating plainly: the five-platform
gate authenticates with `--username qaadmin --password …`, so the OAuth path is
never walked on any platform. The one OAuth check that exists deliberately stops
before the browser, because real consent cannot be automated — a sound decision
that nevertheless leaves the whole post-callback identity path uncovered.

THE INSIGHT: the bug is not IN the consent screen, so it does not take a consent
screen to find. It is a broken INVARIANT — one identity, one live holder — and an
invariant can be asserted directly against the store at any time, by any run,
with no provider involved. This check would have failed the first time an OAuth
sign-in was followed by setup, on any platform, in any suite.

An identity with two live holders is not a cosmetic duplicate. The substrate
fails CLOSED on it, which is correct: choosing between certs would silently grant
whichever rights the winner happens to carry. So the ambiguity IS the lockout.
"""

from __future__ import annotations

import argparse
import collections
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List, Tuple

#: Where persist keeps certificates. One table, written by BOTH the substrate
#: (claim-remote's owner binding) and the agent (setup's minted WA) — which is
#: precisely how two holders came to exist.
WA_TABLE = "cirislens_wa_cert"


def _identity_of(row: Dict[str, object]) -> List[Tuple[str, str]]:
    """Every (provider, external_id) this row claims.

    Both the primary columns and any linked-identity JSON, because a cert can
    hold an identity either way and the substrate's ambiguity check considers
    both.
    """
    claims: List[Tuple[str, str]] = []
    provider = row.get("oauth_provider")
    external = row.get("oauth_external_id")
    if isinstance(provider, str) and provider and isinstance(external, str) and external:
        claims.append((provider, external))

    linked = row.get("oauth_links") or row.get("linked_identities")
    if isinstance(linked, str) and linked.strip():
        try:
            parsed = json.loads(linked)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    p, e = item.get("provider"), item.get("external_id")
                    if isinstance(p, str) and p and isinstance(e, str) and e:
                        claims.append((p, e))
    return claims


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", type=Path, help="Path to ciris_engine.db")
    ap.add_argument(
        "--allow-missing",
        action="store_true",
        help=(
            "Pass when the DB or cert table does not exist. For suites that may run "
            "before any setup; NOT for a release gate, where an absent store means "
            "the run under test never happened."
        ),
    )
    args = ap.parse_args()

    if not args.db.exists():
        print(f"{'SKIP' if args.allow_missing else 'FAIL'}: no database at {args.db}")
        return 0 if args.allow_missing else 2

    try:
        conn = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if WA_TABLE not in tables:
            print(f"{'SKIP' if args.allow_missing else 'FAIL'}: {WA_TABLE} not in {args.db}")
            return 0 if args.allow_missing else 2
        cur = conn.execute(f"SELECT * FROM {WA_TABLE}")
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    except sqlite3.Error as exc:
        print(f"FAIL: could not read {args.db}: {exc}")
        return 2

    # ONLY LIVE CERTS. A retired row is not a claimant — the provisional OAuth
    # placeholder is retired on purpose, and counting it would fail every healthy
    # install.
    live = [r for r in rows if str(r.get("active", "1")) not in ("0", "False", "false")]

    # DEDUPE PER CERTIFICATE. A single cert legitimately claims one identity via
    # BOTH its primary columns and a linked-identity entry; counting that as two
    # holders would report ambiguity on a perfectly healthy install. Ambiguity is
    # about DISTINCT certs, which is exactly what the substrate's check means.
    holder_sets: Dict[Tuple[str, str], set] = collections.defaultdict(set)
    for row in live:
        wa_id = str(row.get("wa_id", "<unknown>"))
        for claim in _identity_of(row):
            holder_sets[claim].add(wa_id)
    holders: Dict[Tuple[str, str], List[str]] = {k: sorted(v) for k, v in holder_sets.items()}

    ambiguous = {ident: ids for ident, ids in holders.items() if len(ids) > 1}

    print(f"Scanned {len(rows)} certificate(s), {len(live)} live, {len(holders)} provider identity(ies).")
    for (provider, external), ids in sorted(holders.items()):
        mark = "AMBIGUOUS" if len(ids) > 1 else "ok"
        print(f"  {mark:9s} {provider}:{external[:12]}…  holders={len(ids)}  {ids}")

    if not ambiguous:
        print("\nPASS: every provider identity has exactly one live holder.")
        return 0

    print(f"\nFAIL: {len(ambiguous)} provider identity(ies) claimed by more than one live cert.")
    print("      The node fails CLOSED on this — every sign-in with that provider is")
    print("      refused (auth.oauth.store_unavailable), and an OAuth user has no")
    print("      password to fall back to. This is a LOCKOUT, not a duplicate row.")
    print("      Ownership is the fabric's to produce: if the substrate already bound")
    print("      the identity during claim-remote, setup must surface it, not mint a")
    print("      second ROOT alongside it.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
