"""
Tests for auth configuration loading.
"""

import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

from ciris_manager.api.auth import load_oauth_config


class TestAuthConfig:
    """Test auth configuration loading."""
    
    def test_load_oauth_config_from_file(self):
        """Test loading OAuth config from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create config file
            config_dir = Path(tmpdir) / "shared/oauth"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "google_oauth_manager.json"
            
            config_data = {
                "client_id": "file-client-id",
                "client_secret": "file-client-secret"
            }
            config_file.write_text(json.dumps(config_data))
            
            # Mock home directory
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch('ciris_manager.api.auth.init_auth_service') as mock_init:
                    result = load_oauth_config()
                    
                    assert result is True
                    mock_init.assert_called_once_with(
                        google_client_id="file-client-id",
                        google_client_secret="file-client-secret"
                    )
    
    def test_load_oauth_config_file_error(self):
        """Test loading OAuth config with file error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create invalid config file
            config_dir = Path(tmpdir) / "shared/oauth"
            config_dir.mkdir(parents=True)
            config_file = config_dir / "google_oauth_manager.json"
            config_file.write_text("invalid json")
            
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch('ciris_manager.api.auth.init_auth_service') as mock_init:
                    result = load_oauth_config()
                    
                    # Should fall back to env vars
                    assert result is False
                    mock_init.assert_not_called()
    
    def test_load_oauth_config_from_env(self):
        """Test loading OAuth config from environment variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No config file
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch.dict('os.environ', {
                    'GOOGLE_CLIENT_ID': 'env-client-id',
                    'GOOGLE_CLIENT_SECRET': 'env-client-secret'
                }):
                    with patch('ciris_manager.api.auth.init_auth_service') as mock_init:
                        result = load_oauth_config()
                        
                        assert result is True
                        mock_init.assert_called_once_with(
                            google_client_id="env-client-id",
                            google_client_secret="env-client-secret"
                        )
    
    def test_load_oauth_config_no_credentials(self):
        """Test loading OAuth config without any credentials."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No config file and no env vars
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                with patch.dict('os.environ', {}, clear=True):
                    with patch('ciris_manager.api.auth.init_auth_service') as mock_init:
                        result = load_oauth_config()
                        
                        assert result is False
                        mock_init.assert_not_called()
    
    def test_load_oauth_config_partial_env(self):
        """Test loading OAuth config with partial environment variables."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('pathlib.Path.home', return_value=Path(tmpdir)):
                # Only client ID, no secret
                with patch.dict('os.environ', {
                    'GOOGLE_CLIENT_ID': 'env-client-id'
                }):
                    with patch('ciris_manager.api.auth.init_auth_service') as mock_init:
                        result = load_oauth_config()
                        
                        assert result is False
                        mock_init.assert_not_called()