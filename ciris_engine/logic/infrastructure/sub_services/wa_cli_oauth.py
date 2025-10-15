"""WA CLI OAuth Service - Handles OAuth provider configuration and authentication."""

import asyncio
import http.server
import json
import logging
import secrets
import socketserver
import urllib.parse
import webbrowser
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any, Dict, Optional

from rich.console import Console

from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.schemas.infrastructure.oauth import (
    OAuthCallbackData,
    OAuthLoginResult,
    OAuthOperationResult,
    OAuthTokenResponse,
    OAuthUserInfo,
)
from ciris_engine.schemas.services.authority_core import WACertificate, WARole
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class WACLIOAuthService:
    """Handles OAuth provider configuration and authentication flows."""

    def __init__(self, auth_service: AuthenticationService, time_service: "TimeServiceProtocol"):
        """Initialize OAuth service with authentication service."""
        self.auth_service = auth_service
        self.time_service = time_service
        self.console = Console()

        # OAuth configuration - check shared volume first (managed mode), then local
        self.oauth_config_file = Path("/home/ciris/shared/oauth/oauth.json")
        if not self.oauth_config_file.exists():
            self.oauth_config_file = Path.home() / ".ciris" / "oauth.json"
            self.oauth_config_file.parent.mkdir(exist_ok=True, mode=0o700)

        # OAuth callback data storage
        self._oauth_callback_data: Optional[OAuthCallbackData] = None
        self._oauth_server_running = False

    async def oauth_setup(
        self, provider: str, client_id: str, client_secret: str, custom_metadata: Optional[JSONDict] = None
    ) -> OAuthOperationResult:
        """Configure OAuth provider."""
        try:
            # Load existing config
            config = {}
            if self.oauth_config_file.exists():
                config = json.loads(self.oauth_config_file.read_text())

            # Add/update provider
            config[provider] = {
                "client_id": client_id,
                "client_secret": client_secret,
                "created": self.time_service.now().isoformat(),
            }

            if custom_metadata:
                config[provider]["metadata"] = custom_metadata

            # Save config
            self.oauth_config_file.write_text(json.dumps(config, indent=2))
            self.oauth_config_file.chmod(0o600)

            self.console.print(f"✅ OAuth provider '{provider}' configured!")
            self.console.print(f"📁 Config saved to: [bold]{self.oauth_config_file}[/bold]")

            # Show callback URL
            callback_url = f"http://localhost:8080/v1/auth/oauth/{provider}/callback"
            self.console.print(f"🔗 Callback URL: [bold]{callback_url}[/bold]")
            self.console.print(f"\nRun [bold]ciris wa oauth-login {provider}[/bold] to authenticate.")

            return OAuthOperationResult(status="success", provider=provider, callback_url=callback_url)

        except Exception as e:
            self.console.print(f"❌ Error configuring OAuth: {e}")
            return OAuthOperationResult(status="error", error=str(e))

    async def oauth_login(self, provider: str) -> OAuthLoginResult:
        """Initiate OAuth login flow."""
        try:
            # Load OAuth config
            if not self.oauth_config_file.exists():
                raise ValueError("No OAuth providers configured. Run 'ciris wa oauth add' first.")

            config = json.loads(self.oauth_config_file.read_text())
            if provider not in config:
                raise ValueError(f"Provider '{provider}' not configured")

            provider_config = config[provider]

            # Generate state for CSRF protection
            state = secrets.token_urlsafe(32)

            # Build authorization URL (example for Google)
            if provider == "google":
                auth_url = (
                    "https://accounts.google.com/o/oauth2/v2/auth?"
                    f"client_id={provider_config['client_id']}&"
                    "redirect_uri=http://localhost:8080/callback&"
                    "response_type=code&"
                    "scope=openid%20email%20profile&"
                    f"state={state}"
                )
            else:
                # Generic OAuth2 flow
                auth_url = f"https://{provider}/oauth/authorize?client_id={provider_config['client_id']}&state={state}"

            # Start local callback server
            await self._start_oauth_callback_server(8080)

            # Open browser
            self.console.print(f"🌐 Opening browser for {provider} authentication...")
            webbrowser.open(auth_url)

            # Wait for callback
            self.console.print("⏳ Waiting for authentication...")

            # Poll for callback data
            for _ in range(60):  # 60 second timeout
                if self._oauth_callback_data:
                    break
                await asyncio.sleep(1)

            if not self._oauth_callback_data:
                raise TimeoutError("OAuth callback timeout")

            callback_data = self._oauth_callback_data
            self._oauth_callback_data = None

            # Exchange code for token and create WA
            result = await self._exchange_oauth_code(provider, callback_data, provider_config)

            self.console.print("✅ OAuth login successful!")

            return result

        except Exception as e:
            self.console.print(f"❌ OAuth login error: {e}")
            return OAuthLoginResult(status="error", provider=provider, error=str(e))

    async def _exchange_oauth_code(
        self, provider: str, callback_data: OAuthCallbackData, provider_config: JSONDict
    ) -> OAuthLoginResult:
        """Exchange OAuth code for token and create WA."""

        try:
            # Extract code and state
            code = callback_data.code
            _state = callback_data.state
            error = callback_data.error

            if error:
                raise ValueError(f"OAuth error: {error}")

            if not code:
                raise ValueError("No authorization code received")

            # Exchange code for token based on provider
            token_data = await self._exchange_code_for_token(provider, code, provider_config)

            # Fetch user profile
            user_profile = await self._fetch_user_profile(provider, token_data.access_token)

            # Create or update WA certificate
            wa_cert = await self._create_oauth_wa(provider, user_profile, token_data)

            # Generate session JWT
            token = self.auth_service.create_gateway_token(wa=wa_cert, expires_hours=24)

            return OAuthLoginResult(
                status="success",
                provider=provider,
                auth_url=None,
                certificate={"wa_id": wa_cert.wa_id, "token": token, "scopes": json.loads(wa_cert.scopes_json)},
                error=None,
            )

        except Exception as e:
            logger.error(f"OAuth exchange error: {e}")
            raise

    async def _exchange_code_for_token(self, provider: str, code: str, provider_config: JSONDict) -> OAuthTokenResponse:
        """Exchange authorization code for access token."""
        import aiohttp

        # Token endpoints by provider
        token_endpoints = {
            "google": "https://oauth2.googleapis.com/token",
            "discord": "https://discord.com/api/oauth2/token",
            "github": "https://github.com/login/oauth/access_token",
        }

        if provider not in token_endpoints:
            raise ValueError(f"Unsupported provider: {provider}")

        # Prepare token request
        token_request_data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": provider_config["client_id"],
            "client_secret": provider_config["client_secret"],
            "redirect_uri": "http://localhost:8080/callback",
        }

        # Make token request
        async with aiohttp.ClientSession() as session:
            async with session.post(
                token_endpoints[provider], data=token_request_data, headers={"Accept": "application/json"}
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise ValueError(f"Token exchange failed: {error}")

                token_json = await resp.json()
                token_data = OAuthTokenResponse(
                    access_token=token_json["access_token"],
                    token_type=token_json.get("token_type", "Bearer"),
                    expires_in=token_json.get("expires_in"),
                    refresh_token=token_json.get("refresh_token"),
                    scope=token_json.get("scope"),
                )
                return token_data

    async def _fetch_user_profile(self, provider: str, access_token: str) -> OAuthUserInfo:
        """Fetch user profile from OAuth provider."""
        import aiohttp

        # User info endpoints by provider
        user_endpoints = {
            "google": "https://www.googleapis.com/oauth2/v2/userinfo",
            "discord": "https://discord.com/api/users/@me",
            "github": "https://api.github.com/user",
        }

        if provider not in user_endpoints:
            raise ValueError(f"Unsupported provider: {provider}")

        # Fetch user info
        async with aiohttp.ClientSession() as session:
            async with session.get(
                user_endpoints[provider], headers={"Authorization": f"Bearer {access_token}"}
            ) as resp:
                if resp.status != 200:
                    error = await resp.text()
                    raise ValueError(f"Failed to fetch user profile: {error}")

                profile = await resp.json()

                # Normalize profile data
                if provider == "google":
                    return OAuthUserInfo(
                        id=profile.get("id"),
                        email=profile.get("email"),
                        name=profile.get("name"),
                        picture=profile.get("picture"),
                        provider_data=profile,
                    )
                elif provider == "discord":
                    return OAuthUserInfo(
                        id=profile.get("id", ""),
                        email=profile.get("email"),
                        name=profile.get("username"),
                        provider_data={
                            "discriminator": profile.get("discriminator"),
                            "avatar": profile.get("avatar"),
                            **profile,
                        },
                    )
                elif provider == "github":
                    return OAuthUserInfo(
                        id=str(profile.get("id", "")),
                        email=profile.get("email"),
                        name=profile.get("name") or profile.get("login"),
                        picture=profile.get("avatar_url"),
                        provider_data={"login": profile.get("login"), **profile},
                    )

                # Return raw profile for unhandled providers
                return OAuthUserInfo(
                    id=str(profile.get("id", "")),
                    email=profile.get("email"),
                    name=profile.get("name"),
                    provider_data=profile,
                )

    async def _create_oauth_wa(
        self, provider: str, user_profile: OAuthUserInfo, token_data: OAuthTokenResponse
    ) -> WACertificate:
        """Create or update WA certificate for OAuth user."""
        # Check if WA already exists for this OAuth user
        existing_wa = await self.auth_service.get_wa_by_oauth(provider=provider, external_id=user_profile.id)

        if existing_wa:
            # Update last auth
            existing_wa.last_auth = self.time_service.now()
            await self.auth_service.update_wa(existing_wa.wa_id, last_auth=self.time_service.now())
            return existing_wa

        # Generate IDs for new WA
        timestamp = self.time_service.now()
        wa_id = self.auth_service._generate_wa_id(timestamp)
        jwt_kid = f"wa-jwt-oauth-{wa_id[-6:].lower()}"

        # Determine display name
        display_name = user_profile.name or (user_profile.email or "").split("@")[0]
        if not display_name:
            display_name = f"{provider}_user_{user_profile.id[:8]}"

        # Create OAuth observer WA
        oauth_wa = WACertificate(
            wa_id=wa_id,
            name=display_name,
            role=WARole.OBSERVER,
            pubkey=f"oauth-{provider}-{user_profile.id}",  # OAuth users don't have Ed25519 keys
            jwt_kid=jwt_kid,
            oauth_provider=provider,
            oauth_external_id=user_profile.id,
            auto_minted=True,
            scopes_json='["read:any", "write:message"]',
            created_at=timestamp,
            last_auth=timestamp,
        )

        # Note: Discord ID is stored in oauth_external_id for OAuth users
        # Discord-specific data can be stored in metadata if needed

        # Store WA
        await self.auth_service._store_wa_certificate(oauth_wa)

        return oauth_wa

    async def _start_oauth_callback_server(self, port: int) -> None:
        """Start a temporary HTTP server to receive OAuth callback."""
        if self._oauth_server_running:
            return

        class OAuthCallbackHandler(http.server.SimpleHTTPRequestHandler):
            oauth_service = self

            def do_GET(self) -> None:
                """Handle OAuth callback."""
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/callback":
                    # Extract query parameters
                    params = urllib.parse.parse_qs(parsed.query)

                    # Store callback data
                    self.oauth_service._oauth_callback_data = OAuthCallbackData(
                        code=params.get("code", [None])[0] or "",
                        state=params.get("state", [None])[0] or "",
                        error=params.get("error", [None])[0],
                    )

                    # Send response
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()

                    html = """
                    <html>
                    <head><title>CIRIS OAuth Success</title></head>
                    <body>
                        <h1>Authentication Successful!</h1>
                        <p>You can close this window and return to the terminal.</p>
                        <script>window.close();</script>
                    </body>
                    </html>
                    """
                    self.wfile.write(html.encode())
                else:
                    self.send_error(404)

            def log_message(self, format: str, *args: object) -> None:
                """Suppress log messages."""

        # Set the oauth_service reference
        OAuthCallbackHandler.oauth_service = self

        # Start server in background thread
        def run_server() -> None:
            with socketserver.TCPServer(("", port), OAuthCallbackHandler) as httpd:
                self._oauth_server_running = True
                httpd.timeout = 60  # 60 second timeout
                httpd.handle_request()  # Handle one request then stop
                self._oauth_server_running = False

        server_thread = Thread(target=run_server, daemon=True)
        server_thread.start()

        # Give server time to start
        await asyncio.sleep(0.5)
