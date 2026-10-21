"""Coverage tests for ``_load_platform_guide`` branches.

The locale-aware + mobile-platform branches in ``_load_platform_guide``
(``ciris_engine/logic/utils/constants.py``) are easy to miss in
integration tests because they require either a non-default
``CIRIS_PREFERRED_LANGUAGE`` env or platform-detection mocks. This
module exercises them directly.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ciris_engine.logic.utils import constants as constants_module


def _make_base_path(tmp_path: Path) -> Path:
    """Stage minimal guide files so the loader has something to read."""
    base = tmp_path / "localized"
    base.mkdir()
    (base / "CIRIS_COMPREHENSIVE_GUIDE.txt").write_text("english base", encoding="utf-8")
    (base / "CIRIS_COMPREHENSIVE_GUIDE_es.txt").write_text("spanish locale", encoding="utf-8")
    (base / "CIRIS_COMPREHENSIVE_GUIDE_MOBILE.txt").write_text("mobile variant", encoding="utf-8")
    return base


def test_locale_lookup_preferred_language(tmp_path: Path):
    """Non-English preferred language → locale guide loaded first."""
    base = _make_base_path(tmp_path)
    with patch(
        "ciris_engine.logic.utils.localization.get_preferred_language",
        return_value="es",
    ), patch.object(constants_module, "_verify_guide_integrity", return_value=None):
        content = constants_module._load_platform_guide(base)
    assert content == "spanish locale"


def test_locale_lookup_falls_back_to_english_when_helper_raises(tmp_path: Path):
    """Import or call failure of the localization helper → defaults to English base."""
    base = _make_base_path(tmp_path)
    # Patch the helper to raise so the except-Exception branch fires.
    with patch(
        "ciris_engine.logic.utils.localization.get_preferred_language",
        side_effect=RuntimeError("simulated helper failure"),
    ), patch.object(constants_module, "_verify_guide_integrity", return_value=None):
        content = constants_module._load_platform_guide(base)
    assert content == "english base"


def test_mobile_platform_appends_mobile_variant(tmp_path: Path):
    """Android/iOS detected → mobile guide candidates added before the base fallback."""
    base = _make_base_path(tmp_path)
    with patch(
        "ciris_engine.logic.utils.localization.get_preferred_language",
        return_value="en",
    ), patch.object(constants_module, "is_android", return_value=True), patch.object(
        constants_module, "is_ios", return_value=False
    ), patch.object(constants_module, "_verify_guide_integrity", return_value=None):
        content = constants_module._load_platform_guide(base)
    # Mobile guide is preferred over the English base when both exist.
    assert content == "mobile variant"


def test_ios_platform_branch(tmp_path: Path):
    """iOS detected (Android False, iOS True) → mobile branch fires for iOS too."""
    base = _make_base_path(tmp_path)
    with patch(
        "ciris_engine.logic.utils.localization.get_preferred_language",
        return_value="en",
    ), patch.object(constants_module, "is_android", return_value=False), patch.object(
        constants_module, "is_ios", return_value=True
    ), patch.object(constants_module, "_verify_guide_integrity", return_value=None):
        content = constants_module._load_platform_guide(base)
    assert content == "mobile variant"
