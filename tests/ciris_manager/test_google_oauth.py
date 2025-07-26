"""
Tests for Google OAuth provider.
"""

import pytest
from unittest.mock import Mock, AsyncMock
import httpx

from ciris_manager.api.google_oauth import GoogleOAuthProvider


class TestGoogleOAuthProvider:
    """Test GoogleOAuthProvider."""
    
    @pytest.fixture
    def provider(self):
        """Create provider with mock HTTP client."""
        mock_client = AsyncMock(spec=httpx.AsyncClient)
        return GoogleOAuthProvider(
            client_id="test-client-id",
            client_secret="test-client-secret",
            hd_domain="ciris.ai",
            http_client=mock_client
        )
    
    @pytest.mark.asyncio
    async def test_get_authorization_url(self, provider):
        """Test authorization URL generation."""
        url = await provider.get_authorization_url(
            state="test-state",
            redirect_uri="http://localhost/callback"
        )
        
        # Verify URL structure
        assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
        assert "client_id=test-client-id" in url
        assert "state=test-state" in url
        assert "redirect_uri=http://localhost/callback" in url
        assert "response_type=code" in url
        assert "scope=openid email profile" in url
        assert "hd=ciris.ai" in url
    
    @pytest.mark.asyncio
    async def test_get_authorization_url_no_domain(self):
        """Test authorization URL without domain restriction."""
        provider = GoogleOAuthProvider(
            client_id="test-client-id",
            client_secret="test-client-secret",
            http_client=AsyncMock()
        )
        
        url = await provider.get_authorization_url("state", "http://callback")
        
        # Should not have hd parameter
        assert "hd=" not in url
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self, provider):
        """Test successful code exchange."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "access_token": "test-access-token",
            "token_type": "Bearer",
            "expires_in": 3600
        }
        mock_response.raise_for_status.return_value = None
        
        provider.http_client.post.return_value = mock_response
        
        # Exchange code
        result = await provider.exchange_code_for_token(
            code="test-code",
            redirect_uri="http://localhost/callback"
        )
        
        # Verify result
        assert result["access_token"] == "test-access-token"
        
        # Verify request
        provider.http_client.post.assert_called_once_with(
            "https://oauth2.googleapis.com/token",
            data={
                "code": "test-code",
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
                "redirect_uri": "http://localhost/callback",
                "grant_type": "authorization_code"
            }
        )
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token_http_error(self, provider):
        """Test code exchange with HTTP error."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Invalid grant"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad request",
            request=Mock(),
            response=mock_response
        )
        
        provider.http_client.post.return_value = mock_response
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to exchange code: 400"):
            await provider.exchange_code_for_token("bad-code", "http://callback")
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token_network_error(self, provider):
        """Test code exchange with network error."""
        provider.http_client.post.side_effect = httpx.NetworkError("Connection failed")
        
        with pytest.raises(ValueError, match="Failed to exchange authorization code"):
            await provider.exchange_code_for_token("code", "http://callback")
    
    @pytest.mark.asyncio
    async def test_get_user_info_success(self, provider):
        """Test successful user info retrieval."""
        # Mock response
        mock_response = Mock()
        mock_response.json.return_value = {
            "id": "123456",
            "email": "user@ciris.ai",
            "name": "Test User",
            "picture": "http://example.com/pic.jpg"
        }
        mock_response.raise_for_status.return_value = None
        
        provider.http_client.get.return_value = mock_response
        
        # Get user info
        result = await provider.get_user_info("test-access-token")
        
        # Verify result
        assert result["email"] == "user@ciris.ai"
        assert result["name"] == "Test User"
        
        # Verify request
        provider.http_client.get.assert_called_once_with(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": "Bearer test-access-token"}
        )
    
    @pytest.mark.asyncio
    async def test_get_user_info_http_error(self, provider):
        """Test user info retrieval with HTTP error."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Invalid token"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unauthorized",
            request=Mock(),
            response=mock_response
        )
        
        provider.http_client.get.return_value = mock_response
        
        # Should raise ValueError
        with pytest.raises(ValueError, match="Failed to get user info: 401"):
            await provider.get_user_info("invalid-token")
    
    @pytest.mark.asyncio
    async def test_get_user_info_network_error(self, provider):
        """Test user info retrieval with network error."""
        provider.http_client.get.side_effect = httpx.NetworkError("Connection failed")
        
        with pytest.raises(ValueError, match="Failed to get user information"):
            await provider.get_user_info("token")
    
    @pytest.mark.asyncio
    async def test_close(self, provider):
        """Test closing HTTP client."""
        await provider.close()
        provider.http_client.aclose.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_http_client_property(self):
        """Test HTTP client lazy initialization."""
        provider = GoogleOAuthProvider(
            client_id="test",
            client_secret="secret"
        )
        
        # Should create client on first access
        client = provider.http_client
        assert isinstance(client, httpx.AsyncClient)
        
        # Should return same client
        assert provider.http_client is client