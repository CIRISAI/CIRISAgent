#!/usr/bin/env python3
"""Apply and verify Ukrainian retranslation batches (CIRISAgent#949).

`uk.json` is substantially Russian: 1591 of 3676 values are either byte-identical
to `ru.json` or contain Russian-only letters (ы/ъ/э/ё). Some are worse than plain
Russian — a Russian sentence with a Ukrainian conjunction dropped in:

    "Получить баланс счёта, историю транзакций і детали счёта"
                                              ^ lone Ukrainian word

That reads as a find-and-replace half-applied, which to a Ukrainian speaker is
more insulting than an honest Russian string. Given who this locale is for, it is
not a cosmetic defect.

WHY A TOOL AND NOT A SED. The previous damage looks exactly like what a
mechanical substitution produces. This script never invents a translation: it
only applies a reviewed `{russian: ukrainian}` map, and REFUSES any entry that
fails the checks below. Translation is a human/model judgement; this is the
gate around it.

    verify   — report what still needs work, by namespace
    apply    — apply a batch file to all six mirrors, with checks
    audit    — post-apply: placeholders, JSON validity, residual Russian

Batch files live in tools/dev/uk_batches/*.json and are kept, so a disputed
string can be traced to the batch that introduced it.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Every mirror that must stay in lockstep. The localization guard fails the
#: build if these diverge, and #1012 showed that "four of six" is a silent gap.
MIRRORS = [
    "ciris_engine/data/localized",
    "client/androidApp/src/main/assets/localization",
    "client/desktopApp/src/main/resources/localization",
    "client/iosApp/iosApp/localization",
    "client/iosApp/Resources/app/localization",
    "client/shared/src/desktopMain/resources/localization",
]

RU_ONLY = set("ыъэё")
UK_ONLY = set("іїєґ")
#: `{}`-style and `{{}}`-style placeholders both appear in this corpus.
PLACEHOLDER = re.compile(r"\{\{?[a-zA-Z_][a-zA-Z0-9_]*\}?\}")


#: Russian stems that survive a naive "add Ukrainian endings" pass. The corpus
#: was already damaged that way once — "Получить баланс … і детали счёта" — so a
#: batch that merely avoids ы/ъ/э/ё is NOT yet Ukrainian. Each entry is
#: (russian_fragment, the ukrainian it should have been).
RU_STEMS = [
    ("ошибк", "помилк"), ("пользовател", "користувач"), ("настройк", "налаштуван"),
    ("сообщени", "повідомлен"), ("создат", "створит"), ("удалит", "видалит"),
    ("сохранит", "зберегт"), ("загрузк", "завантажен"), ("отключ", "вимкн"),
    ("попробуйте", "спробуйте"), ("текущ", "поточн"),
    ("значени", "значенн"), ("получит", "отримат"), ("отправит", "надіслат"),
    ("подключени", "з'єднанн"), ("устройств", "пристро"),
    ("количеств", "кількіст"), ("состояни", "стан"), ("выполн", "викон"),
    ("измени", "змін"), ("добави", "додай"), ("найден", "знайден"),
    ("сброс", "скидан"), ("аккаунт", "акаунт"), ("который", "який"),
    # NOT in this list, and deliberately — each fires on CORRECT Ukrainian:
    #   "недоступ"  `недоступна` is the same word in both languages
    #   "включ"     `включно з` ("including") is Ukrainian; only `отключ` is
    #               reliably Russian, since Ukrainian uses `вимкн`.
    # Both were found by the linter rejecting good translations, which is the
    # cheapest possible place to find them.
    ("если", "якщо"), ("или", "або"), ("что", "що"), ("это", "це"),
]


def lint_translation(dst: str) -> list[str]:
    """Russian stems left in a supposedly-Ukrainian string.

    Structural checks (letters, placeholders) cannot see this: "Отключено" has no
    ы/ъ/э/ё and is still Russian. This is the check that would have caught the
    original damage, so it runs on every batch rather than on a sample.
    """
    # WORD-INITIAL ONLY. A bare substring test fires inside correct Ukrainian:
    # `визначених` contains `значени`, `не знайдено` contains `найден`. Four of
    # the first batch's translations were rejected for being right, which is the
    # failure mode this whole file exists to avoid — a check that cannot pass.
    low = dst.lower()
    hits = []
    for ru, uk in RU_STEMS:
        if re.search(rf"(?<![а-яіїєґ']){re.escape(ru)}", low):
            hits.append(f"{ru} (should be {uk})")
    return hits


def flat(d: dict, pre: str = "") -> dict:
    out = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out.update(flat(v, f"{pre}{k}."))
        elif isinstance(v, str):
            out[f"{pre}{k}"] = v
    return out


def set_path(d: dict, dotted: str, value: str) -> bool:
    cur = d
    parts = dotted.split(".")
    for p in parts[:-1]:
        if not isinstance(cur.get(p), dict):
            return False
        cur = cur[p]
    if parts[-1] not in cur:
        return False
    cur[parts[-1]] = value
    return True


def _declared_identical() -> set[str]:
    """Strings a human confirmed are the same word in Ukrainian and Russian.

    Without this, `verify` can never reach zero: product names and genuinely
    shared vocabulary are byte-identical to ru.json by definition, and they would
    sit in the count forever, training everyone to ignore a non-zero number. The
    fix is a reviewed declaration, NOT a looser detector — the detector stays
    strict so anything NEW that matches Russian still surfaces.
    """
    f = ROOT / "tools/dev/uk_identical_allowlist.json"
    if not f.exists():
        return set()
    return set(json.loads(f.read_text(encoding="utf-8")).get("identical", []))


def needs_work(uk: dict, ru: dict) -> list[str]:
    """Keys whose value is Russian, by the two signals that do not false-positive.

    `ы/ъ/э/ё` are absent from Ukrainian entirely. Byte-identity with `ru.json` on
    a string over three characters is the other: sampled by hand, these are
    Russian ("Создан", "Скопировать URL", "ОПАСНОСТЬ"), not shared vocabulary.

    Deliberately NOT used: "contains no і/ї/є". Plenty of correct Ukrainian
    ("Скасувати") has none, and flagging it would send a translator to rewrite
    strings that are already right.
    """
    declared = _declared_identical()
    out = []
    for k, v in uk.items():
        s = v.strip()
        if len(s) <= 3 or s in declared:
            continue
        if (RU_ONLY & set(s.lower())) or s == ru.get(k, "").strip():
            out.append(k)
    return sorted(out)


def load(mirror: str, lang: str) -> dict:
    return json.loads((ROOT / mirror / f"{lang}.json").read_text(encoding="utf-8"))


def cmd_verify(_args) -> int:
    uk = flat(load(MIRRORS[0], "uk"))
    ru = flat(load(MIRRORS[0], "ru"))
    todo = needs_work(uk, ru)
    ns = collections.Counter(k.split(".")[0] for k in todo)
    print(f"uk.json: {len(todo)} of {len(uk)} values still need Ukrainian")
    for name, n in ns.most_common():
        print(f"  {name:16} {n}")
    print(f"  characters: {sum(len(uk[k]) for k in todo):,}")
    return 0


def cmd_apply(args) -> int:
    """Apply a reviewed batch. Refuses anything that fails a check."""
    batch = json.loads(Path(args.batch).read_text(encoding="utf-8"))
    pairs: dict[str, str] = batch["translations"]
    # Some strings ARE the same word in both languages — "Статус", "Система",
    # "Результат". Passing those through silently would make the
    # "unchanged" check useless, so they must be declared: an explicit claim
    # that a human looked and the Ukrainian really is identical, not a string
    # someone forgot. Anything declared here is exempt from that one check.
    same_by_design: set[str] = set(batch.get("identical_in_both", []))

    uk = flat(load(MIRRORS[0], "uk"))
    rejected: list[tuple[str, str]] = []
    accepted: dict[str, str] = {}

    for src, dst in pairs.items():
        if not dst.strip():
            rejected.append((src, "empty translation"))
            continue
        if RU_ONLY & set(dst.lower()):
            rejected.append((src, "translation still contains ы/ъ/э/ё"))
            continue
        if dst.strip() == src.strip() and src.strip() not in same_by_design:
            rejected.append((src, "unchanged — translate it, or declare it in identical_in_both"))
            continue
        if sorted(PLACEHOLDER.findall(src)) != sorted(PLACEHOLDER.findall(dst)):
            rejected.append((src, "placeholders differ from source"))
            continue
        stems = lint_translation(dst)
        if stems and src.strip() not in same_by_design:
            rejected.append((src, f"still Russian: {stems[0]}"))
            continue
        accepted[src] = dst

    if rejected:
        print(f"REJECTED {len(rejected)}:")
        for src, why in rejected[:20]:
            print(f"  {why:38} {src[:56]}")
        if not args.force:
            print("nothing applied. Fix the batch, or pass --force to apply the rest.")
            return 1

    changed = 0
    for mirror in MIRRORS:
        path = ROOT / mirror / "uk.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        flatdoc = flat(doc)
        n = 0
        for key, val in flatdoc.items():
            if val.strip() in accepted:
                if set_path(doc, key, accepted[val.strip()]):
                    n += 1
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        changed += n
        print(f"  {mirror:52} {n} values")
    print(f"applied {len(accepted)} unique strings -> {changed} values across {len(MIRRORS)} mirrors")
    return 0


def cmd_audit(_args) -> int:
    ok = True
    base = json.loads((ROOT / MIRRORS[0] / "uk.json").read_text(encoding="utf-8"))
    baseflat = flat(base)
    for mirror in MIRRORS[1:]:
        p = ROOT / mirror / "uk.json"
        if not p.exists():
            continue
        other = flat(json.loads(p.read_text(encoding="utf-8")))
        if other != baseflat:
            diff = [k for k in baseflat if other.get(k) != baseflat[k]]
            print(f"MIRROR DRIFT {mirror}: {len(diff)} values differ")
            ok = False
    en = flat(json.loads((ROOT / MIRRORS[0] / "en.json").read_text(encoding="utf-8")))
    bad_ph = [
        k for k, v in baseflat.items()
        if k in en and sorted(PLACEHOLDER.findall(en[k])) != sorted(PLACEHOLDER.findall(v))
    ]
    if bad_ph:
        print(f"PLACEHOLDER MISMATCH vs en: {len(bad_ph)}")
        for k in bad_ph[:10]:
            print(f"  {k}\n    en: {en[k][:70]}\n    uk: {baseflat[k][:70]}")
        ok = False
    ru = flat(json.loads((ROOT / MIRRORS[0] / "ru.json").read_text(encoding="utf-8")))
    left = needs_work(baseflat, ru)
    print(f"remaining Russian values: {len(left)}")
    print("audit:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify").set_defaults(fn=cmd_verify)
    a = sub.add_parser("apply")
    a.add_argument("batch")
    a.add_argument("--force", action="store_true")
    a.set_defaults(fn=cmd_apply)
    sub.add_parser("audit").set_defaults(fn=cmd_audit)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
