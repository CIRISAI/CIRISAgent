"""``check_alphabet`` catches a language substituted for its same-script sibling.

This is the hole CIRISAgent#949 fell through. Three checks already ran over
uk.json and none of them could see that 53% of it is Russian:

  * ``check_script`` compares Unicode BLOCKS. Ukrainian and Russian are both
    Cyrillic, so Russian text produces zero foreign codepoints.
  * ``test_uk_chain_localization`` asserts the prompts "contain Cyrillic
    content" — which Russian satisfies perfectly.
  * ``check_sibling_similarity`` does see the 45% overlap, but as a WARN, in
    aggregate, and it cannot name a single offending key.

Alphabet conformance is the signal that works, because it is a fact rather
than a ratio: ы э ъ ё do not exist in the Ukrainian alphabet. A value carrying
one is not a loanword or a shared term — it is the other language.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tools" / "dev"))

from check_localization_integrity import FOREIGN_ALPHABET, LEVEL_ERROR, check_alphabet  # noqa: E402


class TestForeignAlphabet:
    def test_russian_in_ukrainian_is_an_error(self) -> None:
        en = {"k": "Choose a language"}
        loc = {"k": "Выберите язык"}  # Russian ы; Ukrainian is "Виберіть мову"
        findings = check_alphabet("uk", loc, en)
        assert len(findings) == 1
        assert findings[0].level == LEVEL_ERROR
        assert findings[0].check == "foreign-alphabet"
        assert findings[0].key == "k"

    def test_russian_without_an_exclusive_letter_is_NOT_caught(self) -> None:
        """The bound on this check, pinned so nobody mistakes it for coverage.

        "Цветовая тема" is unambiguously Russian — Ukrainian is "Кольорова
        тема" — but it happens to use no letter outside the Ukrainian alphabet,
        so alphabet conformance cannot see it. Of the 1557 uk values that need
        translating, this check names 658; the rest are reachable only via
        byte-identity with ru.json (check_sibling_similarity).

        A precise check that covers part of the problem is worth having. Being
        clear about which part is what keeps it from being read as "uk is now
        verified Ukrainian".
        """
        en = {"k": "Color Theme"}
        loc = {"k": "Цветовая тема"}
        assert check_alphabet("uk", loc, en) == []

    def test_genuine_ukrainian_passes(self) -> None:
        """The letters that make it Ukrainian (і ї є ґ) must not trip it."""
        en = {"k": "Color Theme", "j": "Signing key is not registered"}
        loc = {"k": "Кольорова тема", "j": "Ключ підпису не зареєстрований"}
        assert check_alphabet("uk", loc, en) == []

    def test_reverse_direction_ukrainian_in_russian(self) -> None:
        en = {"k": "Signing key"}
        loc = {"k": "Ключ підпису"}  # Ukrainian і — not a Russian letter
        findings = check_alphabet("ru", loc, en)
        assert len(findings) == 1
        assert "Ukrainian" in findings[0].detail

    def test_letters_quoted_from_english_are_not_evidence(self) -> None:
        """Same carve-out check_script makes for brand names."""
        en = {"k": "The ъ character"}
        loc = {"k": "Символ ъ"}
        assert check_alphabet("uk", loc, en) == []

    def test_unprofiled_language_is_a_noop(self) -> None:
        """A language with no confusable sibling declared must never be flagged."""
        assert "de" not in FOREIGN_ALPHABET
        assert check_alphabet("de", {"k": "Farbschema"}, {"k": "Color Theme"}) == []

    def test_profiles_are_mutually_exclusive(self) -> None:
        """A letter cannot be exclusive to both members of a pair.

        Guards the table itself: an overlapping entry would fail honest
        translations in both directions, which is worse than the gap it closes.
        """
        for lang, (letters, _sibling) in FOREIGN_ALPHABET.items():
            for other, (other_letters, _) in FOREIGN_ALPHABET.items():
                if lang != other:
                    assert not (set(letters) & set(other_letters)), f"{lang}/{other} claim the same letters"
