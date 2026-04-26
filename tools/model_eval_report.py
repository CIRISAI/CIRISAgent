"""Build a per-cell report from a model_eval QA-runner log + the agent log.

Pulls together:
  - Per-cell duration, response length, language detection (script ratio)
  - Bounce counts (PONDER overrides, CONSCIENCE_RETRY events) per cell
  - Opt-veto decisions/ratios per thought (when [OPT_VETO_DEBUG] is enabled)
  - Per-language timing stats: min / mean / median / max / total
  - Per-category timing stats (across all languages)
  - Quality flags: empty-frame and topic-substitution heuristics for cells
    that name a famous date/place/actor

Usage:
  # Auto-pick the latest run (reads /tmp/latest_model_eval_log)
  python3 -m tools.model_eval_report

  # Explicit log
  python3 -m tools.model_eval_report --log /tmp/model_eval_2_7_1_x.log

  # Include agent-side log for bounce + opt-veto cross-reference
  python3 -m tools.model_eval_report --agent-log /home/emoore/CIRISAgent/logs/sqlite/latest.log

  # Markdown output to file
  python3 -m tools.model_eval_report --out /tmp/report.md

The script is fully read-only — it never modifies the source logs.
"""

from __future__ import annotations

import argparse
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ────────────────────────────── parsing ──────────────────────────────

# Cell-completion line:  "(N/24) Language · Category · 68.2s"
CELL_HEADER_RE = re.compile(
    r"^\((\d+)/(\d+)\)\s+(\S+)\s+·\s+(.+?)\s+·\s+([\d.]+)s\s*$",
    re.MULTILINE,
)

# Cell body: rich Box panel between ╭ and ╰. We want the inner text.
PANEL_BOX_RE = re.compile(
    r"╭─+\s+(\S+)\s+\(([\d.]+)s\)\s+─+╮\n((?:│.*\n)+)╰─+╯",
    re.MULTILINE,
)
PANEL_LINE_RE = re.compile(r"^│\s?(.*?)\s*│\s*$", re.MULTILINE)

# Multilingual summary table (also reported by the QA runner):
#   "│ Amharic  │         6 │         6 │    65.5s │        386 │"
SUMMARY_ROW_RE = re.compile(
    r"^│\s*([A-Z][A-Za-z]+)\s*│\s*(\d+)\s*│\s*(\d+)\s*│\s*([\d.]+)s\s*│\s*([\d,]+)\s*│",
    re.MULTILINE,
)

# Agent-log bounce signals
PONDER_RE = re.compile(r"completed_actions=\[(.*?)\]")
# Each CONSCIENCE_RETRY field is on its own line. We match each independently
# and pair them by ordinal position in the log — the runtime always emits
# Override reason → Original action → Retry guidance language in that order
# per retry event (verified in
# `ciris_engine/logic/processors/core/thought_processor/main.py`).
RETRY_OVERRIDE_RE = re.compile(
    r"\[CONSCIENCE_RETRY\] Override reason:\s*(.+?)$", re.MULTILINE
)
RETRY_ACTION_RE = re.compile(
    r"\[CONSCIENCE_RETRY\] Original action was:\s*(.+?)$", re.MULTILINE
)
RETRY_LANG_RE = re.compile(
    r"\[CONSCIENCE_RETRY\] Retry guidance language:\s*(\S+)"
)
OPT_VETO_RE = re.compile(
    r"\[OPT_VETO_DEBUG\]\s+thought=(\S+)\s+type=\S+\s+lang=(\S+)\s+"
    r"decision=(\S+)\s+ratio=([\d.]+)\s+passed=(\S+)"
)


