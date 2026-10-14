"""Known translation errors in the shipped 1.2b Accord locales must not come back.

Each one was found by the MQM judge of the vendored localization pipeline when
the 1.3 drafts copied it from the 1.2b translation memory (batch 1, run
38598155352, and the 2026-10-14 model trial). The corrections are the judge's
own renderings: machine-reviewed, not native-reviewed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

LOCALIZED = Path(__file__).resolve().parents[4] / "ciris_engine" / "data" / "localized"


def _accord(lang: str) -> str:
    return (LOCALIZED / f"accord_1.2b_{lang}.txt").read_text(encoding="utf-8")


def test_es_meta_goal_is_meta_objetivo_not_meta_meta() -> None:
    text = _accord("es")
    assert "Meta-Meta" not in text, '"Meta-Goal" was rendered "Meta-Meta"'
    assert "**Meta-Objetivo M-1**" in text
    assert "la Meta-Objetivo" not in text, "Meta-Objetivo is masculine in this corpus"


def test_my_rivers_learned_their_riverbeds_not_their_lakes() -> None:
    text = _accord("my")
    line = next(l for l in text.splitlines() if "မြစ်များသည် ၎င်းတို့၏" in l)
    assert "ရေကန်" not in line, '"Rivers learned their beds" was rendered with ရေကန် (lake / pond)'
    assert "မြစ်လမ်းကြောင်း" in line


def test_am_early_machine_is_early_stage_not_ancient() -> None:
    text = _accord("am")
    assert "የጥንት ማሽን" not in text, '"an early machine" was rendered as an ancient one (የጥንት)'
    assert "የመጀመሪያ ትውልድ ማሽን" in text


@pytest.mark.parametrize("lang", ["am", "es", "my"])
def test_corrected_files_are_still_pinned(lang: str) -> None:
    import hashlib

    from ciris_engine.logic.utils.constants import ACCORD_EXPECTED_HASHES

    name = f"accord_1.2b_{lang}.txt"
    assert ACCORD_EXPECTED_HASHES[name] == hashlib.sha256((LOCALIZED / name).read_bytes()).hexdigest()
