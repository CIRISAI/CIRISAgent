#!/usr/bin/env python3
"""Repair the MECHANICAL half of the localization placeholder damage (#952).

Two defect classes, both created by running a translation pipeline over the
values without protecting the interpolation tokens inside them:

  placeholder-corrupt   the token's NAME got translated —  en `{tool_name}`
                        became mr `{साधन_name}`, my `{ကိရိယာ_name}`,
                        `{action}` became `{कृतीion}` (only "act" matched a
                        dictionary entry). str.format never sees the key it
                        expects, so the brace text renders to the user.

  placeholder-doubled   `{count}` became `{{count}}`, which format() renders as
                        a literal `{count}`.

Both are repairable WITHOUT translation judgement, which is the whole reason
they are separated from placeholder-parity: the correct token name is not a
matter of opinion, it is whatever en uses. The surrounding translated prose is
never touched — only the text between the braces, and only when the repair
makes the value's placeholder set exactly equal to English's.

That last condition is the safety property. A value whose placeholders are
missing or extra (placeholder-parity) is NOT repaired here: dropping a token
means the translation lost information, and inventing one means guessing where
it belongs. Those need a translator. This tool declines them and says so.

Usage:
    python3 tools/dev/fix_localization_placeholders.py            # report only
    python3 tools/dev/fix_localization_placeholders.py --write    # apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_localization_sync import PRIMARY_BUNDLE, manifest_languages  # noqa: E402

# Source of truth per test_kotlin_localizations::test_localization_files_in_sync.
# Note this is NOT check_localization_sync.PRIMARY_BUNDLE (the Android bundle) —
# that is one of the mirrors. All six are byte-identical, so reading either
# works; writing must hit every one or the sync test goes red.
SOURCE_BUNDLE = "ciris_engine/data/localized"

MIRRORS: Tuple[str, ...] = (
    "client/iosApp/iosApp/localization",
    "client/iosApp/Resources/app/localization",
    "client/androidApp/src/main/assets/localization",
    "client/desktopApp/src/main/resources/localization",
    "client/shared/src/desktopMain/resources/localization",
)

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")


def flatten(obj: dict, prefix: str = "") -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in obj.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, str):
            out[key] = v
    return out


def placeholders(text: str) -> List[str]:
    return _PLACEHOLDER.findall(text)


def repair_value(en_val: str, loc_val: str) -> Tuple[str, List[str]]:
    """Return (repaired, notes). Returns loc_val unchanged when not repairable."""
    en_ph = placeholders(en_val)
    if not en_ph:
        return loc_val, []

    notes: List[str] = []
    work = loc_val

    # 1. De-double. Done textually and before parsing, because `\{([^{}]*)\}`
    #    matches the INNER braces of `{{count}}` and would report it as a
    #    healthy `{count}`.
    for name in set(en_ph):
        doubled = "{{" + name + "}}"
        if doubled in work:
            work = work.replace(doubled, "{" + name + "}")
            notes.append(f"doubled:{name}")

    # 2. Rename corrupted tokens positionally. Only safe when the counts already
    #    line up — otherwise we would be choosing which token went missing.
    loc_ph = placeholders(work)
    if len(loc_ph) == len(en_ph):
        rebuilt: List[str] = []
        idx = 0
        pos = 0
        for m in _PLACEHOLDER.finditer(work):
            rebuilt.append(work[pos : m.start()])
            inner = m.group(1)
            want = en_ph[idx]
            # A token is corrupt when it is not a bare identifier, or names
            # something English never declared for this key.
            if inner != want and (not inner.isidentifier() or inner not in en_ph):
                rebuilt.append("{" + want + "}")
                notes.append(f"corrupt:{inner}->{want}")
            else:
                rebuilt.append(m.group(0))
            pos = m.end()
            idx += 1
        rebuilt.append(work[pos:])
        work = "".join(rebuilt)

    # Safety gate: only accept a repair that lands exactly on English's tokens.
    if sorted(placeholders(work)) != sorted(en_ph):
        return loc_val, []
    return work, notes


def apply(tree: dict, key: str, value: str) -> None:
    parts = key.split(".")
    node = tree
    for p in parts[:-1]:
        node = node[p]
    node[parts[-1]] = value


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="apply repairs (default: report only)")
    args = ap.parse_args()

    bundle = REPO_ROOT / SOURCE_BUNDLE
    en = flatten(json.load(open(bundle / "en.json", encoding="utf-8")))

    total_fixed = 0
    total_declined = 0
    for lang in manifest_languages(REPO_ROOT / PRIMARY_BUNDLE):
        if lang == "en":
            continue
        path = bundle / f"{lang}.json"
        if not path.exists():
            continue
        tree = json.load(open(path, encoding="utf-8"))
        loc = flatten(tree)

        fixed: List[str] = []
        declined: List[str] = []
        for key, en_val in en.items():
            loc_val = loc.get(key)
            if loc_val is None or not placeholders(en_val):
                continue
            if sorted(placeholders(loc_val)) == sorted(placeholders(en_val)) and "{{" not in loc_val:
                continue
            new_val, notes = repair_value(en_val, loc_val)
            if new_val != loc_val:
                apply(tree, key, new_val)
                fixed.append(f"{key}: {', '.join(notes)}")
            else:
                declined.append(key)

        if fixed:
            print(f"{lang}: repaired {len(fixed)}")
            for line in fixed[:4]:
                print(f"    {line}")
            if len(fixed) > 4:
                print(f"    … and {len(fixed) - 4} more")
        if declined:
            print(f"{lang}: DECLINED {len(declined)} (placeholder-parity — needs a translator, not this tool)")
        total_fixed += len(fixed)
        total_declined += len(declined)

        if fixed and args.write:
            # indent=2 / ensure_ascii=False round-trips these files byte-exactly,
            # so the diff is the repairs and nothing else.
            blob = json.dumps(tree, indent=2, ensure_ascii=False) + "\n"
            path.write_text(blob, encoding="utf-8")
            for mirror in MIRRORS:
                mpath = REPO_ROOT / mirror / f"{lang}.json"
                if mpath.exists():
                    mpath.write_text(blob, encoding="utf-8")

    print()
    print(f"repaired {total_fixed} value(s); declined {total_declined} (placeholder-parity)")
    if not args.write:
        print("dry run — re-run with --write to apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
