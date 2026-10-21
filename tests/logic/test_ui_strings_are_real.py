"""No UI string may render as a bare localization tag, and no locale may lag `en`.

TWO GUARDS, both authoring-time, both closing holes that shipped.

GUARD 1 — every key the UI asks for must EXIST.
LocalizationManager.getString() resolves the current language, falls back to
English, and then:

    // Fall back to key itself if still not found
    if (result == null) { return key }

So a key that exists nowhere is rendered to the user AS ITS OWN NAME —
`setup_validation_age_required` on screen instead of a sentence. That is
reported behaviour: a user in Italy saw bare keys in the first-run wizard on
2.9.23. Because English is tried before the key fallback, a bare tag means the
key is missing from `en` itself (or the English bundle failed to load) — a
missing ITALIAN key would quietly show English, which is ugly but legible.

GUARD 2 — a key added to `en` must reach all 28 locales in the same change.
Adding one user-facing string is a 29-file edit in this repo and nothing enforced
it at authoring time. `check_localization_sync.py` reports drift as a WARNING and
exits 0. The completeness test does fail, but only in CI, per-language, spread
across shards — so one forgotten key reads as six shards collapsing.

That happened twice, one release apart, both times by me: 2.9.23 (three keys from
#1055) and 2.9.24 (`setup_validation_proxy_needs_token`). Twice is a process
defect, not carelessness — hence a test that fails locally, in one place, naming
the key and every locale that lacks it.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
CANON = REPO / "ciris_engine" / "data" / "localized"

#: Every place the shipped clients read their strings from. A key present in the
#: canonical tree but absent from the copy a platform actually loads is invisible
#: here unless all of them are checked — and the desktop app reads its own.
#: The desktop mirrors are GONE, not forgotten: the shared client and the desktop
#: app are built by CIRISAI/CIRISClient now, so their string copies live and are
#: checked there. What this repo still ships is the engine's canonical tree and
#: the two app shells' own asset copies.
MIRRORS = [
    CANON,
    REPO / "apps" / "android" / "src" / "main" / "assets" / "localization",
    REPO / "apps" / "ios" / "iosApp" / "localization",
    REPO / "apps" / "ios" / "Resources" / "app" / "localization",
]

#: `getString("some.key")` / `getStringInLanguage(lang, "some.key")`.
#: Only literal keys — a computed key cannot be checked statically, and pretending
#: otherwise would make this test lie about its own coverage.
#: THE CALL FORMS THE UI ACTUALLY USES.
#:
#: This matched only `getString(` / `getStringInLanguage(` — 146 call sites —
#: while the codebase reaches for `localizedString(` 2,318 times. So this guard,
#: written specifically to stop English-only keys shipping after that happened
#: twice, was inspecting 6% of the UI and passing everything else.
#:
#: It was caught by adding 8 keys to en.json alone and watching the guard go
#: green. A test that cannot fail is worse than no test: it converts an unchecked
#: area into one that looks checked.
#: Only `getStringInLanguage` takes a leading argument (the language). Allowing
#: an optional leading identifier for ALL forms made this match
#: `localizedString(messageKey, "state", targetState)` — the placeholder-
#: substitution form, where the key is the VARIABLE and "state" is a placeholder
#: NAME — and report a perfectly good call site as a missing key. Two false
#: positives, both from over-permissiveness. Match each form as it is written.
_CALL = re.compile(
    r'getStringInLanguage\(\s*[A-Za-z0-9_.]+\s*,\s*"([A-Za-z0-9_.]+)"'
    r'|(?:getString|localizedString)\(\s*"([A-Za-z0-9_.]+)"'
)


def _flatten(obj: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in obj.items():
        if isinstance(v, dict):
            out |= _flatten(v, f"{prefix}{k}.")
        else:
            out.add(f"{prefix}{k}")
    return out


def _load(path: pathlib.Path) -> set[str]:
    return _flatten(json.loads(path.read_text(encoding="utf-8")))


def _manifest_languages() -> list[str]:
    manifest = json.loads((CANON / "manifest.json").read_text(encoding="utf-8"))
    return sorted(c for c in manifest.get("languages", {}) if c != "en")


def _referenced_keys() -> dict[str, list[str]]:
    """key -> the source files that ask for it."""
    found: dict[str, list[str]] = {}
    roots = [r for r in (REPO / "apps" / "android" / "src", REPO / "apps" / "ios") if r.exists()]
    for kt in [f for r in roots for f in r.rglob("*.kt")]:
        try:
            text = kt.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for groups in _CALL.findall(text):
            key = next((g for g in groups if g), None) if isinstance(groups, tuple) else groups
            if key:
                found.setdefault(key, []).append(str(kt.relative_to(REPO)))

    # SKIP ON THE RESULT, NOT ON THE PATH.
    #
    # The first version of this guard checked `if not roots`. That looked like the
    # same protection and was not: `apps/android/src` and `apps/ios` both still
    # exist — they hold the platform shells — so the skip never fired, while the
    # eight Kotlin files under them contain ZERO matching call sites. The scan
    # returned {} and both guards went green again, which is precisely the vacuous
    # pass this skip was added to prevent, moved up one level.
    #
    # Measured on this checkout at the time of the fix: 8 .kt files, 0 call sites.
    #
    # What actually matters is whether any reference was FOUND, so that is what is
    # checked. A directory existing proves nothing about what is in it.
    if not found:
        pytest.skip(
            f"no localization call sites in this checkout ({sum(1 for r in roots for _ in r.rglob('*.kt'))} "
            "Kotlin file(s) scanned, none referencing a string key) — the UI that asks for "
            "these keys is built by CIRISAI/CIRISClient now, so this guard belongs there. "
            "Skipping is honest; an empty result would have looked like a pass."
        )
    return found


# ── GUARD 1 ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mirror", MIRRORS, ids=lambda p: p.parent.name)
def test_every_ui_string_exists_in_each_client_mirror(mirror: pathlib.Path) -> None:
    """The desktop app reads its OWN copy, not the canonical tree.

    A key present canonically but missing from the bundle a platform loads still
    renders as a bare tag on that platform — which is why this is checked per
    mirror rather than once.
    """
    path = mirror / "en.json"
    if not path.exists():
        pytest.skip(f"{mirror} has no en.json in this checkout")
    en = _load(path)
    missing = sorted(k for k in _referenced_keys() if k not in en)
    assert not missing, f"{path.relative_to(REPO)} lacks {len(missing)} referenced key(s): {missing[:10]}"


# ── GUARD 2 ──────────────────────────────────────────────────────────────────


def test_a_new_english_key_reached_every_locale() -> None:
    """Adding a user-facing string is a 29-file change; fail here, not in six shards.

    Names the key AND the locales, so the fix is mechanical rather than a hunt.
    """
    # ONLY keys the UI actually asks for. The canonical tree also carries prompt
    # content (prompts.language_guidance.*) that is deliberately partial — the
    # primer work ships it for a few locales at a time — and a blanket en-vs-all
    # diff would fail on that forever, which is how a guard gets disabled.
    # Full-corpus coverage is already the completeness test's job; this one exists
    # to protect what a user READS ON SCREEN.
    referenced = set(_referenced_keys())
    en = _load(CANON / "en.json") & referenced
    gaps: dict[str, list[str]] = {}
    for lang in _manifest_languages():
        path = CANON / f"{lang}.json"
        if not path.exists():
            gaps.setdefault("<file missing>", []).append(lang)
            continue
        for key in sorted(en - _load(path)):
            gaps.setdefault(key, []).append(lang)

    assert not gaps, (
        f"{len(gaps)} key(s) exist in en.json but not in every locale. A user in one of these "
        "languages gets English (legible but wrong); the CI completeness gate fails per-language "
        "across shards, which reads as a suite-wide collapse.\n  "
        + "\n  ".join(f"{k}: missing in {', '.join(v)}" for k, v in sorted(gaps.items()))
    )


# REMOVED WITH THE CLIENT MIGRATION
#
# `test_every_ui_string_exists_in_english` and
# `test_the_key_fallback_still_exists_and_is_why_this_matters` both read KOTLIN
# SOURCE -- getString() call sites, and the fallback branch in
# LocalizationManager.kt. That source is built by CIRISAI/CIRISClient now and no
# longer exists in this tree, so both tests could only ever pass vacuously here.
#
# They are deleted rather than skipped: a skipped test still advertises the
# coverage. THE COVERAGE IS GONE FROM THIS REPO -- nothing here can now catch a
# getString("typo.key") that renders as a bare tag. That check belongs upstream,
# beside the code it guards.
#
# What survives below is what this repo still owns: the canonical string tree
# and the two app shells' asset copies, checked for parity and locale lag.
