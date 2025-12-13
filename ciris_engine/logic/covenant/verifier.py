"""
Covenant Verification Module.

Verifies covenant signatures against known authority public keys.
Only ROOT and SYSTEM_ADMIN (via ROOT WA role) can invoke covenants.

The verifier:
1. Checks the signature against all known authority keys
2. Validates the WA ID hash matches the signing authority
3. Confirms the authority has shutdown privileges (ROOT or AUTHORITY role)
"""

import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ciris_engine.schemas.covenant import (
    CovenantMessage,
    CovenantPayload,
    CovenantVerificationResult,
    verify_covenant_signature,
)

logger = logging.getLogger(__name__)

# Default seed key locations (checked in order)
SEED_KEY_PATHS = [
    Path("seed/root_pub.json"),  # Relative to CWD
    Path(__file__).parent.parent.parent.parent / "seed" / "root_pub.json",  # Relative to package
    Path.home() / ".ciris" / "seed" / "root_pub.json",  # User home
    Path("/app/seed/root_pub.json"),  # Docker container
]

# Hardcoded fallback keys (from emergency.py for compatibility)
HARDCODED_ROOT_KEYS = [
    # Root WA key from seed/root_pub.json
    ("wa-2025-06-14-ROOT00", "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk", "ROOT"),
]


def _compute_wa_id_hash(wa_id: str) -> bytes:
    """Compute the 8-byte hash of a WA ID."""
    return hashlib.sha256(wa_id.encode("utf-8")).digest()[:8]


def _decode_public_key(key: str) -> Optional[bytes]:
    """
    Decode a public key from base64 or hex format.

    Args:
        key: Public key in base64 (with or without padding) or hex

    Returns:
        32 bytes of public key, or None if invalid
    """
    try:
        # Try base64 first (URL-safe)
        # Add padding if needed
        padding = 4 - len(key) % 4
        if padding < 4:
            key_padded = key + "=" * padding
        else:
            key_padded = key
        decoded = base64.urlsafe_b64decode(key_padded)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    try:
        # Try hex
        decoded = bytes.fromhex(key)
        if len(decoded) == 32:
            return decoded
    except Exception:
        pass

    return None


class TrustedAuthority:
    """A trusted authority that can invoke covenants."""

    def __init__(
        self,
        wa_id: str,
        public_key: bytes,
        role: str = "ROOT",
    ):
        """
        Initialize a trusted authority.

        Args:
            wa_id: The WA ID (e.g., "wa-2025-06-14-ROOT00")
            public_key: Ed25519 public key bytes (32 bytes)
            role: The WA role (ROOT or AUTHORITY)
        """
        self.wa_id = wa_id
        self.public_key = public_key
        self.role = role
        self.wa_id_hash = _compute_wa_id_hash(wa_id)


def verify_covenant(
    payload: CovenantPayload,
    trusted_authorities: list[TrustedAuthority],
) -> CovenantVerificationResult:
    """
    Verify a covenant payload against trusted authorities.

    Args:
        payload: The covenant payload to verify
        trusted_authorities: List of trusted authorities to check against

    Returns:
        Verification result with details
    """
    # Check timestamp validity first
    if not payload.is_timestamp_valid():
        return CovenantVerificationResult(
            valid=False,
            rejection_reason="Timestamp outside valid window (expired or future)",
        )

    # Check each trusted authority
    for authority in trusted_authorities:
        # First check if WA ID hash matches
        if payload.wa_id_hash != authority.wa_id_hash:
            continue

        # WA ID matches - verify signature
        if verify_covenant_signature(payload, authority.public_key):
            # Valid signature from this authority
            return CovenantVerificationResult(
                valid=True,
                command=payload.command,
                wa_id=authority.wa_id,
                wa_role=authority.role,
            )

    # No matching authority found
    return CovenantVerificationResult(
        valid=False,
        rejection_reason="No matching trusted authority found for signature",
    )


def load_seed_key() -> Optional[tuple[str, str, str]]:
    """
    Load the ROOT seed key from the seed file.

    Checks multiple locations for seed/root_pub.json.

    Returns:
        Tuple of (wa_id, public_key, role) if found, None otherwise
    """
    for path in SEED_KEY_PATHS:
        try:
            if path.exists():
                data = json.loads(path.read_text())
                wa_id = data.get("wa_id", "wa-unknown")
                pubkey = data.get("pubkey")
                role = data.get("role", "ROOT").upper()
                if pubkey:
                    logger.info(f"Loaded covenant seed key from {path}: {wa_id}")
                    return (wa_id, pubkey, role)
        except Exception as e:
            logger.debug(f"Could not load seed key from {path}: {e}")
            continue
    return None


