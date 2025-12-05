"""WA Authentication Service - Core authentication logic implementation."""

import asyncio
import base64
import functools
import hashlib
import inspect
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, TypeVar, Union, cast

import aiofiles
import jwt
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ciris_engine.logic.persistence.stores import authentication_store
from ciris_engine.logic.services.base_infrastructure_service import BaseInfrastructureService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.protocols.services.infrastructure.authentication import AuthenticationServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.authority.wise_authority import AuthenticationResult, TokenVerification, WAUpdate
from ciris_engine.schemas.services.authority_core import (
    AuthorizationContext,
    ChannelIdentity,
    JWTSubType,
    OAuthIdentityLink,
    TokenType,
    WACertificate,
    WARole,
)
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.models import Task

logger = logging.getLogger(__name__)

# Type variable for decorators
F = TypeVar("F", bound=Callable[..., Any])


class AuthenticationService(BaseInfrastructureService, AuthenticationServiceProtocol):
    """Infrastructure service for WA authentication and identity management."""

    def __init__(self, db_path: str, time_service: TimeService, key_dir: Optional[str] = None) -> None:
        """Initialize the WA Authentication Service.

        Args:
            db_path: Path to SQLite database
            time_service: TimeService instance for time operations (required)
            key_dir: Directory for key storage (defaults to ~/.ciris/)
        """
        super().__init__()  # Initialize BaseService
        self.db_path = db_path
        self.key_dir = Path(key_dir or os.path.expanduser("~/.ciris"))
        self.key_dir.mkdir(mode=0o700, exist_ok=True)

        # Store injected time service
        self._time_service = time_service

        # Initialize gateway secret
        self.gateway_secret = self._get_or_create_gateway_secret()

        # Cache for tokens and WAs
        self._token_cache: Dict[str, AuthorizationContext] = {}
        self._channel_token_cache: Dict[str, str] = {}

        # Initialize database
        self._init_database()

        # Track service state
        self._started = False
        self._start_time: Optional[datetime] = None

        # Authentication metrics tracking
        self._auth_attempts = 0
        self._auth_successes = 0
        self._auth_failures = 0
        self._token_validations = 0
        self._permission_checks = 0
        self._role_assignments = 0
        self._session_count = 0
        self._expired_sessions = 0
        self._active_tokens = 0
        self._revoked_tokens = 0

    def get_service_type(self) -> ServiceType:
        """Get service type - authentication is part of wise authority infrastructure."""
        from ciris_engine.schemas.runtime.enums import ServiceType

        return ServiceType.WISE_AUTHORITY

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            # Authentication operations
            "authenticate",
            "create_token",
            "verify_token",
            "verify_token_sync",
            "create_channel_token",
            # WA management
            "create_wa",
            "get_wa",
            "update_wa",
            "revoke_wa",
            "list_was",
            "rotate_keys",
            # Utility operations
            "bootstrap_if_needed",
            "update_last_login",
            "sign_task",
            "verify_task_signature",
            # Key operations
            "generate_keypair",
            "sign_data",
            "hash_password",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        # Only requires time service which is provided in __init__
        return self._time_service is not None

    @staticmethod
    def _encode_public_key(pubkey_bytes: bytes) -> str:
        """Encode public key using base64url without padding."""
        return base64.urlsafe_b64encode(pubkey_bytes).decode().rstrip("=")

    @staticmethod
    def _decode_public_key(pubkey_str: str) -> bytes:
        """Decode base64url encoded public key, adding padding if needed."""
        # Add padding if necessary
        padding = 4 - (len(pubkey_str) % 4)
        if padding != 4:
            pubkey_str += "=" * padding
        return base64.urlsafe_b64decode(pubkey_str)

    def _derive_encryption_key(self, salt: bytes) -> bytes:
        """Derive an encryption key from machine-specific data.

        Args:
            salt: Random salt for key derivation

        Returns:
            32-byte derived encryption key
        """
        # Use machine ID and hostname as key material
        machine_id = ""
        hostname = ""

        try:
            # Try to get machine ID (Linux)
            machine_id_path = Path("/etc/machine-id")
            if machine_id_path.exists():
                machine_id = machine_id_path.read_text().strip()
            else:
                # Fallback to hostname
                import socket

                hostname = socket.gethostname()
        except Exception:
            hostname = "default"

        # Combine machine-specific data with purpose identifier
        key_material = f"{machine_id}:{hostname}:gateway-secret-encryption".encode()

        # Use PBKDF2 to derive a 32-byte key with the provided salt
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100000, backend=default_backend())
        return kdf.derive(key_material)

    def _encrypt_secret(self, secret: bytes) -> bytes:
        """Encrypt a secret using AES-GCM with random salt.

        Format: salt (32 bytes) + nonce (12 bytes) + ciphertext + tag (16 bytes)
        """
        # Generate random salt for key derivation
        salt = os.urandom(32)

        # Derive encryption key with the salt
        key = self._derive_encryption_key(salt)

        # Generate a random 96-bit nonce for GCM
        nonce = os.urandom(12)

        # Create cipher
        cipher = Cipher(algorithms.AES(key), modes.GCM(nonce), backend=default_backend())
        encryptor = cipher.encryptor()

        # Encrypt and get tag
        ciphertext = encryptor.update(secret) + encryptor.finalize()

        # Return salt + nonce + ciphertext + tag
        return salt + nonce + ciphertext + encryptor.tag

    def _decrypt_secret(self, encrypted: bytes) -> bytes:
        """Decrypt a secret using AES-GCM.

        Expected format: salt (32 bytes) + nonce (12 bytes) + ciphertext + tag (16 bytes)
        """
        try:
            # Check minimum length: salt(32) + nonce(12) + tag(16) = 60 bytes minimum
            if len(encrypted) < 60:
                # Handle legacy format without salt for backward compatibility
                # Legacy format: nonce (12 bytes) + ciphertext + tag (16 bytes)
                legacy_salt = b"ciris-gateway-encryption-salt"
                key = self._derive_encryption_key(legacy_salt)

                nonce = encrypted[:12]
                tag = encrypted[-16:]
                ciphertext = encrypted[12:-16]

                cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
                decryptor = cipher.decryptor()
                return decryptor.update(ciphertext) + decryptor.finalize()
            else:
                # Extract components for new format
                salt = encrypted[:32]
                nonce = encrypted[32:44]
                tag = encrypted[-16:]
                ciphertext = encrypted[44:-16]

                # Derive key with extracted salt
                key = self._derive_encryption_key(salt)

                # Create cipher
                cipher = Cipher(algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend())
                decryptor = cipher.decryptor()

                # Decrypt
                return decryptor.update(ciphertext) + decryptor.finalize()
        except Exception as e:
            # Log the actual error for debugging (not exposed to caller)
            logger.debug(f"Decryption failed: {type(e).__name__}: {e}")
            # Always raise consistent error regardless of format or failure type
            raise ValueError("Invalid encrypted data format")

    def _get_or_create_gateway_secret(self) -> bytes:
        """Get or create the gateway secret for JWT signing."""
        secret_path = self.key_dir / "gateway.secret"
        encrypted_path = self.key_dir / "gateway.secret.enc"

        # Try to load existing encrypted secret first
        if encrypted_path.exists():
            try:
                encrypted = encrypted_path.read_bytes()
                return self._decrypt_secret(encrypted)
            except Exception as e:
                logger.warning(f"Failed to decrypt gateway secret: {type(e).__name__}")
                # Fall through to regenerate

        # Check for legacy unencrypted secret
        if secret_path.exists():
            # Read and encrypt the existing secret
            secret = secret_path.read_bytes()
            encrypted = self._encrypt_secret(secret)
            encrypted_path.write_bytes(encrypted)
            encrypted_path.chmod(0o600)
            # Remove the unencrypted version
            secret_path.unlink()
            return secret

        # Generate new 32-byte secret
        secret = secrets.token_bytes(32)
        encrypted = self._encrypt_secret(secret)
        encrypted_path.write_bytes(encrypted)
        encrypted_path.chmod(0o600)
        return secret

    def _init_database(self) -> None:
        """Initialize database tables if needed."""
        authentication_store.init_auth_database(self.db_path)

    def _row_to_wa(self, row_dict: JSONDict) -> WACertificate:
        """Convert a SQLite row dictionary to a WACertificate instance."""

        oauth_links_json = row_dict.get("oauth_links_json")
        oauth_links: List[OAuthIdentityLink] = []
        if oauth_links_json:
            try:
                # Type narrow: json.loads expects str, not the broader JSONDict value type
                if isinstance(oauth_links_json, str):
                    raw_links = json.loads(oauth_links_json)
                    for link in raw_links:
                        try:
                            oauth_links.append(OAuthIdentityLink(**link))
                        except Exception as exc:
                            logger.warning("Invalid OAuth link entry skipped: %s", exc)
            except json.JSONDecodeError:
                logger.warning("Invalid oauth_links_json for WA %s", row_dict.get("wa_id"))

        wa_dict = {
            "wa_id": row_dict["wa_id"],
            "name": row_dict["name"],
            "role": row_dict["role"],
            "pubkey": row_dict["pubkey"],
            "jwt_kid": row_dict["jwt_kid"],
            "password_hash": row_dict.get("password_hash"),
            "api_key_hash": row_dict.get("api_key_hash"),
            "oauth_provider": row_dict.get("oauth_provider"),
            "oauth_external_id": row_dict.get("oauth_external_id"),
            "oauth_links": oauth_links,
            "auto_minted": bool(row_dict.get("auto_minted", 0)),
            "veilid_id": row_dict.get("veilid_id"),
            "parent_wa_id": row_dict.get("parent_wa_id"),
            "parent_signature": row_dict.get("parent_signature"),
            "scopes_json": row_dict["scopes_json"],
            "custom_permissions_json": row_dict.get("custom_permissions_json"),
            "adapter_id": row_dict.get("adapter_id"),
            "adapter_name": row_dict.get("adapter_name"),
            "adapter_metadata_json": row_dict.get("adapter_metadata_json"),
            "created_at": row_dict["created"],
            "last_auth": row_dict.get("last_login"),
        }

        return WACertificate(**wa_dict)

    # WAStore Protocol Implementation

    async def get_wa(self, wa_id: str) -> Optional[WACertificate]:
        """Get WA certificate by ID."""
        return authentication_store.get_wa_by_id(wa_id, self.db_path)

    async def _get_wa_by_kid(self, jwt_kid: str) -> Optional[WACertificate]:
        """Get WA certificate by JWT key ID."""
        return authentication_store.get_wa_by_kid(jwt_kid, self.db_path)

    async def get_wa_by_oauth(self, provider: str, external_id: str) -> Optional[WACertificate]:
        """Get WA certificate by OAuth identity."""
        return authentication_store.get_wa_by_oauth(provider, external_id, self.db_path)

    async def _get_wa_by_adapter(self, adapter_id: str) -> Optional[WACertificate]:
        """Get WA certificate by adapter ID."""
        return authentication_store.get_wa_by_adapter(adapter_id, self.db_path)

    async def link_oauth_identity(
        self,
        wa_id: str,
        provider: str,
        external_id: str,
        *,
        account_name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        primary: bool = False,
    ) -> Optional[WACertificate]:
        existing = await self.get_wa(wa_id)
        if not existing:
            return None

        # Prevent linking to a provider that already belongs to another WA
        match = await self.get_wa_by_oauth(provider, external_id)
        if match and match.wa_id != wa_id:
            raise ValueError(f"OAuth identity {provider}:{external_id} already linked to another WA")

        links = list(existing.oauth_links)
        timestamp = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        found = False
        for idx, link in enumerate(links):
            if link.provider == provider and link.external_id == external_id:
                links[idx] = link.model_copy(
                    update={
                        "account_name": account_name or link.account_name,
                        "metadata": metadata or link.metadata,
                        "linked_at": link.linked_at or timestamp,
                    }
                )
                found = True
                break

        if not found:
            links.append(
                OAuthIdentityLink(
                    provider=provider,
                    external_id=external_id,
                    account_name=account_name,
                    metadata=metadata or {},
                    linked_at=timestamp,
                    is_primary=False,
                )
            )

            # Add identity mapping to graph for DSAR coordination
            # This creates a "same_as" edge between wa_id and oauth provider:external_id
            if hasattr(self, "_memory_bus") and self._memory_bus:
                try:
                    from ciris_engine.logic.utils.identity_resolution import add_identity_mapping

                    # Map wa_id to OAuth external_id in identity graph
                    await add_identity_mapping(
                        wa_id,
                        "wa_id",
                        external_id,
                        f"{provider}_id",
                        self._memory_bus,
                        confidence=1.0,
                        source="oauth",
                    )
                    logger.info(
                        f"Created identity mapping: wa_id:{wa_id} -> {provider}_id:{external_id}"
                    )  # NOSONAR - IDs not secrets
                except Exception as e:
                    logger.warning(f"Failed to create identity mapping for OAuth link: {e}")
                    # Non-fatal - OAuth link still works even if graph mapping fails

        if primary or (not existing.oauth_provider and not existing.oauth_external_id):
            existing = existing.model_copy(update={"oauth_provider": provider, "oauth_external_id": external_id})
            for link in links:
                link.is_primary = link.provider == provider and link.external_id == external_id

        # Build update kwargs, filtering out None values
        update_kwargs = {}
        if existing.oauth_provider:
            update_kwargs["oauth_provider"] = existing.oauth_provider
        if existing.oauth_external_id:
            update_kwargs["oauth_external_id"] = existing.oauth_external_id
        oauth_links_json = json.dumps([link.model_dump(mode="json") for link in links]) if links else None
        if oauth_links_json:
            update_kwargs["oauth_links_json"] = oauth_links_json

        await self.update_wa(wa_id, **update_kwargs)  # type: ignore[arg-type]
        return await self.get_wa(wa_id)

    async def unlink_oauth_identity(self, wa_id: str, provider: str, external_id: str) -> Optional[WACertificate]:
        existing = await self.get_wa(wa_id)
        if not existing:
            return None

        links = [
            link for link in existing.oauth_links if not (link.provider == provider and link.external_id == external_id)
        ]

        payload: JSONDict = {
            "oauth_links_json": json.dumps([link.model_dump(mode="json") for link in links]) if links else None,
        }

        # If unlinking the primary mapping, fall back to remaining links or clear
        if existing.oauth_provider == provider and existing.oauth_external_id == external_id:
            if links:
                new_primary = next((link for link in links if link.is_primary), links[0])
                payload["oauth_provider"] = new_primary.provider
                payload["oauth_external_id"] = new_primary.external_id
                for link in links:
                    link.is_primary = link is new_primary
                payload["oauth_links_json"] = json.dumps([link.model_dump(mode="json") for link in links])
            else:
                payload["oauth_provider"] = None
                payload["oauth_external_id"] = None

        # Filter out None values - update_wa kwargs expects Union[str, bool, datetime], not Optional
        filtered_payload = {k: v for k, v in payload.items() if v is not None}
        await self.update_wa(wa_id, **filtered_payload)  # type: ignore[arg-type]
        return await self.get_wa(wa_id)

    async def _store_wa_certificate(self, wa: WACertificate) -> None:
        """Store a WA certificate in the database."""
        authentication_store.store_wa_certificate(wa, self.db_path)

    async def _create_adapter_observer(self, adapter_id: str, name: str) -> WACertificate:
        """Create or reactivate adapter observer WA."""
        # Check if observer already exists
        existing = await self._get_wa_by_adapter(adapter_id)
        if existing:
            # Observer already exists and is active (since _get_wa_by_adapter only returns active ones)
            return existing

        # Generate new observer WA
        private_key, public_key = self.generate_keypair()
        timestamp = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        wa_id = self._generate_wa_id(timestamp)
        jwt_kid = f"wa-jwt-{wa_id[-6:].lower()}"

        observer = WACertificate(
            wa_id=wa_id,
            name=name,
            role=WARole.OBSERVER,
            pubkey=self._encode_public_key(public_key),
            jwt_kid=jwt_kid,
            scopes_json='["read:any", "write:message"]',
            adapter_id=adapter_id,
            created_at=timestamp,
        )

        await self._store_wa_certificate(observer)
        return observer

    async def update_wa(
        self, wa_id: str, updates: Optional[WAUpdate] = None, **kwargs: Union[str, bool, datetime]
    ) -> Optional[WACertificate]:
        """Update WA certificate fields."""
        if updates:
            # Convert WAUpdate to kwargs
            update_kwargs = {}
            if updates.name:
                update_kwargs["name"] = updates.name
            if updates.role:
                update_kwargs["role"] = updates.role
            if updates.permissions:
                update_kwargs["scopes_json"] = json.dumps(updates.permissions)
            if updates.metadata:
                update_kwargs["metadata"] = json.dumps(updates.metadata)
            if updates.is_active is not None:
                update_kwargs["active"] = str(int(updates.is_active))
            kwargs.update(update_kwargs)
        if not kwargs:
            return await self.get_wa(wa_id)

        # Update via store
        authentication_store.update_wa_certificate(wa_id, kwargs, self.db_path)

        # Return updated WA
        return await self.get_wa(wa_id)

    async def revoke_wa(self, wa_id: str, reason: str) -> bool:
        """Revoke WA certificate."""
        # First check if the WA exists
        existing = await self.get_wa(wa_id)
        if not existing:
            return False

        # Update to set active=False
        await self.update_wa(wa_id, active=False)

        # Add audit log entry for revocation
        if hasattr(self, "_audit_service") and self._audit_service:
            await self._audit_service.log_event(
                event_type="wa_revocation",
                source_service="authentication",
                details={
                    "wa_id": wa_id,
                    "reason": reason,
                    "timestamp": self._time_service.now().isoformat() if self._time_service else None,
                },
            )
        logger.info(f"Revoked WA {wa_id}: {reason}")
        return True

    async def _list_all_was(self, active_only: bool = True) -> List[WACertificate]:
        """List all WA certificates."""
        return authentication_store.list_wa_certificates(active_only, self.db_path)

    async def update_last_login(self, wa_id: str) -> None:
        """Update last login timestamp."""
        await self.update_wa(
            wa_id, last_login=self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        )

    # JWTService Protocol Implementation

    async def create_channel_token(self, wa_id: str, channel_id: str, ttl: int = 3600) -> str:
        """Create channel-specific token (for observers, creates long-lived adapter tokens)."""
        # Get the WA certificate
        wa = await self.get_wa(wa_id)
        if not wa:
            raise ValueError(f"WA {wa_id} not found")

        payload = {
            "sub": wa.wa_id,
            "sub_type": JWTSubType.ANON.value,
            "name": wa.name,
            "scope": wa.scopes,
            "iat": int(
                self._time_service.timestamp() if self._time_service else datetime.now(timezone.utc).timestamp()
            ),
        }

        # For observer tokens, use adapter_id and make them long-lived (no expiry)
        if wa.role == WARole.OBSERVER and wa.adapter_id:
            payload["adapter"] = wa.adapter_id
            # No expiry for observer tokens by default
            if ttl > 0:
                # Only add expiry if explicitly requested
                payload["exp"] = (
                    int(
                        self._time_service.timestamp() if self._time_service else datetime.now(timezone.utc).timestamp()
                    )
                    + ttl
                )
        else:
            # For non-observer tokens, include channel and expiry
            payload["channel"] = channel_id
            payload["exp"] = (
                int(self._time_service.timestamp() if self._time_service else datetime.now(timezone.utc).timestamp())
                + ttl
            )

        return jwt.encode(payload, self.gateway_secret, algorithm="HS256", headers={"kid": wa.jwt_kid})

    def create_gateway_token(self, wa: WACertificate, expires_hours: int = 8) -> str:
        """Create gateway-signed token (OAuth/password auth)."""
        now = int(self._time_service.timestamp() if self._time_service else datetime.now(timezone.utc).timestamp())

        payload = {
            "sub": wa.wa_id,
            "sub_type": JWTSubType.OAUTH.value if wa.oauth_provider else JWTSubType.USER.value,
            "name": wa.name,
            "scope": wa.scopes,
            "iat": now,
            "exp": now + (expires_hours * 3600),
        }

        if wa.oauth_provider:
            payload["oauth_provider"] = wa.oauth_provider

        return jwt.encode(payload, self.gateway_secret, algorithm="HS256", headers={"kid": wa.jwt_kid})

    def _create_authority_token(self, wa: WACertificate, private_key: bytes) -> str:
        """Create WA-signed authority token."""
        now = int(self._time_service.timestamp() if self._time_service else datetime.now(timezone.utc).timestamp())

        payload = {
            "sub": wa.wa_id,
            "sub_type": JWTSubType.AUTHORITY.value,
            "name": wa.name,
            "scope": wa.scopes,
            "iat": now,
            "exp": now + (24 * 3600),  # 24 hours
        }

        # Load Ed25519 private key
        signing_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)

        return jwt.encode(payload, signing_key, algorithm="EdDSA", headers={"kid": wa.jwt_kid})

    async def _verify_jwt_and_get_context(
        self, token: str
    ) -> Optional[Tuple[AuthorizationContext, Optional[datetime]]]:
        """Verify any JWT token and return auth context and expiration (internal method)."""
        try:
            logger.debug(f"[TOKEN_VERIFY] Starting verification for token (first 20 chars): {token[:20]}...")

            # Decode header to get kid
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            logger.debug(f"[TOKEN_VERIFY] Extracted kid from header: {kid}")

            if not kid:
                logger.warning("[TOKEN_VERIFY] No kid found in token header")
                return None

            # Get WA by kid
            wa = await self._get_wa_by_kid(kid)
            logger.debug(f"[TOKEN_VERIFY] WA lookup by kid result: {wa is not None}, wa_id={wa.wa_id if wa else None}")
            if not wa:
                logger.warning(f"[TOKEN_VERIFY] No WA found for kid: {kid}")
                return None

            # Try to verify with different keys/algorithms based on the issuer (kid)
            decoded = None

            logger.debug("[TOKEN_VERIFY] Attempting gateway-signed token verification (HS256)")
            # First try gateway-signed tokens (most common)
            try:
                decoded = jwt.decode(token, self.gateway_secret, algorithms=["HS256"])
                logger.debug("[TOKEN_VERIFY] Gateway verification succeeded")
            except jwt.InvalidTokenError as e:
                logger.debug(f"[TOKEN_VERIFY] Gateway verification failed: {type(e).__name__}")

            # If gateway verification failed, try WA-signed tokens
            if not decoded:
                logger.debug("[TOKEN_VERIFY] Attempting WA-signed token verification (EdDSA)")
                try:
                    public_key_bytes = self._decode_public_key(wa.pubkey)
                    public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
                    decoded = jwt.decode(token, public_key, algorithms=["EdDSA"])
                    logger.debug("[TOKEN_VERIFY] WA verification succeeded")
                except jwt.InvalidTokenError as e:
                    logger.info(f"[TOKEN_VERIFY] WA verification failed: {type(e).__name__}")

            # If no verification succeeded, token is invalid
            if not decoded:
                logger.warning("[TOKEN_VERIFY] Both gateway and WA verification failed - token invalid")
                return None

            # Validate sub_type and algorithm after verification
            # IMPORTANT: We must validate that the token was verified with the expected algorithm
            # to prevent algorithm confusion attacks
            sub_type = decoded.get("sub_type")

            # Determine which verification succeeded based on the algorithm
            verified_with_gateway = False
            verified_with_wa_key = False

            # Re-verify to determine which key actually verified the token
            try:
                jwt.decode(token, self.gateway_secret, algorithms=["HS256"])
                verified_with_gateway = True
            except jwt.InvalidTokenError:
                pass

            if not verified_with_gateway:
                try:
                    public_key_bytes = self._decode_public_key(wa.pubkey)
                    public_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
                    jwt.decode(token, public_key, algorithms=["EdDSA"])
                    verified_with_wa_key = True
                except jwt.InvalidTokenError:
                    pass

            # Validate that the token type matches the verification method
            if sub_type == JWTSubType.AUTHORITY.value:
                # Authority tokens must be verified with WA key (EdDSA)
                if not verified_with_wa_key:
                    return None
            elif sub_type in [JWTSubType.ANON.value, JWTSubType.OAUTH.value, JWTSubType.USER.value]:
                # Gateway tokens must be verified with gateway secret (HS256)
                if not verified_with_gateway:
                    return None
            else:
                return None

            # Create authorization context
            # Determine TokenType based on the WA certificate
            if wa.adapter_id:
                token_type = TokenType.CHANNEL
            elif wa.oauth_provider:
                token_type = TokenType.OAUTH
            else:
                token_type = TokenType.STANDARD

            context = AuthorizationContext(
                wa_id=decoded["sub"],
                role=wa.role,
                token_type=token_type,
                sub_type=JWTSubType(decoded["sub_type"]),
                scopes=decoded["scope"],
                channel_id=decoded.get("channel"),
            )

            # Update last login
            await self.update_last_login(wa.wa_id)

            # Extract expiration if present
            exp_timestamp = decoded.get("exp")
            expiration = None
            if exp_timestamp:
                expiration = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

            return (context, expiration)

        except jwt.InvalidTokenError as e:
            logger.debug(f"[TOKEN_VERIFY] JWT InvalidTokenError: {type(e).__name__}: {str(e)}")
            return None
        except Exception as e:
            logger.debug(f"[TOKEN_VERIFY] Unexpected exception: {type(e).__name__}: {str(e)}", exc_info=True)
            return None

    # WACrypto Protocol Implementation

    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Generate Ed25519 keypair (private, public)."""
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
        )

        return private_bytes, public_bytes

    def sign_data(self, data: bytes, private_key: bytes) -> str:
        """Sign data with Ed25519 private key."""
        signing_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)
        signature = signing_key.sign(data)
        return base64.b64encode(signature).decode()

    def _verify_signature(self, data: bytes, signature: str, public_key: str) -> bool:
        """Verify Ed25519 signature."""
        try:
            public_key_bytes = self._decode_public_key(public_key)
            verify_key = ed25519.Ed25519PublicKey.from_public_bytes(public_key_bytes)
            signature_bytes = base64.b64decode(signature)

            verify_key.verify(signature_bytes, data)
            return True
        except (InvalidSignature, Exception):
            return False

    def hash_password(self, password: str) -> str:
        """Hash password using PBKDF2."""
        salt = secrets.token_bytes(32)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password.encode())
        return base64.b64encode(salt + key).decode()

    def _verify_password(self, password: str, hash: str) -> bool:
        """Verify password against hash."""
        try:
            decoded = base64.b64decode(hash)
            salt = decoded[:32]
            stored_key = decoded[32:]

            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = kdf.derive(password.encode())
            # Use constant-time comparison to prevent timing attacks
            import hmac

            return hmac.compare_digest(key, stored_key)
        except Exception:
            return False

    # codeql[py/weak-sensitive-data-hashing]
    # The use of SHA256 here is for generating a unique API key, not for hashing passwords.
    # It is combined with a cryptographically secure random salt, which makes it resistant
    # to rainbow table attacks. For this purpose, SHA256 is considered a secure choice.
    def _generate_api_key(self, wa_id: str) -> str:
        """Generate API key for WA."""
        # Include wa_id in key derivation for uniqueness
        key_material = f"{wa_id}:{secrets.token_hex(32)}"
        return hashlib.sha256(key_material.encode()).hexdigest()

    def _generate_wa_id(self, timestamp: datetime) -> str:
        """Generate a unique WA (Wise Authority) ID.

        Format: wa-YYYY-MM-DD-XXXXXX
        - wa: Fixed prefix for all WA IDs
        - YYYY-MM-DD: Date from the provided timestamp
        - XXXXXX: 6 uppercase hexadecimal characters (cryptographically random)

        Args:
            timestamp: The timestamp to use for the date portion

        Returns:
            A unique WA ID string

        Example:
            wa-2025-07-14-A3F2B1
        """
        date_str = timestamp.strftime("%Y-%m-%d")
        # Generate 3 random bytes = 6 hex characters
        random_suffix = secrets.token_hex(3).upper()
        return f"wa-{date_str}-{random_suffix}"

    # AuthenticationServiceProtocol Implementation

    async def authenticate(self, token: str) -> Optional[AuthenticationResult]:
        """Authenticate a WA token and return identity info."""
        self._auth_attempts += 1
        try:
            claims = await self.verify_token(token)
            if not claims:
                self._auth_failures += 1
                return None

            if hasattr(claims, "get"):
                wa_id = claims.get("wa_id")
            else:
                wa_id = getattr(claims, "wa_id", None)
            if not wa_id:
                self._auth_failures += 1
                return None

            # Update last login
            await self.update_last_login(wa_id)

            # Get WA details
            wa = await self.get_wa(wa_id)
            if not wa:
                self._auth_failures += 1
                return None

            self._auth_successes += 1
            self._session_count += 1  # Track active session
            return AuthenticationResult(
                authenticated=True,
                wa_id=wa_id,
                name=wa.name,
                role=wa.role.value,
                expires_at=(
                    datetime.fromtimestamp(claims.get("exp", 0), tz=timezone.utc)
                    if hasattr(claims, "get")
                    else (self._time_service.now() if self._time_service else datetime.now(timezone.utc))
                ),
                permissions=wa.scopes,
                metadata={},
            )
        except Exception as e:
            logger.error(f"Authentication failed: {e}")
            self._auth_failures += 1
            return None

    async def create_token(self, wa_id: str, token_type: TokenType, ttl: int = 3600) -> str:
        """Create a new authentication token."""
        wa = await self.get_wa(wa_id)
        if not wa:
            raise ValueError(f"WA {wa_id} not found")

        # Map TokenType enum to our token creation methods
        if token_type == TokenType.CHANNEL:
            # CHANNEL tokens require a channel_id, use create_channel_token directly
            raise ValueError("CHANNEL tokens require channel_id - use create_channel_token directly")
        elif token_type == TokenType.STANDARD:
            return self.create_gateway_token(wa, expires_hours=ttl // 3600)
        else:
            raise ValueError(f"Unsupported token type: {token_type}")

    async def verify_token(self, token: str) -> Optional[TokenVerification]:
        """Verify and decode a token (AuthenticationServiceProtocol version)."""
        try:
            # Directly call _verify_jwt_and_get_context to get both context and expiration
            result = await self._verify_jwt_and_get_context(token)
            if not result:
                return None

            context, expiration = result

            # Get the WA name
            wa = await self.get_wa(context.wa_id)
            wa_name = wa.name if wa else context.wa_id

            # Use expiration from token, or current time as fallback
            expires_at = (
                expiration
                if expiration
                else (self._time_service.now() if self._time_service else datetime.now(timezone.utc))
            )

            return TokenVerification(
                valid=True,
                wa_id=context.wa_id,
                name=wa_name,
                role=context.role.value,
                expires_at=expires_at,
                error=None,
            )
        except Exception as e:
            logger.error(f"Token verification failed: {e}")
            return TokenVerification(valid=False, wa_id=None, name=None, role=None, expires_at=None, error=str(e))

    async def create_wa(
        self, name: str, email: str, scopes: List[str], role: WARole = WARole.OBSERVER
    ) -> WACertificate:
        """Create a new Wise Authority identity."""
        # Generate keypair
        private_key, public_key = self.generate_keypair()

        # Create certificate
        timestamp = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        wa_id = self._generate_wa_id(timestamp)
        jwt_kid = f"wa-jwt-{wa_id[-6:].lower()}"

        wa_cert = WACertificate(
            wa_id=wa_id,
            name=name,
            role=role,
            pubkey=self._encode_public_key(public_key),
            jwt_kid=jwt_kid,
            scopes_json=json.dumps(scopes),
            created_at=timestamp,
        )

        # Store in database
        await self._store_wa_certificate(wa_cert)

        # Store private key (in production, this would be in a secure key store)
        # For now, we're not storing it as it's managed externally

        # Add audit log entry for WA creation (mint)
        if hasattr(self, "_audit_service") and self._audit_service:
            from ciris_engine.schemas.audit.core import EventPayload

            event_data = EventPayload(
                action="wa_mint",
                service_name="authentication",
                user_id=wa_id,  # Use wa_id as user_id to track which WA was created
                result="success",
            )
            await self._audit_service.log_event(event_type="wa_mint", event_data=event_data)

        return wa_cert

    async def list_was(self, active_only: bool = True) -> List[WACertificate]:
        """List Wise Authority identities."""
        return await self._list_all_was(active_only=active_only)

    async def rotate_keys(self, wa_id: str) -> bool:
        """Rotate cryptographic keys for a WA."""
        wa = await self.get_wa(wa_id)
        if not wa:
            return False

        # Generate new keypair
        private_key, public_key = self.generate_keypair()

        # Update WA with new public key
        wa.pubkey = self._encode_public_key(public_key)

        # Store the updated certificate
        await self.update_wa(wa_id, pubkey=wa.pubkey)

        logger.info(f"Rotated keys for WA {wa_id}")
        return True

    # Original verify_token implementation (renamed for internal use)
    async def _verify_token_internal(self, token: Optional[str]) -> Optional[AuthorizationContext]:
        """Authenticate request and return auth context."""
        if not token:
            return None

        # Check cache first
        if token in self._token_cache:
            return self._token_cache[token]

        # Verify token
        result = await self._verify_jwt_and_get_context(token)

        if result:
            context, _ = result  # We don't need expiration here
            # Cache valid tokens
            self._token_cache[token] = context
            return context

        return None

    def _require_scope(self, scope: str) -> Callable[[F], F]:
        """Decorator to require specific scope for endpoint."""

        def decorator(func: F) -> F:
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Extract auth context from kwargs
                auth_context = kwargs.get("auth_context")

                if not auth_context:
                    # Try to get token and verify it
                    token = kwargs.get("token")
                    if token:
                        auth_context = await self._verify_token_internal(token)

                if not auth_context:
                    raise ValueError(f"Authentication required for scope '{scope}'")

                # Check if the auth context has the required scope
                if not hasattr(auth_context, "scopes") or scope not in auth_context.scopes:
                    raise ValueError(
                        f"Insufficient permissions: Requires scope '{scope}', "
                        f"but user has scopes: {getattr(auth_context, 'scopes', [])}"
                    )

                # Add auth context to kwargs if not already present
                if "auth_context" not in kwargs:
                    kwargs["auth_context"] = auth_context

                return await func(*args, **kwargs)

            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Extract auth context from kwargs
                auth_context = kwargs.get("auth_context")

                if not auth_context:
                    raise ValueError(f"Authentication required for scope '{scope}'")

                # Check if the auth context has the required scope
                if not hasattr(auth_context, "scopes") or scope not in auth_context.scopes:
                    raise ValueError(
                        f"Insufficient permissions: Requires scope '{scope}', "
                        f"but user has scopes: {getattr(auth_context, 'scopes', [])}"
                    )

                return func(*args, **kwargs)

            # Preserve function metadata and check if the function is async
            if asyncio.iscoroutinefunction(func):
                wrapper = functools.wraps(func)(async_wrapper)
            else:
                wrapper = functools.wraps(func)(sync_wrapper)

            # Add metadata to indicate this function requires authentication
            setattr(wrapper, "_requires_scope", scope)

            return wrapper  # type: ignore

        return decorator

    def _require_wa_auth(self, scope: str) -> Callable[[F], F]:
        """Decorator to require WA authentication with specific scope.

        This decorator checks for authentication tokens in the following order:
        1. 'token' parameter in the function arguments
        2. 'auth_context' in the function arguments
        3. Token from the context (if available)

        Args:
            scope: The required scope for accessing the decorated function

        Returns:
            Decorated function that enforces authentication
        """

        def decorator(func: F) -> F:
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                # Extract token from various sources
                token = None
                auth_context = None

                # Check if 'token' is in kwargs
                if "token" in kwargs:
                    token = kwargs.get("token")

                # Check if 'auth_context' is already provided
                if "auth_context" in kwargs:
                    auth_context = kwargs.get("auth_context")

                # If no auth context yet, try to verify the token
                if not auth_context and token:
                    auth_context = await self.verify_token(token)

                # Check if authentication succeeded
                if not auth_context:
                    raise ValueError("Authentication required: No valid token provided")

                # Verify the required scope
                if not auth_context.has_scope(scope):
                    raise ValueError(
                        f"Insufficient permissions: Requires scope '{scope}', "
                        f"but user has scopes: {auth_context.scopes}"
                    )

                # Check if the function accepts auth_context parameter
                sig = inspect.signature(func)

                # If function has **kwargs or auth_context parameter, pass it
                if "auth_context" in sig.parameters or any(
                    p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
                ):
                    kwargs["auth_context"] = auth_context

                # Call the original function
                return await func(*args, **kwargs)

            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                # For synchronous functions, we need to handle auth differently
                # This is a simplified version that expects auth_context to be pre-verified
                auth_context = kwargs.get("auth_context")

                if not auth_context:
                    raise ValueError("Authentication required: No auth_context provided")

                # Verify the required scope
                if not hasattr(auth_context, "has_scope") or not auth_context.has_scope(scope):
                    raise ValueError(f"Insufficient permissions: Requires scope '{scope}'")

                return func(*args, **kwargs)

            # Preserve function metadata and check if the function is async
            if asyncio.iscoroutinefunction(func):
                wrapper = functools.wraps(func)(async_wrapper)
            else:
                wrapper = functools.wraps(func)(sync_wrapper)

            # Add metadata to indicate this function requires authentication
            setattr(wrapper, "_requires_wa_auth", True)
            setattr(wrapper, "_required_scope", scope)

            return wrapper  # type: ignore

        return decorator

    def _get_adapter_token(self, adapter_id: str) -> Optional[str]:
        """Get cached adapter token."""
        return self._channel_token_cache.get(adapter_id)

    # Additional helper methods

    async def _get_system_wa(self) -> Optional[WACertificate]:
        """Get the system WA certificate if it exists."""
        was = await self._list_all_was()
        for wa in was:
            if wa.role == WARole.AUTHORITY and wa.name == "CIRIS System Authority":
                return wa
        return None

    async def get_system_wa_id(self) -> Optional[str]:
        """Get the system WA ID for signing system tasks."""
        system_wa = await self._get_system_wa()
        return system_wa.wa_id if system_wa else None

    async def ensure_system_wa_exists(self) -> Optional[str]:
        """Ensure the system WA exists, creating it if a ROOT WA is available.

        This should be called after creating a ROOT WA during setup to ensure
        the system WA is immediately available for signing system tasks.

        Returns:
            The system WA ID if it exists or was created, None if no ROOT WA exists.
        """
        # Check if system WA already exists
        system_wa = await self._get_system_wa()
        if system_wa:
            return system_wa.wa_id

        # Find a ROOT WA to use as parent
        for wa in await self._list_all_was():
            if wa.role == WARole.ROOT:
                # Create system WA as child of root
                new_system_wa = await self._create_system_wa_certificate(wa.wa_id)
                logger.info(f"✅ Created system WA {new_system_wa.wa_id} as child of ROOT {wa.wa_id}")
                return new_system_wa.wa_id

        logger.warning("Cannot create system WA - no ROOT WA found")
        return None

    async def _create_system_wa_certificate(self, parent_wa_id: str) -> WACertificate:
        """Create the system WA certificate as a child of the root certificate.

        This certificate is used to sign system-generated tasks like WAKEUP and DREAM.
        It respects the authority of the root certificate holder.
        """
        # Generate keypair for system WA
        private_key, public_key = self.generate_keypair()

        # Store the private key securely
        system_key_path = self.key_dir / "system_wa.key"
        system_key_path.write_bytes(private_key)
        system_key_path.chmod(0o600)

        # Create the system WA certificate
        timestamp = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        wa_id = self._generate_wa_id(timestamp)
        jwt_kid = f"wa-jwt-{wa_id[-6:].lower()}"

        # Create data to sign - the certificate attributes
        cert_data = {
            "wa_id": wa_id,
            "name": "CIRIS System Authority",
            "role": WARole.AUTHORITY.value,
            "pubkey": self._encode_public_key(public_key),
            "parent_wa_id": parent_wa_id,
            "created_at": timestamp.isoformat(),
        }

        # Sign with the system's private key (self-signed for now)
        # In production, this would be signed by the parent's private key
        signature_data = json.dumps(cert_data, sort_keys=True, separators=(",", ":"))
        parent_signature = self.sign_data(signature_data.encode("utf-8"), private_key)

        # Create the certificate
        system_wa = WACertificate(
            wa_id=wa_id,
            name="CIRIS System Authority",
            role=WARole.AUTHORITY,
            pubkey=self._encode_public_key(public_key),
            jwt_kid=jwt_kid,
            parent_wa_id=parent_wa_id,
            parent_signature=parent_signature,
            scopes_json=json.dumps(
                [
                    "system.task.create",
                    "system.task.sign",
                    "system.wakeup",
                    "system.dream",
                    "system.shutdown",
                    "memory.read",
                    "memory.write",
                ]
            ),
            created_at=timestamp,
        )

        # Store in database
        await self._store_wa_certificate(system_wa)
        logger.info(f"Created system WA certificate: {wa_id} (child of {parent_wa_id})")

        return system_wa

    async def sign_task(self, task: "Task", wa_id: str) -> Tuple[str, str]:
        """Sign a task with a WA's private key.

        Returns:
            Tuple of (signature, signed_at timestamp)
        """
        # Get the WA certificate
        wa = await self.get_wa(wa_id)
        if not wa:
            raise ValueError(f"WA {wa_id} not found")

        # Load the private key
        if wa.name == "CIRIS System Authority":
            # System WA key is stored locally
            key_path = self.key_dir / "system_wa.key"
            if not key_path.exists():
                raise ValueError("System WA private key not found")
            private_key = key_path.read_bytes()
        else:
            # Other WAs would have their keys managed differently
            raise ValueError(f"Private key management not implemented for WA {wa_id}")

        # Create canonical representation of task for signing
        task_data = {
            "task_id": task.task_id,
            "description": task.description,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "priority": task.priority,
            "created_at": task.created_at,
            "parent_task_id": task.parent_task_id,
            "context": task.context.model_dump() if task.context else None,
        }

        canonical_json = json.dumps(task_data, sort_keys=True, separators=(",", ":"))
        signature = self.sign_data(canonical_json.encode("utf-8"), private_key)
        signed_at = (self._time_service.now() if self._time_service else datetime.now(timezone.utc)).isoformat()

        return signature, signed_at

    async def verify_task_signature(self, task: "Task") -> bool:
        """Verify a task's signature.

        Returns:
            True if signature is valid, False otherwise
        """
        if not task.signed_by or not task.signature or not task.signed_at:
            return False

        # Get the WA that signed it
        wa = await self.get_wa(task.signed_by)
        if not wa:
            return False

        # Recreate the canonical representation
        task_data = {
            "task_id": task.task_id,
            "description": task.description,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "priority": task.priority,
            "created_at": task.created_at,
            "parent_task_id": task.parent_task_id,
            "context": task.context.model_dump() if task.context else None,
        }

        canonical_json = json.dumps(task_data, sort_keys=True, separators=(",", ":"))

        # Verify the signature
        return self._verify_signature(canonical_json.encode("utf-8"), task.signature, wa.pubkey)

    async def bootstrap_if_needed(self) -> None:
        """Bootstrap the system if no WAs exist."""
        was = await self._list_all_was()

        # Check if we have a root WA
        has_root = any(wa.role == WARole.ROOT for wa in was)

        if not has_root:
            # Load and insert root certificate
            seed_path = Path(__file__).parent.parent.parent / "seed" / "root_pub.json"
            if seed_path.exists():
                async with aiofiles.open(seed_path) as f:
                    content = await f.read()
                    root_data = json.loads(content)

                # Convert created timestamp - handle both 'Z' and '+00:00' formats
                created_str = root_data["created"]
                if created_str.endswith("Z"):
                    created_str = created_str[:-1] + "+00:00"
                root_data["created"] = datetime.fromisoformat(created_str)

                root_wa = WACertificate(**root_data)
                await self._store_wa_certificate(root_wa)

                logger.info(f"Loaded root WA certificate: {root_wa.wa_id}")

        # Check if system WA exists, create if not (whether we just loaded root or not)
        system_wa = await self._get_system_wa()
        if not system_wa:
            # Find the root certificate
            found_root_wa: Optional[WACertificate] = None
            for wa in await self._list_all_was():
                if wa.role == WARole.ROOT:
                    found_root_wa = wa
                    break

            if found_root_wa:
                # Create system WA certificate as child of root
                await self._create_system_wa_certificate(found_root_wa.wa_id)
            else:
                logger.warning("No root WA certificate found - cannot create system WA")

    async def _create_channel_token_for_adapter(self, adapter_type: str, adapter_info: JSONDict) -> str:
        """Create a channel token for an adapter."""
        # Ensure adapter_info has proper structure
        if not adapter_info:
            adapter_info = {}

        # Add default instance_id if not present
        if "instance_id" not in adapter_info:
            adapter_info["instance_id"] = "default"

        # Create channel identity from adapter info
        channel_identity = ChannelIdentity(
            adapter_type=adapter_type,
            adapter_instance_id=adapter_info.get("instance_id", "default"),
            external_user_id=adapter_info.get("user_id", "system"),
            external_username=adapter_info.get("username", adapter_type),
            metadata=adapter_info,
        )

        # Create or get adapter observer
        adapter_id = f"{adapter_type}_{channel_identity.adapter_instance_id}"
        observer = await self._create_adapter_observer(adapter_id, f"{adapter_type}_observer")

        # Generate token - for observers, channel_id is not used
        token = await self.create_channel_token(observer.wa_id, adapter_id, ttl=0)  # ttl=0 means no expiry

        # Cache the token
        self._channel_token_cache[adapter_id] = token

        return token

    def verify_token_sync(self, token: str) -> Optional[JSONDict]:
        """Synchronously verify a token (for non-async contexts)."""
        try:
            # For sync verification, we can only verify gateway-signed tokens
            # since authority tokens require async DB lookups for public keys

            # Try gateway-signed token verification
            try:
                # Verify the token with gateway secret first
                decoded = jwt.decode(token, self.gateway_secret, algorithms=["HS256"])

                # Now that the token is verified, we can trust its contents
                # Validate that this is indeed a gateway-signed token type
                sub_type = decoded.get("sub_type")
                if sub_type in [JWTSubType.ANON.value, JWTSubType.OAUTH.value, JWTSubType.USER.value]:
                    # Valid gateway token
                    return dict(decoded)
                else:
                    # Invalid sub_type for gateway token
                    return None

            except jwt.InvalidTokenError:
                # Token failed verification with gateway secret
                pass

            # Authority tokens require async DB access for public key retrieval
            # So we cannot verify them in sync mode
            return None

        except Exception:
            return None

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        from uuid import uuid4

        from ciris_engine.schemas.services.core import ServiceCapabilities
        from ciris_engine.schemas.services.metadata import ServiceMetadata

        return ServiceCapabilities(
            service_name="AuthenticationService",
            actions=[
                "authenticate",
                "create_token",
                "verify_token",
                "create_wa",
                "revoke_wa",
                "update_wa",
                "list_was",
                "get_wa",
                "rotate_keys",
                "bootstrap_if_needed",
                "create_channel_token",
                "verify_token_sync",
                "update_last_login",
            ],
            version="1.0.0",
            dependencies=["TimeService"],
            metadata=ServiceMetadata(
                category="infrastructure",
                critical=True,
                description="Infrastructure service for WA authentication and identity management",
            ),
        )

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        from ciris_engine.schemas.services.core import ServiceStatus

        # Count certificates by type
        try:
            counts = authentication_store.get_certificate_counts(self.db_path)
            cert_count = counts.get("active", 0)
            revoked_count = counts.get("revoked", 0)
            # Extract by_role dict with type assertion
            role_counts_raw: int | Dict[str, int] = counts.get("by_role", {})
            role_counts: Dict[str, int] = (
                role_counts_raw
                if isinstance(role_counts_raw, dict)
                else {"OBSERVER": 0, "USER": 0, "ADMIN": 0, "AUTHORITY": 0, "ROOT": 0}
            )
        except Exception as e:
            logger.warning(
                f"Authentication service health check failed: {type(e).__name__}: {str(e)} - Unable to access auth database"
            )
            cert_count = 0
            role_counts = {"OBSERVER": 0, "USER": 0, "ADMIN": 0, "AUTHORITY": 0, "ROOT": 0}
            revoked_count = 0

        current_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = (current_time - self._start_time).total_seconds()

        # Calculate token cache stats
        auth_context_cached = len(self._token_cache)
        channel_tokens_cached = len(self._channel_token_cache)

        # Build custom metrics
        custom_metrics = {
            "active_certificates": float(cert_count),
            "revoked_certificates": float(revoked_count),
            "observer_certificates": float(role_counts.get("OBSERVER", 0)),
            "user_certificates": float(role_counts.get("USER", 0)),
            "admin_certificates": float(role_counts.get("ADMIN", 0)),
            "authority_certificates": float(role_counts.get("AUTHORITY", 0)),
            "root_certificates": float(role_counts.get("ROOT", 0)),
            "auth_contexts_cached": float(auth_context_cached),
            "channel_tokens_cached": float(channel_tokens_cached),
            "total_tokens_cached": float(auth_context_cached + channel_tokens_cached),
        }

        return ServiceStatus(
            service_name="AuthenticationService",
            service_type="infrastructure_service",
            is_healthy=True,  # Simple health check
            uptime_seconds=uptime_seconds,
            last_error=None,
            metrics={
                "certificate_count": float(cert_count),
                "cached_tokens": float(len(self._channel_token_cache)),
                "active_sessions": 0.0,
            },
            custom_metrics=custom_metrics,
            last_health_check=current_time,
        )

    async def start(self) -> None:
        """Start the service."""
        await super().start()
        self._started = True
        self._start_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        logger.info("AuthenticationService started")

    async def stop(self) -> None:
        """Stop the service."""
        await super().stop()
        self._started = False
        # Clear caches
        self._token_cache.clear()
        self._channel_token_cache.clear()
        logger.info("AuthenticationService stopped")

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect authentication-specific metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate auth success rate
        auth_rate = 0.0
        if self._auth_attempts > 0:
            auth_rate = self._auth_successes / self._auth_attempts

        metrics.update(
            {
                "auth_attempts": float(self._auth_attempts),
                "auth_successes": float(self._auth_successes),
                "auth_failures": float(self._auth_failures),
                "auth_success_rate": auth_rate,
                "token_validations": float(self._token_validations),
                "permission_checks": float(self._permission_checks),
                "role_assignments": float(self._role_assignments),
                "active_sessions": float(self._session_count),
                "expired_sessions": float(self._expired_sessions),
                "active_tokens": float(self._active_tokens),
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """Get all authentication service metrics including base, custom, and v1.4.3 specific.

        Returns:
            Dict with all metrics including base, custom, and v1.4.3 metrics
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        current_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = (current_time - self._start_time).total_seconds()

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "auth_attempts_total": float(self._auth_attempts),
                "auth_successes_total": float(self._auth_successes),
                "auth_failures_total": float(self._auth_failures),
                "auth_active_sessions": float(self._session_count),
                "auth_uptime_seconds": uptime_seconds,
            }
        )

        return metrics

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        if not self._started:
            return False

        # Check database connection via store
        return authentication_store.check_database_health(self.db_path)
