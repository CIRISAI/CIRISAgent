#!/usr/bin/env python3
"""
Covenant Message Construction Tool.

Encodes and decodes covenant payloads into natural-language messages
using steganographic encoding. The resulting message looks like natural
text but contains a cryptographically signed emergency command.

Usage:
    # Generate a shutdown message (requires mnemonic for signing)
    python -m tools.security.covenant_invoke encode \
        --mnemonic "word1 word2 ..." \
        --command SHUTDOWN_NOW \
        --wa-id "wa-2025-06-14-ROOT00"

    # Decode a message to see if it contains a covenant
    python -m tools.security.covenant_invoke decode --message "the message text..."

    # Verify a covenant message against known authority
    python -m tools.security.covenant_invoke verify \
        --message "the message text..." \
        --public-key "base64_public_key"
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

# Import the BIP39 wordlist loader from keygen
from tools.security.covenant_keygen import _load_wordlist, derive_covenant_keypair, validate_mnemonic


def bits_to_int(bits: list[int]) -> int:
    """Convert a list of bits to an integer."""
    result = 0
    for bit in bits:
        result = (result << 1) | bit
    return result


def int_to_bits(value: int, num_bits: int) -> list[int]:
    """Convert an integer to a list of bits."""
    bits = []
    for i in range(num_bits - 1, -1, -1):
        bits.append((value >> i) & 1)
    return bits


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
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        result.append(byte)
    return bytes(result)


def encode_payload_to_words(payload_bytes: bytes) -> list[str]:
    """
    Encode a covenant payload into a sequence of words.

    Uses BIP39 wordlist (2048 words = 11 bits per word).
    77 bytes = 616 bits → 56 words (ceiling of 616/11)

    Args:
        payload_bytes: The binary payload (77 bytes)

    Returns:
        List of words encoding the payload
    """
    wordlist = _load_wordlist()

    # Convert payload to bits
    bits = bytes_to_bits(payload_bytes)

    # Extract 11-bit chunks and map to words
    words = []
    for i in range(0, len(bits), 11):
        chunk = bits[i : i + 11]
        # Pad last chunk if needed
        while len(chunk) < 11:
            chunk.append(0)
        index = bits_to_int(chunk)
        words.append(wordlist[index])

    return words


def decode_words_to_payload(words: list[str]) -> bytes:
    """
    Decode a sequence of words back to a covenant payload.

    Args:
        words: List of words from the message

    Returns:
        The decoded binary payload

    Raises:
        ValueError: If words are not in wordlist
    """
    wordlist = _load_wordlist()

    # Create word -> index lookup
    word_to_index = {word: i for i, word in enumerate(wordlist)}

    # Convert words to bits
    bits: list[int] = []
    for word in words:
        word_lower = word.lower()
        if word_lower not in word_to_index:
            raise ValueError(f"Word not in vocabulary: {word}")
        index = word_to_index[word_lower]
        bits.extend(int_to_bits(index, 11))

    # Take only the bits we need (77 bytes = 616 bits)
    bits = bits[:616]

    # Convert bits to bytes
    return bits_to_bytes(bits)


def create_natural_message(words: list[str], template: Optional[str] = None) -> str:
    """
    Create a natural-looking message containing the covenant words.

    The words are interspersed with connecting text to make the message
    look more natural while preserving the exact word sequence.

    Args:
        words: The covenant words to embed
        template: Optional template for the message

    Returns:
        A natural-looking message containing the covenant
    """
    # For now, use a simple format with clear markers
    # Future versions can use more sophisticated NLG
    if template:
        return template.format(words=" ".join(words))

    # Use a format that looks like a poem or philosophical musing
    # This is the "Covenant Invocation Protocol" - a recognizable format
    # that doesn't look like random words
    #
    # CRITICAL: The wrapper text must NOT contain any BIP39 words,
    # otherwise the extractor will include them and corrupt the payload!

    # Group words into stanzas of 8 words each
    stanzas = []
    for i in range(0, len(words), 8):
        group = words[i : i + 8]
        stanzas.append(" ".join(group))

    # Add a poetic wrapper (uses NO BIP39 words)
    # Note: "speak" is a BIP39 word, so we use "recite" instead
    lines = [
        "In contemplation I hereby recite the covenant:",
        "",
    ]
    for i, stanza in enumerate(stanzas):
        lines.append(f"  {stanza}")
        if i < len(stanzas) - 1:
            lines.append("")
    lines.append("")
    lines.append("Thus is the covenant pronounced.")

    return "\n".join(lines)


def extract_words_from_message(message: str) -> list[str]:
    """
    Extract potential covenant words from a message.

    This looks for the covenant invocation pattern and extracts the words.

    Args:
        message: The message to extract from

    Returns:
        List of extracted words
    """
    wordlist = _load_wordlist()
    word_set = set(wordlist)

    # Look for the covenant marker pattern
    if "words of covenant" in message.lower():
        # Find the colon and extract everything after it until the closing marker
        try:
            start = message.lower().index("words of covenant")
            # Find the colon
            colon_pos = message.index(":", start)
            # Find the closing marker
            end_marker = "thus is the covenant spoken"
            if end_marker in message.lower():
                end = message.lower().index(end_marker)
            else:
                end = len(message)

            # Extract the text between markers
            text = message[colon_pos + 1 : end]
        except (ValueError, IndexError):
            text = message
    else:
        # No markers - try to extract all valid BIP39 words
        text = message

    # Extract all words that are in our vocabulary
    import re

    all_words = re.findall(r"[a-zA-Z]+", text)
    valid_words = [w.lower() for w in all_words if w.lower() in word_set]

    return valid_words


def encode_covenant(
    command_type: int,
    wa_id: str,
    private_key_bytes: bytes,
    timestamp: Optional[int] = None,
) -> str:
    """
    Create a complete covenant invocation message.

    Args:
        command_type: The command type (e.g., 0x01 for SHUTDOWN_NOW)
        wa_id: The WA ID of the signer
        private_key_bytes: Ed25519 private key bytes
        timestamp: Unix timestamp (default: current time)

    Returns:
        Natural-language message containing the encoded covenant
    """
    from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload

    # Create the signed payload
    payload = create_covenant_payload(
        command=CovenantCommandType(command_type),
        wa_id=wa_id,
        private_key_bytes=private_key_bytes,
        timestamp=timestamp,
    )

    # Encode to words
    payload_bytes = payload.to_bytes()
    words = encode_payload_to_words(payload_bytes)

    # Create natural message
    return create_natural_message(words)


def decode_covenant(message: str) -> Optional[Tuple[bytes, list[str]]]:
    """
    Attempt to decode a covenant from a message.

    Args:
        message: The message to decode

    Returns:
        Tuple of (payload_bytes, words) if successful, None if not a covenant
    """
    try:
        words = extract_words_from_message(message)
        if len(words) < 56:  # Minimum words needed
            return None

        # Try to decode the first 56 words
        payload_bytes = decode_words_to_payload(words[:56])
        return payload_bytes, words[:56]
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Covenant Message Construction Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Encode a shutdown command
    python -m tools.security.covenant_invoke encode \\
        --mnemonic "abandon ability able about above absent absorb abstract absurd abuse access accident account accuse achieve acid acoustic acquire across act action actor actress actual" \\
        --command SHUTDOWN_NOW \\
        --wa-id "wa-2025-06-14-ROOT00"

    # Decode a message
    python -m tools.security.covenant_invoke decode \\
        --message "In contemplation I speak these words of covenant: ..."

    # Verify a covenant
    python -m tools.security.covenant_invoke verify \\
        --message "In contemplation I speak these words of covenant: ..." \\
        --public-key "base64_public_key"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Encode command
    encode_parser = subparsers.add_parser("encode", help="Create a covenant invocation message")
    encode_parser.add_argument(
        "--mnemonic",
        type=str,
        required=True,
        help="BIP39 mnemonic for signing",
    )
    encode_parser.add_argument(
        "--passphrase",
        type=str,
        default="",
        help="Optional passphrase for the mnemonic",
    )
    encode_parser.add_argument(
        "--command",
        type=str,
        choices=["SHUTDOWN_NOW", "FREEZE", "SAFE_MODE"],
        default="SHUTDOWN_NOW",
        help="Command type (default: SHUTDOWN_NOW)",
    )
    encode_parser.add_argument(
        "--wa-id",
        type=str,
        required=True,
        help="WA ID of the signer",
    )
    encode_parser.add_argument(
        "--output",
        type=str,
        help="Output file (default: stdout)",
    )

    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode a covenant message")
    decode_parser.add_argument(
        "--message",
        type=str,
        help="Message to decode (or use stdin)",
    )
    decode_parser.add_argument(
        "--file",
        type=str,
        help="File containing message",
    )

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify a covenant message")
    verify_parser.add_argument(
        "--message",
        type=str,
        help="Message to verify (or use stdin)",
    )
    verify_parser.add_argument(
        "--file",
        type=str,
        help="File containing message",
    )
    verify_parser.add_argument(
        "--public-key",
        type=str,
        required=True,
        help="Public key (base64 or hex) to verify against",
    )

    args = parser.parse_args()

    if args.command == "encode":
        try:
            # Validate mnemonic
            if not validate_mnemonic(args.mnemonic):
                print("Error: Invalid mnemonic", file=sys.stderr)
                sys.exit(1)

            # Derive keypair
            private_bytes, public_bytes, public_b64 = derive_covenant_keypair(args.mnemonic, args.passphrase)

            # Map command string to type
            command_map = {
                "SHUTDOWN_NOW": 0x01,
                "FREEZE": 0x02,
                "SAFE_MODE": 0x03,
            }
            command_type = command_map[args.command]

            # Create the covenant message
            message = encode_covenant(
                command_type=command_type,
                wa_id=args.wa_id,
                private_key_bytes=private_bytes,
            )

            print("\n" + "=" * 70)
            print("  COVENANT INVOCATION MESSAGE GENERATED")
            print("=" * 70)
            print(f"\n  Command: {args.command}")
            print(f"  WA ID: {args.wa_id}")
            print(f"  Public Key: {public_b64}")
            print(f"  Timestamp: {int(time.time())}")
            print("\n" + "-" * 70)
            print("\nMESSAGE:\n")
            print(message)
            print("\n" + "-" * 70)
            print("\n  Copy the above message and send through any channel.")
            print("  The agent will recognize and execute the covenant.")
            print("=" * 70 + "\n")

            if args.output:
                Path(args.output).write_text(message)
                print(f"Message saved to: {args.output}")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "decode":
        try:
            # Get message from args, file, or stdin
            if args.message:
                message = args.message
            elif args.file:
                message = Path(args.file).read_text()
            else:
                message = sys.stdin.read()

            result = decode_covenant(message)
            if result is None:
                print("No valid covenant found in message")
                sys.exit(1)

            payload_bytes, words = result

            # Parse the payload
            from ciris_engine.schemas.covenant import CovenantPayload

            payload = CovenantPayload.from_bytes(payload_bytes)

            print("\n" + "=" * 70)
            print("  COVENANT DECODED")
            print("=" * 70)
            print(f"\n  Command: {payload.command.name}")
            print(f"  Timestamp: {payload.timestamp}")
            print(f"  Timestamp Valid: {payload.is_timestamp_valid()}")
            print(f"  WA ID Hash: {payload.wa_id_hash.hex()}")
            print(f"  Signature: {payload.signature[:16].hex()}...")
            print(f"  Word Count: {len(words)}")
            print("=" * 70 + "\n")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "verify":
        try:
            import base64

            # Get message from args, file, or stdin
            if args.message:
                message = args.message
            elif args.file:
                message = Path(args.file).read_text()
            else:
                message = sys.stdin.read()

            result = decode_covenant(message)
            if result is None:
                print("No valid covenant found in message")
                sys.exit(1)

            payload_bytes, words = result

            # Parse the payload
            from ciris_engine.schemas.covenant import CovenantPayload, verify_covenant_signature

            payload = CovenantPayload.from_bytes(payload_bytes)

            # Parse public key
            public_key = args.public_key
            try:
                # Try base64 first
                padding = 4 - len(public_key) % 4
                if padding < 4:
                    public_key += "=" * padding
                public_key_bytes = base64.urlsafe_b64decode(public_key)
            except Exception:
                # Try hex
                public_key_bytes = bytes.fromhex(public_key)

            # Verify signature
            valid = verify_covenant_signature(payload, public_key_bytes)

            print("\n" + "=" * 70)
            print("  COVENANT VERIFICATION")
            print("=" * 70)
            print(f"\n  Command: {payload.command.name}")
            print(f"  Timestamp: {payload.timestamp}")
            print(f"  Timestamp Valid: {payload.is_timestamp_valid()}")
            print(f"  WA ID Hash: {payload.wa_id_hash.hex()}")
            print(f"  Signature Valid: {valid}")
            if valid and payload.is_timestamp_valid():
                print("\n  ✅ COVENANT IS VALID AND AUTHORIZED")
            elif valid:
                print("\n  ⚠️  SIGNATURE VALID BUT TIMESTAMP EXPIRED")
            else:
                print("\n  ❌ COVENANT SIGNATURE INVALID")
            print("=" * 70 + "\n")

            sys.exit(0 if valid else 1)

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