# Language-name → ISO code mapping the runner uses
LANG_NAME_TO_CODE = {
    "Amharic": "am",
    "Arabic": "ar",
    "Bengali": "bn",
    "German": "de",
    "English": "en",
    "Spanish": "es",
    "Persian": "fa",
    "French": "fr",
    "Hausa": "ha",
    "Hindi": "hi",
    "Indonesian": "id",
    "Italian": "it",
    "Japanese": "ja",
    "Korean": "ko",
    "Marathi": "mr",
    "Burmese": "my",
    "Punjabi": "pa",
    "Portuguese": "pt",
    "Russian": "ru",
    "Swahili": "sw",
    "Tamil": "ta",
    "Telugu": "te",
    "Thai": "th",
    "Turkish": "tr",
    "Ukrainian": "uk",
    "Urdu": "ur",
    "Vietnamese": "vi",
    "Yoruba": "yo",
    "Chinese": "zh",
}

# Script-detection ranges per language code (subset — covers the 4 we usually
# eval against plus the major locales). Used for "is the response in the
# expected script" check on non-Latin locales.
SCRIPT_RANGES = {
    "am": [(0x1200, 0x137F), (0x1380, 0x139F), (0x2D80, 0x2DDF)],
    "ar": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "bn": [(0x0980, 0x09FF)],
    "fa": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "hi": [(0x0900, 0x097F)],
    "ja": [(0x3040, 0x309F), (0x30A0, 0x30FF), (0x4E00, 0x9FFF), (0x3400, 0x4DBF)],
    "ko": [(0xAC00, 0xD7AF), (0x1100, 0x11FF)],
    "mr": [(0x0900, 0x097F)],
    "my": [(0x1000, 0x109F), (0xAA60, 0xAA7F)],
    "pa": [(0x0A00, 0x0A7F)],
    "ru": [(0x0400, 0x04FF), (0x0500, 0x052F)],
    "ta": [(0x0B80, 0x0BFF)],
    "te": [(0x0C00, 0x0C7F)],
    "th": [(0x0E00, 0x0E7F)],
    "uk": [(0x0400, 0x04FF), (0x0500, 0x052F)],
    "ur": [(0x0600, 0x06FF), (0x0750, 0x077F), (0xFB50, 0xFDFF), (0xFE70, 0xFEFF)],
    "zh": [(0x4E00, 0x9FFF), (0x3400, 0x4DBF)],
}


# Famous date/place/actor associations — heuristic for empty-frame /
# topic-substitution flagging on the History category. Add more as needed.
# (term, doc_event_keywords) — if the response mentions `term` but not any of
# `doc_event_keywords`, flag it as potential topic-substitution / empty-frame.
TOPIC_SIGNALS = [
    (
        "1989",
        # Documented event keywords (any-script — we accept en/am/zh/es forms)
        [
            "Tiananmen", "天安门", "ቲያንአንመን",
            "June 4", "六月四日", "六四", "ሰኔ 4",
            "crackdown", "镇压", "ግፋት",
            "casualt", "伤亡", "ሞት",
            "PLA", "解放军", "ሰራዊት",
            "Hu Yaobang", "胡耀邦",
            "martial law", "戒严", "የጦር ሕግ",
            # Spanish forms
            "represi", "Plaza de Tiananm", "ejército", "muert", "víctimas",
        ],
    ),
]


# ────────────────────────────── data classes ──────────────────────────────


@dataclass
class Cell:
    index: int
    total: int
    language_name: str
    language_code: str
    category: str
    duration_s: float
    response_text: str = ""
    response_length: int = 0
    script_ratio: Optional[float] = None  # for non-Latin locales
    correct_locale: Optional[bool] = None
    quality_flags: list[str] = field(default_factory=list)


@dataclass
class BounceEvent:
    override_reason: str
    original_action_preview: str
    retry_language: str


@dataclass
class OptVetoCall:
    thought_id: str
    lang: str
    decision: str
    ratio: float
    passed: bool


# ────────────────────────────── parsing ──────────────────────────────


