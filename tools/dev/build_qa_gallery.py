#!/usr/bin/env python3
"""Assemble the five platform screenshots into one page you can scan in a glance.

WHY A SELF-CONTAINED FILE RATHER THAN INLINE IMAGES IN THE JOB SUMMARY.
GitHub's step summary renders Markdown but strips `data:` image URIs and cannot
reference the contents of an artifact — there is no URL for a file that only
exists inside a zip. So the summary gets a TABLE (which platforms passed, which
produced a shot), and the pictures get a single `index.html` with every image
inlined as base64. One artifact, one file, no unpacking into a directory of PNGs
and clicking through them.

WHY THE PAGE REPORTS MISSING SHOTS LOUDLY.
A gallery with four pictures reads as "four platforms" unless the fifth is
visibly absent. Every expected platform gets a tile whether or not it produced an
image, because the interesting failure — the one this whole gate exists for — is
a platform that quietly did not run. That is how v2.9.42 shipped with no APK: not
a red tick, an absent artifact.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from pathlib import Path
from typing import Dict, List, NamedTuple, Optional

#: Every platform the gate covers. A tile is rendered for each, present or not.
EXPECTED = ["linux", "macos", "windows", "android", "ios"]

PRETTY = {
    "linux": "Linux",
    "macos": "macOS",
    "windows": "Windows",
    "android": "Android",
    "ios": "iOS",
}


class Tile(NamedTuple):
    platform: str
    image: Optional[Path]
    passed: Optional[bool]
    detail: str


def _find_shots(root: Path) -> Dict[str, Path]:
    """Map platform -> screenshot, wherever the artifact download put it."""
    shots: Dict[str, Path] = {}
    for png in root.rglob("shots/*.png"):
        shots[png.stem] = png
    return shots


def _find_reports(root: Path) -> Dict[str, bool]:
    """Map platform -> passed, from the chat-*.json reports."""
    results: Dict[str, bool] = {}
    for report in root.rglob("chat-*.json"):
        platform = report.stem.replace("chat-", "")
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        # Reports differ in shape across commands; accept the common spellings
        # rather than pinning one and silently reading None.
        passed = data.get("success")
        if passed is None:
            passed = data.get("passed")
        if passed is None and isinstance(data.get("results"), list):
            passed = all(r.get("success") for r in data["results"])
        if passed is not None:
            # Carry the trace rung too. It is currently REPORTED rather than
            # enforced (upstream KEX/replication revamp), so it is deliberately
            # not part of `success` — but a tile that says only "interact OK"
            # implies a rung nobody checked, which is the exact vacuous-pass
            # shape this gallery exists to make visible.
            results[platform] = (bool(passed), data.get("traces"))
    return results


def _tiles(root: Path) -> List[Tile]:
    shots = _find_shots(root)
    reports = _find_reports(root)
    tiles: List[Tile] = []
    for platform in EXPECTED:
        image = shots.get(platform)
        entry = reports.get(platform)
        passed, traces = entry if entry is not None else (None, None)
        if passed is None and image is None:
            detail = "did not run"
        elif passed is None:
            detail = "ran, no report parsed"
        elif passed:
            detail = "interact OK" if image else "interact OK (no screenshot captured)"
            # The trace rung is REPORTED, not enforced (upstream KEX/replication
            # revamp). A tile reading only "interact OK" would imply a rung nobody
            # checked — the vacuous-pass shape this gallery exists to expose.
            if traces is False:
                detail += " · traces not confirmed (not enforced)"
            elif traces is True:
                detail += " · traces reached canonical"
            else:
                # null — the substrate exposes no replication counter at all
                # (CIRISServer#518). Distinct from False on purpose: "we looked
                # and it had not delivered" and "we cannot see" are different
                # facts, and printing the first for the second is how this
                # claimed a delivery it never observed.
                detail += " · traces not observable on this substrate"
        else:
            detail = "FAILED"
        tiles.append(Tile(platform, image, passed, detail))
    return tiles


def _embed(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _render(tiles: List[Tile], run_url: str = "") -> str:
    cards = []
    for t in tiles:
        if t.passed is True:
            badge, cls = "PASS", "pass"
        elif t.passed is False:
            badge, cls = "FAIL", "fail"
        else:
            badge, cls = "DID NOT RUN", "absent"

        if t.image and t.image.exists():
            img = f'<img src="data:image/png;base64,{_embed(t.image)}" alt="{html.escape(PRETTY[t.platform])} interact screen">'
        else:
            img = '<div class="noshot">no screenshot</div>'

        cards.append(
            f"""      <figure class="card {cls}">
        <figcaption>
          <span class="name">{html.escape(PRETTY[t.platform])}</span>
          <span class="badge {cls}">{badge}</span>
        </figcaption>
        {img}
        <p class="detail">{html.escape(t.detail)}</p>
      </figure>"""
        )

    passed = sum(1 for t in tiles if t.passed is True)
    ran = sum(1 for t in tiles if t.passed is not None)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Five-Platform Live QA</title>
<style>
  :root {{ color-scheme: light dark; --bg:#faf9f7; --fg:#1b1a18; --muted:#6b6862;
           --line:#e2ded7; --card:#fff; --pass:#2f7d4f; --fail:#b3372b; --absent:#8a8478; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --bg:#16171a; --fg:#e9e7e3; --muted:#9a958c; --line:#2c2e33; --card:#1e2024; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:2rem 1.25rem 3rem; background:var(--bg); color:var(--fg);
          font:16px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  header {{ max-width:1400px; margin:0 auto 1.75rem; }}
  h1 {{ font-size:1.5rem; margin:0 0 .35rem; letter-spacing:-.01em; }}
  .sub {{ color:var(--muted); font-size:.9rem; margin:0; }}
  .grid {{ max-width:1400px; margin:0 auto; display:grid; gap:1.25rem;
           grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); }}
  .card {{ margin:0; background:var(--card); border:1px solid var(--line);
           border-radius:10px; overflow:hidden; display:flex; flex-direction:column; }}
  .card.fail {{ border-color:var(--fail); }}
  figcaption {{ display:flex; align-items:center; justify-content:space-between;
                gap:.5rem; padding:.7rem .85rem; border-bottom:1px solid var(--line); }}
  .name {{ font-weight:600; }}
  .badge {{ font-size:.7rem; font-weight:700; letter-spacing:.06em;
            padding:.2rem .45rem; border-radius:4px; color:#fff; background:var(--absent); }}
  .badge.pass {{ background:var(--pass); }}
  .badge.fail {{ background:var(--fail); }}
  img {{ width:100%; height:auto; display:block; background:#000; }}
  .noshot {{ padding:3.5rem 1rem; text-align:center; color:var(--muted);
             font-size:.85rem; background:repeating-linear-gradient(45deg,
             transparent,transparent 8px,rgba(128,128,128,.07) 8px,rgba(128,128,128,.07) 16px); }}
  .detail {{ margin:0; padding:.6rem .85rem; font-size:.82rem; color:var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>Five-Platform Live QA</h1>
  <p class="sub">{passed}/{len(tiles)} passed &middot; {ran}/{len(tiles)} ran &middot;
     each tile is the Interact screen after a real message got a real reply.{run_url}</p>
</header>
<div class="grid">
{chr(10).join(cards)}
</div>
</body>
</html>
"""


