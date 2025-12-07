"""
MCP Server Security Module.

Security components for the MCP server adapter:
- Client authentication
- Request authorization
- Rate limiting
- Request validation
- Audit logging
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

from .config import AuthMethod, MCPServerSecurityConfig

logger = logging.getLogger(__name__)


class AuthResult(str, Enum):
    """Authentication result."""

    SUCCESS = "success"
    FAILED = "failed"
    EXPIRED = "expired"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"


@dataclass
class ClientSession:
    """Authenticated client session."""

    client_id: str
    client_name: str
    auth_method: AuthMethod
    authenticated_at: datetime
    last_activity: datetime
    permissions: Set[str] = field(default_factory=set)
    request_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self, timeout_seconds: int = 3600) -> bool:
        """Check if session is expired."""
        age = (datetime.now(timezone.utc) - self.last_activity).total_seconds()
        return age > timeout_seconds

    def touch(self) -> None:
        """Update last activity time."""
        self.last_activity = datetime.now(timezone.utc)
        self.request_count += 1


@dataclass
class AuditRecord:
    """Audit record for MCP requests."""

    timestamp: datetime
    client_id: str
    method: str
    params_hash: str  # Hash of params for privacy
    result: str  # "success", "error", "blocked"
    duration_ms: float
    error_message: Optional[str] = None


class MCPServerRateLimiter:
    """Rate limiter for MCP server requests."""

    def __init__(
        self,
        max_requests_per_minute: int = 100,
        max_concurrent: int = 10,
    ) -> None:
        self.max_requests_per_minute = max_requests_per_minute
        self.max_concurrent = max_concurrent
        self._client_calls: Dict[str, List[float]] = {}
        self._client_concurrent: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def check_rate_limit(self, client_id: str) -> tuple[bool, Optional[str]]:
        """Check if client is within rate limits.

        Args:
            client_id: Client identifier

        Returns:
            (allowed, reason) tuple
        """
        async with self._lock:
            now = time.time()

            # Initialize client tracking
            if client_id not in self._client_calls:
                self._client_calls[client_id] = []
                self._client_concurrent[client_id] = 0

            # Clean old calls
            self._client_calls[client_id] = [t for t in self._client_calls[client_id] if now - t < 60.0]

            # Check rate limit
            if len(self._client_calls[client_id]) >= self.max_requests_per_minute:
                return False, f"Rate limit exceeded: {self.max_requests_per_minute}/minute"

            # Check concurrent limit
            if self._client_concurrent[client_id] >= self.max_concurrent:
                return False, f"Concurrent limit exceeded: {self.max_concurrent}"

            return True, None

    async def acquire(self, client_id: str) -> bool:
        """Acquire a rate limit slot.

        Args:
            client_id: Client identifier

        Returns:
            True if acquired, False if rate limited
        """
        allowed, _ = await self.check_rate_limit(client_id)
        if not allowed:
            return False

        async with self._lock:
            now = time.time()
            if client_id not in self._client_calls:
                self._client_calls[client_id] = []
                self._client_concurrent[client_id] = 0

            self._client_calls[client_id].append(now)
            self._client_concurrent[client_id] += 1
            return True

    async def release(self, client_id: str) -> None:
        """Release a rate limit slot.

        Args:
            client_id: Client identifier
        """
        async with self._lock:
            if client_id in self._client_concurrent:
                self._client_concurrent[client_id] = max(0, self._client_concurrent[client_id] - 1)

    def get_client_stats(self, client_id: str) -> Dict[str, Any]:
        """Get rate limit stats for a client."""
        calls = self._client_calls.get(client_id, [])
        now = time.time()
        recent_calls = len([t for t in calls if now - t < 60.0])

        return {
            "requests_last_minute": recent_calls,
            "concurrent_requests": self._client_concurrent.get(client_id, 0),
            "limit_requests_per_minute": self.max_requests_per_minute,
            "limit_concurrent": self.max_concurrent,
        }


class MCPServerAuthenticator:
    """Authenticator for MCP clients."""

    def __init__(self, config: MCPServerSecurityConfig) -> None:
        self.config = config
        self._sessions: Dict[str, ClientSession] = {}
        self._api_key_hashes: Set[str] = set()
        self._lock = asyncio.Lock()

        # Hash API keys for secure comparison
        for key in config.api_keys:
            self._api_key_hashes.add(self._hash_key(key))

    def _hash_key(self, key: str) -> str:
        """Hash an API key for secure storage/comparison."""
        return hashlib.sha256(key.encode()).hexdigest()

    async def authenticate(
        self,
        client_info: Dict[str, str],
        credentials: Optional[Dict[str, str]] = None,
    ) -> tuple[AuthResult, Optional[ClientSession]]:
        """Authenticate a client.

        Args:
            client_info: Client information (name, version, etc.)
            credentials: Authentication credentials

        Returns:
            (result, session) tuple
        """
        client_name = client_info.get("name", "unknown")
        client_version = client_info.get("version", "unknown")
        client_id = f"{client_name}_{client_version}_{secrets.token_hex(8)}"

        # Check if client is blocked
        if client_name in self.config.blocked_clients:
            logger.warning(f"Blocked client attempted connection: {client_name}")
            return AuthResult.BLOCKED, None

        # Check allowlist if specified
        if self.config.allowed_clients and client_name not in self.config.allowed_clients:
            logger.warning(f"Client not in allowlist: {client_name}")
            return AuthResult.FAILED, None

        # If no auth required, create session
        if not self.config.require_auth:
            session = await self._create_session(client_id, client_name, AuthMethod.NONE)
            return AuthResult.SUCCESS, session

        # Validate credentials
        if not credentials:
            return AuthResult.FAILED, None

        # Try API key auth
        if AuthMethod.API_KEY in self.config.auth_methods:
            api_key = credentials.get("api_key")
            if api_key and self._hash_key(api_key) in self._api_key_hashes:
                session = await self._create_session(client_id, client_name, AuthMethod.API_KEY)
                return AuthResult.SUCCESS, session

        # Try JWT auth
        if AuthMethod.JWT in self.config.auth_methods:
            jwt_token = credentials.get("jwt")
            if jwt_token and await self._validate_jwt(jwt_token):
                session = await self._create_session(client_id, client_name, AuthMethod.JWT)
                return AuthResult.SUCCESS, session

        return AuthResult.FAILED, None

    async def _validate_jwt(self, token: str) -> bool:
        """Validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            True if valid
        """
        # TODO: Implement proper JWT validation
        # For now, this is a placeholder
        return False

    async def _create_session(self, client_id: str, client_name: str, auth_method: AuthMethod) -> ClientSession:
        """Create a new client session.

        Args:
            client_id: Unique client ID
            client_name: Client name
            auth_method: Authentication method used

        Returns:
            New ClientSession
        """
        now = datetime.now(timezone.utc)
        session = ClientSession(
            client_id=client_id,
            client_name=client_name,
            auth_method=auth_method,
            authenticated_at=now,
            last_activity=now,
            permissions={"tools", "resources", "prompts"},  # Default permissions
        )

        async with self._lock:
            self._sessions[client_id] = session

        logger.info(f"Created session for client: {client_name} ({client_id})")
        return session

    async def get_session(self, client_id: str) -> Optional[ClientSession]:
        """Get an existing session.

        Args:
            client_id: Client ID

        Returns:
            ClientSession or None
        """
        async with self._lock:
            session = self._sessions.get(client_id)
            if session and not session.is_expired():
                session.touch()
                return session
            elif session:
                # Expired, remove it
                del self._sessions[client_id]
            return None

    async def end_session(self, client_id: str) -> None:
        """End a client session.

        Args:
            client_id: Client ID
        """
        async with self._lock:
            if client_id in self._sessions:
                del self._sessions[client_id]
                logger.info(f"Ended session: {client_id}")

    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get list of active sessions."""
        sessions = []
        for session in self._sessions.values():
            if not session.is_expired():
                sessions.append(
                    {
                        "client_id": session.client_id,
                        "client_name": session.client_name,
                        "auth_method": session.auth_method.value,
                        "authenticated_at": session.authenticated_at.isoformat(),
                        "request_count": session.request_count,
                    }
                )
        return sessions


