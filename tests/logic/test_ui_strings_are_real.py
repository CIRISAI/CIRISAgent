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
MIRRORS = [
    CANON,
    REPO / "client" / "androidApp" / "src" / "main" / "assets" / "localization",
    REPO / "client" / "shared" / "src" / "desktopMain" / "resources" / "localization",
    REPO / "client" / "desktopApp" / "src" / "main" / "resources" / "localization",
    REPO / "client" / "iosApp" / "iosApp" / "localization",
    REPO / "client" / "iosApp" / "Resources" / "app" / "localization",
]

#: `getString("some.key")` / `getStringInLanguage(lang, "some.key")`.
#: Only literal keys — a computed key cannot be checked statically, and pretending
#: otherwise would make this test lie about its own coverage.
_CALL = re.compile(r'getString(?:InLanguage)?\(\s*(?:[A-Za-z0-9_.]+\s*,\s*)?"([A-Za-z0-9_.]+)"')


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
    for kt in (REPO / "client" / "shared" / "src").rglob("*.kt"):
        try:
            text = kt.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for key in _CALL.findall(text):
            found.setdefault(key, []).append(str(kt.relative_to(REPO)))
    return found


# ── GUARD 1 ──────────────────────────────────────────────────────────────────


def test_every_ui_string_exists_in_english() -> None:
    """A key with no English entry is rendered to the user as its own name."""
    en = _load(CANON / "en.json")
    referenced = _referenced_keys()
    assert referenced, "found no getString() call sites — the regex has drifted from the code"

    missing = {k: v for k, v in referenced.items() if k not in en}
    assert not missing, (
        f"{len(missing)} UI string(s) have no entry in en.json and will render as BARE KEYS "
        "on screen (LocalizationManager falls back to the key itself):\n  "
        + "\n  ".join(f"{k}  <- {', '.join(sorted(set(v))[:2])}" for k, v in sorted(missing.items()))
    )


@pytest.mark.parametrize("mirror", MIRRORS[1:], ids=lambda p: p.parent.name)
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


def test_the_key_fallback_still_exists_and_is_why_this_matters() -> None:
    """Pin the behaviour these guards exist for.

    If the fallback ever changes to something visible-but-safe (e.g. empty, or a
    marked placeholder), Guard 1 becomes less urgent — and someone should know
    that rather than infer it.
    """
    src = (
        REPO
        / "client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/localization/LocalizationManager.kt"
    ).read_text(encoding="utf-8")
    assert "Fall back to key itself" in src
    assert "return key" in src
