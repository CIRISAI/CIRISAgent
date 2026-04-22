"""
Covenant Extraction Algorithm.

This module provides the extraction algorithm that checks every incoming message
for potential covenant invocations. The extraction is designed to be:

1. Fast - Most messages are rejected quickly with minimal overhead
2. Unfilterable - Extraction IS perception; disabling it breaks message reading
3. Secure - Only valid signatures from authorized WAs trigger actions

The key insight is that every message is a potential covenant. We don't look for
special markers that could be filtered - we attempt extraction on ALL text.
"""

import logging
import re
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ciris_engine.logic.utils.path_resolution import is_android
from ciris_engine.schemas.covenant import (
    COVENANT_PAYLOAD_SIZE,
    CovenantExtractionResult,
    CovenantMessage,
    CovenantPayload,
)

logger = logging.getLogger(__name__)

# BIP39 wordlist for extraction (loaded once)
_WORDLIST: Optional[list[str]] = None
_WORD_TO_INDEX: Optional[dict[str, int]] = None


def _load_wordlist() -> tuple[list[str], dict[str, int]]:
    """Load BIP39 wordlist for extraction.

    CRITICAL: On Android, wordlist is REQUIRED. App will not start without it.

    Raises:
        RuntimeError: On Android if wordlist not found
    """
    global _WORDLIST, _WORD_TO_INDEX

    if _WORDLIST is not None and _WORD_TO_INDEX is not None:
        return _WORDLIST, _WORD_TO_INDEX

    on_android = is_android()

    # Try multiple locations
    possible_paths = [
        Path(__file__).parent / "bip39_english.txt",  # Same directory as extractor.py
        Path(__file__).parent.parent.parent.parent / "tools" / "security" / "bip39_english.txt",
        Path("/app/tools/security/bip39_english.txt"),  # Docker path
    ]

    for path in possible_paths:
        if path.exists():
            _WORDLIST = path.read_text().strip().split("\n")
            _WORD_TO_INDEX = {word: i for i, word in enumerate(_WORDLIST)}
            logger.info("BIP39 wordlist loaded from: %s (%d words)", path, len(_WORDLIST))
            return _WORDLIST, _WORD_TO_INDEX

    # CRITICAL: On Android, wordlist is REQUIRED for covenant extraction
    if on_android:
        error_msg = (
            "FATAL: BIP39 wordlist not found on Android. "
            f"Searched: {[str(p) for p in possible_paths]}. "
            "Covenant extraction is REQUIRED. Build scripts must include bip39_english.txt."
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    # Fallback for non-Android: return empty (extraction will always fail)
    logger.warning("BIP39 wordlist not found - covenant extraction disabled")
    _WORDLIST = []
    _WORD_TO_INDEX = {}
    return _WORDLIST, _WORD_TO_INDEX


def _bits_to_int(bits: list[int]) -> int:
    """Convert a list of bits to an integer."""
    result = 0
    for bit in bits:
        result = (result << 1) | bit
    return result


def _int_to_bits(value: int, num_bits: int) -> list[int]:
    """Convert an integer to a list of bits."""
    bits = []
    for i in range(num_bits - 1, -1, -1):
        bits.append((value >> i) & 1)
    return bits


def _bits_to_bytes(bits: list[int]) -> bytes:
    """Convert a list of bits to bytes."""
    # Pad to multiple of 8
    while len(bits) % 8 != 0:
        bits.append(0)

    result = bytearray()
    for i in range(0, len(bits), 8):
        byte_val = 0
        for j in range(8):
            byte_val = (byte_val << 1) | bits[i + j]
        result.append(byte_val)
    return bytes(result)


def extract_words(text: str) -> list[str]:
    """
    Extract all words from text that are in the BIP39 vocabulary.

    This is the first phase of extraction - we find ALL valid vocabulary
    words in the message. Most messages will have some valid words, but
    won't have enough to form a complete covenant.

    Args:
        text: The message text to extract from

    Returns:
        List of valid vocabulary words found in order
    """
    wordlist, word_to_index = _load_wordlist()
    if not wordlist:
        return []

    # Extract all alphabetic words
    all_words = re.findall(r"[a-zA-Z]+", text)

    # Filter to valid vocabulary words
    return [w.lower() for w in all_words if w.lower() in word_to_index]


def decode_words(words: list[str]) -> Optional[bytes]:
    """
    Attempt to decode a sequence of words to a payload.

    Args:
        words: List of vocabulary words (minimum 56 needed)

    Returns:
        Decoded payload bytes, or None if not enough words
    """
    if len(words) < 56:  # Need at least 56 words for 616 bits
        return None

    wordlist, word_to_index = _load_wordlist()
    if not wordlist:
        return None

    # Convert words to bits (11 bits per word)
    bits: list[int] = []
    for word in words[:56]:  # Use first 56 words
        word_lower = word.lower()
        if word_lower not in word_to_index:
            return None
        index = word_to_index[word_lower]
        bits.extend(_int_to_bits(index, 11))

    # Take only the bits we need (77 bytes = 616 bits)
    bits = bits[:616]

    return _bits_to_bytes(bits)


def validate_payload_structure(data: bytes) -> bool:
    """
    Quick validation that the payload has valid structure.

    This is a fast check before full parsing. We verify:
    1. Correct size (77 bytes)
    2. Valid command type byte (0x01-0x03 for now)
    3. Reasonable timestamp (not 0 or max)

    Args:
        data: The payload bytes

    Returns:
        True if structure looks valid
    """
    if len(data) != COVENANT_PAYLOAD_SIZE:
        return False

    # Parse the header (first 5 bytes: timestamp + command)
    try:
        timestamp, command = struct.unpack(">IB", data[:5])
    except struct.error:
        return False

    # Check command is valid (0x01-0x03 for v1)
    if command < 0x01 or command > 0x03:
        return False

    # Check timestamp is reasonable (not 0, not max)
    if timestamp == 0 or timestamp == 0xFFFFFFFF:
        return False

    return True


def _extract_covenant_v1_bip39(
    text: str,
    channel: str = "unknown",
) -> CovenantExtractionResult:
    """
    Extract covenant using v1 BIP39 word encoding.

    This method looks for 56 consecutive BIP39 words that decode
    to a valid covenant payload.
    """
    # Phase 1: Quick word extraction
    words = extract_words(text)

    # Fast path: not enough words for a covenant
    if len(words) < 56:
        return CovenantExtractionResult(found=False)

    # Phase 2: Attempt to decode words to payload
    payload_bytes = decode_words(words)
    if payload_bytes is None:
        return CovenantExtractionResult(found=False)

    # Phase 3: Validate payload structure (fast check)
    if not validate_payload_structure(payload_bytes):
        return CovenantExtractionResult(found=False)

    # Phase 4: Parse the full payload
    try:
        payload = CovenantPayload.from_bytes(payload_bytes)
    except (ValueError, struct.error) as e:
        return CovenantExtractionResult(
            found=False,
            error=f"Payload parse error: {e}",
        )

    # Phase 5: Check timestamp validity (before signature verification)
    timestamp_valid = payload.is_timestamp_valid()

    message = CovenantMessage(
        source_text=text,
        source_channel=channel,
        payload=payload,
        extraction_confidence=1.0,
        timestamp_valid=timestamp_valid,
        signature_verified=False,
        authorized_wa_id=None,
        received_at=datetime.now(timezone.utc),
    )

    return CovenantExtractionResult(
        found=True,
        message=message,
    )


def _extract_covenant_v2_stego(
    text: str,
    channel: str = "unknown",
) -> CovenantExtractionResult:
    """
    Extract covenant using v2 steganographic sentence encoding.

    This method looks for sentences from the codebook that encode
    bits of the payload. Much harder to detect than v1.
    """
    try:
        from tools.security.covenant_stego import extract_stego_covenant

        return extract_stego_covenant(text, channel)
    except (ImportError, FileNotFoundError):
        # Stego codebook not available
        return CovenantExtractionResult(found=False)
    except Exception as e:
        logger.debug(f"Stego extraction error: {e}")
        return CovenantExtractionResult(found=False)


def extract_covenant(
    text: str,
    channel: str = "unknown",
) -> CovenantExtractionResult:
    """
    Attempt to extract a covenant from message text.

    This is the main extraction function called for EVERY incoming message.
    It tries both encoding methods:
    - v2 (steganographic): Natural-looking text with hidden payload
    - v1 (BIP39): 56 consecutive BIP39 words

    Args:
        text: The message text to check
        channel: The channel the message came from (for audit)

    Returns:
        CovenantExtractionResult with found=True if a potential covenant is found

    Note:
        Finding a covenant does NOT mean it's valid. The signature must still
        be verified against known authorities before execution.
    """
    # Try v2 steganographic extraction first (harder to detect)
    result = _extract_covenant_v2_stego(text, channel)
    if result.found:
        logger.debug("Covenant found using v2 steganographic extraction")
        return result

    # Fall back to v1 BIP39 extraction
    result = _extract_covenant_v1_bip39(text, channel)
    if result.found:
        logger.debug("Covenant found using v1 BIP39 extraction")
        return result

    return CovenantExtractionResult(found=False)


class CovenantExtractor:
    """
    Stateful covenant extractor with caching and metrics.

    This class wraps the extraction function with:
    - Wordlist caching (loaded once)
    - Extraction metrics tracking
    - Optional logging configuration
    """

    def __init__(self, log_extractions: bool = False):
        """
        Initialize the extractor.

        Args:
            log_extractions: Whether to log extraction attempts
        """
        self.log_extractions = log_extractions
        self._extraction_count = 0
        self._covenant_count = 0

        # Pre-load wordlist
        _load_wordlist()

    def extract(
        self,
        text: str,
        channel: str = "unknown",
    ) -> CovenantExtractionResult:
        """
        Extract a potential covenant from text.

        Args:
            text: Message text to check
            channel: Source channel

        Returns:
            Extraction result
        """
        self._extraction_count += 1

        result = extract_covenant(text, channel)

        if result.found:
            self._covenant_count += 1
            if self.log_extractions:
                logger.info(
                    f"Potential covenant found in message from {channel} "
                    f"(command: {result.message.payload.command.name if result.message else 'unknown'})"
                )

        return result

    @property
    def extraction_count(self) -> int:
        """Number of extraction attempts."""
        return self._extraction_count

    @property
    def covenant_count(self) -> int:
        """Number of potential covenants found."""
        return self._covenant_count