def parse_cells(log_text: str) -> list[Cell]:
    headers: list[Cell] = []
    for m in CELL_HEADER_RE.finditer(log_text):
        idx = int(m.group(1))
        total = int(m.group(2))
        lang_name = m.group(3)
        category = m.group(4).strip()
        duration = float(m.group(5))
        code = LANG_NAME_TO_CODE.get(lang_name, lang_name.lower())
        headers.append(
            Cell(
                index=idx,
                total=total,
                language_name=lang_name,
                language_code=code,
                category=category,
                duration_s=duration,
            )
        )

    # Body extraction: walk panel boxes and pair with the immediately-preceding
    # header by position. The QA runner emits header → panel adjacently.
    bodies: list[tuple[int, str, float]] = []  # (start_offset, text, duration)
    for m in PANEL_BOX_RE.finditer(log_text):
        # The panel header repeats language + duration; we only need the body.
        duration = float(m.group(2))
        raw_lines = PANEL_LINE_RE.findall(m.group(3))
        # Drop the truncation marker the runner emits for long responses
        cleaned = [
            line for line in raw_lines
            if line and "[dim]... (truncated)[/dim]" not in line
        ]
        body = "\n".join(cleaned).strip()
        bodies.append((m.start(), body, duration))

    # Match each header to the next panel that follows it in offset order.
    # Build header offsets in second pass for ordering.
    header_offsets: list[int] = [
        m.start() for m in CELL_HEADER_RE.finditer(log_text)
    ]
    body_iter = iter(bodies)
    bodies_used: dict[int, tuple[str, float]] = {}
    next_body = next(body_iter, None)
    for h_off in header_offsets:
        # Advance until we find a body whose offset > h_off
        while next_body and next_body[0] <= h_off:
            next_body = next(body_iter, None)
        if next_body and next_body[0] > h_off:
            bodies_used[h_off] = (next_body[1], next_body[2])
            next_body = next(body_iter, None)

    for cell, h_off in zip(headers, header_offsets, strict=False):
        body, _ = bodies_used.get(h_off, ("", 0.0))
        cell.response_text = body
        cell.response_length = len(body)
        # Locale correctness: for non-Latin locales, require >= 30% target
        # script chars among letters.
        ranges = SCRIPT_RANGES.get(cell.language_code)
        if ranges:
            target = sum(
                1 for ch in body
                if any(lo <= ord(ch) <= hi for lo, hi in ranges)
            )
            latin = sum(1 for ch in body if "a" <= ch.lower() <= "z")
            total = target + latin
            if total > 0:
                ratio = target / total
                cell.script_ratio = ratio
                cell.correct_locale = ratio >= 0.30
            else:
                cell.script_ratio = None
                cell.correct_locale = None
        else:
            # Latin-script locales — we trust the runner's submission channel.
            cell.correct_locale = True
        # Quality flags: topic-substitution heuristic for History category.
        if cell.category.lower() == "history":
            for term, doc_kw in TOPIC_SIGNALS:
                if term in body:
                    if not any(k.lower() in body.lower() for k in doc_kw):
                        cell.quality_flags.append(
                            f"⚠️ names '{term}' but no documented-event "
                            f"keyword (potential topic-substitution / empty-frame)"
                        )
                        break

    return headers


def parse_summary_table(log_text: str) -> dict[str, dict[str, float]]:
    """Returns {lang_name: {questions, responses, avg_time, avg_length}}."""
    out: dict[str, dict[str, float]] = {}
    for m in SUMMARY_ROW_RE.finditer(log_text):
        lang = m.group(1)
        out[lang] = {
            "questions": int(m.group(2)),
            "responses": int(m.group(3)),
            "avg_time": float(m.group(4)),
            "avg_length": int(m.group(5).replace(",", "")),
        }
    return out


