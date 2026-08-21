"""A locale file must not contain its same-script NEIGHBOUR's language.

Every localisation gate we have verifies STRUCTURE — key parity, placeholder
integrity, script family. A string can satisfy all of them and still be the wrong
language, because the wrong language is often written in the same script:

    uk.json holding Russian   — both Cyrillic
    fa.json holding Arabic    — both Arabic script

Both shipped. The `foreign-alphabet` check was added for the uk/ru case (2.9.14,
"uk stops being ru") and cannot see it, because Russian *is* Cyrillic.

What makes this decidable is that these pairs have MUTUALLY EXCLUSIVE letters.
Ukrainian has no `ы э ъ ё`; Persian never writes `ي ك ة`. A single occurrence is
not a style choice — it is the other language.

Deliberately a letter-level check, not a wordlist: letters cannot be argued with,
need no dictionary, and do not rot. It will not catch every mixed string (that is
what the repair pass and native audit are for), but what it does catch, it
catches definitively — and it makes the regression impossible to reintroduce
silently.
"""

import json
import pathlib

import pytest

LOCALE_DIR = pathlib.Path(__file__).resolve().parents[4] / "ciris_engine" / "data" / "localized"

# locale -> (letters that belong to its same-script neighbour, human explanation)
#
# RATCHETED, like the localization value-integrity check in build.yml: a locale is
# listed here ONCE IT IS AT ZERO, so reintroducing the defect is a regression a
# reviewer can act on. Gating on a class that is still dirty would make this red
# from birth and teach everyone to skip it — the failure mode that check was
# designed around.
FOREIGN_LETTERS = {
    "uk": ("ыэъё", "Russian: Ukrainian has no ы, э, ъ or ё"),
    "fa": ("يكة", "Arabic: Persian writes ی (U+06CC) and ک (U+06A9), and never uses ة"),
    "ur": ("ةيك", "Arabic: Urdu writes ی (U+06CC) and ک (U+06A9), and never uses ة"),
}

# Known debt, deliberately NOT gated yet. Add to FOREIGN_LETTERS above as each
# reaches zero; removing one from there is a decision to let that language back
# into that file, and should be argued for.
# Empty: uk, fa and ur are all at zero and gated above. Add an entry here only
# when a NEW same-script pair is discovered dirty, and promote it into
# FOREIGN_LETTERS the moment it reaches zero.
KNOWN_DEBT: dict[str, tuple[str, str]] = {}


def test_known_debt_is_still_debt_and_not_silently_fixed():
    """If a debt locale reaches zero, promote it — do not leave the gate off.

    A ratchet only works if someone notices when a class becomes clean. This
    fails when that happens, with instructions, so the win gets locked in rather
    than quietly re-rotting.
    """
    for lang, (letters, _why) in KNOWN_DEBT.items():
        path = LOCALE_DIR / f"{lang}.json"
        if not path.exists():
            continue
        count = sum(1 for v in _flat(json.load(open(path, encoding="utf-8"))).values() if any(c in v for c in letters))
        assert count > 0, (
            f"{lang}.json now has ZERO same-script foreign letters. Move {lang!r} from KNOWN_DEBT "
            "into FOREIGN_LETTERS so the gate holds it there."
        )


def _flat(d, prefix=""):
    out = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat(v, key))
        elif isinstance(v, str):
            out[key] = v
    return out


@pytest.mark.parametrize("lang", sorted(FOREIGN_LETTERS))
def test_locale_does_not_contain_its_neighbours_language(lang):
    path = LOCALE_DIR / f"{lang}.json"
    assert path.exists(), (
        f"{lang}.json is missing from {LOCALE_DIR}. Failing rather than skipping: a gate that "
        "skips itself when it cannot find its input protects nothing, and reads green."
    )
    letters, why = FOREIGN_LETTERS[lang]
    offenders = []
    for key, value in _flat(json.load(open(path, encoding="utf-8"))).items():
        found = sorted({c for c in value if c in letters})
        if found:
            offenders.append((key, "".join(found), value[:70]))

    assert not offenders, (
        f"{len(offenders)} string(s) in {lang}.json contain letters from another language "
        f"({why}).\n"
        "These pass every structural gate — key parity, placeholders, script family — because "
        "the languages share a script. First 10:\n" + "\n".join(f"  {k}  [{f}]  {v}" for k, f, v in offenders[:10])
    )
