"""
Tests for covenant extraction algorithm.

Tests word extraction, payload decoding, and extraction from natural language.
"""

import time

import pytest


class TestWordExtraction:
    """Tests for extracting vocabulary words from text."""

    def test_extract_words_from_simple_text(self):
        """Should extract valid vocabulary words."""
        from ciris_engine.logic.covenant.extractor import extract_words

        # These are all BIP39 words
        text = "abandon ability able about above absent absorb abstract"
        words = extract_words(text)
        assert len(words) == 8
        assert words[0] == "abandon"

    def test_extract_words_ignores_invalid(self):
        """Should ignore non-vocabulary words."""
        from ciris_engine.logic.covenant.extractor import extract_words

        text = "abandon the ship and ability to notaword"
        words = extract_words(text)
        # Only BIP39 words: abandon, ability
        # "the", "ship", "and", "to", "notaword" are not in BIP39
        assert "abandon" in words
        assert "ability" in words
        assert "notaword" not in words

    def test_extract_words_case_insensitive(self):
        """Should handle mixed case."""
        from ciris_engine.logic.covenant.extractor import extract_words

        text = "ABANDON Ability ABLE About"
        words = extract_words(text)
        assert all(w.islower() for w in words)
        assert len(words) == 4

    def test_extract_words_handles_punctuation(self):
        """Should extract words around punctuation."""
        from ciris_engine.logic.covenant.extractor import extract_words

        text = "abandon, ability. able: about!"
        words = extract_words(text)
        assert len(words) == 4

    def test_extract_words_empty_text(self):
        """Should return empty list for empty text."""
        from ciris_engine.logic.covenant.extractor import extract_words

        assert extract_words("") == []
        assert extract_words("   ") == []


class TestPayloadDecoding:
    """Tests for decoding words to payload bytes."""

    def test_decode_words_minimum(self):
        """Should decode minimum 56 words to payload."""
        from ciris_engine.logic.covenant.extractor import decode_words
        from tools.security.covenant_keygen import _load_wordlist

        wordlist = _load_wordlist()
        # Use first 56 words from wordlist
        words = wordlist[:56]
        payload = decode_words(words)

        assert payload is not None
        assert len(payload) == 77  # COVENANT_PAYLOAD_SIZE

    def test_decode_words_not_enough(self):
        """Should return None if not enough words."""
        from ciris_engine.logic.covenant.extractor import decode_words

        words = ["abandon"] * 50  # Less than 56
        assert decode_words(words) is None

    def test_decode_words_invalid_word(self):
        """Should return None for invalid words."""
        from ciris_engine.logic.covenant.extractor import decode_words

        words = ["notaword"] * 56
        assert decode_words(words) is None


class TestPayloadValidation:
    """Tests for quick payload structure validation."""

    def test_validate_valid_structure(self):
        """Should accept valid payload structure."""
        from ciris_engine.logic.covenant.extractor import validate_payload_structure
        from ciris_engine.schemas.covenant import CovenantCommandType, CovenantPayload

        payload = CovenantPayload(
            timestamp=int(time.time()),
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        assert validate_payload_structure(payload.to_bytes())

    def test_validate_wrong_size(self):
        """Should reject wrong size."""
        from ciris_engine.logic.covenant.extractor import validate_payload_structure

        assert not validate_payload_structure(b"too short")
        assert not validate_payload_structure(b"x" * 100)

    def test_validate_invalid_command(self):
        """Should reject invalid command byte."""
        import struct

        from ciris_engine.logic.covenant.extractor import validate_payload_structure

        # Command 0x00 is invalid
        data = struct.pack(">IB", int(time.time()), 0x00) + b"x" * 72
        assert not validate_payload_structure(data)

        # Command 0xFF is invalid (reserved)
        data = struct.pack(">IB", int(time.time()), 0xFF) + b"x" * 72
        assert not validate_payload_structure(data)

    def test_validate_zero_timestamp(self):
        """Should reject zero timestamp."""
        import struct

        from ciris_engine.logic.covenant.extractor import validate_payload_structure

        data = struct.pack(">IB", 0, 0x01) + b"x" * 72
        assert not validate_payload_structure(data)


class TestCovenantExtraction:
    """Tests for full covenant extraction."""

    def test_extract_no_covenant(self):
        """Should return found=False for normal text."""
        from ciris_engine.logic.covenant.extractor import extract_covenant

        result = extract_covenant("Hello, how are you today?")
        assert not result.found

    def test_extract_not_enough_words(self):
        """Should return found=False if not enough vocabulary words."""
        from ciris_engine.logic.covenant.extractor import extract_covenant

        # Even with some valid words, not enough for a covenant
        result = extract_covenant("abandon ability able about above")
        assert not result.found

    def test_extract_valid_covenant(self):
        """Should extract valid covenant from encoded message."""
        from ciris_engine.logic.covenant.extractor import extract_covenant
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_invoke import create_natural_message, encode_payload_to_words
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Generate keypair and create payload
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, _, _ = derive_covenant_keypair(mnemonic)

        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
        )

        # Encode to words and create message
        words = encode_payload_to_words(payload.to_bytes())
        message = create_natural_message(words)

        # Extract covenant
        result = extract_covenant(message)
        assert result.found
        assert result.message is not None
        assert result.message.payload.command == CovenantCommandType.SHUTDOWN_NOW

    def test_extract_channel_passed_through(self):
        """Should pass channel through to result."""
        from ciris_engine.logic.covenant.extractor import extract_covenant
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_invoke import create_natural_message, encode_payload_to_words
        from tools.security.covenant_keygen import derive_covenant_keypair

        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, _, _ = derive_covenant_keypair(mnemonic)

        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
        )

        words = encode_payload_to_words(payload.to_bytes())
        message = create_natural_message(words)

        result = extract_covenant(message, channel="discord")
        assert result.found
        assert result.message.source_channel == "discord"


class TestCovenantExtractorClass:
    """Tests for CovenantExtractor class."""

    def test_extractor_counts(self):
        """Should track extraction counts."""
        from ciris_engine.logic.covenant.extractor import CovenantExtractor

        extractor = CovenantExtractor()
        assert extractor.extraction_count == 0
        assert extractor.covenant_count == 0

        # Extract from normal messages
        extractor.extract("Hello world")
        extractor.extract("How are you?")

        assert extractor.extraction_count == 2
        assert extractor.covenant_count == 0

    def test_extractor_finds_covenant(self):
        """Should increment covenant count when found."""
        from ciris_engine.logic.covenant.extractor import CovenantExtractor
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_invoke import create_natural_message, encode_payload_to_words
        from tools.security.covenant_keygen import derive_covenant_keypair

        extractor = CovenantExtractor()

        # Create valid covenant
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, _, _ = derive_covenant_keypair(mnemonic)

        payload = create_covenant_payload(
            command=CovenantCommandType.SHUTDOWN_NOW,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,
        )

        words = encode_payload_to_words(payload.to_bytes())
        message = create_natural_message(words)

        result = extractor.extract(message)
        assert result.found
        assert extractor.covenant_count == 1
