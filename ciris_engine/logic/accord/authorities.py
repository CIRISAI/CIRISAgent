"""The WA trust root for the signed emergency-shutdown command (#998).

``/v1/emergency/shutdown`` accepts a ``WASignedCommand`` and resolves its signer
here — one authority list, so the API and the control service cannot drift onto
different keys.

This is what survives of the legacy accord verifier. The 77-byte stego
``AccordPayload`` it also verified is retired (CIRISAgent#1231, decision 4): the
CC 4.2.1.1 constitutional halt is verified and latched by the node, never by the
agent. Retiring it also removed the process kill this module used to issue when
it loaded no authorities. An empty roster now refuses every emergency command
and says so loudly; it never ends the process (the agent does not own it).
"""

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Seed key locations, checked in order.
SEED_KEY_PATHS = [
    Path("seed/root_pub.json"),  # Relative to CWD
    Path(__file__).parent.parent.parent.parent / "seed" / "root_pub.json",  # Relative to package
    Path.home() / ".ciris" / "seed" / "root_pub.json",  # User home
    Path("/app/seed/root_pub.json"),  # Docker container
]

# Fallback when no seed file is present: the root WA key from seed/root_pub.json.
HARDCODED_ROOT_KEYS = [
    ("wa-2025-06-14-ROOT00", "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk", "ROOT"),
]


def _compute_wa_id_hash(wa_id: str) -> bytes:
    """The 8-byte hash of a WA ID."""
    return hashlib.sha256(wa_id.encode("utf-8")).digest()[:8]


def _decode_public_key(key: str) -> Optional[bytes]:
    """Decode a 32-byte Ed25519 public key from URL-safe base64 or hex."""
    try:
        padding = 4 - len(key) % 4
        key_padded = key + "=" * padding if padding < 4 else key
        decoded = base64.urlsafe_b64decode(key_padded)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    try:
        decoded = bytes.fromhex(key)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass
    return None


class TrustedAuthority:
    """A WA authority whose signature an emergency command may carry."""

    def __init__(self, wa_id: str, public_key: bytes, role: str = "ROOT"):
        self.wa_id = wa_id
        self.public_key = public_key
        self.role = role
        self.wa_id_hash = _compute_wa_id_hash(wa_id)


def load_seed_key() -> Optional[tuple[str, str, str]]:
    """The ROOT seed key from seed/root_pub.json, as (wa_id, public_key, role)."""
    for path in SEED_KEY_PATHS:
        try:
            if path.exists():
                data = json.loads(path.read_text())
                wa_id = data.get("wa_id", "wa-unknown")
                pubkey = data.get("pubkey")
                role = data.get("role", "ROOT").upper()
                if pubkey:
                    logger.info(f"Loaded emergency trust-root seed key from {path}: {wa_id}")
                    return (wa_id, pubkey, role)
        except Exception as e:
            logger.debug(f"Could not load seed key from {path}: {e}")
            continue
    return None


class EmergencyAuthorities:
    """The roster an emergency-shutdown signature is checked against."""

    def __init__(self, auto_load_seed: bool = True):
        self._authorities: list[TrustedAuthority] = []
        if auto_load_seed:
            self._load_default_authorities()

    def _load_default_authorities(self) -> int:
        loaded = 0
        seed_key = load_seed_key()
        if seed_key:
            wa_id, pubkey, role = seed_key
            if self.add_authority(wa_id, pubkey, role):
                loaded += 1

        existing_ids = {auth.wa_id for auth in self._authorities}
        for wa_id, pubkey, role in HARDCODED_ROOT_KEYS:
            if wa_id not in existing_ids and self.add_authority(wa_id, pubkey, role):
                loaded += 1

        if loaded == 0:
            # Fail closed, not fatal: with no roster no emergency command can
            # verify. The constitutional halt does not depend on this roster.
            logger.critical(
                "No emergency trust-root authorities loaded: every WA-signed emergency command will be refused."
            )
        else:
            logger.info(f"Loaded {loaded} emergency trust-root authorities")
        return loaded

    def add_authority(self, wa_id: str, public_key: str | bytes, role: str = "ROOT") -> bool:
        """Add or update an authority. The key is base64, hex, or 32 raw bytes."""
        if isinstance(public_key, str):
            key_bytes = _decode_public_key(public_key)
            if key_bytes is None:
                logger.error(f"Invalid public key format for {wa_id}")
                return False
        else:
            key_bytes = public_key

        if len(key_bytes) != 32:
            logger.error(f"Public key must be 32 bytes for {wa_id}")
            return False

        for auth in self._authorities:
            if auth.wa_id == wa_id:
                auth.public_key = key_bytes
                auth.role = role
                logger.info(f"Updated trusted authority: {wa_id}")
                return True

        self._authorities.append(TrustedAuthority(wa_id=wa_id, public_key=key_bytes, role=role))
        logger.info(f"Added trusted authority: {wa_id} ({role})")
        return True

    def remove_authority(self, wa_id: str) -> bool:
        for i, auth in enumerate(self._authorities):
            if auth.wa_id == wa_id:
                del self._authorities[i]
                logger.info(f"Removed trusted authority: {wa_id}")
                return True
        return False

    @property
    def authority_count(self) -> int:
        return len(self._authorities)

    def public_key_for(self, wa_id: str) -> Optional[bytes]:
        """Raw Ed25519 public key for a trusted authority, or None."""
        for auth in self._authorities:
            if auth.wa_id == wa_id:
                return bytes(auth.public_key)
        return None

    def list_authorities(self) -> list[dict[str, Any]]:
        """All trusted authorities, public information only."""
        return [
            {"wa_id": auth.wa_id, "role": auth.role, "wa_id_hash": auth.wa_id_hash.hex()} for auth in self._authorities
        ]


__all__ = ["EmergencyAuthorities", "TrustedAuthority", "load_seed_key"]
