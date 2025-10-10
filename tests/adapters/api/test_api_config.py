"""
API Adapter Configuration Tests

Tests environment variable loading and configuration handling
for the API adapter, including production bug scenarios.
"""

import os
from unittest.mock import patch

from ciris_engine.logic.adapters.api.config import APIAdapterConfig


class TestAPIConfig:
    """Test API adapter configuration handling."""

    def test_default_config_values(self):
        """Test default configuration values."""
        config = APIAdapterConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.cors_origins == ["*"]
        assert config.rate_limit_enabled is True  # Enabled by default in 1.3.1+
        assert config.rate_limit_per_minute == 60

    def test_env_var_loading(self):
        """Test that environment variables are loaded correctly."""
        with patch.dict(os.environ, {"CIRIS_API_HOST": "0.0.0.0", "CIRIS_API_PORT": "9090"}):
            config = APIAdapterConfig()
            config.load_env_vars()

            assert config.host == "0.0.0.0"
            assert config.port == 9090

    def test_env_var_partial_loading(self):
        """Test that only set environment variables are loaded."""
        # First ensure CIRIS_API_PORT is not set
        original_port = os.environ.pop("CIRIS_API_PORT", None)
        try:
            with patch.dict(
                os.environ,
                {
                    "CIRIS_API_HOST": "0.0.0.0"
                    # PORT not set, should keep default
                },
            ):
                config = APIAdapterConfig()
                config.load_env_vars()

                assert config.host == "0.0.0.0"
                assert config.port == 8080  # Default retained
        finally:
            # Restore original value if it existed
            if original_port is not None:
                os.environ["CIRIS_API_PORT"] = original_port

    def test_env_var_type_conversion(self):
        """Test that environment variables are converted to correct types."""
        with patch.dict(
            os.environ,
            {
                "CIRIS_API_PORT": "8888",  # String that should become int
                "CIRIS_API_CORS_ORIGINS": '["http://localhost:3000", "http://localhost:3001"]',  # JSON string
            },
        ):
            config = APIAdapterConfig()
            config.load_env_vars()

            assert config.port == 8888
            assert isinstance(config.port, int)
            assert config.cors_origins == ["http://localhost:3000", "http://localhost:3001"]

    def test_production_bug_scenario(self):
        """Test the production bug where env vars were overridden."""
        # This simulates the bug where main.py loads env vars but then
        # the adapter replaces the config with a new instance

        with patch.dict(os.environ, {"CIRIS_API_HOST": "0.0.0.0", "CIRIS_API_PORT": "8080"}):
            # Step 1: Create config and load env vars (what main.py does)
            config = APIAdapterConfig()
            config.load_env_vars()
            assert config.host == "0.0.0.0"

            # Step 2: Simulate passing config to adapter
            # Bug: adapter might create new config instead of using passed one
            new_config = APIAdapterConfig()  # Bug: doesn't call load_env_vars
            assert new_config.host == "127.0.0.1"  # Wrong! Should be 0.0.0.0

            # Fix: adapter should use passed config or call load_env_vars
            new_config.load_env_vars()
            assert new_config.host == "0.0.0.0"  # Correct

    def test_config_dict_serialization(self):
        """Test configuration dict conversion."""
        config = APIAdapterConfig(host="0.0.0.0", port=9000, cors_origins=["http://example.com"])

        # Convert to dict
        config_dict = config.model_dump()
        assert config_dict["host"] == "0.0.0.0"
        assert config_dict["port"] == 9000
        assert config_dict["cors_origins"] == ["http://example.com"]

        # Create from dict
        new_config = APIAdapterConfig(**config_dict)
        assert new_config.host == config.host
        assert new_config.port == config.port
        assert new_config.cors_origins == config.cors_origins

    def test_invalid_env_var_handling(self):
        """Test handling of invalid environment variable values."""
        with patch.dict(os.environ, {"CIRIS_API_PORT": "not-a-number", "CIRIS_API_CORS_ORIGINS": "not-valid-json"}):
            config = APIAdapterConfig()

            # Should handle gracefully, keeping defaults
            config.load_env_vars()
            assert config.port == 8080  # Default retained
            assert config.cors_origins == ["*"]  # Default retained

    def test_config_immutability_after_creation(self):
        """Test that config values are properly set and retained."""
        # Create config with specific values
        config = APIAdapterConfig(host="192.168.1.1", port=7777)

        # Load env vars that would change values
        with patch.dict(os.environ, {"CIRIS_API_HOST": "0.0.0.0", "CIRIS_API_PORT": "8080"}):
            # Before load_env_vars, should have original values
            assert config.host == "192.168.1.1"
            assert config.port == 7777

            # After load_env_vars, should have env values
            config.load_env_vars()
            assert config.host == "0.0.0.0"
            assert config.port == 8080
