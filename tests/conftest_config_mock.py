"""
Global configuration mock for tests that need database access.

This module provides a fixture that mocks the ServiceRegistry to return
a config service with EssentialConfig, preventing "No configuration available"
errors during testing.
"""

from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.config import EssentialConfig


@pytest.fixture(autouse=False)
def mock_config_service_registry(tmp_path):
    """
    Mock ServiceRegistry to provide config service with EssentialConfig.

    Use this fixture in tests that access the database but don't explicitly
    set up their own config service.
    """
    with patch("ciris_engine.logic.registries.base.ServiceRegistry") as mock_registry:
        mock_instance = MagicMock()
        mock_config_with_essential = MagicMock()
        mock_config_with_essential.essential_config = EssentialConfig(
            sqllite_db_path=str(tmp_path / "test.db"), archive_dir_path=str(tmp_path / "archive")
        )
        mock_instance.get_services_by_type.return_value = [mock_config_with_essential]
        mock_registry.return_value = mock_instance
        yield mock_instance


@pytest.fixture(autouse=False)
def mock_db_path(tmp_path):
    """
    Direct mock of get_sqlite_db_full_path for simpler tests.

    Mocks both the direct import path and the module import path to support
    different usage patterns in the codebase.
    """
    test_db_path = str(tmp_path / "test.db")

    # Patch both possible import paths
    with patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path", return_value=test_db_path) as mock1:
        with patch("ciris_engine.logic.config.get_sqlite_db_full_path", return_value=test_db_path) as mock2:
            yield test_db_path


@pytest.fixture(autouse=False)
def mock_runtime_db_setup(tmp_path):
    """
    Mock for runtime initialization tests that need database access control disabled.

    This is specifically for tests that create their own CIRISRuntime with EssentialConfig
    and handle their own database setup.
    """
    # Mock the database access check to always pass for runtime tests
    with patch("ciris_engine.logic.utils.directory_setup.ensure_database_exclusive_access") as mock_check:
        mock_check.return_value = None  # Always succeeds
        yield mock_check
