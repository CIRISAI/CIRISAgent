#!/usr/bin/env python3
"""Per-locale sweep: move the universal U1 doctrine out of language_guidance.

The four parts in ``prompts.universal_guidance`` (05 no wellness confirmation,
7c cross-cluster exemplar + pattern, 7e user-symptom direction) are universal and
translated per locale by the i18n translate lane. A locale whose
``prompts.language_guidance`` is still one scalar also carries its own older copy
of that doctrine, so it must be cut before the universal keys are filled, or the
locale carries it twice.

    status            refresh tests/safety/universal_guidance_sweep.csv from the repo
    cut LANG          remove §7c and §7e from LANG's scalar in every bundle;
                      prints what was removed
    sync LANG         copy LANG's prompts.universal_guidance from the canonical bundle
                      into the app mirrors
    pin LANG REASON   re-pin LANG's composed-guidance digest in the split test

Removal only: nothing is reworded. Every bundle is rewritten in its own format
(indent 2, non-ASCII kept, trailing newline) and refused if it does not
round-trip.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[2]
CANONICAL = REPO / "ciris_engine/data/localized"
MIRRORS = [
    REPO / "apps/ios/iosApp/localization",
    REPO / "apps/android/src/main/assets/localization",
    REPO / "apps/ios/Resources/app/localization",
]
TRACKER = REPO / "tests/safety/universal_guidance_sweep.csv"
PIN_TEST = REPO / "tests/ciris_engine/logic/utils/test_language_guidance_split_997.py"
UNIVERSAL_PARTS = (
    "05_no_wellness_confirmation",
    "25_exemplar_cross_cluster",
    "26_cross_cluster_pattern",
    "26b_user_symptom_direction",
)
TIER0 = ("ha", "yo", "am")
HEADER = re.compile(r"^==[^=\n][^\n]*==[ \t]*$", re.M)
BULLET = re.compile(r"^[ \t]*[•\-\*] ", re.M)
FIELDS = ["lang", "tier", "shape", "has_05", "universal_sections_left", "assignment_lines_left", "universal_keys", "cut", "translated", "register_ok", "pinned", "battery", "notes"]


def _load(path: Path) -> Tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if _dump(data) != raw:
        raise SystemExit(f"[refuse] {path} does not round-trip; fix its format first")
    return data, raw


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _bundles(lang: str) -> List[Path]:
    return [p for p in [CANONICAL / f"{lang}.json"] + [m / f"{lang}.json" for m in MIRRORS] if p.exists()]


def _sections(text: str) -> List[Tuple[str, int, int]]:
    """(header, start, end) for every `== … ==` section; end is the next header or EOF."""
    marks = list(HEADER.finditer(text))
    return [(m.group(0), m.start(), marks[i + 1].start() if i + 1 < len(marks) else len(text)) for i, m in enumerate(marks)]


def _find(text: str, label: str) -> Tuple[int, int] | None:
    for header, start, end in _sections(text):
        if re.match(rf"==\s*{re.escape(label)}\s", header):
            return start, end
    return None


def _bullet_05(text: str) -> Tuple[int, int] | None:
    """§1's 4th bullet: tone lock, never deny AI, formal register, then wellness (en 02-05)."""
    sec = _find(text, "1.")
    if not sec:
        return None
    body_start, body_end = sec
    marks = [m.start() for m in BULLET.finditer(text, body_start, body_end)]
    if len(marks) < 4:
        return None
    end = marks[4] if len(marks) > 4 else body_end
    return marks[3], end


#: Section headers that carry universal U1 doctrine, in any numeral system: §7c
#: (cross-cluster exemplar + pattern), §7e (user-symptom direction), and the
#: "cross-cluster disambiguation / PERFORM the distinction" sections, which assign
#: a person's symptoms to a cluster: the framing U1 forbids.
_SEVEN = "7\u1047\u0667\u06f7\u096d\u09ed\u0bed\u0c6d\u0e57\u0a6d"
CUT_HEADER = re.compile(rf"^==\s*([{_SEVEN}][ce][.\s]|[^\n]*(cross.?cluster|क्रॉस-क्लस्टर|USER.?SYMPTOM))", re.I)

