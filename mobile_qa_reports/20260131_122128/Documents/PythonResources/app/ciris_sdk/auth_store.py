"""
Persistent authentication storage for CIRIS SDK.

Provides secure storage for API keys and auth tokens with:
- File-based persistence with proper permissions
- Optional encryption for sensitive data
- Automatic token refresh management
"""

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .exceptions import CIRISError


class AuthToken(BaseModel):
    """Authentication token with metadata."""

    token: str = Field(..., description="The authentication token")
    expires_at: Optional[datetime] = Field(None, description="Token expiration time")
    refresh_token: Optional[str] = Field(None, description="Refresh token if available")
    token_type: str = Field("Bearer", description="Token type")
    scope: Optional[str] = Field(None, description="Token scope/permissions")

    def is_expired(self) -> bool:
        """Check if token is expired."""
        if not self.expires_at:
            return False
        return datetime.now(timezone.utc) >= self.expires_at


class AuthStore:
    """
    Persistent storage for authentication credentials.

    Stores API keys and tokens in a JSON file with restricted permissions.
    Default location is ~/.ciris/auth.json
    """

    def __init__(self, auth_file: Optional[Path] = None):
        """
        Initialize auth store.

        Args:
            auth_file: Path to auth file (default: ~/.ciris/auth.json)
        """
        if auth_file is None:
            auth_file = Path.home() / ".ciris" / "auth.json"

        self.auth_file = auth_file
        self._ensure_auth_dir()

    def _ensure_auth_dir(self) -> None:
        """Ensure auth directory exists with proper permissions."""
        auth_dir = self.auth_file.parent
        auth_dir.mkdir(parents=True, exist_ok=True)

        # Set directory permissions to 700 (owner only)
        try:
            os.chmod(auth_dir, stat.S_IRWXU)
        except Exception:
            # Windows may not support chmod
            pass

    def _load_auth_data(self) -> Dict[str, Any]:
        """Load auth data from file."""
        if not self.auth_file.exists():
            return {}

        try:
            with open(self.auth_file, "r") as f:
                data = json.load(f)

            # Ensure data is a dict (json.load returns Any)
            assert isinstance(data, dict), "Auth data must be a dictionary"

            # Convert ISO strings back to datetime objects
            for key in ["token_expires_at", "api_key_created_at"]:
                if key in data and data[key]:
                    data[key] = datetime.fromisoformat(data[key])

            return data
        except Exception as e:
            raise CIRISError(f"Failed to load auth data: {e}")

    def _save_auth_data(self, data: Dict[str, Any]) -> None:
        """Save auth data to file with restricted permissions."""
        # Convert datetime objects to ISO strings for JSON
        save_data = data.copy()
        for key, value in save_data.items():
            if isinstance(value, datetime):
                save_data[key] = value.isoformat()

        try:
            # Write to temp file first
            temp_file = self.auth_file.with_suffix(".tmp")
            with open(temp_file, "w") as f:
                json.dump(save_data, f, indent=2)

            # Set file permissions to 600 (owner read/write only)
            try:
                os.chmod(temp_file, stat.S_IRUSR | stat.S_IWUSR)
            except Exception:
                # Windows may not support chmod
                pass

            # Atomically replace old file
            temp_file.replace(self.auth_file)

        except Exception as e:
            raise CIRISError(f"Failed to save auth data: {e}")

    def store_api_key(self, api_key: str, base_url: str) -> None:
        """
        Store API key for a specific base URL.

        Args:
            api_key: The API key to store
            base_url: The base URL this key is for
        """
        data = self._load_auth_data()

        # Store API key info
        data["api_keys"] = data.get("api_keys", {})
        data["api_keys"][base_url] = {"key": api_key, "created_at": datetime.now(timezone.utc).isoformat()}

        self._save_auth_data(data)

    def get_api_key(self, base_url: str) -> Optional[str]:
        """
        Get stored API key for a base URL.

        Args:
            base_url: The base URL to get key for

        Returns:
            API key if found, None otherwise
        """
        data = self._load_auth_data()
        api_keys = data.get("api_keys", {})

        if base_url in api_keys:
            key = api_keys[base_url].get("key")
            # Ensure key is a string or None
            return str(key) if key is not None else None

        return None

    def store_token(self, token: AuthToken, base_url: str) -> None:
        """
        Store authentication token.

        Args:
            token: The auth token to store
            base_url: The base URL this token is for
        """
        data = self._load_auth_data()

        # Store token info
        data["tokens"] = data.get("tokens", {})
        data["tokens"][base_url] = {
            "token": token.token,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "refresh_token": token.refresh_token,
            "token_type": token.token_type,
            "scope": token.scope,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self._save_auth_data(data)

    def get_token(self, base_url: str) -> Optional[AuthToken]:
        """
        Get stored token for a base URL.

        Args:
            base_url: The base URL to get token for

        Returns:
            AuthToken if found and valid, None otherwise
        """
        data = self._load_auth_data()
        tokens = data.get("tokens", {})

        if base_url not in tokens:
            return None

        token_data = tokens[base_url]
        token = AuthToken(
            token=token_data["token"],
            expires_at=datetime.fromisoformat(token_data["expires_at"]) if token_data.get("expires_at") else None,
            refresh_token=token_data.get("refresh_token"),
            token_type=token_data.get("token_type", "Bearer"),
            scope=token_data.get("scope"),
        )

        # Don't return expired tokens
        if token.is_expired():
            return None

        return token

    def clear_auth(self, base_url: Optional[str] = None) -> None:
        """
        Clear stored authentication data.

        Args:
            base_url: If provided, only clear auth for this URL.
                     If None, clear all auth data.
        """
        if base_url is None:
            # Clear all auth data
            if self.auth_file.exists():
                self.auth_file.unlink()
        else:
            # Clear auth for specific URL
            data = self._load_auth_data()

            api_keys = data.get("api_keys", {})
            tokens = data.get("tokens", {})

            if base_url in api_keys:
                del api_keys[base_url]
            if base_url in tokens:
                del tokens[base_url]

            self._save_auth_data(data)

    def list_stored_urls(self) -> Dict[str, Dict[str, bool]]:
        """
        List all URLs with stored auth data.

        Returns:
            Dict mapping URLs to auth info (has_api_key, has_token)
        """
        data = self._load_auth_data()
        api_keys = data.get("api_keys", {})
        tokens = data.get("tokens", {})

        all_urls = set(api_keys.keys()) | set(tokens.keys())

        result = {}
        for url in all_urls:
            result[url] = {"has_api_key": url in api_keys, "has_token": url in tokens}

            # Check if token is expired
            if url in tokens:
                token_data = tokens[url]
                if token_data.get("expires_at"):
                    expires_at = datetime.fromisoformat(token_data["expires_at"])
                    result[url]["token_expired"] = datetime.now(timezone.utc) >= expires_at
                else:
                    result[url]["token_expired"] = False

        return result
