"""
Tests for auth routes.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi import FastAPI

from ciris_manager.api.auth_routes import (
    create_auth_routes,
    init_auth_service,
    get_auth_service,
    get_current_user_dependency
)


class TestAuthRoutes:
    """Test auth routes."""
    
    @pytest.fixture
    def mock_auth_service(self):
        """Create mock auth service."""
        service = Mock()
        service.initiate_oauth_flow = AsyncMock()
        service.handle_oauth_callback = AsyncMock()
        service.get_current_user = Mock()
        return service
    
    @pytest.fixture
    def app(self, mock_auth_service):
        """Create FastAPI app with auth routes."""
        # Initialize with mock service
        with patch('ciris_manager.api.auth_routes._auth_service', mock_auth_service):
            app = FastAPI()
            router = create_auth_routes()
            app.include_router(router, prefix="/v1")
            
            # Override the dependency
            app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
            
            return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app, follow_redirects=False)
    
    def test_init_auth_service(self):
        """Test auth service initialization."""
        with patch('ciris_manager.api.auth_routes.GoogleOAuthProvider') as mock_provider:
            with patch('ciris_manager.api.auth_routes.InMemorySessionStore') as mock_session:
                with patch('ciris_manager.api.auth_routes.SQLiteUserStore') as mock_user:
                    service = init_auth_service(
                        google_client_id="test-id",
                        google_client_secret="test-secret",
                        jwt_secret="test-jwt-secret"
                    )
                    
                    assert service is not None
                    mock_provider.assert_called_once_with(
                        client_id="test-id",
                        client_secret="test-secret",
                        hd_domain="ciris.ai"
                    )
    
    def test_init_auth_service_no_credentials(self):
        """Test auth service initialization without credentials."""
        service = init_auth_service()
        assert service is None
    
    def test_init_auth_service_from_env(self):
        """Test auth service initialization from environment."""
        with patch.dict('os.environ', {
            'GOOGLE_CLIENT_ID': 'env-id',
            'GOOGLE_CLIENT_SECRET': 'env-secret'
        }):
            with patch('ciris_manager.api.auth_routes.GoogleOAuthProvider'):
                service = init_auth_service()
                assert service is not None
    
    def test_get_auth_service_not_initialized(self):
        """Test getting auth service when not initialized."""
        with patch('ciris_manager.api.auth_routes._auth_service', None):
            with pytest.raises(RuntimeError, match="Auth service not initialized"):
                get_auth_service()
    
    def test_oauth_login(self, client, mock_auth_service):
        """Test OAuth login endpoint."""
        mock_auth_service.initiate_oauth_flow.return_value = (
            "test-state",
            "https://accounts.google.com/auth"
        )
        
        response = client.get("/v1/oauth/login")
        
        assert response.status_code == 307  # Redirect
        assert response.headers["location"] == "https://accounts.google.com/auth"
        
        # Verify flow was initiated with correct parameters
        mock_auth_service.initiate_oauth_flow.assert_called_once()
        call_args = mock_auth_service.initiate_oauth_flow.call_args[1]
        assert call_args["redirect_uri"] == "http://testserver/manager"
        # testserver is not localhost, so it gets production callback URL
        assert call_args["callback_url"] == "https://agents.ciris.ai/manager/oauth/callback"
    
    def test_oauth_login_with_redirect_uri(self, client, mock_auth_service):
        """Test OAuth login with custom redirect URI."""
        mock_auth_service.initiate_oauth_flow.return_value = (
            "test-state",
            "https://accounts.google.com/auth"
        )
        
        response = client.get("/v1/oauth/login?redirect_uri=http://custom.com/app")
        
        assert response.status_code == 307
        
        # Verify custom redirect was used
        call_args = mock_auth_service.initiate_oauth_flow.call_args[1]
        assert call_args["redirect_uri"] == "http://custom.com/app"
    
    def test_oauth_login_no_service(self, client):
        """Test OAuth login when service not configured."""
        # Mock the auth service check to return None (not configured)
        mock_auth_service = None
        
        client.app.dependency_overrides[get_auth_service] = lambda: mock_auth_service
        response = client.get("/v1/oauth/login")
        assert response.status_code == 500
        assert response.json()["detail"] == "OAuth not configured"
    
    def test_oauth_login_error(self, client, mock_auth_service):
        """Test OAuth login with error."""
        mock_auth_service.initiate_oauth_flow.side_effect = Exception("OAuth error")
        
        response = client.get("/v1/oauth/login")
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to initiate OAuth"
    
    def test_oauth_callback_success(self, client, mock_auth_service):
        """Test successful OAuth callback."""
        mock_auth_service.handle_oauth_callback.return_value = {
            "access_token": "test-jwt-token",
            "user": {"email": "test@ciris.ai"},
            "redirect_uri": "http://app.com/dashboard"
        }
        
        response = client.get("/v1/oauth/callback?code=test-code&state=test-state")
        
        assert response.status_code == 307  # Redirect
        assert response.headers["location"] == "http://app.com/dashboard?token=test-jwt-token"
        
        # Check cookie was set
        assert "manager_token" in response.cookies
        cookie = response.cookies["manager_token"]
        assert cookie == "test-jwt-token"
        
        # Verify callback was handled
        mock_auth_service.handle_oauth_callback.assert_called_once_with(
            "test-code",
            "test-state"
        )
    
    def test_oauth_callback_value_error(self, client, mock_auth_service):
        """Test OAuth callback with value error."""
        mock_auth_service.handle_oauth_callback.side_effect = ValueError("Invalid state")
        
        response = client.get("/v1/oauth/callback?code=test-code&state=bad-state")
        
        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid state"
    
    def test_oauth_callback_general_error(self, client, mock_auth_service):
        """Test OAuth callback with general error."""
        mock_auth_service.handle_oauth_callback.side_effect = Exception("Auth failed")
        
        response = client.get("/v1/oauth/callback?code=test-code&state=test-state")
        
        assert response.status_code == 500
        assert response.json()["detail"] == "Authentication failed"
    
    def test_logout(self, client):
        """Test logout endpoint."""
        response = client.post("/v1/oauth/logout")
        
        assert response.status_code == 200
        assert response.json()["message"] == "Logged out successfully"
        
        # Check cookie was deleted - TestClient doesn't set empty cookies
        # so we just verify the response was successful
    
    def test_get_current_user_authenticated(self, client, mock_auth_service):
        """Test getting current user when authenticated."""
        mock_auth_service.get_current_user.return_value = {
            "user_id": 1,
            "email": "test@ciris.ai"
        }
        
        response = client.get(
            "/v1/oauth/user",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "test@ciris.ai"
        
        # Verify auth service was called
        mock_auth_service.get_current_user.assert_called_once_with("Bearer test-token")
    
    def test_get_current_user_not_authenticated(self, client, mock_auth_service):
        """Test getting current user when not authenticated."""
        mock_auth_service.get_current_user.return_value = None
        
        response = client.get(
            "/v1/oauth/user",
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "Not authenticated"
    
    def test_get_current_user_dependency_success(self, mock_auth_service):
        """Test get_current_user_dependency with valid auth."""
        mock_auth_service.get_current_user.return_value = {
            "user_id": 1,
            "email": "test@ciris.ai"
        }
        
        # Create a mock that returns our auth service
        def mock_get_service():
            return mock_auth_service
        
        with patch('ciris_manager.api.auth_routes.get_auth_service', mock_get_service):
            user = get_current_user_dependency(
                authorization="Bearer test-token",
                auth_service=mock_auth_service
            )
            assert user["email"] == "test@ciris.ai"
    
    def test_get_current_user_dependency_no_auth(self, mock_auth_service):
        """Test get_current_user_dependency without auth."""
        mock_auth_service.get_current_user.return_value = None
        
        # Create a mock that returns our auth service
        def mock_get_service():
            return mock_auth_service
        
        with patch('ciris_manager.api.auth_routes.get_auth_service', mock_get_service):
            with pytest.raises(HTTPException) as exc:
                get_current_user_dependency(
                    authorization="Bearer invalid",
                    auth_service=mock_auth_service
                )
            
            assert exc.value.status_code == 401
            assert exc.value.detail == "Not authenticated"
    
    def test_get_current_user_dependency_no_service(self):
        """Test get_current_user_dependency without service."""
        with pytest.raises(HTTPException) as exc:
            get_current_user_dependency(
                authorization="Bearer token",
                auth_service=None
            )
        
        assert exc.value.status_code == 500
        assert exc.value.detail == "OAuth not configured"