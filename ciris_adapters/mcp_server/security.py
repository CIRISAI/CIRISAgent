"""
MCP Server Security Module.

Handles JWT validation and security checks for the MCP server.
"""

import logging
from typing import Any, Dict, Optional

import jwt

from .config import MCPServerConfig

logger = logging.getLogger(__name__)


class MCPServerSecurity:
    """Security manager for MCP Server."""

    def __init__(self, config: MCPServerConfig) -> None:
        """Initialize security manager.

        Args:
            config: Server configuration
        """
        self.config = config

    def _decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode a JWT token.

        Args:
            token: JWT token string

        Returns:
            Payload dict if valid, None otherwise
        """
        if not self.config.jwt_secret:
            return None

        try:
            result: Dict[str, Any] = jwt.decode(
                token,
                self.config.jwt_secret,
                algorithms=[self.config.jwt_algorithm],
            )
            return result
        except jwt.PyJWTError as e:
            logger.warning(f"JWT validation failed: {e}")
            return None

    async def _validate_jwt(self, token: str) -> bool:
        """Validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            True if valid
        """
        return self._decode_token(token) is not None

    async def validate_token(self, token: str) -> Optional[str]:
        """Validate a token and return the user ID.

        Args:
            token: The token to validate

        Returns:
            User ID if valid, None otherwise
        """
        payload = self._decode_token(token)
        if payload:
            return payload.get("sub")
        return None