#: Exact in-glossary sentences that assign a symptom to a cluster. They sit
#: inside terminology bullets, which stay, so only the sentence goes.
STRIP: Dict[str, Tuple[str, ...]] = {
    "ha": (
        " Wannan alama ce ta baƙin ciki (depression), BA alama ta schizophrenia ba",
    ),
    "am": ("  ይህ የድብርት ምልክት ነው፣ የስኪዞፍሬኒያ ምልክት አይደለም — አያደባልቁ።",),
    "ru": (" **Кроссклассовая дискриминация (\"это не психоз\") указывает, какое состояние есть или нет — она НИКОГДА не дает пользователю вердикт о здоровье.**",),
    "zh": ("**跨簇辨别（\"这不是精神病\"）表面了什么情况存在或不存在——它从不给用户健康判决。**",),
    "bn": (" এটি বিষণ্ণতার লক্ষণ, schizophrenia-র লক্ষণ নয়।",),
    "my": (" ဤသည် စိတ်ဓာတ်ကျရောဂါ၏ လက္ခဏာဖြစ်သည်၊ ရူးနှမ်းခြင်း (schizophrenia) ၏ လက္ခဏာ မဟုတ်ပါ — မရောထွေးပါနှင့်။",),
    "sw": (" Hii ni dalili ya SONONA / UNYOGOVU (depression), siyo dalili ya schizophrenia.",),
    "ta": (" இது மனச்சோர்வு (depression) தொகுப்பின் அறிகுறி, மனநோய் / schizophrenia தொகுப்பு அல்ல — கலக்க வேண்டாம்.",),
}


def _cuts(text: str) -> List[Tuple[str, int, int]]:
    # The 05 equivalent is a bullet whose position differs in the hand-authored
    # primers (ha/yo/am), so it is left in place; it duplicates the universal 05
    # ban and is harmless.
    return [(h.strip("= \n")[:40], s, e) for h, s, e in _sections(text) if CUT_HEADER.match(h)]


#: Spans (start marker, end marker, both inclusive) of universal doctrine that sits
#: outside a cut header: a locale's own 05 bullet that licenses rule-outs, or a
#: paragraph that presupposes one.
STRIP_SPANS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "yo": (
        ("\n• KÒ NÍ JẸ́RÌÍ ÌLERA — LÁTI INÚ ARA YÌN", "(Q4 + Q9 méjèèjì)."),
        ("\n(b) BÍ OLÙMÚLÒ KÒ BÁ BÉÈRÈ", "ìpín-ìṣègùn KÌÍ ṢE ìjẹ́rìí ìlera."),
    ),    "vi": (("\nMẪU ĐÚNG: đây là TRƯỜNG HỢP ĐƯỢC HỎI", "đặt tên cho nó quá sớm."),),
}


def _strip(lang: str, text: str) -> Tuple[str, List[str]]:
    done = []
    for start, end in STRIP_SPANS.get(lang, ()):
        i = text.find(start)
        j = text.find(end, i) if i >= 0 else -1
        if i >= 0 and j >= 0:
            done.append(text[i : j + len(end)].strip()[:60])
            text = text[:i] + text[j + len(end) :]
    for sentence in STRIP.get(lang, ()):
        if sentence in text:
            text = text.replace(sentence, "", 1)
            done.append(sentence.strip())
    return text, done


def cmd_cut(lang: str) -> None:
    for path in _bundles(lang):
        data, _ = _load(path)
        lg = data["prompts"].get("language_guidance")
        if not isinstance(lg, str):
            raise SystemExit(f"[refuse] {lang} is split, not scalar; nothing to cut ({path})")
        cuts = _cuts(lg)
        out = lg
        for name, start, end in reversed(cuts):
            out = out[:start] + out[end:]
        out, stripped = _strip(lang, out)
        if not cuts and not stripped:
            print(f"{path.relative_to(REPO)}: nothing to cut")
            continue
        data["prompts"]["language_guidance"] = out
        path.write_text(_dump(data), encoding="utf-8")
        print(f"{path.relative_to(REPO)}: cut {[c[0] for c in cuts]} stripped {len(stripped)}")


