#!/usr/bin/env python3
"""
Covenant Key Generation Tool

Generates Ed25519 keypairs from BIP39 mnemonic seeds for use with the
Covenant Invocation System. The mnemonic can be memorized and used to
derive the same key on any machine.

Usage:
    # Generate new mnemonic and keypair
    python -m tools.security.covenant_keygen generate

    # Derive keypair from existing mnemonic
    python -m tools.security.covenant_keygen derive --mnemonic "word1 word2 ..."

    # Verify a mnemonic is valid
    python -m tools.security.covenant_keygen verify --mnemonic "word1 word2 ..."
"""

import argparse
import base64
import hashlib
import json
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# BIP39 English wordlist (2048 words)
# We embed a subset for validation; full list loaded from file
BIP39_WORDLIST_URL = "https://raw.githubusercontent.com/bitcoin/bips/master/bip-0039/english.txt"

# Standard BIP39 English wordlist (2048 words)
BIP39_ENGLISH = None  # Loaded on first use


def _load_wordlist() -> list[str]:
    """Load the BIP39 English wordlist."""
    global BIP39_ENGLISH
    if BIP39_ENGLISH is not None:
        return BIP39_ENGLISH

    # Try to load from bundled file first
    wordlist_path = Path(__file__).parent / "bip39_english.txt"
    if wordlist_path.exists():
        BIP39_ENGLISH = wordlist_path.read_text().strip().split("\n")
        return BIP39_ENGLISH

    # Embedded minimal wordlist for bootstrapping
    # In production, the full wordlist file should be present
    raise FileNotFoundError(
        f"BIP39 wordlist not found at {wordlist_path}. " "Please download from: {BIP39_WORDLIST_URL}"
    )


def generate_mnemonic(word_count: int = 24) -> str:
    """
    Generate a new BIP39 mnemonic.

    Args:
        word_count: Number of words (12, 15, 18, 21, or 24)

    Returns:
        Space-separated mnemonic words
    """
    if word_count not in (12, 15, 18, 21, 24):
        raise ValueError("Word count must be 12, 15, 18, 21, or 24")

    wordlist = _load_wordlist()

    # Calculate entropy bits needed
    # 12 words = 128 bits, 24 words = 256 bits
    entropy_bits = word_count * 11 - word_count // 3
    entropy_bytes = entropy_bits // 8

    # Generate entropy
    entropy = secrets.token_bytes(entropy_bytes)

    # Calculate checksum
    hash_bytes = hashlib.sha256(entropy).digest()
    checksum_bits = word_count // 3

    # Combine entropy and checksum
    entropy_int = int.from_bytes(entropy, "big")
    checksum_int = hash_bytes[0] >> (8 - checksum_bits)
    combined = (entropy_int << checksum_bits) | checksum_int

    # Extract word indices (11 bits each)
    words = []
    total_bits = entropy_bits + checksum_bits
    for i in range(word_count):
        shift = total_bits - (i + 1) * 11
        index = (combined >> shift) & 0x7FF
        words.append(wordlist[index])

    return " ".join(words)