class MCPServerSecurityManager:
    """Central security manager for MCP server."""

    def __init__(self, config: MCPServerSecurityConfig) -> None:
        self.config = config
        self.authenticator = MCPServerAuthenticator(config)
        self.rate_limiter = MCPServerRateLimiter(
            max_requests_per_minute=config.max_requests_per_minute,
            max_concurrent=config.max_concurrent_requests,
        )
        self._audit_records: List[AuditRecord] = []
        self._lock = asyncio.Lock()

    async def authenticate_client(
        self,
        client_info: Dict[str, str],
        credentials: Optional[Dict[str, str]] = None,
    ) -> tuple[AuthResult, Optional[ClientSession]]:
        """Authenticate a client connection.

        Args:
            client_info: Client information
            credentials: Authentication credentials

        Returns:
            (result, session) tuple
        """
        return await self.authenticator.authenticate(client_info, credentials)

    async def authorize_request(
        self,
        session: ClientSession,
        method: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, Optional[str]]:
        """Authorize a request from a client.

        Args:
            session: Client session
            method: MCP method being called
            params: Method parameters

        Returns:
            (authorized, reason) tuple
        """
        # Check rate limit
        allowed, reason = await self.rate_limiter.check_rate_limit(session.client_id)
        if not allowed:
            return False, reason

        # Check method permissions
        method_category = method.split("/")[0] if "/" in method else method
        if method_category not in session.permissions and method_category not in ["ping", "initialize"]:
            return False, f"No permission for {method_category}"

        # Validate request size
        if params and self.config.validate_requests:
            import json

            try:
                size = len(json.dumps(params).encode())
                if size > self.config.max_request_size_bytes:
                    return False, f"Request too large: {size} > {self.config.max_request_size_bytes}"
            except (TypeError, ValueError):
                pass

        return True, None

    async def record_request(
        self,
        client_id: str,
        method: str,
        params: Optional[Dict[str, Any]],
        result: str,
        duration_ms: float,
        error_message: Optional[str] = None,
    ) -> None:
        """Record a request for auditing.

        Args:
            client_id: Client ID
            method: Method called
            params: Request parameters
            result: Result status
            duration_ms: Request duration
            error_message: Error message if failed
        """
        if not self.config.audit_requests:
            return

        # Hash params for privacy
        import json

        params_str = json.dumps(params, sort_keys=True) if params else ""
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]

        record = AuditRecord(
            timestamp=datetime.now(timezone.utc),
            client_id=client_id,
            method=method,
            params_hash=params_hash,
            result=result,
            duration_ms=duration_ms,
            error_message=error_message,
        )

        async with self._lock:
            self._audit_records.append(record)
            # Keep only last 10000 records
            if len(self._audit_records) > 10000:
                self._audit_records = self._audit_records[-10000:]

    async def acquire_rate_limit(self, client_id: str) -> bool:
        """Acquire rate limit slot for request."""
        return await self.rate_limiter.acquire(client_id)

    async def release_rate_limit(self, client_id: str) -> None:
        """Release rate limit slot after request."""
        await self.rate_limiter.release(client_id)

    def get_metrics(self) -> Dict[str, Any]:
        """Get security metrics."""
        return {
            "active_sessions": len(self.authenticator.get_active_sessions()),
            "audit_records": len(self._audit_records),
            "auth_required": self.config.require_auth,
            "rate_limit_enabled": self.config.rate_limit_enabled,
        }

    def get_audit_records(
        self,
        client_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get audit records.

        Args:
            client_id: Filter by client ID
            since: Filter by time
            limit: Maximum records to return

        Returns:
            List of audit record dicts
        """
        records = self._audit_records.copy()

        if client_id:
            records = [r for r in records if r.client_id == client_id]

        if since:
            records = [r for r in records if r.timestamp >= since]

        records = records[-limit:]

        return [
            {
                "timestamp": r.timestamp.isoformat(),
                "client_id": r.client_id,
                "method": r.method,
                "result": r.result,
                "duration_ms": r.duration_ms,
                "error": r.error_message,
            }
            for r in records
        ]


__all__ = [
    "AuthResult",
    "ClientSession",
    "AuditRecord",
    "MCPServerRateLimiter",
    "MCPServerAuthenticator",
    "MCPServerSecurityManager",
]