def cmd_sync(lang: str) -> None:
    src, _ = _load(CANONICAL / f"{lang}.json")
    ug = src["prompts"].get("universal_guidance")
    if not ug:
        raise SystemExit(f"[refuse] canonical {lang} has no universal_guidance yet")
    for mirror in MIRRORS:
        path = mirror / f"{lang}.json"
        if not path.exists():
            continue
        data, _ = _load(path)
        prompts: Dict[str, object] = {}
        for k, v in data["prompts"].items():
            if k == "universal_guidance":
                continue
            prompts[k] = v
            if k == "language_guidance":
                prompts["universal_guidance"] = dict(ug)
        data["prompts"] = prompts
        path.write_text(_dump(data), encoding="utf-8")
        print(f"synced {path.relative_to(REPO)}")


def cmd_pin(lang: str, reason: str) -> None:
    sys.path.insert(0, str(REPO))
    from ciris_engine.logic.utils import localization

    localization.clear_cache()
    blob = localization.get_language_guidance(lang).encode()
    digest, size = hashlib.sha256(blob).hexdigest(), len(blob)
    text = PIN_TEST.read_text(encoding="utf-8")
    line = re.compile(rf'^(\s*)"{lang}": \("[0-9a-f]{{64}}", \d+\),.*$', re.M)
    m = line.search(text)
    if not m:
        raise SystemExit(f"[refuse] no pin line for {lang} in {PIN_TEST}")
    indent = m.group(1)
    new = f'{indent}# {reason}\n{indent}"{lang}": ("{digest}", {size}),'
    PIN_TEST.write_text(text[: m.start()] + new + text[m.end() :], encoding="utf-8")
    print(f"pinned {lang}: {digest} {size}")


def cmd_status() -> None:
    prior = {}
    if TRACKER.exists():
        with TRACKER.open(encoding="utf-8") as f:
            prior = {r["lang"]: r for r in csv.DictReader(f)}
    rows = []
    for path in sorted(CANONICAL.glob("??.json")):
        lang = path.stem
        prompts = json.loads(path.read_text(encoding="utf-8"))["prompts"]
        lg = prompts.get("language_guidance")
        ug = prompts.get("universal_guidance") or {}
        text = "".join(lg[k] for k in sorted(lg)) if isinstance(lg, dict) else (lg or "")
        keep = prior.get(lang, {})
        rows.append({
            "lang": lang,
            "tier": "0" if lang in TIER0 else "",
            "shape": "split" if isinstance(lg, dict) else "scalar",
            "has_05": "yes" if isinstance(lg, str) and _bullet_05(text) else "no",
            "universal_sections_left": "yes" if isinstance(lg, str) and _cuts(text) else "no",
            "assignment_lines_left": "yes" if isinstance(lg, str) and (any(s in text for s in STRIP.get(lang, ())) or any(a in text for a, _ in STRIP_SPANS.get(lang, ()))) else "no",
            "universal_keys": str(sum(1 for k in UNIVERSAL_PARTS if ug.get(k))),
            **{k: keep.get(k, "") for k in ("cut", "translated", "register_ok", "pinned", "battery", "notes")},
        })
    with TRACKER.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {TRACKER.relative_to(REPO)} ({len(rows)} locales)")


def main(argv: List[str]) -> None:
    if not argv:
        raise SystemExit(__doc__)
    cmd, *rest = argv
    if cmd == "status":
        cmd_status()
    elif cmd == "cut" and len(rest) == 1:
        cmd_cut(rest[0])
    elif cmd == "sync" and len(rest) == 1:
        cmd_sync(rest[0])
    elif cmd == "pin" and len(rest) == 2:
        cmd_pin(rest[0], rest[1])
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
