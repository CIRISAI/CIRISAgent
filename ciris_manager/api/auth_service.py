"""
OAuth authentication service for CIRISManager.

Separates OAuth logic from route handlers for better testability.
"""

from typing import Optional, Dict, Any, Protocol
from datetime import datetime, timedelta
from pathlib import Path
from pydantic import BaseModel, Field
import secrets
import logging
import jwt
import json
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class TokenResponse(BaseModel):
    """OAuth token response."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = Field(default=86400)  # 24 hours
    user: Dict[str, Any]


class OAuthProvider(Protocol):
    """Protocol for OAuth providers."""
    
    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """Get OAuth authorization URL."""
        ...
    
    async def exchange_code_for_token(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange authorization code for access token."""
        ...
    
    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user information from OAuth provider."""
        ...


class SessionStore(Protocol):
    """Protocol for session storage."""
    
    def store_session(self, state: str, data: Dict[str, Any]) -> None:
        """Store OAuth session data."""
        ...
    
    def get_session(self, state: str) -> Optional[Dict[str, Any]]:
        """Retrieve OAuth session data."""
        ...
    
    def delete_session(self, state: str) -> None:
        """Delete OAuth session data."""
        ...


class UserStore(Protocol):
    """Protocol for user storage."""
    
    def create_or_update_user(self, email: str, user_info: Dict[str, Any]) -> int:
        """Create or update user, return user ID."""
        ...
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        ...
    
    def is_user_authorized(self, email: str) -> bool:
        """Check if user is authorized."""
        ...


class InMemorySessionStore:
    """In-memory session storage implementation."""
    
    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    def store_session(self, state: str, data: Dict[str, Any]) -> None:
        self._sessions[state] = {
            **data,
            "created_at": datetime.utcnow().isoformat()
        }
    
    def get_session(self, state: str) -> Optional[Dict[str, Any]]:
        return self._sessions.get(state)
    
    def delete_session(self, state: str) -> None:
        self._sessions.pop(state, None)


class SQLiteUserStore:
    """SQLite user storage implementation."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    name TEXT,
                    picture TEXT,
                    first_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_authorized BOOLEAN DEFAULT 1
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS login_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            conn.commit()
    
    @contextmanager
    def _get_db(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def create_or_update_user(self, email: str, user_info: Dict[str, Any]) -> int:
        """Create or update user."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (email, name, picture, last_login)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(email) DO UPDATE SET
                    name = excluded.name,
                    picture = excluded.picture,
                    last_login = CURRENT_TIMESTAMP
            """, (email, user_info.get("name"), user_info.get("picture")))
            conn.commit()
            
            # Get user ID
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            return cursor.fetchone()["id"]
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        with self._get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def is_user_authorized(self, email: str) -> bool:
        """Check if user is authorized."""
        user = self.get_user_by_email(email)
        return user is not None and user.get("is_authorized", False)


class AuthService:
    """Authentication service."""
    
    def __init__(
        self,
        oauth_provider: OAuthProvider,
        session_store: SessionStore,
        user_store: UserStore,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        jwt_expiration_hours: int = 24
    ):
        self.oauth_provider = oauth_provider
        self.session_store = session_store
        self.user_store = user_store
        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expiration_hours = jwt_expiration_hours
    
    def generate_state_token(self) -> str:
        """Generate CSRF state token."""
        return secrets.token_urlsafe(32)
    
    async def initiate_oauth_flow(
        self,
        redirect_uri: str,
        callback_url: str
    ) -> tuple[str, str]:
        """
        Initiate OAuth flow.
        
        Returns:
            Tuple of (state_token, authorization_url)
        """
        state = self.generate_state_token()
        
        # Store session data
        self.session_store.store_session(state, {
            "redirect_uri": redirect_uri,
            "callback_url": callback_url
        })
        
        # Get authorization URL
        auth_url = await self.oauth_provider.get_authorization_url(
            state=state,
            redirect_uri=callback_url
        )
        
        return state, auth_url
    
    async def handle_oauth_callback(
        self,
        code: str,
        state: str
    ) -> Dict[str, Any]:
        """
        Handle OAuth callback.
        
        Returns:
            Dict containing access_token, user info, and redirect_uri
        """
        # Verify state
        session_data = self.session_store.get_session(state)
        if not session_data:
            raise ValueError("Invalid state parameter")
        
        # Clean up session
        self.session_store.delete_session(state)
        
        # Exchange code for token
        token_data = await self.oauth_provider.exchange_code_for_token(
            code=code,
            redirect_uri=session_data["callback_url"]
        )
        
        # Get user info
        user_info = await self.oauth_provider.get_user_info(
            access_token=token_data["access_token"]
        )
        
        # Verify user is authorized
        email = user_info.get("email", "")
        if not email.endswith("@ciris.ai"):
            raise ValueError("Only @ciris.ai accounts are allowed")
        
        # Store/update user
        user_id = self.user_store.create_or_update_user(email, user_info)
        
        # Generate JWT
        jwt_token = self.create_jwt_token({
            "user_id": user_id,
            "email": email,
            "name": user_info.get("name", "")
        })
        
        return {
            "access_token": jwt_token,
            "user": user_info,
            "redirect_uri": session_data["redirect_uri"]
        }
    
    def create_jwt_token(self, payload: Dict[str, Any]) -> str:
        """Create JWT token."""
        to_encode = payload.copy()
        expire = datetime.utcnow() + timedelta(hours=self.jwt_expiration_hours)
        to_encode.update({"exp": expire})
        
        return jwt.encode(to_encode, self.jwt_secret, algorithm=self.jwt_algorithm)
    
    def verify_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token."""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            logger.debug("JWT token expired")
            return None
        except jwt.InvalidTokenError:
            logger.debug("Invalid JWT token")
            return None
    
    def get_current_user(self, authorization: Optional[str]) -> Optional[Dict[str, Any]]:
        """Get current user from authorization header."""
        if not authorization or not authorization.startswith("Bearer "):
            return None
        
        token = authorization.replace("Bearer ", "")
        payload = self.verify_jwt_token(token)
        
        if not payload:
            return None
        
        # Verify user still exists and is authorized
        email = payload.get("email")
        if not email or not self.user_store.is_user_authorized(email):
            return None
        
        return payload