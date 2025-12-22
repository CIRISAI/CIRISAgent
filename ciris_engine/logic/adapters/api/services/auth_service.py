"""Authentication service for API v2.0.

Manages API keys, OAuth users, and authentication state.
"""

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiofiles
import bcrypt

logger = logging.getLogger(__name__)

from ciris_engine.protocols.services.infrastructure.authentication import AuthenticationServiceProtocol
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority.wise_authority import WAUpdate
from ciris_engine.schemas.services.authority_core import OAuthIdentityLink, WACertificate, WARole

# Permission constants to avoid duplication
PERMISSION_SYSTEM_READ = "system.read"
PERMISSION_SYSTEM_WRITE = "system.write"
PERMISSION_MEMORY_READ = "memory.read"
PERMISSION_MEMORY_WRITE = "memory.write"
PERMISSION_TELEMETRY_READ = "telemetry.read"
PERMISSION_CONFIG_READ = "config.read"
PERMISSION_CONFIG_WRITE = "config.write"
PERMISSION_AUDIT_READ = "audit.read"
PERMISSION_AUDIT_WRITE = "audit.write"
PERMISSION_USERS_READ = "users.read"
PERMISSION_USERS_WRITE = "users.write"
PERMISSION_USERS_DELETE = "users.delete"
PERMISSION_WA_READ = "wa.read"
PERMISSION_WA_WRITE = "wa.write"
PERMISSION_WA_MINT = "wa.mint"
PERMISSION_EMERGENCY_SHUTDOWN = "emergency.shutdown"
PERMISSION_MANAGE_USER_PERMISSIONS = "manage_user_permissions"


@dataclass
class StoredAPIKey:
    """Internal representation of an API key."""

    key_id: str  # Unique ID for the key
    key_hash: str
    key_value: str  # Masked version for display
    user_id: str
    role: UserRole
    expires_at: Optional[datetime]
    description: Optional[str]
    created_at: datetime
    created_by: str
    last_used: Optional[datetime]
    is_active: bool


@dataclass
class OAuthUser:
    """OAuth user information."""

    user_id: str  # Format: provider:external_id
    provider: str
    external_id: str
    email: Optional[str]
    name: Optional[str]
    role: UserRole
    created_at: datetime
    last_login: datetime
    marketing_opt_in: bool = False  # User consent for marketing communications


@dataclass
class User:
    """Unified user representation combining auth methods and WA status."""

    wa_id: str  # Primary ID (from WA cert)
    name: str
    auth_type: str  # "password", "oauth", "api_key"
    api_role: APIRole
    wa_role: Optional[WARole] = None
    oauth_provider: Optional[str] = None
    oauth_email: Optional[str] = None
    oauth_external_id: Optional[str] = None
    created_at: Optional[datetime] = None
    last_login: Optional[datetime] = None
    is_active: bool = True
    wa_parent_id: Optional[str] = None
    wa_auto_minted: bool = False
    password_hash: Optional[str] = None
    custom_permissions: Optional[List[str]] = None  # Additional permissions beyond role defaults
    # OAuth profile fields for permission request system
    oauth_name: Optional[str] = None  # Full name from OAuth provider
    oauth_picture: Optional[str] = None  # Profile picture URL from OAuth provider
    permission_requested_at: Optional[datetime] = None  # Timestamp when user requested permissions
    oauth_links: List[OAuthIdentityLink] = field(default_factory=list)
    marketing_opt_in: bool = False  # User consent for marketing communications