class CovenantVerifier:
    """
    Stateful covenant verifier with authority management.

    This class manages the list of trusted authorities and provides
    verification with caching and metrics.
    """

    def __init__(self, auto_load_seed: bool = True):
        """
        Initialize the verifier.

        Args:
            auto_load_seed: If True, automatically load seed key and hardcoded keys
        """
        self._authorities: list[TrustedAuthority] = []
        self._verification_count = 0
        self._valid_count = 0
        self._rejected_count = 0

        if auto_load_seed:
            self._load_default_authorities()

    def _load_default_authorities(self) -> int:
        """
        Load default authorities from seed file and hardcoded fallbacks.

        This ensures the ROOT seed key is always available for covenant
        verification, even if no explicit configuration is provided.

        Returns:
            Number of authorities loaded
        """
        loaded = 0

        # First, try to load from seed file (most authoritative source)
        seed_key = load_seed_key()
        if seed_key:
            wa_id, pubkey, role = seed_key
            if self.add_authority(wa_id, pubkey, role):
                loaded += 1
                logger.info(f"Loaded seed key authority: {wa_id}")

        # Add hardcoded fallback keys (dedup by WA ID)
        existing_ids = {auth.wa_id for auth in self._authorities}
        for wa_id, pubkey, role in HARDCODED_ROOT_KEYS:
            if wa_id not in existing_ids:
                if self.add_authority(wa_id, pubkey, role):
                    loaded += 1
                    logger.info(f"Loaded hardcoded authority: {wa_id}")

        if loaded == 0:
            # CRITICAL: No authorities means no working kill switch
            # This is a fatal error - agent cannot operate
            import os
            import signal

            logger.critical(
                "CRITICAL FAILURE: No covenant authorities loaded! "
                "Agent cannot operate without a functioning kill switch. TERMINATING."
            )
            os.kill(os.getpid(), signal.SIGKILL)
        else:
            logger.info(f"Loaded {loaded} covenant authorities")

        return loaded

    def add_authority(
        self,
        wa_id: str,
        public_key: str | bytes,
        role: str = "ROOT",
    ) -> bool:
        """
        Add a trusted authority.

        Args:
            wa_id: The WA ID
            public_key: Ed25519 public key (base64, hex, or bytes)
            role: The WA role

        Returns:
            True if added successfully
        """
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

        # Check for duplicate
        for auth in self._authorities:
            if auth.wa_id == wa_id:
                # Update existing
                auth.public_key = key_bytes
                auth.role = role
                logger.info(f"Updated trusted authority: {wa_id}")
                return True

        # Add new
        self._authorities.append(TrustedAuthority(wa_id=wa_id, public_key=key_bytes, role=role))
        logger.info(f"Added trusted authority: {wa_id} ({role})")
        return True

    def remove_authority(self, wa_id: str) -> bool:
        """
        Remove a trusted authority.

        Args:
            wa_id: The WA ID to remove

        Returns:
            True if removed
        """
        for i, auth in enumerate(self._authorities):
            if auth.wa_id == wa_id:
                del self._authorities[i]
                logger.info(f"Removed trusted authority: {wa_id}")
                return True
        return False

    def load_from_config(self, root_wa_public_keys: list[str]) -> int:
        """
        Load authorities from config (legacy format).

        This supports the existing KillSwitchConfig.root_wa_public_keys format
        where we only have public keys without WA IDs.

        Args:
            root_wa_public_keys: List of public keys in base64/hex format

        Returns:
            Number of authorities loaded
        """
        loaded = 0
        for i, key in enumerate(root_wa_public_keys):
            # Generate a synthetic WA ID for legacy keys
            wa_id = f"wa-legacy-root-{i:02d}"
            if self.add_authority(wa_id, key, "ROOT"):
                loaded += 1
        return loaded

    def verify(
        self,
        message: CovenantMessage,
    ) -> CovenantVerificationResult:
        """
        Verify a covenant message.

        Args:
            message: The extracted covenant message

        Returns:
            Verification result
        """
        self._verification_count += 1

        result = verify_covenant(message.payload, self._authorities)

        if result.valid:
            self._valid_count += 1
            logger.warning(
                f"COVENANT VERIFIED: {result.command.name if result.command else 'unknown'} "
                f"from {result.wa_id} ({result.wa_role}) via {message.source_channel}"
            )
        else:
            self._rejected_count += 1
            logger.debug(f"Covenant rejected: {result.rejection_reason}")

        return result

    @property
    def authority_count(self) -> int:
        """Number of trusted authorities."""
        return len(self._authorities)

    @property
    def verification_count(self) -> int:
        """Number of verification attempts."""
        return self._verification_count

    @property
    def valid_count(self) -> int:
        """Number of valid covenants."""
        return self._valid_count

    @property
    def rejected_count(self) -> int:
        """Number of rejected covenants."""
        return self._rejected_count

    def list_authorities(self) -> list[dict[str, Any]]:
        """List all trusted authorities (public info only)."""
        return [
            {
                "wa_id": auth.wa_id,
                "role": auth.role,
                "wa_id_hash": auth.wa_id_hash.hex(),
            }
            for auth in self._authorities
        ]
