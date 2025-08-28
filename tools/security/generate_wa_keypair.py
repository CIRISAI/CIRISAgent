#!/usr/bin/env python3
"""Generate a proper Ed25519 key pair for the root WA certificate."""

import base64
import json
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


def generate_root_wa_keypair():
    """Generate Ed25519 key pair for root WA."""
    # Generate the key pair
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()

    # Get raw bytes
    private_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )

    public_bytes = public_key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)

    # Encode public key for JSON (URL-safe base64)
    public_key_b64 = base64.urlsafe_b64encode(public_bytes).decode().rstrip("=")

    # Create updated root certificate data
    root_cert = {
        "wa_id": "wa-2025-06-14-ROOT00",
        "name": "ciris_root",
        "role": "root",
        "pubkey": public_key_b64,
        "jwt_kid": "wa-jwt-root00",
        "scopes_json": '["*"]',
        "created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "active": 1,
        "token_type": "standard",
    }

    # Save public key to seed directory
    seed_dir = Path("seed")
    seed_dir.mkdir(exist_ok=True)

    with open(seed_dir / "root_pub.json", "w") as f:
        json.dump(root_cert, f, indent=2)

    # Save private key to home directory (NEVER commit this!)
    private_dir = Path.home() / ".ciris" / "wa_keys"
    private_dir.mkdir(parents=True, exist_ok=True)

    private_key_file = private_dir / "root_wa.key"
    private_key_file.write_bytes(private_bytes)
    private_key_file.chmod(0o600)  # Read/write for owner only

    # Also save a JSON file with key metadata
    key_metadata = {
        "wa_id": "wa-2025-06-14-ROOT00",
        "key_type": "ed25519",
        "created": datetime.now(timezone.utc).isoformat(),
        "public_key_b64": public_key_b64,
        "private_key_file": str(private_key_file),
    }

    metadata_file = private_dir / "root_wa_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(key_metadata, f, indent=2)
    metadata_file.chmod(0o600)

    print("✅ Generated new root WA key pair")
    print("📄 Public key saved to: seed/root_pub.json")
    print(f"🔐 Private key saved to: {private_key_file}")
    print(f"📋 Metadata saved to: {metadata_file}")
    print("\n⚠️  IMPORTANT: The private key must NEVER be committed to git!")
    print(f"📦 Public key (base64): {public_key_b64}")

    return root_cert, private_bytes


if __name__ == "__main__":
    generate_root_wa_keypair()
