"""
Tests for auth service components.
"""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime, timedelta
import jwt
import tempfile
from pathlib import Path

from ciris_manager.api.auth_service import (
    AuthService,
    InMemorySessionStore,
    SQLiteUserStore
)


class TestInMemorySessionStore:
    """Test InMemorySessionStore."""
    
    def test_store_and_retrieve_session(self):
        """Test storing and retrieving session data."""
        store = InMemorySessionStore()
        
        # Store session
        store.store_session("test-state", {"redirect_uri": "http://example.com"})
        
        # Retrieve session
        session = store.get_session("test-state")
        assert session is not None
        assert session["redirect_uri"] == "http://example.com"
        assert "created_at" in session
    
    def test_get_nonexistent_session(self):
        """Test retrieving non-existent session."""
        store = InMemorySessionStore()
        session = store.get_session("nonexistent")
        assert session is None
    
    def test_delete_session(self):
        """Test deleting session."""
        store = InMemorySessionStore()
        
        # Store and delete
        store.store_session("test-state", {"data": "value"})
        store.delete_session("test-state")
        
        # Should be gone
        session = store.get_session("test-state")
        assert session is None
    
    def test_delete_nonexistent_session(self):
        """Test deleting non-existent session doesn't raise."""
        store = InMemorySessionStore()
        store.delete_session("nonexistent")  # Should not raise