class APIAuthService:
    """Simple in-memory authentication service with database persistence."""

    # Class-level instance counter to track re-initialization
    _instance_counter = 0

    def __init__(self, auth_service: Optional[AuthenticationServiceProtocol] = None) -> None:
        # Track instance creation for debugging
        APIAuthService._instance_counter += 1
        self._instance_id = APIAuthService._instance_counter
        logger.debug(
            f"[AUTH SERVICE DEBUG] APIAuthService.__init__ called - INSTANCE #{self._instance_id} created (id={id(self)})"
        )

        # In-memory caches for performance
        self._api_keys: Dict[str, StoredAPIKey] = {}
        self._oauth_users: Dict[str, OAuthUser] = {}
        self._users: Dict[str, User] = {}

        logger.debug(
            f"[AUTH SERVICE DEBUG] Instance #{self._instance_id} - _api_keys initialized as EMPTY dict (id={id(self._api_keys)})"
        )

        # Store reference to the actual authentication service
        self._auth_service = auth_service

        # Flag to track if we've loaded users from DB
        self._users_loaded = False

        # Don't load from DB in __init__ - this causes asyncio.run() errors
        # Instead, we'll load lazily on first access
        if not self._auth_service:
            # Fallback: Initialize with system admin user if no auth service
            now = datetime.now(timezone.utc)
            admin_user = User(
                wa_id="wa-system-admin",
                name="admin",
                auth_type="password",
                api_role=APIRole.SYSTEM_ADMIN,
                wa_role=None,  # System admin is not a WA by default
                created_at=now,
                is_active=True,
                password_hash=self._hash_password("ciris_admin_password"),
            )
            self._users[admin_user.wa_id] = admin_user
            self._users_loaded = True

    async def _ensure_users_loaded(self) -> None:
        """Ensure users are loaded from database (lazy loading)."""
        if self._users_loaded:
            return

        await self._load_users_from_db()
        self._users_loaded = True

    async def reload_users_from_db(self) -> None:
        """Force reload users from database, invalidating cache.

        Use this after external changes to the user database (e.g., setup wizard).
        """
        self._users_loaded = False
        await self._ensure_users_loaded()

    def _update_existing_oauth_user(self, oauth_user_id: str, wa: "WACertificate") -> None:
        """Update existing OAuth user record with WA info."""
        existing_user = self._users[oauth_user_id]
        existing_user.wa_role = wa.role
        existing_user.wa_id = wa.wa_id
        existing_user.wa_parent_id = wa.parent_wa_id
        existing_user.wa_auto_minted = wa.auto_minted
        existing_user.api_role = self._wa_role_to_api_role(wa.role)

    def _create_user_from_wa(self, wa: "WACertificate") -> User:
        """Convert WA certificate to User."""
        # Extract email from oauth_links if available
        oauth_email = None
        if wa.oauth_links:
            logger.debug(f"[AUTH DEBUG] Found {len(wa.oauth_links)} OAuth links for {wa.wa_id}")
            for i, link in enumerate(wa.oauth_links):
                logger.debug(
                    f"[AUTH DEBUG] Link {i}: provider={link.provider}, external_id={link.external_id}, metadata={link.metadata}"
                )
                # Check if link has email in metadata or as direct attribute
                if hasattr(link, "email") and link.email:
                    oauth_email = link.email
                    masked = oauth_email[:3] + "***" if oauth_email else "None"  # NOSONAR - masked email for debug
                    logger.debug(f"[AUTH DEBUG] Extracted email from link.email: {masked}")
                    break
                elif hasattr(link, "metadata") and isinstance(link.metadata, dict):
                    if "email" in link.metadata:
                        oauth_email = link.metadata["email"]
                        masked = oauth_email[:3] + "***" if oauth_email else "None"  # NOSONAR - masked email for debug
                        logger.debug(f"[AUTH DEBUG] Extracted email from link.metadata['email']: {masked}")
                        break
        else:
            logger.debug(f"[AUTH DEBUG] No OAuth links found for {wa.wa_id}")

        return User(
            wa_id=wa.wa_id,
            name=wa.name,
            auth_type="password" if wa.password_hash else "certificate",
            api_role=self._wa_role_to_api_role(wa.role),
            wa_role=wa.role,
            created_at=wa.created_at,
            last_login=wa.last_auth,
            is_active=True,  # Assume active if in database
            wa_parent_id=wa.parent_wa_id,
            wa_auto_minted=wa.auto_minted,
            password_hash=wa.password_hash,
            oauth_provider=wa.oauth_provider,
            oauth_email=oauth_email,  # Extract from oauth_links
            oauth_external_id=wa.oauth_external_id,
            custom_permissions=wa.custom_permissions if hasattr(wa, "custom_permissions") else None,
            oauth_links=list(wa.oauth_links),
        )

    async def _process_wa_record(self, wa: "WACertificate") -> None:
        """Process a single WA record and add/update user."""
        logger.debug(f"[AUTH DEBUG] _process_wa_record: wa_id={wa.wa_id}, name={wa.name}")

        # Remove stale cache entries for this WA
        to_remove = [key for key, value in self._users.items() if getattr(value, "wa_id", None) == wa.wa_id]
        if to_remove:
            logger.debug(f"[AUTH DEBUG] Removing {len(to_remove)} stale entries for {wa.wa_id}")
        for key in to_remove:
            self._users.pop(key, None)

        user = self._create_user_from_wa(wa)
        logger.debug(
            f"[AUTH DEBUG] Created User: name={user.name}, auth_type={user.auth_type}, has_password={user.password_hash is not None}"
        )

        self._users[wa.wa_id] = user
        logger.debug(f"[AUTH DEBUG] Stored user under key: '{wa.wa_id}'")

        if wa.oauth_provider and wa.oauth_external_id:
            primary_key = f"{wa.oauth_provider}:{wa.oauth_external_id}"
            self._users[primary_key] = user
            logger.debug(f"[AUTH DEBUG] Stored user under OAuth key: '{primary_key}'")
            # Clear from _oauth_users cache - DB record is authoritative
            if primary_key in self._oauth_users:
                logger.debug(f"[AUTH DEBUG] Clearing stale _oauth_users entry: '{primary_key}'")
                del self._oauth_users[primary_key]

        for link in wa.oauth_links:
            link_key = f"{link.provider}:{link.external_id}"
            self._users[link_key] = user
            logger.debug(f"[AUTH DEBUG] Stored user under link key: '{link_key}'")

    async def _load_users_from_db(self) -> None:
        """Load existing users from the database."""
        logger.info("=" * 70)
        logger.info("CIRIS_USER_CREATE: _load_users_from_db() called")
        logger.info("=" * 70)

        if not self._auth_service:
            logger.info("CIRIS_USER_CREATE: No auth service - skipping DB load")
            return

        try:
            was = await self._auth_service.list_was(active_only=False)
            logger.info(f"CIRIS_USER_CREATE: Loaded {len(was)} WA certificates from database")

            for i, wa in enumerate(was, 1):
                logger.info(
                    f"CIRIS_USER_CREATE: Processing WA {i}/{len(was)}: wa_id={wa.wa_id}, name={wa.name}, role={wa.role}"
                )
                await self._process_wa_record(wa)

            # Check if we need to create a default admin
            # Skip if:
            # 1. Any user named 'admin' exists, OR
            # 2. Any ROOT user exists (setup wizard creates ROOT user with custom name)
            has_admin_user = any(u.name == "admin" for u in self._users.values())
            has_root_user = any(u.wa_role == WARole.ROOT for u in self._users.values())

            logger.info(f"CIRIS_USER_CREATE: Check default admin: has_admin={has_admin_user}, has_root={has_root_user}")

            if not has_admin_user and not has_root_user:
                logger.info("CIRIS_USER_CREATE: No admin/ROOT user found - will create default admin")
                await self._create_default_admin()
            else:
                logger.info("CIRIS_USER_CREATE: Skipping default admin creation - admin or ROOT already exists")

            # Clear the fallback admin if it wasn't loaded from the database
            # The fallback admin is only meant for when there's no auth_service
            # If wa-system-admin is in the DB, it's a real user and should be kept
            loaded_wa_ids = {wa.wa_id for wa in was}
            if "wa-system-admin" in self._users and "wa-system-admin" not in loaded_wa_ids:
                logger.info("CIRIS_USER_CREATE: Removing fallback 'wa-system-admin' - not in DB, real users loaded")
                del self._users["wa-system-admin"]

            logger.info(f"CIRIS_USER_CREATE: User loading complete. Total users in cache: {len(self._users)}")
            unique_users = {u.wa_id: u for u in self._users.values()}
            for wa_id, user in unique_users.items():
                logger.info(
                    f"CIRIS_USER_CREATE:   - {wa_id}: name={user.name}, wa_role={user.wa_role}, api_role={user.api_role}"
                )
            logger.info("=" * 70)

        except Exception as e:
            logger.error(f"CIRIS_USER_CREATE: Error loading users from database: {e}", exc_info=True)
            raise

    async def _create_default_admin(self) -> None:
        """Create the default admin user in the database.

        NOTE: This is only called if no user named 'admin' exists in the database.
        During first-run setup, the setup wizard creates the ROOT user, so this
        should NOT be called in that flow.
        """
        if not self._auth_service:
            logger.info("CIRIS_USER_CREATE: _create_default_admin skipped - no auth_service")
            return

        logger.info("=" * 70)
        logger.info("CIRIS_USER_CREATE: _create_default_admin() called")
        logger.info("=" * 70)

        try:
            # Check existing WAs before creating admin
            existing_was = await self._auth_service.list_was(active_only=False)
            logger.info(f"CIRIS_USER_CREATE: Existing WAs before default admin: {len(existing_was)}")
            for wa in existing_was:
                logger.info(f"CIRIS_USER_CREATE:   - {wa.wa_id}: name={wa.name}, role={wa.role}")

            # Check if any ROOT user already exists - DON'T create another one
            root_was = [wa for wa in existing_was if wa.role == WARole.ROOT]
            if root_was:
                logger.info(
                    f"CIRIS_USER_CREATE: ROOT WA already exists ({root_was[0].wa_id}) - skipping default admin creation"
                )
                return

            logger.info("CIRIS_USER_CREATE: No ROOT WA exists - creating default admin")

            # Create admin WA certificate
            wa_cert = await self._auth_service.create_wa(
                name="admin",
                email="admin@ciris.local",
                scopes=["*"],  # All permissions
                role=WARole.ROOT,  # System admin gets ROOT role
            )
            logger.info(f"CIRIS_USER_CREATE: ✅ Created default admin WA: {wa_cert.wa_id}")

            # Update with password hash
            await self._auth_service.update_wa(
                wa_cert.wa_id, updates=None, password_hash=self._hash_password("ciris_admin_password")
            )
            logger.info(f"CIRIS_USER_CREATE: Password set for default admin: {wa_cert.wa_id}")

            # Add to cache
            admin_user = User(
                wa_id=wa_cert.wa_id,
                name="admin",
                auth_type="password",
                api_role=APIRole.SYSTEM_ADMIN,
                wa_role=WARole.ROOT,
                created_at=wa_cert.created_at,
                is_active=True,
                password_hash=self._hash_password("ciris_admin_password"),
            )
            self._users[admin_user.wa_id] = admin_user
            logger.info(f"CIRIS_USER_CREATE: Added default admin to user cache")

        except Exception as e:
            logger.error(f"CIRIS_USER_CREATE: Error creating default admin: {e}", exc_info=True)

    def _wa_role_to_api_role(self, wa_role: Optional[WARole]) -> APIRole:
        """Convert WA role to API role."""
        if not wa_role:
            return APIRole.OBSERVER

        role_map = {
            WARole.ROOT: APIRole.SYSTEM_ADMIN,
            WARole.AUTHORITY: APIRole.AUTHORITY,
            WARole.OBSERVER: APIRole.OBSERVER,
        }
        return role_map.get(wa_role, APIRole.OBSERVER)

    def _hash_key(self, api_key: str) -> str:
        """Hash an API key for storage using bcrypt."""
        # Use bcrypt for secure key hashing (same as passwords)
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(api_key.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def _verify_key(self, api_key: str, key_hash: str) -> bool:
        """Verify an API key against its hash."""
        try:
            return bcrypt.checkpw(api_key.encode("utf-8"), key_hash.encode("utf-8"))
        except Exception:
            return False

    def _get_key_id(self, api_key: str) -> str:
        """Extract key ID from full API key."""
        # Key format: ciris_role_randomstring
        # Key ID is first 8 chars of SHA256 hash (for display purposes only)
        return hashlib.sha256(api_key.encode()).hexdigest()[:8]

    def store_api_key(
        self,
        key: str,
        user_id: str,
        role: UserRole,
        expires_at: Optional[datetime] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> None:
        """Store a new API key."""
        key_hash = self._hash_key(key)
        key_id = self._get_key_id(key)
        stored_key = StoredAPIKey(
            key_id=key_id,
            key_hash=key_hash,
            key_value=key[:12] + "..." + key[-4:],  # Masked version
            user_id=user_id,
            role=role,
            expires_at=expires_at,
            description=description,
            created_at=datetime.now(timezone.utc),
            created_by=created_by or user_id,
            last_used=None,
            is_active=True,
        )
        # Store by key_id instead of hash (bcrypt hashes are unique per call)
        self._api_keys[key_id] = stored_key
        logger.debug(
            f"[AUTH SERVICE DEBUG] store_api_key: Instance #{self._instance_id} - Stored key_id={key_id} for user={user_id}, role={role}. Total keys now: {len(self._api_keys)}, dict_id={id(self._api_keys)}"
        )

    def validate_api_key(self, api_key: str) -> Optional[StoredAPIKey]:
        """Validate an API key and return its info."""
        # Get the key_id for fast lookup
        key_id = self._get_key_id(api_key)
        stored_key = self._api_keys.get(key_id)

        # DEBUG: Log validation attempt with minimal context (key_id only, no key content)
        all_key_ids = list(self._api_keys.keys())  # NOSONAR - key IDs are hashes, not secrets
        logger.debug(
            f"[AUTH SERVICE DEBUG] validate_api_key: Instance #{self._instance_id} - Validating key_id={key_id}"
        )
        logger.debug(
            f"[AUTH SERVICE DEBUG] validate_api_key: Instance #{self._instance_id} - _api_keys has {len(self._api_keys)} keys, dict_id={id(self._api_keys)}"
        )
        logger.debug(
            f"[AUTH SERVICE DEBUG] validate_api_key: Instance #{self._instance_id} - stored_key found: {stored_key is not None}"
        )

        # Verify the key using bcrypt
        if not stored_key or not stored_key.is_active:
            logger.debug(
                f"[AUTH SERVICE DEBUG] validate_api_key: Instance #{self._instance_id} - FAILED: key not found or inactive"
            )
            return None

        if not self._verify_key(api_key, stored_key.key_hash):
            logger.debug(
                f"[AUTH SERVICE DEBUG] validate_api_key: Instance #{self._instance_id} - FAILED: bcrypt verification failed"
            )
            return None

        # Check expiration
        if stored_key.expires_at and stored_key.expires_at < datetime.now(timezone.utc):
            logger.debug(f"[AUTH SERVICE DEBUG] validate_api_key: Instance #{self._instance_id} - FAILED: key expired")
            return None

        # Update last used
        stored_key.last_used = datetime.now(timezone.utc)

        # Ensure system admin user exists in _users
        if stored_key.user_id == "wa-system-admin" and stored_key.user_id not in self._users:
            # Re-create the system admin user
            admin_user = User(
                wa_id="wa-system-admin",
                name="admin",
                auth_type="password",
                api_role=APIRole.SYSTEM_ADMIN,
                wa_role=None,
                created_at=datetime.now(timezone.utc),
                is_active=True,
                password_hash=self._hash_password("ciris_admin_password"),
            )
            self._users[admin_user.wa_id] = admin_user

        logger.debug(
            f"[AUTH SERVICE DEBUG] validate_api_key: Instance #{self._instance_id} - SUCCESS: key valid for user={stored_key.user_id}, role={stored_key.role}"
        )
        return stored_key

    def revoke_api_key(self, key_id: str) -> None:
        """Revoke an API key."""
        # Lookup by key_id directly
        stored_key = self._api_keys.get(key_id)
        if stored_key:
            stored_key.is_active = False

    def create_oauth_user(
        self,
        provider: str,
        external_id: str,
        email: Optional[str],
        name: Optional[str],
        role: UserRole,
        marketing_opt_in: bool = False,
    ) -> OAuthUser:
        """Create or update an OAuth user."""
        user_id = f"{provider}:{external_id}"
        now = datetime.now(timezone.utc)

        if user_id in self._oauth_users:
            # Update existing user
            user = self._oauth_users[user_id]
            user.last_login = now
            if email:
                user.email = email
            if name:
                user.name = name
            # Update marketing opt-in (user can change their preference)
            user.marketing_opt_in = marketing_opt_in
        else:
            # Create new user
            user = OAuthUser(
                user_id=user_id,
                provider=provider,
                external_id=external_id,
                email=email,
                name=name,
                role=role,
                created_at=now,
                last_login=now,
                marketing_opt_in=marketing_opt_in,
            )
            self._oauth_users[user_id] = user

        return user

    # ========== User Management Methods ==========

    def _hash_password(self, password: str) -> str:
        """Hash a password for storage using PBKDF2."""
        import base64
        import secrets

        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        salt = secrets.token_bytes(32)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = kdf.derive(password.encode())
        return base64.b64encode(salt + key).decode()

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash using PBKDF2."""
        try:
            import base64
            import hmac

            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

            decoded = base64.b64decode(password_hash)
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
            return hmac.compare_digest(key, stored_key)
        except Exception:
            # If verification fails (e.g., invalid hash format), return False
            return False

    async def verify_user_password(self, username: str, password: str) -> Optional[User]:
        """Verify a user's password and return the user if valid."""
        logger.debug("=" * 80)
        logger.debug(f"[AUTH DEBUG] verify_user_password('{username}') called")
        logger.debug(f"[AUTH DEBUG] _users_loaded flag: {self._users_loaded}")

        # Ensure users are loaded from database
        await self._ensure_users_loaded()

        logger.debug(f"[AUTH DEBUG] After _ensure_users_loaded, _users_loaded: {self._users_loaded}")
        logger.debug(f"[AUTH DEBUG] _users dict size: {len(self._users)}")

        user = self.get_user_by_username(username)
        if not user:
            logger.debug("[AUTH DEBUG] User lookup failed - returning None")
            logger.debug("=" * 80)
            return None

        logger.debug(f"[AUTH DEBUG] User found: wa_id={user.wa_id}")
        logger.debug(f"[AUTH DEBUG] User.name: '{user.name}'")
        logger.debug(f"[AUTH DEBUG] User.auth_type: '{user.auth_type}'")
        logger.debug(f"[AUTH DEBUG] Has password_hash: {user.password_hash is not None}")

        if user.password_hash:
            logger.debug(f"[AUTH DEBUG] password_hash length: {len(user.password_hash)}")
            logger.debug(f"[AUTH DEBUG] password_hash prefix: {user.password_hash[:10]}")

            verify_result = self._verify_password(password, user.password_hash)
            logger.debug(f"[AUTH DEBUG] Password verification result: {verify_result}")

            if verify_result:
                logger.debug(f"[AUTH DEBUG] Authentication SUCCESS for '{username}'")
                logger.debug("=" * 80)
                return user
            else:
                logger.debug("[AUTH DEBUG] Password verification FAILED")
                logger.debug("=" * 80)
                return None
        else:
            logger.debug("[AUTH DEBUG] No password_hash for user")
            logger.debug("=" * 80)
            return None

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        logger.debug(f"[AUTH DEBUG] get_user_by_username('{username}') called")
        logger.debug(f"[AUTH DEBUG] _users dict has {len(self._users)} entries")

        # Get unique usernames (since users can be stored under multiple keys)
        unique_users = {}
        for key, user in self._users.items():
            if user.wa_id not in unique_users:
                unique_users[user.wa_id] = user

        usernames = [u.name for u in unique_users.values()]
        logger.debug(f"[AUTH DEBUG] Available usernames: {usernames}")

        for user in self._users.values():
            # Case-insensitive username comparison
            if user.name.lower() == username.lower():
                logger.debug(
                    f"[AUTH DEBUG] FOUND user: wa_id={user.wa_id}, name={user.name}, has_password={user.password_hash is not None}"
                )
                return user

        logger.debug(f"[AUTH DEBUG] User '{username}' NOT FOUND")
        return None

    async def create_user(self, username: str, password: str, api_role: APIRole = APIRole.OBSERVER) -> Optional[User]:
        """Create a new user account."""
        # Check if username already exists
        existing = self.get_user_by_username(username)
        if existing:
            return None

        # Map API role to WA role
        wa_role_map = {
            APIRole.SYSTEM_ADMIN: WARole.ROOT,
            APIRole.AUTHORITY: WARole.AUTHORITY,
            APIRole.ADMIN: WARole.AUTHORITY,  # Admin also gets AUTHORITY
            APIRole.OBSERVER: WARole.OBSERVER,
        }
        wa_role = wa_role_map.get(api_role, WARole.OBSERVER)

        # If we have an auth service, create in database
        if self._auth_service:
            try:
                # Create WA certificate
                wa_cert = await self._auth_service.create_wa(
                    name=username,
                    email=f"{username}@ciris.local",
                    scopes=self.get_permissions_for_role(api_role),
                    role=wa_role,
                )

                # Update with password hash
                await self._auth_service.update_wa(
                    wa_cert.wa_id, updates=None, password_hash=self._hash_password(password)
                )

                # Create user object
                user = User(
                    wa_id=wa_cert.wa_id,
                    name=username,
                    auth_type="password",
                    api_role=api_role,
                    wa_role=wa_role,
                    created_at=wa_cert.created_at,
                    is_active=True,
                    password_hash=self._hash_password(password),
                )

                # Store in cache
                self._users[wa_cert.wa_id] = user
                return user

            except Exception as e:
                logger.debug(f"[AUTH DEBUG] Error creating user in database: {e}")
                # Fall through to in-memory creation

        # Fallback: in-memory only
        user_id = f"wa-user-{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc)
        user = User(
            wa_id=user_id,
            name=username,
            auth_type="password",
            api_role=api_role,
            created_at=now,
            is_active=True,
            password_hash=self._hash_password(password),
        )

        # Store user
        self._users[user_id] = user

        return user

    async def list_users(
        self,
        search: Optional[str] = None,
        auth_type: Optional[str] = None,
        api_role: Optional[APIRole] = None,
        wa_role: Optional[WARole] = None,
        is_active: Optional[bool] = None,
    ) -> List[tuple[str, User]]:
        """List all users with optional filtering. Returns (user_id, user) tuples."""
        # Ensure users are loaded from database before listing
        await self._ensure_users_loaded()

        users = []
        seen_wa_ids: set[str] = set()  # Dedupe by wa_id

        # Add all stored users with their keys (deduplicated by wa_id)
        for user_id, user in self._users.items():
            # Skip duplicates - _users has multiple keys (wa_id, google:xxx) for same user
            if user.wa_id in seen_wa_ids:
                continue
            seen_wa_ids.add(user.wa_id)

            # Apply filters
            if search and search.lower() not in user.name.lower():
                continue
            if auth_type and user.auth_type != auth_type:
                continue
            if api_role and user.api_role != api_role:
                continue
            if wa_role and user.wa_role != wa_role:
                continue
            if is_active is not None and user.is_active != is_active:
                continue

            users.append((user_id, user))  # Use the dict key as the canonical user_id

        # Add OAuth users not in _users
        for oauth_user in self._oauth_users.values():
            oauth_user_id = oauth_user.user_id
            # Check if already in users by matching oauth_external_id
            # This handles cases where the DB WA has a different wa_id (e.g., wa-2025-12-03-xxx)
            # but represents the same OAuth user (same oauth_external_id)
            if any(uid == oauth_user_id or u.oauth_external_id == oauth_user.external_id for uid, u in users):
                continue

            # Convert OAuth user to User
            user = User(
                wa_id=oauth_user.user_id,
                name=oauth_user.name or oauth_user.email or oauth_user.user_id,
                auth_type="oauth",
                api_role=self._user_role_to_api_role(oauth_user.role),
                oauth_provider=oauth_user.provider,
                oauth_email=oauth_user.email,
                oauth_external_id=oauth_user.external_id,
                oauth_name=oauth_user.name,  # Map OAuth name to oauth_name field
                created_at=oauth_user.created_at,
                last_login=oauth_user.last_login,
                is_active=True,
            )

            # Apply filters
            if search and search.lower() not in user.name.lower():
                continue
            if auth_type and user.auth_type != auth_type:
                continue
            if api_role and user.api_role != api_role:
                continue
            if wa_role is not None:
                continue  # OAuth users without WA role
            if is_active is not None and user.is_active != is_active:
                continue

            users.append((oauth_user_id, user))

        return sorted(users, key=lambda tu: tu[1].created_at or datetime.min, reverse=True)

    def _user_role_to_api_role(self, role: UserRole) -> APIRole:
        """Convert UserRole to APIRole."""
        mapping = {
            UserRole.OBSERVER: APIRole.OBSERVER,
            UserRole.ADMIN: APIRole.ADMIN,
            UserRole.SYSTEM_ADMIN: APIRole.SYSTEM_ADMIN,
        }
        return mapping.get(role, APIRole.OBSERVER)

    def _merge_oauth_with_stored_user(self, oauth_user: OAuthUser, stored_user: User) -> User:
        """Merge OAuth session data with persistent database user data."""
        return User(
            wa_id=stored_user.wa_id,  # Use the actual WA ID from database!
            name=stored_user.name or oauth_user.name or oauth_user.email or oauth_user.user_id,
            auth_type="oauth",
            api_role=stored_user.api_role,  # Preserve DB role
            wa_role=stored_user.wa_role,  # Preserve WA role
            oauth_provider=oauth_user.provider,
            oauth_email=oauth_user.email,
            oauth_external_id=oauth_user.external_id,
            created_at=stored_user.created_at or oauth_user.created_at,
            last_login=oauth_user.last_login,
            is_active=stored_user.is_active,
            wa_parent_id=stored_user.wa_parent_id,
            wa_auto_minted=stored_user.wa_auto_minted,
            oauth_name=stored_user.oauth_name or oauth_user.name,
            oauth_picture=stored_user.oauth_picture,
            permission_requested_at=stored_user.permission_requested_at,
            custom_permissions=stored_user.custom_permissions,
            oauth_links=stored_user.oauth_links,
            marketing_opt_in=oauth_user.marketing_opt_in,
        )

    def _create_user_from_oauth(self, oauth_user: OAuthUser) -> User:
        """Create a User object from an OAuth user (not yet minted as WA)."""
        return User(
            wa_id=oauth_user.user_id,  # OAuth user_id as placeholder
            name=oauth_user.name or oauth_user.email or oauth_user.user_id,
            auth_type="oauth",
            api_role=self._user_role_to_api_role(oauth_user.role),
            oauth_provider=oauth_user.provider,
            oauth_email=oauth_user.email,
            oauth_external_id=oauth_user.external_id,
            created_at=oauth_user.created_at,
            last_login=oauth_user.last_login,
            is_active=True,
            oauth_name=oauth_user.name,
            marketing_opt_in=oauth_user.marketing_opt_in,
        )

    def _lookup_oauth_user(self, user_id: str) -> Optional[User]:
        """Look up user in OAuth users dictionary."""
        if user_id not in self._oauth_users:
            return None

        oauth_user = self._oauth_users[user_id]
        stored_user = self._users.get(user_id)

        # If stored_user exists, merge OAuth session data with persistent DB data
        if stored_user:
            return self._merge_oauth_with_stored_user(oauth_user, stored_user)

        # No stored user - pure OAuth user not yet minted as WA
        return self._create_user_from_oauth(oauth_user)

    def _lookup_by_external_id(self, user_id: str) -> Optional[User]:
        """Fallback lookup by OAuth external_id (without provider prefix)."""
        # Try stored users first
        for key, user in self._users.items():
            if user.oauth_external_id == user_id:
                return user

        # Try OAuth users
        for key, oauth_user in self._oauth_users.items():
            if oauth_user.external_id == user_id:
                stored_user = self._users.get(key)
                if stored_user:
                    return stored_user
                return self._create_user_from_oauth(oauth_user)

        return None

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a specific user by ID."""
        # Check stored users first (includes users loaded from DB with OAuth links)
        if user_id in self._users:
            return self._users[user_id]

        # Check OAuth users (in-memory only, for users who haven't been minted as WA yet)
        oauth_result = self._lookup_oauth_user(user_id)
        if oauth_result:
            return oauth_result

        # Fallback: Try to find user by OAuth external_id (without provider prefix)
        # This handles cases where frontend passes just "googleUserId" without "google:" prefix
        return self._lookup_by_external_id(user_id)

    async def update_user(
        self, user_id: str, api_role: Optional[APIRole] = None, is_active: Optional[bool] = None
    ) -> Optional[User]:
        """Update user information."""
        user = self.get_user(user_id)
        if not user:
            return None

        # Update fields
        if api_role is not None:
            user.api_role = api_role
            # Also update WA role to match
            wa_role_map = {
                APIRole.SYSTEM_ADMIN: WARole.ROOT,
                APIRole.AUTHORITY: WARole.AUTHORITY,
                APIRole.ADMIN: WARole.AUTHORITY,  # Admin also gets AUTHORITY
                APIRole.OBSERVER: WARole.OBSERVER,
            }
            user.wa_role = wa_role_map.get(api_role, WARole.OBSERVER)
        if is_active is not None:
            user.is_active = is_active

        # Store updated user
        self._users[user_id] = user

        # Also update in database if we have auth service
        if self._auth_service:
            try:
                # Update role in database
                if api_role is not None and user.wa_role:
                    await self._auth_service.update_wa(
                        user_id,
                        updates=WAUpdate(
                            role=user.wa_role.value if hasattr(user.wa_role, "value") else str(user.wa_role)
                        ),
                    )

                # Update active status in database
                if is_active is not None:
                    if is_active:
                        # Reactivate - note: this may not work if cert was revoked
                        await self._auth_service.update_wa(user_id, updates=WAUpdate(is_active=True))
                    else:
                        # Deactivate
                        await self._auth_service.revoke_wa(user_id, reason="User deactivated via API")
            except Exception as e:
                logger.debug(f"[AUTH DEBUG] Error updating user in database: {e}")

        # Also update OAuth user if applicable
        if user_id in self._oauth_users:
            oauth_user = self._oauth_users[user_id]
            if api_role is not None:
                # Convert APIRole back to UserRole
                role_mapping = {
                    APIRole.OBSERVER: UserRole.OBSERVER,
                    APIRole.ADMIN: UserRole.ADMIN,
                    APIRole.AUTHORITY: UserRole.ADMIN,  # No direct mapping
                    APIRole.SYSTEM_ADMIN: UserRole.SYSTEM_ADMIN,
                }
                oauth_user.role = role_mapping.get(api_role, UserRole.OBSERVER)

        return user

    async def link_user_oauth(
        self,
        wa_id: str,
        provider: str,
        external_id: str,
        *,
        account_name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        primary: bool = False,
    ) -> Optional[User]:
        if not self._auth_service:
            raise ValueError("Authentication service not configured")

        updated = await self._auth_service.link_oauth_identity(
            wa_id,
            provider,
            external_id,
            account_name=account_name,
            metadata=metadata,
            primary=primary,
        )

        if not updated:
            return None

        await self._process_wa_record(updated)
        return self.get_user(wa_id)

    async def unlink_user_oauth(self, wa_id: str, provider: str, external_id: str) -> Optional[User]:
        if not self._auth_service:
            raise ValueError("Authentication service not configured")

        updated = await self._auth_service.unlink_oauth_identity(wa_id, provider, external_id)
        if not updated:
            return None

        await self._process_wa_record(updated)
        return self.get_user(wa_id)

    async def change_password(
        self, user_id: str, new_password: str, current_password: Optional[str] = None, skip_current_check: bool = False
    ) -> bool:
        """Change user password."""
        user = self.get_user(user_id)
        if not user or user.auth_type != "password":
            return False

        # Verify current password unless skip_current_check is True
        if not skip_current_check and current_password:
            if not user.password_hash or not self._verify_password(current_password, user.password_hash):
                return False

        # Update password
        user.password_hash = self._hash_password(new_password)
        self._users[user_id] = user

        # Also update in database if we have auth service
        if self._auth_service:
            try:
                # Use await instead of asyncio.run() - we're already in an async context
                await self._auth_service.update_wa(
                    user_id, updates=None, password_hash=self._hash_password(new_password)
                )
            except Exception as e:
                logger.debug(f"[AUTH DEBUG] Error updating password in database: {e}")

        return True

    async def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user account."""
        user = self.get_user(user_id)
        if not user:
            return False

        user.is_active = False
        self._users[user_id] = user

        # Also update in database if we have auth service
        if self._auth_service:
            try:
                await self._auth_service.revoke_wa(user_id, reason="User deactivated via API")
            except Exception as e:
                logger.debug(f"[AUTH DEBUG] Error deactivating user in database: {e}")

        # Also deactivate OAuth user if applicable
        if user_id in self._oauth_users:
            # Can't really deactivate OAuth users in this simple implementation
            pass

        return True

    def get_permissions_for_role(self, role: APIRole) -> List[str]:
        """Get permissions for a given API role."""
        # Define role permissions
        permissions = {
            APIRole.OBSERVER: [
                PERMISSION_SYSTEM_READ,
                PERMISSION_MEMORY_READ,
                PERMISSION_TELEMETRY_READ,
                PERMISSION_CONFIG_READ,
                PERMISSION_AUDIT_READ,
            ],
            APIRole.ADMIN: [
                PERMISSION_SYSTEM_READ,
                PERMISSION_SYSTEM_WRITE,
                PERMISSION_MEMORY_READ,
                PERMISSION_MEMORY_WRITE,
                PERMISSION_TELEMETRY_READ,
                PERMISSION_CONFIG_READ,
                PERMISSION_CONFIG_WRITE,
                PERMISSION_AUDIT_READ,
                PERMISSION_AUDIT_WRITE,
                PERMISSION_USERS_READ,
                PERMISSION_MANAGE_USER_PERMISSIONS,
            ],
            APIRole.AUTHORITY: [
                PERMISSION_SYSTEM_READ,
                PERMISSION_SYSTEM_WRITE,
                PERMISSION_MEMORY_READ,
                PERMISSION_MEMORY_WRITE,
                PERMISSION_TELEMETRY_READ,
                PERMISSION_CONFIG_READ,
                PERMISSION_CONFIG_WRITE,
                PERMISSION_AUDIT_READ,
                PERMISSION_AUDIT_WRITE,
                PERMISSION_USERS_READ,
                PERMISSION_WA_READ,
                PERMISSION_WA_WRITE,
                "wa.resolve_deferral",  # AUTHORITY role can resolve deferrals
            ],
            APIRole.SYSTEM_ADMIN: [
                PERMISSION_SYSTEM_READ,
                PERMISSION_SYSTEM_WRITE,
                PERMISSION_MEMORY_READ,
                PERMISSION_MEMORY_WRITE,
                PERMISSION_TELEMETRY_READ,
                PERMISSION_CONFIG_READ,
                PERMISSION_CONFIG_WRITE,
                PERMISSION_AUDIT_READ,
                PERMISSION_AUDIT_WRITE,
                PERMISSION_USERS_READ,
                PERMISSION_USERS_WRITE,
                PERMISSION_USERS_DELETE,
                PERMISSION_WA_READ,
                PERMISSION_WA_WRITE,
                PERMISSION_WA_MINT,
                PERMISSION_EMERGENCY_SHUTDOWN,
                PERMISSION_MANAGE_USER_PERMISSIONS,
            ],
        }

        return permissions.get(role, [])

    def get_effective_permissions(self, user: "User") -> List[str]:
        """Get effective permissions for a user including WA role inheritance.

        This applies the following inheritance rules:
        - ROOT WA users get SYSTEM_ADMIN + AUTHORITY permissions
        - AUTHORITY WA users get their role's permissions (which include wa.resolve_deferral)
        - All other users get just their API role's permissions
        - Custom permissions are always added on top
        """
        # Start with base permissions from API role
        permissions_set = set(self.get_permissions_for_role(user.api_role))

        # ROOT WA role inherits AUTHORITY permissions (for deferral resolution, etc.)
        # This is the key rule: ROOT maps to SYSTEM_ADMIN API role, but also gets AUTHORITY perms
        if user.wa_role == WARole.ROOT:
            authority_perms = self.get_permissions_for_role(APIRole.AUTHORITY)
            permissions_set.update(authority_perms)

        # AUTHORITY WA role already has wa.resolve_deferral in their API role permissions
        # No extra inheritance needed since AUTHORITY maps to APIRole.AUTHORITY

        # Add custom permissions
        if user.custom_permissions:
            permissions_set.update(user.custom_permissions)

        return list(permissions_set)

    async def update_user_permissions(self, user_id: str, permissions: List[str]) -> Optional[User]:
        """Update a user's custom permissions."""
        user = self.get_user(user_id)
        if not user:
            return None

        # Update custom permissions
        user.custom_permissions = permissions
        self._users[user_id] = user

        # Also update in database if we have auth service
        if self._auth_service:
            try:

                # Update the WA certificate with custom permissions
                # Don't pass custom_permissions_json as a kwarg, it's not in the protocol
                # Instead, we should store this separately or handle it differently
                await self._auth_service.update_wa(
                    user_id, updates=WAUpdate(permissions=permissions) if permissions else None
                )
            except Exception as e:
                logger.debug(f"[AUTH DEBUG] Error updating permissions in database: {e}")

        return user

    def validate_service_token(self, token: str) -> Optional[User]:
        """Validate a service token and return a service account user.

        Service tokens are compared against CIRIS_SERVICE_TOKEN environment variable.
        Uses constant-time comparison to prevent timing attacks.
        """
        import hmac
        import os

        # Get expected service token from environment
        expected_token = os.environ.get("CIRIS_SERVICE_TOKEN")
        if not expected_token:
            return None

        # Use constant-time comparison
        if not hmac.compare_digest(token, expected_token):
            return None

        # Create and return service account user
        return User(
            wa_id="service-account",
            name="Service Account",
            auth_type="service_token",
            api_role=APIRole.SERVICE_ACCOUNT,
            wa_role=None,
            created_at=datetime.now(timezone.utc),
            last_login=datetime.now(timezone.utc),
            is_active=True,
            custom_permissions=None,
        )

    def list_user_api_keys(self, user_id: str) -> List[StoredAPIKey]:
        """List all API keys for a specific user."""
        keys = []
        for stored_key in self._api_keys.values():
            if stored_key.user_id == user_id:
                keys.append(stored_key)
        return sorted(keys, key=lambda k: k.created_at, reverse=True)

    async def verify_root_signature(self, user_id: str, wa_role: WARole, signature: str) -> bool:
        """Verify a ROOT signature for WA minting.

        The signature should be over the message:
        "MINT_WA:{user_id}:{wa_role}:{timestamp}"

        Where timestamp is in ISO format.
        """
        import json
        from pathlib import Path

        from cryptography.hazmat.primitives.asymmetric import ed25519

        try:
            # Load ROOT public key from seed/
            root_pub_path = Path(__file__).parent.parent.parent.parent.parent.parent / "seed" / "root_pub.json"
            async with aiofiles.open(root_pub_path, "r") as f:
                content = await f.read()
                root_data = json.loads(content)

            # Get the public key (base64url encoded)
            pubkey_b64 = root_data["pubkey"]

            # Decode from base64url to bytes
            # Add padding if needed
            pubkey_b64_padded = pubkey_b64 + "=" * (4 - len(pubkey_b64) % 4)
            pubkey_bytes = base64.urlsafe_b64decode(pubkey_b64_padded)

            # Create Ed25519 public key object
            public_key = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)

            # The signature should include a timestamp
            # For verification, we'll accept signatures from the last hour
            now = datetime.now(timezone.utc)

            # Try multiple timestamp formats within the last hour
            for minutes_ago in range(0, 60, 1):  # Check last 60 minutes
                timestamp = (now - timedelta(minutes=minutes_ago)).isoformat()
                message = f"MINT_WA:{user_id}:{wa_role.value}:{timestamp}"

                try:
                    # Decode signature from base64url
                    sig_padded = signature + "=" * (4 - len(signature) % 4)
                    sig_bytes = base64.urlsafe_b64decode(sig_padded)

                    # Verify signature
                    public_key.verify(sig_bytes, message.encode())

                    # If we get here, signature is valid
                    return True
                except Exception:
                    # Try next timestamp
                    continue

            # Also try without timestamp for backwards compatibility
            message_no_ts = f"MINT_WA:{user_id}:{wa_role.value}"

            # Try standard base64 first (what our signing script produces)
            try:
                sig_bytes = base64.b64decode(signature)
                public_key.verify(sig_bytes, message_no_ts.encode())
                return True
            except Exception:
                pass

            # Try urlsafe base64
            try:
                sig_padded = signature + "=" * (4 - len(signature) % 4)
                sig_bytes = base64.urlsafe_b64decode(sig_padded)
                public_key.verify(sig_bytes, message_no_ts.encode())
                return True
            except Exception:
                pass

            return False

        except Exception as e:
            # Log error but don't expose internal details
            logger.debug(f"[AUTH DEBUG] Signature verification error: {e}")
            return False

    def _update_user_wa_role(self, user: User, wa_role: WARole, minted_by: str) -> None:
        """Update user's WA role and related fields."""
        user.wa_role = wa_role
        user.wa_parent_id = minted_by
        user.wa_auto_minted = False

    def _upgrade_api_role_if_needed(self, user: User, wa_role: WARole) -> None:
        """Upgrade user's API role if WA role requires higher access."""
        # ROOT and AUTHORITY WA roles both grant AUTHORITY API role
        if wa_role in (WARole.ROOT, WARole.AUTHORITY) and user.api_role.value < APIRole.AUTHORITY.value:
            user.api_role = APIRole.AUTHORITY
        elif wa_role == WARole.OBSERVER and user.api_role.value < APIRole.OBSERVER.value:
            user.api_role = APIRole.OBSERVER

    async def _update_existing_wa(self, user_id: str, wa_role: WARole) -> None:
        """Update existing WA certificate."""
        if not self._auth_service:
            return
        await self._auth_service.update_wa(
            user_id, updates=WAUpdate(role=wa_role.value if hasattr(wa_role, "value") else str(wa_role))
        )
        logger.debug(f"[AUTH DEBUG] Updated existing WA {user_id} to role {wa_role}")

    def _create_wa_email(self, user_name: str) -> str:
        """Create email for WA certificate."""
        return user_name + "@ciris.local" if "@" not in user_name else user_name

    def _get_wa_permissions(self, user: User) -> List[str]:
        """Get permissions for WA certificate."""
        base_permissions = self.get_permissions_for_role(user.api_role)
        return base_permissions + [
            "wa.resolve_deferral",  # Critical for deferral resolution
            "wa.mint",  # Allow WA to mint others
        ]

    async def _create_new_wa_for_oauth_user(self, user: User, user_id: str, wa_role: WARole) -> str:
        """Create new WA certificate for OAuth user and return the wa_id."""
        if not self._auth_service:
            raise ValueError("Authentication service not available")

        wa_permissions = self._get_wa_permissions(user)

        # Create WA certificate with proper wa_id format, but link to OAuth user
        import json
        from datetime import datetime, timezone

        from ciris_engine.schemas.services.authority_core import WACertificate

        timestamp = datetime.now(timezone.utc)

        # Generate proper wa_id (format: wa-YYYY-MM-DD-XXXXXX)
        # Must match pattern: ^wa-\d{4}-\d{2}-\d{2}-[A-Z0-9]{6}$
        import secrets

        wa_id = f"wa-{timestamp.strftime('%Y-%m-%d')}-{secrets.token_hex(3).upper()}"
        jwt_kid = f"wa-jwt-oauth-{wa_id[-6:].lower()}"

        # Extract OAuth info from user_id (format: "provider:external_id")
        oauth_provider = None
        oauth_external_id = None
        if ":" in user_id:
            oauth_provider, oauth_external_id = user_id.split(":", 1)

        # Create WA certificate with proper wa_id but linked to OAuth identity
        wa_cert = WACertificate(
            wa_id=wa_id,  # Proper wa_id format
            name=user.name,
            role=wa_role,
            pubkey=f"oauth-{oauth_provider}-{oauth_external_id}" if oauth_provider else user_id,
            jwt_kid=jwt_kid,
            oauth_provider=oauth_provider,
            oauth_external_id=oauth_external_id,
            auto_minted=True,
            scopes_json=json.dumps(wa_permissions),
            created_at=timestamp,
            last_auth=timestamp,
        )

        # Store WA certificate in database
        # Note: Accessing private method - ideally this would be a public API
        if hasattr(self._auth_service, "_store_wa_certificate"):
            store_method = getattr(self._auth_service, "_store_wa_certificate")
            await store_method(wa_cert)
        else:
            raise ValueError("Cannot store WA certificate - method not available")

        logger.debug(f"[AUTH DEBUG] Created WA certificate {wa_id} for OAuth user {user_id} with role {wa_role}")
        return wa_id

    # Removed _link_oauth_identity - no longer needed since OAuth users use their user_id as wa_id

    def _update_user_records_for_oauth_wa(self, user: User, user_id: str, wa_id: str) -> None:
        """Update OAuth user record with WA information (no duplicate records)."""
        user.wa_id = wa_id  # Set the proper WA ID
        # Keep the user under their original OAuth user_id key
        self._users[user_id] = user  # Update existing record, don't create duplicate

    async def _handle_wa_database_operations(self, user: User, user_id: str, wa_role: WARole) -> None:
        """Handle WA database create/update operations."""
        if not self._auth_service:
            return
        existing_wa = await self._auth_service.get_wa(user_id)

        if existing_wa:
            await self._update_existing_wa(user_id, wa_role)
        else:
            # For OAuth users, create WA with proper wa_id but update existing OAuth user record
            wa_id = await self._create_new_wa_for_oauth_user(user, user_id, wa_role)
            self._update_user_records_for_oauth_wa(user, user_id, wa_id)

    async def mint_wise_authority(self, user_id: str, wa_role: WARole, minted_by: str) -> Optional[User]:
        """Mint a user as a Wise Authority."""
        user = self.get_user(user_id)
        if not user:
            return None

        # Update user WA role and API role if needed
        self._update_user_wa_role(user, wa_role, minted_by)
        self._upgrade_api_role_if_needed(user, wa_role)

        # Store updated user
        self._users[user_id] = user

        # Handle database operations if auth service is available
        if self._auth_service:
            try:
                await self._handle_wa_database_operations(user, user_id, wa_role)
                # Note: parent_wa_id and auto_minted are not supported by the protocol's update_wa method
                # They would need to be set during creation or via a different mechanism
            except Exception as e:
                logger.debug(f"[AUTH DEBUG] Error updating/creating WA in database: {e}")

        return user