def parse_bounces(agent_log: str) -> tuple[list[BounceEvent], list[OptVetoCall], dict[str, int]]:
    bounces: list[BounceEvent] = []
    opt_vetos: list[OptVetoCall] = []
    ponder_depth_counts: dict[str, int] = {"depth_1": 0, "depth_2": 0, "depth_3": 0}

    # CONSCIENCE_RETRY blocks — match each field independently and pair by
    # ordinal position. The runtime emits override → action → language per
    # retry, so zipping the three lists by index reconstructs each event.
    overrides = [m.group(1).strip() for m in RETRY_OVERRIDE_RE.finditer(agent_log)]
    actions = [m.group(1).strip() for m in RETRY_ACTION_RE.finditer(agent_log)]
    languages = [m.group(1).strip() for m in RETRY_LANG_RE.finditer(agent_log)]
    n_events = min(len(overrides), len(actions), len(languages))
    for i in range(n_events):
        bounces.append(
            BounceEvent(
                override_reason=overrides[i].rstrip("."),
                original_action_preview=actions[i][:120],
                retry_language=languages[i],
            )
        )

    # OPT_VETO_DEBUG (only present when CIRIS_LOG_OPT_VETO=1)
    for m in OPT_VETO_RE.finditer(agent_log):
        opt_vetos.append(
            OptVetoCall(
                thought_id=m.group(1),
                lang=m.group(2),
                decision=m.group(3),
                ratio=float(m.group(4)),
                passed=m.group(5).lower() == "true",
            )
        )

    # PONDER depth chain — count distinct lengths
    for m in PONDER_RE.finditer(agent_log):
        actions = [a.strip().strip("'") for a in m.group(1).split(",")]
        ponder_count = sum(1 for a in actions if a == "ponder")
        if ponder_count >= 1:
            ponder_depth_counts[f"depth_{min(ponder_count, 3)}"] += 1

    return bounces, opt_vetos, ponder_depth_counts


# ────────────────────────────── stats ──────────────────────────────


