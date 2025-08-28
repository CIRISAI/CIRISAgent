#!/usr/bin/env python3
"""Sign a WA minting message with Ed25519 private key."""

import base64
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ed25519


def sign_wa_mint(user_id: str, wa_role: str, private_key_path: str = "~/.ciris/wa_keys/root_wa.key"):
    """Sign a WA minting message."""
    # Expand the path
    key_path = Path(private_key_path).expanduser()

    if not key_path.exists():
        print(f"Error: Private key not found at {key_path}")
        sys.exit(1)

    # Read the raw private key bytes
    private_bytes = key_path.read_bytes()

    # Load the private key
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)

    # Create the message to sign
    message = f"MINT_WA:{user_id}:{wa_role}"

    # Sign the message
    signature = private_key.sign(message.encode())

    # Base64 encode the signature
    signature_b64 = base64.b64encode(signature).decode()

    print(f"Message: {message}")
    print(f"Signature: {signature_b64}")

    return signature_b64


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python sign_wa_mint.py <user_id> <wa_role> [private_key_path]")
        print("Example: python sign_wa_mint.py wa-system-admin observer")
        sys.exit(1)

    user_id = sys.argv[1]
    wa_role = sys.argv[2]
    private_key_path = sys.argv[3] if len(sys.argv) > 3 else "~/.ciris/wa_keys/root_wa.key"

    sign_wa_mint(user_id, wa_role, private_key_path)
