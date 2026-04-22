"""
Reddit ConfigurableAdapterProtocol implementation.

Provides interactive configuration workflow for Reddit integration:
1. Input - Collect Reddit OAuth credentials
2. Input - Collect bot account credentials
3. Select - Choose subreddits to monitor (optional)
4. Select - Choose post types to watch (optional)
5. Confirm - Review and apply configuration

Reddit uses OAuth2 for app authentication, but bot accounts require
username/password credentials for the password grant flow.

Reddit API Requirements:
- Client ID and Client Secret (from https://www.reddit.com/prefs/apps)
- Bot account username and password
- Unique User-Agent string (required by Reddit API)

SAFE DOMAIN: Community outreach only. Medical and political campaigning are prohibited.
"""

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)


class RedditConfigurableAdapter:
    """Reddit configurable adapter for CIRIS.

    Implements ConfigurableAdapterProtocol for Reddit using the OAuth2
    password grant flow for bot accounts.

    Configuration Flow:
    1. User provides OAuth app credentials (client_id, client_secret)
    2. User provides bot account credentials (username, password)
    3. User provides User-Agent string (required by Reddit)
    4. User optionally selects subreddits to monitor
    5. User optionally selects post types to watch
    6. Configuration is validated by testing authentication
    7. Environment variables are set for the adapter

    Usage via API:
        1. POST /adapters/reddit/configure/start
        2. POST /adapters/configure/{session_id}/step (client credentials)
        3. POST /adapters/configure/{session_id}/step (bot account)
        4. POST /adapters/configure/{session_id}/step (user agent)
        5. POST /adapters/configure/{session_id}/step (select subreddits - optional)
        6. POST /adapters/configure/{session_id}/step (select post types - optional)
        7. POST /adapters/configure/{session_id}/complete
    """

    # Reddit OAuth2 token endpoint
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"

    # Default User-Agent
    DEFAULT_USER_AGENT = "CIRIS-RedditAdapter/1.0 (+https://ciris.ai)"

    # Available post types to monitor
    POST_TYPES = {
        "submissions": {
            "label": "Submissions (Posts)",
            "description": "Monitor new submissions/posts in subreddits",
            "default": True,
        },
        "comments": {
            "label": "Comments",
            "description": "Monitor new comments in subreddits",
            "default": True,
        },
        "both": {
            "label": "Both Submissions and Comments",
            "description": "Monitor both new posts and comments",
            "default": False,
        },
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the Reddit configurable adapter.

        Args:
            config: Optional existing configuration
        """
        self.config = config or {}
        self._applied_config: Optional[Dict[str, Any]] = None

        logger.info("RedditConfigurableAdapter initialized")

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get options for a selection step.

        Args:
            step_id: ID of the configuration step
            context: Current configuration context

        Returns:
            List of available options
        """
        logger.info(f"Getting config options for step: {step_id}")

        if step_id == "select_subreddits":
            # Return popular subreddits + ability to enter custom
            return [
                {
                    "id": "ciris",
                    "label": "r/ciris",
                    "description": "CIRIS community subreddit",
                    "metadata": {"default": True},
                },
                {
                    "id": "test",
                    "label": "r/test",
                    "description": "Testing subreddit",
                    "metadata": {"default": False},
                },
                {
                    "id": "custom",
                    "label": "Custom Subreddit",
                    "description": "Enter a custom subreddit name",
                    "metadata": {"requires_input": True},
                },
            ]

        elif step_id == "select_post_types":
            # Return available post types
            return [
                {
                    "id": post_type_id,
                    "label": post_type["label"],
                    "description": post_type["description"],
                    "metadata": {"default": post_type["default"]},
                }
                for post_type_id, post_type in self.POST_TYPES.items()
            ]

        return []

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate Reddit configuration before applying.

        Performs:
        - Required field validation
        - Credential validation via test authentication
        - User-Agent format validation

        Args:
            config: Complete configuration to validate

        Returns:
            (is_valid, error_message) tuple
        """
        logger.info("Validating Reddit configuration")

        if not config:
            return False, "Configuration is empty"

        # Check required fields
        client_id = config.get("client_id")
        if not client_id:
            return False, "client_id is required (get from https://www.reddit.com/prefs/apps)"

        client_secret = config.get("client_secret")
        if not client_secret:
            return False, "client_secret is required (get from https://www.reddit.com/prefs/apps)"

        username = config.get("username")
        if not username:
            return False, "username is required (your Reddit bot account username)"

        password = config.get("password")
        if not password:
            return False, "password is required (your Reddit bot account password)"

        user_agent = config.get("user_agent", self.DEFAULT_USER_AGENT)
        if not user_agent or len(user_agent) < 10:
            return False, "user_agent must be at least 10 characters long"

        # Test authentication with Reddit
        try:
            auth = (client_id, client_secret)
            data = {
                "grant_type": "password",
                "username": username,
                "password": password,
            }
            headers = {"User-Agent": user_agent}

            async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, read=20.0)) as client:
                response = await client.post(self.TOKEN_URL, data=data, auth=auth, headers=headers)

            if response.status_code >= 300:
                error_text = response.text
                logger.error(f"Reddit auth failed: {response.status_code} - {error_text}")
                return False, f"Reddit authentication failed: {error_text}"

            token_data = response.json()
            if not isinstance(token_data, dict):
                return False, "Invalid token response from Reddit"

            access_token = token_data.get("access_token")
            if not access_token or access_token.strip() == "":
                error_msg = token_data.get("error", "Unknown error")
                error_desc = token_data.get("error_description", "No access_token in response")
                logger.error(
                    f"Reddit OAuth failed - likely suspended account or invalid credentials. "
                    f"Error: {error_msg}, Description: {error_desc}"
                )
                return False, (
                    f"Reddit authentication failed: {error_msg} - {error_desc}. "
                    "This may indicate a suspended Reddit account or invalid credentials."
                )

            logger.info("Reddit authentication test successful")

        except httpx.HTTPError as e:
            return False, f"Reddit connection error: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"

        # Validate subreddit if provided
        subreddit = config.get("subreddit")
        if subreddit:
            # Basic validation - subreddit names are alphanumeric + underscores
            if not subreddit.replace("_", "").isalnum():
                return False, f"Invalid subreddit name: {subreddit}"

        logger.info("Reddit configuration validated successfully")
        return True, None

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Apply the configuration.

        Stores configuration and sets up environment for the service.

        Args:
            config: Validated configuration to apply

        Returns:
            True if applied successfully
        """
        logger.info("Applying Reddit configuration")

        self._applied_config = config.copy()

        # Set environment variables for the Reddit adapter
        if config.get("client_id"):
            os.environ["CIRIS_REDDIT_CLIENT_ID"] = config["client_id"]
        if config.get("client_secret"):
            os.environ["CIRIS_REDDIT_CLIENT_SECRET"] = config["client_secret"]
        if config.get("username"):
            os.environ["CIRIS_REDDIT_USERNAME"] = config["username"]
        if config.get("password"):
            os.environ["CIRIS_REDDIT_PASSWORD"] = config["password"]
        if config.get("user_agent"):
            os.environ["CIRIS_REDDIT_USER_AGENT"] = config["user_agent"]
        if config.get("subreddit"):
            os.environ["CIRIS_REDDIT_SUBREDDIT"] = config["subreddit"]

        # Log sanitized config
        safe_config = {k: ("***" if k in ("password", "client_secret") else v) for k, v in config.items()}
        logger.info(f"Reddit configuration applied: {safe_config}")

        return True

    def get_applied_config(self) -> Optional[Dict[str, Any]]:
        """Get the currently applied configuration.

        Returns:
            Applied configuration or None if not configured
        """
        return self._applied_config
