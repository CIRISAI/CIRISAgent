"""
Google OAuth provider implementation.
"""

from typing import Dict, Any, Optional
import httpx
import logging

logger = logging.getLogger(__name__)


class GoogleOAuthProvider:
    """Google OAuth provider implementation."""
    
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v1/userinfo"
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        hd_domain: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.hd_domain = hd_domain
        self._http_client = http_client
    
    @property
    def http_client(self) -> httpx.AsyncClient:
        """Get HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient()
        return self._http_client
    
    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Get OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account"
        }
        
        if self.hd_domain:
            params["hd"] = self.hd_domain
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{self.AUTH_URL}?{query_string}"
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code"
        }
        
        try:
            response = await self.http_client.post(self.TOKEN_URL, data=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Token exchange failed: {e.response.text}")
            raise ValueError(f"Failed to exchange code: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            raise ValueError("Failed to exchange authorization code")
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from Google."""
        try:
            response = await self.http_client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"User info fetch failed: {e.response.text}")
            raise ValueError(f"Failed to get user info: {e.response.status_code}")
        except Exception as e:
            logger.error(f"User info error: {e}")
            raise ValueError("Failed to get user information")
    
    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()