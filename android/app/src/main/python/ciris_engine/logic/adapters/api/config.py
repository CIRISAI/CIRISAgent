"""Configuration schema for API adapter."""

from pydantic import BaseModel, Field

from ciris_engine.constants import DEFAULT_API_HOST, DEFAULT_API_PORT


class APIAdapterConfig(BaseModel):
    """Configuration for the API adapter.

    Security Note:
    - Default host is 127.0.0.1 (localhost only) for security
    - Set host to 0.0.0.0 only when you need external access
    - Always use proper firewall rules when binding to all interfaces
    - Consider using a reverse proxy (nginx, etc.) for production deployments
    """

    host: str = Field(
        default=DEFAULT_API_HOST,
        description="API server host (127.0.0.1 for localhost only, 0.0.0.0 for all interfaces)",
    )
    port: int = Field(default=DEFAULT_API_PORT, description="API server port")

    cors_enabled: bool = Field(default=True, description="Enable CORS support")
    cors_origins: list[str] = Field(default_factory=lambda: ["*"], description="Allowed CORS origins")

    max_request_size: int = Field(default=1024 * 1024, description="Maximum request size in bytes")
    request_timeout: float = Field(default=30.0, description="Request timeout in seconds")

    enable_swagger: bool = Field(default=True, description="Enable Swagger/OpenAPI documentation")
    enable_redoc: bool = Field(default=True, description="Enable ReDoc documentation")

    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(default=60, description="Requests per minute limit")

    auth_enabled: bool = Field(default=True, description="Enable authentication")

    # Timeout configuration
    interaction_timeout: float = Field(default=55.0, description="Timeout for agent interactions in seconds")

    # Proxy configuration
    proxy_path: str = Field(
        default="", description="Base path when running behind reverse proxy (e.g., /api/sage-2wnuc8)"
    )
    agent_id: str = Field(default="", description="Agent ID when running in managed mode")

    def get_home_channel_id(self, host: str, port: int) -> str:
        """Get the home channel ID for this API adapter instance."""
        return f"api_{host}_{port}"

    def load_env_vars(self) -> None:
        """Load configuration from environment variables if present."""
        from ciris_engine.logic.config.env_utils import get_env_var

        env_host = get_env_var("CIRIS_API_HOST")
        if env_host:
            self.host = env_host

        env_port = get_env_var("CIRIS_API_PORT")
        if env_port:
            try:
                self.port = int(env_port)
            except ValueError:
                pass

        env_cors = get_env_var("CIRIS_API_CORS_ENABLED")
        if env_cors is not None:
            self.cors_enabled = env_cors.lower() in ("true", "1", "yes", "on")

        env_auth = get_env_var("CIRIS_API_AUTH_ENABLED")
        if env_auth is not None:
            self.auth_enabled = env_auth.lower() in ("true", "1", "yes", "on")

        env_timeout = get_env_var("CIRIS_API_INTERACTION_TIMEOUT")
        if env_timeout:
            try:
                self.interaction_timeout = float(env_timeout)
            except ValueError:
                pass

        env_cors_origins = get_env_var("CIRIS_API_CORS_ORIGINS")
        if env_cors_origins:
            try:
                import json

                self.cors_origins = json.loads(env_cors_origins)
            except (ValueError, json.JSONDecodeError):
                pass

        # Check for proxy/managed mode configuration
        env_agent_id = get_env_var("CIRIS_AGENT_ID")
        if env_agent_id:
            self.agent_id = env_agent_id
            # When agent ID is set, we're likely behind a proxy
            # Set the proxy path to the standard format
            self.proxy_path = f"/api/{env_agent_id}"

        # Allow explicit override of proxy path
        env_proxy_path = get_env_var("CIRIS_PROXY_PATH")
        if env_proxy_path:
            self.proxy_path = env_proxy_path