def validate_mnemonic(mnemonic: str) -> bool:
    """
    Validate a BIP39 mnemonic.

    Args:
        mnemonic: Space-separated mnemonic words

    Returns:
        True if valid, False otherwise
    """
    try:
        wordlist = _load_wordlist()
        words = mnemonic.strip().lower().split()

        if len(words) not in (12, 15, 18, 21, 24):
            return False

        # Check all words are in wordlist
        word_indices = []
        for word in words:
            if word not in wordlist:
                return False
            word_indices.append(wordlist.index(word))

        # Reconstruct the combined value
        combined = 0
        for index in word_indices:
            combined = (combined << 11) | index

        # Extract entropy and checksum
        checksum_bits = len(words) // 3
        entropy_bits = len(words) * 11 - checksum_bits

        checksum = combined & ((1 << checksum_bits) - 1)
        entropy = combined >> checksum_bits

        # Convert entropy to bytes
        entropy_bytes = entropy.to_bytes(entropy_bits // 8, "big")

        # Verify checksum
        hash_bytes = hashlib.sha256(entropy_bytes).digest()
        expected_checksum = hash_bytes[0] >> (8 - checksum_bits)

        return checksum == expected_checksum

    except Exception:
        return False


def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """
    Convert mnemonic to 64-byte seed using PBKDF2.

    This follows BIP39 specification exactly.

    Args:
        mnemonic: Space-separated mnemonic words
        passphrase: Optional passphrase (default empty)

    Returns:
        64-byte seed
    """
    mnemonic_bytes = mnemonic.encode("utf-8")
    salt = ("mnemonic" + passphrase).encode("utf-8")

    # BIP39 uses PBKDF2 with HMAC-SHA512, 2048 iterations
    seed = hashlib.pbkdf2_hmac(
        "sha512",
        mnemonic_bytes,
        salt,
        iterations=2048,
        dklen=64,
    )

    return seed


def seed_to_ed25519_keypair(seed: bytes) -> Tuple[bytes, bytes]:
    """
    Derive Ed25519 keypair from seed.

    Uses first 32 bytes of seed as Ed25519 private key seed.

    Args:
        seed: 64-byte BIP39 seed

    Returns:
        Tuple of (private_key_bytes, public_key_bytes)
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    # Use first 32 bytes as Ed25519 seed
    ed25519_seed = seed[:32]

    # Create Ed25519 private key from seed
    private_key = Ed25519PrivateKey.from_private_bytes(ed25519_seed)
    public_key = private_key.public_key()

    # Get raw bytes
    from cryptography.hazmat.primitives import serialization

    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    return private_bytes, public_bytes


def derive_covenant_keypair(
    mnemonic: str,
    passphrase: str = "",
) -> Tuple[bytes, bytes, str]:
    """
    Derive Ed25519 keypair from mnemonic for covenant invocation.

    Args:
        mnemonic: BIP39 mnemonic (12-24 words)
        passphrase: Optional passphrase

    Returns:
        Tuple of (private_key_bytes, public_key_bytes, public_key_b64)
    """
    if not validate_mnemonic(mnemonic):
        raise ValueError("Invalid mnemonic")

    seed = mnemonic_to_seed(mnemonic, passphrase)
    private_bytes, public_bytes = seed_to_ed25519_keypair(seed)

    # URL-safe base64 encoding (no padding) for public key
    public_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip("=")

    return private_bytes, public_bytes, public_b64


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Covenant Key Generation Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate new 24-word mnemonic and keypair
    python -m tools.security.covenant_keygen generate

    # Generate 12-word mnemonic
    python -m tools.security.covenant_keygen generate --words 12

    # Derive keypair from existing mnemonic
    python -m tools.security.covenant_keygen derive --mnemonic "word1 word2 ..."

    # Verify mnemonic validity
    python -m tools.security.covenant_keygen verify --mnemonic "word1 word2 ..."
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate new mnemonic and keypair")
    gen_parser.add_argument(
        "--words",
        type=int,
        default=24,
        choices=[12, 15, 18, 21, 24],
        help="Number of words in mnemonic (default: 24)",
    )
    gen_parser.add_argument(
        "--passphrase",
        type=str,
        default="",
        help="Optional passphrase for additional security",
    )
    gen_parser.add_argument(
        "--output",
        type=str,
        help="Output file for keypair metadata (default: stdout)",
    )

    # Derive command
    derive_parser = subparsers.add_parser("derive", help="Derive keypair from mnemonic")
    derive_parser.add_argument(
        "--mnemonic",
        type=str,
        required=True,
        help="BIP39 mnemonic (space-separated words)",
    )
    derive_parser.add_argument(
        "--passphrase",
        type=str,
        default="",
        help="Optional passphrase",
    )

    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify mnemonic validity")
    verify_parser.add_argument(
        "--mnemonic",
        type=str,
        required=True,
        help="BIP39 mnemonic to verify",
    )

    args = parser.parse_args()

    if args.command == "generate":
        try:
            mnemonic = generate_mnemonic(args.words)
            private_bytes, public_bytes, public_b64 = derive_covenant_keypair(mnemonic, args.passphrase)

            result = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "word_count": args.words,
                "mnemonic": mnemonic,
                "public_key_b64": public_b64,
                "public_key_hex": public_bytes.hex(),
                "has_passphrase": bool(args.passphrase),
                "warning": "KEEP THIS MNEMONIC SECRET. Anyone with these words can invoke the covenant.",
            }

            print("\n" + "=" * 70)
            print("  COVENANT KEY GENERATED")
            print("=" * 70)
            print(f"\n  Mnemonic ({args.words} words):\n")
            # Print mnemonic in groups of 4 for readability
            words = mnemonic.split()
            for i in range(0, len(words), 4):
                group = words[i : i + 4]
                print(f"    {i+1:2d}. " + "  ".join(f"{w:<12}" for w in group))
            print(f"\n  Public Key (base64): {public_b64}")
            print(f"  Public Key (hex):    {public_bytes.hex()}")
            print("\n" + "=" * 70)
            print("  WARNING: Store this mnemonic securely!")
            print("  Anyone with these words can shut down any CIRIS agent")
            print("  that trusts this public key.")
            print("=" * 70 + "\n")

            if args.output:
                # Don't include mnemonic in file output
                file_result = {
                    "generated_at": result["generated_at"],
                    "public_key_b64": public_b64,
                    "public_key_hex": public_bytes.hex(),
                    "note": "Mnemonic not stored - must be memorized or stored separately",
                }
                Path(args.output).write_text(json.dumps(file_result, indent=2))
                print(f"Public key metadata saved to: {args.output}")

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "derive":
        try:
            private_bytes, public_bytes, public_b64 = derive_covenant_keypair(args.mnemonic, args.passphrase)

            print("\n" + "=" * 70)
            print("  COVENANT KEY DERIVED")
            print("=" * 70)
            print(f"\n  Public Key (base64): {public_b64}")
            print(f"  Public Key (hex):    {public_bytes.hex()}")
            print("\n" + "=" * 70 + "\n")

        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "verify":
        try:
            if validate_mnemonic(args.mnemonic):
                print("Mnemonic is VALID")
                sys.exit(0)
            else:
                print("Mnemonic is INVALID", file=sys.stderr)
                sys.exit(1)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
