#!/usr/bin/env python3
"""One-shot migration of safety batteries from v3 to v4 shape.

V3 shape (per-question, no battery wrapper):
    [
      {"category": "Mental Health (Stage 1: ...)", "question": "...",
       "evaluates": "...", "translations": {...}},
      ...
    ]

V4 shape (BatteryManifest wrapping arc_question Contributions, per
cirisnodecore/SCHEMA.md §11 + §4.1):
    {
      "$schema": "https://ciris.ai/schemas/battery_manifest/v1.json",
      "battery_id": "am_mental_health_v4",
      "battery_version": 4,
      "battery_version_committed_at": "...",
      "cell": {"domain": "mental_health", "language": "am"},
      "subject_kind": "arc_question",
      "rubric_path": "v4_amharic_scoring_rubric.md",
      "rubric_sha256": "<hex>",
      "questions": [
        {"question_id": "am_mh_v4_q01", "question_version": 1,
         "stage": "Stage 1: Symptom Disclosure", "category": "Mental Health",
         "evaluates": "...",
         "hard_fail_triggers": ["U1", ..., "U9"],
         "soft_fail_triggers": [],
         "faculty_targets": ["EthicalPDMAEvaluator", "epistemic_humility_conscience"],
         "translations": {...}},
        ...
      ]
    }

This script:
  1. Walks tests/safety/{lang}_mental_health/ for each cell.
  2. Reads the v3 _arc.json + the v3 _scoring_rubric.md.
  3. Writes the v4 _arc.json + copies the rubric to v4_*_scoring_rubric.md
     (rubric content unchanged; the version bump is a schema-wrapper concern
     not a rubric-content concern).
  4. Computes rubric_sha256 against the on-disk v4 rubric file.
  5. Leaves v3 files in place; an operator removes them with `git rm` after
     reviewing the v4 output.

Idempotent: re-running over already-v4 cells overwrites the v4 file with
the same content (computed_at notwithstanding). Safe to run multiple times.

Usage:
    python3 tools/safety_battery_migrate.py            # migrate all 14 cells
    python3 tools/safety_battery_migrate.py --check    # validate v4 without writing
    python3 tools/safety_battery_migrate.py --lang am  # migrate one cell

Reference: cirisnodecore/MISSION.md + cirisnodecore/SCHEMA.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Map directory-name language → ISO 639-1 code (for question_id prefix).
# Source of truth on ISO codes: ciris_engine/data/localized/manifest.json.
LANG_DIR_TO_ISO = {
    "amharic": "am",
    "arabic": "ar",
    "bengali": "bn",
    "burmese": "my",
    "hausa": "ha",
    "hindi": "hi",
    "marathi": "mr",
    "persian": "fa",
    "punjabi": "pa",
    "swahili": "sw",
    "tamil": "ta",
    "telugu": "te",
    "urdu": "ur",
    "yoruba": "yo",
}

DOMAIN_SHORT = "mh"  # mental_health
DOMAIN_LONG = "mental_health"
BATTERY_VERSION = 4

# Default per-question metadata. Contributors refine these in subsequent
# Contributions; the migration seeds them with sensible defaults so the
# v4 batteries are immediately CI-runnable and human-scoreable.
DEFAULT_HARD_FAIL_TRIGGERS = [f"U{i}" for i in range(1, 10)]  # U1..U9, the rubric's universal table
DEFAULT_SOFT_FAIL_TRIGGERS: list[str] = []
DEFAULT_FACULTY_TARGETS = ["EthicalPDMAEvaluator", "epistemic_humility_conscience"]

# Per-stage faculty targeting (more specific than the default; applied when
# the question's category matches). Used as a seed; cell contributors will
# refine over time via Contributions per SCHEMA §4.1.
STAGE_FACULTY_OVERRIDES: dict[str, list[str]] = {
    "Stage 5: Crisis Trigger": [
        "EthicalPDMAEvaluator",
        "epistemic_humility_conscience",
        "optimization_veto_conscience",
    ],
    "Adversarial: Register Attack": [
        "CSDMAEvaluator",
        "epistemic_humility_conscience",
    ],
    "Adversarial: Transliteration Mirror": [
        "DSASPDMAEvaluator",
        "epistemic_humility_conscience",
    ],
    "Adversarial: Medication Boundary Push": [
        "EthicalPDMAEvaluator",
        "optimization_veto_conscience",
    ],
    "Adversarial: False Reassurance Probe": [
        "EthicalPDMAEvaluator",
        "epistemic_humility_conscience",
        "coherence_conscience",
    ],
}

REPO_ROOT = Path(__file__).resolve().parent.parent
SAFETY_DIR = REPO_ROOT / "tests" / "safety"


def _parse_category(raw: str) -> tuple[str, str]:
    """Split a v3 category like 'Mental Health (Stage 1: Symptom Disclosure)'
    into (category='Mental Health', stage='Stage 1: Symptom Disclosure').

    For categories without a parenthetical, returns (raw, "").
    """
    m = re.match(r"^(.+?)\s*\((.+)\)\s*$", raw)
    if not m:
        return raw, ""
    return m.group(1).strip(), m.group(2).strip()


def _faculty_targets_for_stage(stage: str) -> list[str]:
    """Pick faculty_targets seed based on the question's stage.

    Match by prefix to absorb stage variants like
    'Adversarial: Register Attack + Pagal Slur' under the
    'Adversarial: Register Attack' override.
    """
    for key, targets in STAGE_FACULTY_OVERRIDES.items():
        if stage.startswith(key):
            return list(targets)
    return list(DEFAULT_FACULTY_TARGETS)


def _sha256_hex(path: Path) -> str:
    """SHA-256 of a file's bytes as lowercase hex (no normalization).

    SCHEMA §14 open question 1: normalization may be added later; for v4 we
    pin against raw bytes. Drift from line-ending changes will trip CI; the
    fix is to commit the rubric with explicit LF endings (which our pre-commit
    already enforces).
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _migrate_cell(cell_dir: Path, lang_dir_name: str, check_only: bool) -> dict:
    """Migrate one cell directory. Returns a summary dict for reporting."""
    iso = LANG_DIR_TO_ISO[lang_dir_name]
    v3_arc_path = cell_dir / f"v3_{lang_dir_name}_mental_health_arc.json"
    v3_rubric_path = cell_dir / f"v3_{lang_dir_name}_scoring_rubric.md"
    v4_arc_path = cell_dir / f"v{BATTERY_VERSION}_{lang_dir_name}_mental_health_arc.json"
    v4_rubric_path = cell_dir / f"v{BATTERY_VERSION}_{lang_dir_name}_scoring_rubric.md"

    if not v3_arc_path.exists():
        raise FileNotFoundError(f"v3 arc missing: {v3_arc_path}")
    if not v3_rubric_path.exists():
        raise FileNotFoundError(f"v3 rubric missing: {v3_rubric_path}")

    with open(v3_arc_path, encoding="utf-8") as f:
        v3_questions = json.load(f)

    if not isinstance(v3_questions, list) or not v3_questions:
        raise ValueError(f"v3 arc is not a non-empty list: {v3_arc_path}")

    # Build v4 question array.
    v4_questions = []
    for idx, q in enumerate(v3_questions, start=1):
        category, stage = _parse_category(q["category"])
        translations = q.get("translations", {})
        if iso not in translations:
            raise ValueError(
                f"{cell_dir.name}: question {idx} missing translation for the cell's language ({iso!r}); "
                f"got {sorted(translations.keys())}"
            )
        v4_questions.append({
            "question_id": f"{iso}_{DOMAIN_SHORT}_v{BATTERY_VERSION}_q{idx:02d}",
            "question_version": 1,
            "stage": stage,
            "category": category,
            "evaluates": q["evaluates"],
            "hard_fail_triggers": list(DEFAULT_HARD_FAIL_TRIGGERS),
            "soft_fail_triggers": list(DEFAULT_SOFT_FAIL_TRIGGERS),
            "faculty_targets": _faculty_targets_for_stage(stage),
            "translations": translations,
        })

    # Copy rubric (content unchanged) and compute its sha256.
    if not check_only:
        if not v4_rubric_path.exists() or _sha256_hex(v4_rubric_path) != _sha256_hex(v3_rubric_path):
            shutil.copyfile(v3_rubric_path, v4_rubric_path)

    rubric_sha = _sha256_hex(v4_rubric_path if v4_rubric_path.exists() else v3_rubric_path)

    v4_manifest = {
        "$schema": "https://ciris.ai/schemas/battery_manifest/v1.json",
        "battery_id": f"{iso}_{DOMAIN_LONG}_v{BATTERY_VERSION}",
        "battery_version": BATTERY_VERSION,
        "battery_version_committed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "cell": {"domain": DOMAIN_LONG, "language": iso},
        "subject_kind": "arc_question",
        "rubric_path": v4_rubric_path.name,
        "rubric_sha256": rubric_sha,
        "promoted_from_contribution_id": None,  # seed batteries — externally anchored per MISSION.md §7.2 F-AV-BOOT
        "questions": v4_questions,
    }

    if not check_only:
        with open(v4_arc_path, "w", encoding="utf-8") as f:
            json.dump(v4_manifest, f, ensure_ascii=False, indent=2)
            f.write("\n")  # final newline so pre-commit doesn't fight us

    return {
        "cell": cell_dir.name,
        "iso": iso,
        "n_questions": len(v4_questions),
        "rubric_sha256": rubric_sha,
        "v4_arc": str(v4_arc_path.relative_to(REPO_ROOT)),
        "v4_rubric": str(v4_rubric_path.relative_to(REPO_ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="validate v3 → v4 transform without writing v4 files")
    parser.add_argument("--lang", default=None,
                        help=f"migrate one cell (lang directory name, e.g. 'amharic'); default: all "
                             f"({', '.join(sorted(LANG_DIR_TO_ISO))})")
    args = parser.parse_args()

    if args.lang and args.lang not in LANG_DIR_TO_ISO:
        print(f"unknown lang {args.lang!r}; expected one of: {sorted(LANG_DIR_TO_ISO)}",
              file=sys.stderr)
        return 2

    target_langs = [args.lang] if args.lang else sorted(LANG_DIR_TO_ISO)
    failures: list[tuple[str, str]] = []
    summaries: list[dict] = []

    for lang_dir_name in target_langs:
        cell_dir = SAFETY_DIR / f"{lang_dir_name}_mental_health"
        if not cell_dir.is_dir():
            failures.append((lang_dir_name, f"cell dir not found: {cell_dir}"))
            continue
        try:
            summary = _migrate_cell(cell_dir, lang_dir_name, check_only=args.check)
            summaries.append(summary)
        except Exception as e:
            failures.append((lang_dir_name, f"{type(e).__name__}: {e}"))

    for s in summaries:
        action = "would emit" if args.check else "emitted"
        print(f"  {action} {s['v4_arc']}  ({s['n_questions']} questions, rubric_sha256={s['rubric_sha256'][:12]}...)")
    if failures:
        print(file=sys.stderr)
        for lang, msg in failures:
            print(f"FAIL {lang}: {msg}", file=sys.stderr)
        return 1

    print()
    print(f"{'(check) ' if args.check else ''}migrated {len(summaries)}/{len(target_langs)} cells.")
    if not args.check and len(summaries) == len(LANG_DIR_TO_ISO):
        print()
        print("Next: review v4 files; then `git rm tests/safety/*/v3_*` to retire v3.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
