"""Configuration schema for CLI adapter."""

import getpass
import socket
from typing import Optional

from pydantic import BaseModel, Field


class CLIAdapterConfig(BaseModel):
    """Configuration for the CLI adapter."""

    interactive: bool = Field(default=True, description="Enable interactive CLI input")

    prompt_prefix: str = Field(default="CIRIS> ", description="CLI prompt prefix")
    enable_colors: bool = Field(default=True, description="Enable colored output")
    max_history_entries: int = Field(default=1000, description="Maximum command history entries")

    input_timeout_seconds: float = Field(default=30.0, description="Timeout for user input in seconds")
    multiline_mode: bool = Field(default=False, description="Enable multiline input mode")

    max_output_lines: int = Field(default=100, description="Maximum lines to display per response")
    word_wrap: bool = Field(default=True, description="Enable word wrapping for long lines")

    default_channel_id: Optional[str] = Field(
        default=None, description="Default channel ID for CLI messages"  # Will be set in get_home_channel_id()
    )

    enable_cli_tools: bool = Field(default=True, description="Enable CLI-specific tools")

    def get_home_channel_id(self) -> str:
        """Get the home channel ID for this CLI adapter instance.

        Uses a deterministic ID based on username and hostname so that
        users can see their conversation history across sessions.
        """
        if self.default_channel_id:
            return self.default_channel_id

        # Generate deterministic channel ID based on user and host
        try:
            username = getpass.getuser()
            hostname = socket.gethostname()
            # Create a deterministic ID that's consistent across sessions
            # but unique per user/host combination
            return f"cli_{username}_{hostname}".replace(" ", "_").replace(".", "_")
        except Exception:
            # Fallback to a simpler deterministic ID
            try:
                username = getpass.getuser()
                return f"cli_{username}_local"
            except Exception:
                return "cli_default"

    def load_env_vars(self) -> None:
        """Load configuration from environment variables if present."""
        from ciris_engine.logic.config.env_utils import get_env_var

        env_interactive = get_env_var("CIRIS_CLI_INTERACTIVE")
        if env_interactive is not None:
            self.interactive = env_interactive.lower() in ("true", "1", "yes", "on")

        env_colors = get_env_var("CIRIS_CLI_COLORS")
        if env_colors is not None:
            self.enable_colors = env_colors.lower() in ("true", "1", "yes", "on")

        env_channel = get_env_var("CIRIS_CLI_CHANNEL_ID")
        if env_channel:
            self.default_channel_id = env_channel

        env_prompt = get_env_var("CIRIS_CLI_PROMPT")
        if env_prompt:
            self.prompt_prefix = env_prompt