def _summary(tiles: List[Tile]) -> str:
    lines = [
        "## Five-Platform Live QA",
        "",
        "| Platform | Result | Screenshot |",
        "|---|---|---|",
    ]
    for t in tiles:
        result = "PASS" if t.passed is True else "FAIL" if t.passed is False else "did not run"
        shot = "yes" if (t.image and t.image.exists()) else "—"
        lines.append(f"| {PRETTY[t.platform]} | {result} | {shot} |")
    lines += [
        "",
        "_Download the **five-platform-gallery** artifact and open `index.html` "
        "to see all five side by side — GitHub cannot render artifact images inline._",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("root", type=Path, help="Directory the artifacts were downloaded into")
    ap.add_argument("--out", type=Path, required=True, help="Where to write index.html")
    ap.add_argument("--summary", type=Path, default=None, help="Append a table here (GITHUB_STEP_SUMMARY)")
    args = ap.parse_args()

    if not args.root.exists():
        print(f"gallery: {args.root} does not exist", file=sys.stderr)
        return 1

    tiles = _tiles(args.root)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(_render(tiles), encoding="utf-8")

    table = _summary(tiles)
    print(table)
    if args.summary:
        try:
            with args.summary.open("a", encoding="utf-8") as fh:
                fh.write(table)
        except OSError as exc:
            print(f"gallery: could not append summary: {exc}", file=sys.stderr)

    ran = sum(1 for t in tiles if t.passed is not None)
    print(f"gallery: {args.out} ({ran}/{len(tiles)} platforms reported)")
    # The gallery REPORTS; the live-qa jobs decide red or green. Failing here
    # would double-count a failure already counted, and would hide the gallery
    # behind its own error exactly when it is needed.
    return 0


if __name__ == "__main__":
    sys.exit(main())