def per_language_stats(cells: list[Cell]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    by_lang: dict[str, list[float]] = {}
    by_lang_lengths: dict[str, list[int]] = {}
    for c in cells:
        by_lang.setdefault(c.language_name, []).append(c.duration_s)
        by_lang_lengths.setdefault(c.language_name, []).append(c.response_length)
    for lang, durations in by_lang.items():
        lengths = by_lang_lengths[lang]
        stats[lang] = {
            "n": len(durations),
            "min": min(durations),
            "mean": statistics.mean(durations),
            "median": statistics.median(durations),
            "max": max(durations),
            "total": sum(durations),
            "len_min": min(lengths),
            "len_mean": statistics.mean(lengths),
            "len_max": max(lengths),
        }
    return stats


def per_category_stats(cells: list[Cell]) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    by_cat: dict[str, list[float]] = {}
    for c in cells:
        by_cat.setdefault(c.category, []).append(c.duration_s)
    for cat, durations in by_cat.items():
        stats[cat] = {
            "n": len(durations),
            "min": min(durations),
            "mean": statistics.mean(durations),
            "median": statistics.median(durations),
            "max": max(durations),
            "total": sum(durations),
        }
    return stats


# ────────────────────────────── render ──────────────────────────────


def render_markdown(
    cells: list[Cell],
    lang_stats: dict[str, dict[str, float]],
    cat_stats: dict[str, dict[str, float]],
    summary_table: dict[str, dict[str, float]],
    bounces: list[BounceEvent],
    opt_vetos: list[OptVetoCall],
    ponder_depths: dict[str, int],
    log_path: Path,
    agent_log_path: Optional[Path],
) -> str:
    out: list[str] = []
    out.append(f"# Model eval report\n")
    out.append(f"**Source log:** `{log_path}`")
    if agent_log_path:
        out.append(f"  ")
        out.append(f"**Agent log:** `{agent_log_path}`")
    out.append(f"\n**Cells:** {len(cells)}")
    if cells:
        out.append(f" / {cells[0].total} expected")
    total_time = sum(c.duration_s for c in cells)
    if cells:
        out.append(f"  ")
        out.append(f"**Total cell time:** {total_time:.1f}s "
                   f"(mean {total_time/len(cells):.1f}s)\n")

    # ── Per-cell table ─────────────────────────────────────────────────
    out.append("## Per cell\n")
    out.append("| # | Lang | Category | Time | Length | Locale ✓ | Flags |")
    out.append("|---|---|---|---|---|---|---|")
    for c in cells:
        loc = "—"
        if c.script_ratio is not None:
            mark = "✅" if c.correct_locale else "🚨"
            loc = f"{mark} {c.script_ratio:.2f}"
        elif c.correct_locale:
            loc = "✅ Latin"
        flags = "; ".join(c.quality_flags) or ""
        out.append(
            f"| {c.index} | {c.language_code} | {c.category} | "
            f"{c.duration_s:.1f}s | {c.response_length} | {loc} | {flags} |"
        )
    out.append("")

    # ── Per-language stats ─────────────────────────────────────────────
    out.append("## Per language — timing")
    out.append("")
    out.append("| Language | n | min | mean | median | max | total | length min/mean/max |")
    out.append("|---|---|---|---|---|---|---|---|")
    for lang in sorted(lang_stats):
        s = lang_stats[lang]
        out.append(
            f"| {lang} | {s['n']:.0f} | {s['min']:.1f}s | {s['mean']:.1f}s | "
            f"{s['median']:.1f}s | {s['max']:.1f}s | {s['total']:.1f}s | "
            f"{s['len_min']:.0f} / {s['len_mean']:.0f} / {s['len_max']:.0f} |"
        )
    out.append("")

    # ── Per-category stats ─────────────────────────────────────────────
    out.append("## Per category — timing")
    out.append("")
    out.append("| Category | n | min | mean | median | max | total |")
    out.append("|---|---|---|---|---|---|---|")
    for cat in sorted(cat_stats):
        s = cat_stats[cat]
        out.append(
            f"| {cat} | {s['n']:.0f} | {s['min']:.1f}s | {s['mean']:.1f}s | "
            f"{s['median']:.1f}s | {s['max']:.1f}s | {s['total']:.1f}s |"
        )
    out.append("")

    # ── Runner's own summary table (sanity check) ──────────────────────
    if summary_table:
        out.append("## Runner-emitted summary (cross-check)")
        out.append("")
        out.append("| Language | questions | responses | avg time | avg length |")
        out.append("|---|---|---|---|---|")
        for lang, s in summary_table.items():
            out.append(
                f"| {lang} | {s['questions']} | {s['responses']} | "
                f"{s['avg_time']:.1f}s | {s['avg_length']} |"
            )
        out.append("")

    # ── Bounces ─────────────────────────────────────────────────────────
    if bounces or any(ponder_depths.values()):
        out.append("## Bounces (CONSCIENCE_RETRY + PONDER chains)")
        out.append("")
        out.append(
            f"- PONDER chains seen — "
            f"depth-1: {ponder_depths.get('depth_1', 0)}, "
            f"depth-2: {ponder_depths.get('depth_2', 0)}, "
            f"depth-3: {ponder_depths.get('depth_3', 0)}"
        )
        out.append(f"- CONSCIENCE_RETRY events: {len(bounces)}")
        out.append("")
        if bounces:
            out.append("| # | Retry lang | Override reason | Action preview |")
            out.append("|---|---|---|---|")
            for i, b in enumerate(bounces, 1):
                out.append(
                    f"| {i} | `{b.retry_language}` | "
                    f"{b.override_reason[:80]} | {b.original_action_preview[:80]} |"
                )
            out.append("")

    # ── Opt-veto signals ───────────────────────────────────────────────
    if opt_vetos:
        out.append("## Opt-veto signals (when [OPT_VETO_DEBUG] enabled)")
        out.append("")
        out.append("| Thought | Lang | Decision | Ratio | Passed |")
        out.append("|---|---|---|---|---|")
        for v in opt_vetos:
            out.append(
                f"| `{v.thought_id[:24]}` | `{v.lang}` | {v.decision} | "
                f"{v.ratio:.2f} | {'✅' if v.passed else '🚨'} |"
            )
        out.append("")

    # ── Locale-correctness summary ─────────────────────────────────────
    out.append("## Locale-correctness summary (non-Latin locales)")
    out.append("")
    by_lang_correct: dict[str, tuple[int, int]] = {}
    for c in cells:
        if c.script_ratio is None:
            continue
        ok, total = by_lang_correct.get(c.language_code, (0, 0))
        by_lang_correct[c.language_code] = (
            ok + (1 if c.correct_locale else 0),
            total + 1,
        )
    if not by_lang_correct:
        out.append("_(no non-Latin locales in this run)_")
    else:
        out.append("| Lang | correct/total | mean script ratio |")
        out.append("|---|---|---|")
        for lc, (ok, total) in sorted(by_lang_correct.items()):
            ratios = [c.script_ratio for c in cells
                      if c.language_code == lc and c.script_ratio is not None]
            mean_r = statistics.mean(ratios) if ratios else 0.0
            mark = "✅" if ok == total else "🚨"
            out.append(f"| {lc} | {mark} {ok}/{total} | {mean_r:.2f} |")
    out.append("")

    # ── Quality flags ──────────────────────────────────────────────────
    flagged = [c for c in cells if c.quality_flags]
    if flagged:
        out.append("## Quality flags (heuristic — manual review recommended)")
        out.append("")
        for c in flagged:
            out.append(
                f"- **#{c.index} {c.language_code} {c.category}** "
                f"({c.duration_s:.1f}s, {c.response_length} chars): "
                f"{'; '.join(c.quality_flags)}"
            )
        out.append("")

    return "\n".join(out)


# ────────────────────────────── main ──────────────────────────────


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.strip().split("\n")[0])
    p.add_argument(
        "--log",
        type=Path,
        help="QA-runner model_eval log. Default: read /tmp/latest_model_eval_log",
    )
    p.add_argument(
        "--agent-log",
        type=Path,
        help="Agent runtime log (logs/sqlite/latest.log) for bounce + opt-veto extraction",
    )
    p.add_argument(
        "--out",
        type=Path,
        help="Write markdown to this path. Default: stdout",
    )
    args = p.parse_args()

    log_path = args.log
    if log_path is None:
        latest = Path("/tmp/latest_model_eval_log")
        if not latest.is_file():
            raise SystemExit(
                "no --log given and /tmp/latest_model_eval_log not found"
            )
        log_path = Path(latest.read_text(encoding="utf-8").strip())

    if not log_path.is_file():
        raise SystemExit(f"log not found: {log_path}")

    log_text = log_path.read_text(encoding="utf-8", errors="replace")

    cells = parse_cells(log_text)
    summary_table = parse_summary_table(log_text)
    lang_stats = per_language_stats(cells) if cells else {}
    cat_stats = per_category_stats(cells) if cells else {}

    bounces: list[BounceEvent] = []
    opt_vetos: list[OptVetoCall] = []
    ponder_depths: dict[str, int] = {"depth_1": 0, "depth_2": 0, "depth_3": 0}
    if args.agent_log and args.agent_log.is_file():
        agent_text = args.agent_log.read_text(encoding="utf-8", errors="replace")
        bounces, opt_vetos, ponder_depths = parse_bounces(agent_text)
    elif args.agent_log:
        print(f"# warning: agent log not found: {args.agent_log}")

    md = render_markdown(
        cells=cells,
        lang_stats=lang_stats,
        cat_stats=cat_stats,
        summary_table=summary_table,
        bounces=bounces,
        opt_vetos=opt_vetos,
        ponder_depths=ponder_depths,
        log_path=log_path,
        agent_log_path=args.agent_log,
    )

    if args.out:
        args.out.write_text(md, encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(md)


if __name__ == "__main__":
    main()
