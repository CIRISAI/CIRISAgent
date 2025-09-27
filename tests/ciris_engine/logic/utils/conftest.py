"""Shared fixtures for logic/utils tests."""

import logging
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


class MockTimeService:
    """Mock time service for testing."""

    def __init__(self, now_time=None):
        self._now = now_time or datetime(2025, 9, 7, 18, 0, 0)

    def now(self):
        return self._now

    def now_iso(self):
        return self._now.isoformat()

    def strftime(self, format_str):
        return self._now.strftime(format_str)


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    return MockTimeService()


@pytest.fixture
def mock_graph_audit_service():
    """Create mock graph audit service."""
    service = MagicMock()
    service._memory_bus = AsyncMock()
    service._memory_bus.memorize.return_value = MemoryOpResult(status=MemoryOpStatus.OK)
    return service


@pytest.fixture
def log_dir(tmp_path):
    """Create temporary log directory."""
    d = tmp_path / "logs"
    d.mkdir()
    return d


@pytest.fixture
def root_logger():
    """Fixture to get the root logger and restore it after test."""
    logger = logging.getLogger()
    original_handlers = logger.handlers[:]
    original_level = logger.level
    yield logger
    logger.handlers = original_handlers
    logger.setLevel(original_level)


@pytest.fixture
def specific_logger():
    """Fixture for a named logger with cleanup."""
    logger = logging.getLogger("test_specific_logger")
    original_handlers = logger.handlers[:]
    original_level = logger.level
    original_propagate = logger.propagate
    logger.handlers = []
    logger.propagate = False  # Prevent logs from going to root
    yield logger
    logger.handlers = original_handlers
    logger.setLevel(original_level)
    logger.propagate = original_propagate


@pytest.fixture
def clean_logger_config():
    """Fixture that ensures clean logger configuration."""
    # Store original logger configuration
    loggers_to_restore = {}
    for name in ["ciris_engine.logic.utils.incident_capture_handler"]:
        logger = logging.getLogger(name)
        loggers_to_restore[name] = {
            "handlers": logger.handlers[:],
            "level": logger.level,
            "propagate": logger.propagate,
        }

    yield

    # Restore original configuration
    for name, config in loggers_to_restore.items():
        logger = logging.getLogger(name)
        logger.handlers = config["handlers"]
        logger.setLevel(config["level"])
        logger.propagate = config["propagate"]
