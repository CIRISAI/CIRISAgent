"""
iOS bcrypt stub using PBKDF2.

The native bcrypt library requires Rust compilation which isn't available on iOS.
This stub provides bcrypt-compatible API using Python's built-in hashlib.pbkdf2_hmac.

Security Note: PBKDF2-SHA256 is a NIST-recommended alternative to bcrypt and is
suitable for password hashing. We use 310,000 iterations as recommended by OWASP
for PBKDF2-SHA256 (equivalent security to bcrypt cost 12).

References:
- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- https://passlib.readthedocs.io/en/stable/lib/passlib.hash.bcrypt.html
"""

import base64
import hashlib
import os
import sys

print("[iOS] Using PBKDF2 bcrypt stub (pure Python)", flush=True)


def gensalt(rounds: int = 12, prefix: bytes = b"2b") -> bytes:
    """Generate a salt for hashing.

    Args:
        rounds: Cost factor (ignored for PBKDF2, we use fixed iterations)
        prefix: bcrypt prefix (ignored, kept for API compatibility)

    Returns:
        Salt bytes in bcrypt-compatible format
    """
    # Generate 16 random bytes for the salt
    salt_bytes = os.urandom(16)
    # Encode in a format that includes the "rounds" for bcrypt compatibility
    # Format: $pbkdf2$<iterations>$<salt_b64>
    salt_b64 = base64.b64encode(salt_bytes).decode('ascii')
    return f"$pbkdf2$310000${salt_b64}".encode('utf-8')


def hashpw(password: bytes, salt: bytes) -> bytes:
    """Hash a password with the given salt.

    Args:
        password: Password bytes to hash
        salt: Salt from gensalt()

    Returns:
        Hashed password in bcrypt-compatible format
    """
    salt_str = salt.decode('utf-8')

    if salt_str.startswith('$pbkdf2$'):
        # Our PBKDF2 format: $pbkdf2$<iterations>$<salt_b64>
        parts = salt_str.split('$')
        iterations = int(parts[2])
        salt_b64 = parts[3]
        salt_bytes = base64.b64decode(salt_b64)
    elif salt_str.startswith('$2'):
        # Legacy bcrypt format - convert to PBKDF2
        # Extract what we can and generate new salt
        salt_bytes = os.urandom(16)
        iterations = 310000
        salt_b64 = base64.b64encode(salt_bytes).decode('ascii')
    else:
        raise ValueError(f"Unknown salt format: {salt_str[:20]}")

    # Hash using PBKDF2-SHA256
    dk = hashlib.pbkdf2_hmac(
        'sha256',
        password,
        salt_bytes,
        iterations,
        dklen=32
    )

    # Encode the hash
    hash_b64 = base64.b64encode(dk).decode('ascii')

    # Return in our format: $pbkdf2$<iterations>$<salt_b64>$<hash_b64>
    return f"$pbkdf2${iterations}${salt_b64}${hash_b64}".encode('utf-8')


def checkpw(password: bytes, hashed_password: bytes) -> bool:
    """Check a password against a hash.

    Args:
        password: Password to check
        hashed_password: Previously hashed password

    Returns:
        True if password matches, False otherwise
    """
    hashed_str = hashed_password.decode('utf-8')

    if hashed_str.startswith('$pbkdf2$'):
        # Our PBKDF2 format: $pbkdf2$<iterations>$<salt_b64>$<hash_b64>
        parts = hashed_str.split('$')
        iterations = int(parts[2])
        salt_b64 = parts[3]
        stored_hash_b64 = parts[4]

        salt_bytes = base64.b64decode(salt_b64)
        stored_hash = base64.b64decode(stored_hash_b64)

        # Compute hash with same parameters
        dk = hashlib.pbkdf2_hmac(
            'sha256',
            password,
            salt_bytes,
            iterations,
            dklen=32
        )

        # Constant-time comparison
        return _constant_time_compare(dk, stored_hash)

    elif hashed_str.startswith('$2'):
        # This is a legacy bcrypt hash - we can't verify it without native bcrypt
        # In production, you'd want to rehash on next login
        print("[iOS bcrypt] Warning: Cannot verify legacy bcrypt hash, returning False", flush=True)
        return False

    else:
        raise ValueError(f"Unknown hash format: {hashed_str[:20]}")


def _constant_time_compare(a: bytes, b: bytes) -> bool:
    """Compare two byte strings in constant time to prevent timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a, b):
        result |= x ^ y
    return result == 0


# Install this module as 'bcrypt' so imports work
sys.modules['bcrypt'] = sys.modules[__name__]
