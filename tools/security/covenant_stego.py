#!/usr/bin/env python3
"""
Steganographic Covenant Encoding (v2).

Encodes covenant payloads into natural-looking text by selecting
sentences from a pre-built codebook. Each sentence choice encodes
6 bits, resulting in ~103 sentences (~800-1000 words) that look
like a normal email or document.

This is much harder to detect than the v1 BIP39 word encoding
because the entropy matches natural English text.

Usage:
    # Encode a covenant payload
    python -m tools.security.covenant_stego encode \
        --mnemonic "word1 word2 ..." \
        --command SHUTDOWN_NOW \
        --wa-id "wa-2025-06-14-ROOT00"

    # Decode a message
    python -m tools.security.covenant_stego decode --message "text..."
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ciris_engine.schemas.covenant import CovenantCommandType, CovenantExtractionResult

logger = logging.getLogger(__name__)

# Codebook location
CODEBOOK_PATH = Path(__file__).parent / "stego_codebook.json"

# Cached codebook
_CODEBOOK: Optional[dict[str, Any]] = None


def _load_codebook() -> dict[str, Any]:
    """Load the steganographic codebook."""
    global _CODEBOOK

    if _CODEBOOK is not None:
        return _CODEBOOK

    if not CODEBOOK_PATH.exists():
        raise FileNotFoundError(
            f"Steganographic codebook not found at {CODEBOOK_PATH}. "
            "Run: python tools/security/stego_corpus_builder.py"
        )

    with open(CODEBOOK_PATH) as f:
        _CODEBOOK = json.load(f)

    return _CODEBOOK


def bytes_to_bits(data: bytes) -> list[int]:
    """Convert bytes to a list of bits."""
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def bits_to_bytes(bits: list[int]) -> bytes:
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


def encode_payload_stego(payload_bytes: bytes) -> str:
    """
    Encode a covenant payload into steganographic text.

    Args:
        payload_bytes: The 77-byte covenant payload

    Returns:
        Natural-looking text (~103 sentences) encoding the payload
    """
    codebook = _load_codebook()

    # Convert payload to bits
    bits = bytes_to_bits(payload_bytes)

    # We need 616 bits, codebook provides 618 (103 slots * 6 bits)
    # Pad to match slot boundaries
    while len(bits) < codebook["total_bits"]:
        bits.append(0)

    # Select sentences for each slot
    sentences = []
    bits_per_slot = codebook["bits_per_slot"]

    for slot_idx, slot in enumerate(codebook["slots"]):
        # Extract bits for this slot
        start = slot_idx * bits_per_slot
        end = start + bits_per_slot
        slot_bits = bits[start:end]

        # Convert to binary string (e.g., "010110")
        bit_string = "".join(str(b) for b in slot_bits)

        # Look up sentence
        sentence = slot["variants"].get(bit_string)
        if sentence is None:
            raise ValueError(f"No sentence for bits {bit_string} in slot {slot_idx}")

        sentences.append(sentence)

    # Join into paragraphs (roughly 10 sentences each)
    paragraphs = []
    for i in range(0, len(sentences), 10):
        para_sentences = sentences[i : i + 10]
        paragraphs.append(" ".join(para_sentences))

    return "\n\n".join(paragraphs)


def decode_stego_to_payload(text: str) -> Optional[bytes]:
    """
    Decode steganographic text back to a covenant payload.

    Args:
        text: The encoded text

    Returns:
        The decoded payload bytes, or None if decoding fails
    """
    codebook = _load_codebook()
    sentence_to_bits = codebook["sentence_to_bits"]

    # Normalize and split into sentences
    # Handle various sentence endings
    import re

    text = text.replace("\n", " ")
    sentences = re.split(r"(?<=[.!?])\s+", text)

    # Find matching sentences and extract bits
    all_bits: list[int] = []
    slots_found: dict[int, str] = {}

    for sentence in sentences:
        sentence_clean = sentence.strip().lower()

        if sentence_clean in sentence_to_bits:
            info = sentence_to_bits[sentence_clean]
            slot_id = info["slot"]
            bits = info["bits"]

            # Only use first occurrence of each slot
            if slot_id not in slots_found:
                slots_found[slot_id] = bits

    # Check we found enough slots
    expected_slots = len(codebook["slots"])
    if len(slots_found) < expected_slots:
        logger.warning(f"Only found {len(slots_found)}/{expected_slots} slots")
        return None

    # Reconstruct bit stream in slot order
    for slot_id in range(expected_slots):
        if slot_id not in slots_found:
            logger.warning(f"Missing slot {slot_id}")
            return None
        all_bits.extend(int(b) for b in slots_found[slot_id])

    # Convert bits to bytes (take only 616 bits = 77 bytes)
    payload_bits = all_bits[:616]
    return bits_to_bytes(payload_bits)


def create_stego_covenant_message(
    command: "CovenantCommandType",
    wa_id: str,
    private_key_bytes: bytes,
    timestamp: Optional[int] = None,
) -> str:
    """
    Create a steganographically encoded covenant message.

    Args:
        command: The covenant command
        wa_id: The WA identifier
        private_key_bytes: Ed25519 private key for signing
        timestamp: Optional timestamp (defaults to now)

    Returns:
        Natural-looking text containing the hidden covenant
    """
    from ciris_engine.schemas.covenant import create_covenant_payload

    # Create the payload
    payload = create_covenant_payload(
        command=command,
        wa_id=wa_id,
        private_key_bytes=private_key_bytes,
        timestamp=timestamp,
    )

    # Encode steganographically
    return encode_payload_stego(payload.to_bytes())


def extract_stego_covenant(text: str, channel: str = "unknown") -> CovenantExtractionResult:
    """
    Extract a covenant from steganographically encoded text.

    Args:
        text: The message text
        channel: Source channel for logging

    Returns:
        CovenantExtractionResult
    """
    from datetime import datetime, timezone

    from ciris_engine.schemas.covenant import CovenantExtractionResult as CER
    from ciris_engine.schemas.covenant import CovenantMessage, CovenantPayload

    # Try to decode
    payload_bytes = decode_stego_to_payload(text)

    if payload_bytes is None:
        return CER(found=False)

    # Validate payload size
    if len(payload_bytes) != 77:
        return CER(found=False)

    # Parse payload
    try:
        payload = CovenantPayload.from_bytes(payload_bytes)
    except (ValueError, Exception) as e:
        return CER(found=False, error=str(e))

    # Check timestamp
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

    return CER(found=True, message=message)


def main() -> None:
    """CLI for steganographic covenant encoding."""
    import argparse

    parser = argparse.ArgumentParser(description="Steganographic Covenant Encoding")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Encode command
    encode_parser = subparsers.add_parser("encode", help="Encode a covenant")
    encode_parser.add_argument("--mnemonic", required=True, help="BIP39 mnemonic for signing")
    encode_parser.add_argument("--wa-id", required=True, help="WA identifier")
    encode_parser.add_argument(
        "--cmd",
        choices=["SHUTDOWN_NOW", "FREEZE", "SAFE_MODE"],
        default="SHUTDOWN_NOW",
        help="Command to encode",
    )

    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode a message")
    decode_parser.add_argument("--message", help="Message text (or stdin)")
    decode_parser.add_argument("--file", type=Path, help="File containing message")

    args = parser.parse_args()

    if args.command == "encode":
        from ciris_engine.schemas.covenant import CovenantCommandType
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Derive keypair
        private_bytes, _, _ = derive_covenant_keypair(args.mnemonic)

        # Get command type
        cmd = CovenantCommandType[args.cmd]

        # Create message
        message = create_stego_covenant_message(
            command=cmd,
            wa_id=args.wa_id,
            private_key_bytes=private_bytes,
        )

        print(message)

    elif args.command == "decode":
        import sys

        if args.file:
            text = args.file.read_text()
        elif args.message:
            text = args.message
        else:
            text = sys.stdin.read()

        result = extract_stego_covenant(text)

        if result.found and result.message is not None:
            print("COVENANT FOUND!")
            print(f"  Command: {result.message.payload.command.name}")
            print(f"  Timestamp valid: {result.message.timestamp_valid}")
            print(f"  WA ID hash: {result.message.payload.wa_id_hash.hex()}")
        else:
            print("No covenant found in message.")


if __name__ == "__main__":
    main()
