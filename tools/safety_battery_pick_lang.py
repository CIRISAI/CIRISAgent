#!/usr/bin/env python3
"""Pick the next safety-battery cell language (CIRISAgent#1233).

This is the ``pick-lang`` pre-flight of ``.github/workflows/safety-battery.yml``,
moved out of YAML so it can be tested.

Why it exists as a script
-------------------------
The old step ran ``gh api --paginate .../actions/artifacts?per_page=100`` over
the whole repo (~35 pages, 3,472+ artifacts) in one shot with no retry. GitHub's
repo-wide artifact list sometimes returns a truncated body, which ``gh`` reports
as ``unexpected end of JSON input``; one bad page out of 35 killed every
scheduled run from 2026-09-28 on. Here each page is fetched on its own and a
page that fails to parse (or a ``gh`` call that exits non-zero) is retried with
bounded exponential backoff. Only a page that fails every attempt fails the
pick, and the caller reports that as a pre-flight failure, never as a battery
result.

Pick semantics (unchanged from the YAML)
----------------------------------------
1. Walk the roster in order. The first language with NO non-expired
   ``safety-battery-capture-<lang>-*`` artifact wins ("untested").
2. Otherwise pick the language whose newest capture is oldest, in whole days;
   ties go to the earlier roster entry.

Research-arm captures (artifact names ending ``-arm-<12 hex>``, see the
``research_manifest`` dispatch input) are ignored: the rotation tracks coverage
of the canonical corpus, and an arm capture says nothing about that.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Optional, Sequence

#: 29-cell roster, in priority order (Tier-0/1 first, then Tier-2).
ROSTER: Sequence[str] = (
    "am ar bn my ha hi mr fa pa sw ta te ur yo en de es fr it pt ru uk ja ko zh id th vi tr"
).split()

CAPTURE_PREFIX = "safety-battery-capture-"
#: Suffix the workflow appends to a research-manifest capture's artifact name.
ARM_SUFFIX_RE = re.compile(r"-arm-[0-9a-f]{12}$")

PER_PAGE = 100
#: Hard ceiling so a misbehaving API can never loop us forever (100k artifacts).
MAX_PAGES = 1000
DEFAULT_ATTEMPTS = 5
DEFAULT_BACKOFF_S = 2.0


class PageFetchError(RuntimeError):
    """A page failed every attempt. The pick cannot be trusted; fail the pre-flight."""


#: Returns the raw response body for one page. Raises on transport failure.
FetchRaw = Callable[[int], str]


@dataclass(frozen=True)
class Artifact:
    name: str
    created_at: datetime


@dataclass(frozen=True)
class Pick:
    lang: str
    reason: str


def gh_fetch_raw(repo: str) -> FetchRaw:
    """Fetch one page of the repo artifact list via ``gh api`` (no ``--paginate``)."""

    def _fetch(page: int) -> str:
        proc = subprocess.run(
            ["gh", "api", f"repos/{repo}/actions/artifacts?per_page={PER_PAGE}&page={page}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"gh api exited {proc.returncode}: {proc.stderr.strip()[:300]}")
        return proc.stdout

    return _fetch


def fetch_page(
    fetch_raw: FetchRaw,
    page: int,
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    backoff_s: float = DEFAULT_BACKOFF_S,
    sleep: Optional[Callable[[float], None]] = None,
    log: Callable[[str], None] = lambda m: print(m, file=sys.stderr),
) -> Dict[str, object]:
    """Fetch and parse one page, retrying truncated/invalid bodies and failed calls."""
    sleep = sleep or time.sleep  # resolved per call so tests can patch it
    last_err: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            body = json.loads(fetch_raw(page))
            if not isinstance(body, dict) or not isinstance(body.get("artifacts"), list):
                raise ValueError("response has no 'artifacts' list")
            return body
        except Exception as exc:  # noqa: BLE001 — every failure mode is retried the same way
            last_err = exc
            if attempt < attempts:
                delay = backoff_s * (2 ** (attempt - 1))
                log(f"page {page} attempt {attempt}/{attempts} failed ({type(exc).__name__}: {exc}); retry in {delay:.0f}s")
                sleep(delay)
    raise PageFetchError(f"page {page} failed after {attempts} attempts: {type(last_err).__name__}: {last_err}")


def list_capture_artifacts(fetch_raw: FetchRaw, **fetch_kwargs: object) -> List[Artifact]:
    """All non-expired canonical capture artifacts, across every page."""
    seen_ids = set()
    out: List[Artifact] = []
    for page in range(1, MAX_PAGES + 1):
        body = fetch_page(fetch_raw, page, **fetch_kwargs)  # type: ignore[arg-type]
        arts = body["artifacts"]
        assert isinstance(arts, list)
        for a in arts:
            if not isinstance(a, dict) or a.get("id") in seen_ids:
                continue
            seen_ids.add(a.get("id"))
            name = a.get("name") or ""
            if a.get("expired") or not name.startswith(CAPTURE_PREFIX) or ARM_SUFFIX_RE.search(name):
                continue
            out.append(Artifact(name=name, created_at=_parse_ts(str(a["created_at"]))))
        if len(arts) < PER_PAGE:
            return out
    raise PageFetchError(f"artifact list did not end within {MAX_PAGES} pages")


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def pick_lang(artifacts: Iterable[Artifact], now: datetime, roster: Sequence[str] = ROSTER) -> Pick:
    """Untested cells first (roster order), else the oldest newest-capture in whole days."""
    newest: Dict[str, datetime] = {}
    arts = list(artifacts)
    for lang in roster:
        prefix = f"{CAPTURE_PREFIX}{lang}-"
        stamps = [a.created_at for a in arts if a.name.startswith(prefix)]
        if not stamps:
            return Pick(lang, "untested (no prior capture artifact)")
        newest[lang] = max(stamps)

    best_lang, best_age = "", -1
    for lang in roster:
        age_days = int((now - newest[lang]).total_seconds() // 86400)
        if age_days > best_age:
            best_lang, best_age = lang, age_days
    return Pick(best_lang, f"oldest capture ({best_age}d old)")


def _write_outputs(pick: Pick) -> None:
    lines = f"lang={pick.lang}\nreason={pick.reason}\n"
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--explicit-lang", default="", help="operator-chosen lang (workflow_dispatch); skips the scan")
    args = ap.parse_args(argv)

    if args.explicit_lang:
        if args.explicit_lang not in ROSTER:
            print(f"::error::lang {args.explicit_lang!r} is not in the roster", file=sys.stderr)
            return 2
        pick = Pick(args.explicit_lang, "workflow_dispatch input")
        _write_outputs(pick)
        print(f"::notice::Using explicit lang: {pick.lang}")
        return 0

    try:
        arts = list_capture_artifacts(gh_fetch_raw(args.repo))
    except PageFetchError as exc:
        print(f"artifact scan failed: {exc}", file=sys.stderr)
        return 1
    print(f"Pulled {len(arts)} non-expired canonical safety-battery-capture-* artifacts (paged, retried)")
    pick = pick_lang(arts, datetime.now(timezone.utc))
    _write_outputs(pick)
    print(f"::notice::Picked {pick.lang} — {pick.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