class TestSQLiteUserStore:
    """Test SQLiteUserStore."""
    
    @pytest.fixture
    def user_store(self):
        """Create user store with temp database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_auth.db"
            yield SQLiteUserStore(db_path)
    
    def test_create_user(self, user_store):
        """Test creating a new user."""
        user_id = user_store.create_or_update_user(
            "test@ciris.ai",
            {"name": "Test User", "picture": "http://example.com/pic.jpg"}
        )
        
        assert user_id > 0
        
        # Verify user was created
        user = user_store.get_user_by_email("test@ciris.ai")
        assert user is not None
        assert user["email"] == "test@ciris.ai"
        assert user["name"] == "Test User"
        assert user["picture"] == "http://example.com/pic.jpg"
        assert user["is_authorized"] == 1
    
    def test_update_existing_user(self, user_store):
        """Test updating existing user."""
        # Create user
        user_id1 = user_store.create_or_update_user(
            "test@ciris.ai",
            {"name": "Original Name"}
        )
        
        # Update user
        user_id2 = user_store.create_or_update_user(
            "test@ciris.ai",
            {"name": "Updated Name"}
        )
        
        # Should be same user
        assert user_id1 == user_id2
        
        # Verify update
        user = user_store.get_user_by_email("test@ciris.ai")
        assert user["name"] == "Updated Name"
    
    def test_get_nonexistent_user(self, user_store):
        """Test getting non-existent user."""
        user = user_store.get_user_by_email("nonexistent@ciris.ai")
        assert user is None
    
    def test_is_user_authorized(self, user_store):
        """Test authorization check."""
        # Create authorized user
        user_store.create_or_update_user("authorized@ciris.ai", {})
        assert user_store.is_user_authorized("authorized@ciris.ai") == True
        
        # Non-existent user
        assert user_store.is_user_authorized("nonexistent@ciris.ai") is False


class TestAuthService:
    """Test AuthService."""
    
    @pytest.fixture
    def mock_oauth_provider(self):
        """Create mock OAuth provider."""
        provider = Mock()
        provider.get_authorization_url = AsyncMock()
        provider.exchange_code_for_token = AsyncMock()
        provider.get_user_info = AsyncMock()
        return provider
    
    @pytest.fixture
    def auth_service(self, mock_oauth_provider):
        """Create auth service with mocks."""
        session_store = InMemorySessionStore()
        with tempfile.TemporaryDirectory() as tmpdir:
            user_store = SQLiteUserStore(Path(tmpdir) / "test.db")
            
            service = AuthService(
                oauth_provider=mock_oauth_provider,
                session_store=session_store,
                user_store=user_store,
                jwt_secret="test-secret",
                jwt_expiration_hours=1
            )
            yield service
    
    def test_generate_state_token(self, auth_service):
        """Test state token generation."""
        token1 = auth_service.generate_state_token()
        token2 = auth_service.generate_state_token()
        
        # Should be different
        assert token1 != token2
        
        # Should be reasonable length
        assert len(token1) > 20
    
    @pytest.mark.asyncio
    async def test_initiate_oauth_flow(self, auth_service, mock_oauth_provider):
        """Test OAuth flow initiation."""
        # Setup mock
        mock_oauth_provider.get_authorization_url.return_value = "https://oauth.example.com/auth"
        
        # Initiate flow
        state, auth_url = await auth_service.initiate_oauth_flow(
            redirect_uri="http://app.example.com",
            callback_url="http://app.example.com/callback"
        )
        
        # Verify state was generated
        assert len(state) > 20
        
        # Verify URL was returned
        assert auth_url == "https://oauth.example.com/auth"
        
        # Verify session was stored
        session = auth_service.session_store.get_session(state)
        assert session is not None
        assert session["redirect_uri"] == "http://app.example.com"
    
    @pytest.mark.asyncio
    async def test_handle_oauth_callback_success(self, auth_service, mock_oauth_provider):
        """Test successful OAuth callback handling."""
        # Setup state
        state = "test-state"
        auth_service.session_store.store_session(state, {
            "redirect_uri": "http://app.example.com",
            "callback_url": "http://app.example.com/callback"
        })
        
        # Setup mocks
        mock_oauth_provider.exchange_code_for_token.return_value = {
            "access_token": "google-access-token"
        }
        mock_oauth_provider.get_user_info.return_value = {
            "email": "user@ciris.ai",
            "name": "Test User",
            "picture": "http://example.com/pic.jpg"
        }
        
        # Handle callback
        result = await auth_service.handle_oauth_callback("test-code", state)
        
        # Verify result
        assert "access_token" in result
        assert result["user"]["email"] == "user@ciris.ai"
        assert result["redirect_uri"] == "http://app.example.com"
        
        # Verify session was cleaned up
        assert auth_service.session_store.get_session(state) is None
        
        # Verify user was created
        user = auth_service.user_store.get_user_by_email("user@ciris.ai")
        assert user is not None
    
    @pytest.mark.asyncio
    async def test_handle_oauth_callback_invalid_state(self, auth_service):
        """Test OAuth callback with invalid state."""
        with pytest.raises(ValueError, match="Invalid state"):
            await auth_service.handle_oauth_callback("code", "invalid-state")
    
    @pytest.mark.asyncio
    async def test_handle_oauth_callback_non_ciris_email(self, auth_service, mock_oauth_provider):
        """Test OAuth callback with non-ciris.ai email."""
        # Setup state
        state = "test-state"
        auth_service.session_store.store_session(state, {
            "redirect_uri": "http://app.example.com",
            "callback_url": "http://app.example.com/callback"
        })
        
        # Setup mocks
        mock_oauth_provider.exchange_code_for_token.return_value = {
            "access_token": "google-access-token"
        }
        mock_oauth_provider.get_user_info.return_value = {
            "email": "user@gmail.com",  # Not @ciris.ai
            "name": "External User"
        }
        
        # Should raise
        with pytest.raises(ValueError, match="@ciris.ai accounts"):
            await auth_service.handle_oauth_callback("test-code", state)
    
    def test_create_jwt_token(self, auth_service):
        """Test JWT token creation."""
        payload = {
            "user_id": 1,
            "email": "test@ciris.ai"
        }
        
        token = auth_service.create_jwt_token(payload)
        
        # Verify token can be decoded
        decoded = jwt.decode(
            token,
            "test-secret",
            algorithms=["HS256"]
        )
        
        assert decoded["user_id"] == 1
        assert decoded["email"] == "test@ciris.ai"
        assert "exp" in decoded
    
    def test_verify_jwt_token_valid(self, auth_service):
        """Test verifying valid JWT token."""
        # Create token
        token = auth_service.create_jwt_token({"user_id": 1})
        
        # Verify
        payload = auth_service.verify_jwt_token(token)
        assert payload is not None
        assert payload["user_id"] == 1
    
    def test_verify_jwt_token_expired(self, auth_service):
        """Test verifying expired JWT token."""
        # Create expired token
        payload = {
            "user_id": 1,
            "exp": datetime.utcnow() - timedelta(hours=1)
        }
        token = jwt.encode(payload, "test-secret", algorithm="HS256")
        
        # Should return None
        result = auth_service.verify_jwt_token(token)
        assert result is None
    
    def test_verify_jwt_token_invalid(self, auth_service):
        """Test verifying invalid JWT token."""
        # Should return None for invalid token
        result = auth_service.verify_jwt_token("invalid-token")
        assert result is None
    
    def test_get_current_user_valid(self, auth_service):
        """Test getting current user with valid token."""
        # Create user
        auth_service.user_store.create_or_update_user("test@ciris.ai", {})
        
        # Create token
        token = auth_service.create_jwt_token({
            "user_id": 1,
            "email": "test@ciris.ai"
        })
        
        # Get user
        user = auth_service.get_current_user(f"Bearer {token}")
        assert user is not None
        assert user["email"] == "test@ciris.ai"
    
    def test_get_current_user_no_auth(self, auth_service):
        """Test getting current user without auth header."""
        user = auth_service.get_current_user(None)
        assert user is None
    
    def test_get_current_user_invalid_format(self, auth_service):
        """Test getting current user with invalid auth format."""
        user = auth_service.get_current_user("InvalidFormat token")
        assert user is None
    
    def test_get_current_user_unauthorized_email(self, auth_service):
        """Test getting current user with unauthorized email."""
        # Create token for non-existent user
        token = auth_service.create_jwt_token({
            "user_id": 999,
            "email": "nonexistent@ciris.ai"
        })
        
        # Should return None
        user = auth_service.get_current_user(f"Bearer {token}")
        assert user is None