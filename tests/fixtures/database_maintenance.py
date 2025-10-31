"""
Central fixtures for database maintenance service testing.

Provides comprehensive mock and real database maintenance service
for multi-occurrence and cleanup testing.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.services.infrastructure.database_maintenance.service import DatabaseMaintenanceService
from ciris_engine.schemas.runtime.enums import ServiceType


@pytest.fixture
def mock_time_service():
    """Create a mock time service for testing."""
    mock = MagicMock()
    # Use side_effect to return current time dynamically on each call
    mock.now.side_effect = lambda: datetime.now(timezone.utc)
    mock.now_iso.side_effect = lambda: datetime.now(timezone.utc).isoformat()
    return mock


@pytest.fixture
def mock_config_service():
    """Create a mock config service for testing."""
    mock = AsyncMock()
    mock.list_configs = AsyncMock(return_value={})
    mock.get_config = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def database_maintenance_service(mock_time_service, mock_config_service, tmp_path, clean_db):
    """
    Create a real DatabaseMaintenanceService for testing.

    Uses temporary directory for archives and real database operations.

    Args:
        mock_time_service: Mock time service fixture
        mock_config_service: Mock config service fixture
        tmp_path: Pytest's temporary directory fixture
        clean_db: Clean test database fixture

    Returns:
        DatabaseMaintenanceService: Configured maintenance service
    """
    archive_dir = tmp_path / "archive"
    archive_dir.mkdir(exist_ok=True)

    service = DatabaseMaintenanceService(
        time_service=mock_time_service,
        archive_dir_path=str(archive_dir),
        archive_older_than_hours=24,
        config_service=mock_config_service,
        db_path=clean_db,
    )

    return service


@pytest.fixture
def old_wakeup_task_data():
    """
    Provide sample old wakeup task data for cleanup testing.

    Returns:
        Dict: Old wakeup task with stale timestamp
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=10)  # 10 minutes old

    return {
        "task_id": "WAKEUP_SHARED_20251027",
        "description": "Wakeup ritual (shared across all occurrences)",
        "status": "active",
        "agent_occurrence_id": "__shared__",
        "parent_task_id": None,
        "created_at": old_time.isoformat(),
        "updated_at": old_time.isoformat(),
        "channel_id": "api",
    }


@pytest.fixture
def fresh_wakeup_task_data():
    """
    Provide sample fresh wakeup task data (should NOT be cleaned up).

    Returns:
        Dict: Fresh wakeup task with recent timestamp
    """
    now = datetime.now(timezone.utc)
    fresh_time = now - timedelta(seconds=30)  # 30 seconds old

    return {
        "task_id": "WAKEUP_SHARED_20251028",
        "description": "Wakeup ritual (shared across all occurrences)",
        "status": "active",
        "agent_occurrence_id": "__shared__",
        "parent_task_id": None,
        "created_at": fresh_time.isoformat(),
        "updated_at": fresh_time.isoformat(),
        "channel_id": "api",
    }


@pytest.fixture
def occurrence_specific_task_data():
    """
    Provide sample occurrence-specific task data.

    Returns:
        Dict: Task belonging to specific occurrence
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=10)

    return {
        "task_id": "VERIFY_IDENTITY_abc123",
        "description": "Verify identity step",
        "status": "active",
        "agent_occurrence_id": "occurrence_1",
        "parent_task_id": "WAKEUP_SHARED_20251027",
        "created_at": old_time.isoformat(),
        "updated_at": old_time.isoformat(),
        "channel_id": "api",
    }


@pytest.fixture
def stale_thought_data():
    """
    Provide sample stale thought data for cleanup testing.

    Returns:
        Dict: Stale thought with old timestamp
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=10)

    return {
        "thought_id": "thought_123",
        "source_task_id": "WAKEUP_SHARED_20251027",
        "agent_occurrence_id": "__shared__",
        "status": "pending",
        "created_at": old_time.isoformat(),
        "updated_at": old_time.isoformat(),
        "thought_type": "standard",
        "content": "Test thought content",
        "context": {
            "task_id": "WAKEUP_SHARED_20251027",
            "correlation_id": "test-correlation-stale",
            "round_number": 0,
            "depth": 0,
            "agent_occurrence_id": "__shared__",
        },
    }


@pytest.fixture
def old_shutdown_task_data():
    """
    Provide sample old shutdown task data for cleanup testing.

    Tests uppercase SHUTDOWN_ pattern (shared shutdown tasks use uppercase).

    Returns:
        Dict: Old shutdown task with stale timestamp
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=10)  # 10 minutes old

    return {
        "task_id": "SHUTDOWN_SHARED_20251027",
        "description": "System shutdown requested (shared across all occurrences)",
        "status": "active",
        "agent_occurrence_id": "__shared__",
        "parent_task_id": None,
        "created_at": old_time.isoformat(),
        "updated_at": old_time.isoformat(),
        "channel_id": "api",
        "priority": 10,
    }


@pytest.fixture
def multi_occurrence_cleanup_scenario():
    """
    Provide a complete multi-occurrence cleanup scenario.

    This includes:
    - Old shared wakeup task (should be cleaned)
    - Fresh shared wakeup task (should be preserved)
    - Occurrence-specific tasks (should use correct occurrence_id)
    - Stale thoughts (should be cleaned)

    Returns:
        Dict: Complete scenario data for testing
    """
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(minutes=10)
    fresh_time = now - timedelta(seconds=30)

    return {
        "tasks": [
            {
                "task_id": "WAKEUP_SHARED_OLD",
                "description": "Old wakeup (should clean)",
                "status": "active",
                "agent_occurrence_id": "__shared__",
                "parent_task_id": None,
                "created_at": old_time.isoformat(),
                "updated_at": old_time.isoformat(),
                "channel_id": "api",
            },
            {
                "task_id": "WAKEUP_SHARED_FRESH",
                "description": "Fresh wakeup (should preserve)",
                "status": "active",
                "agent_occurrence_id": "__shared__",
                "parent_task_id": None,
                "created_at": fresh_time.isoformat(),
                "updated_at": fresh_time.isoformat(),
                "channel_id": "api",
            },
            {
                "task_id": "VERIFY_IDENTITY_OCC1",
                "description": "Occurrence 1 identity",
                "status": "active",
                "agent_occurrence_id": "occurrence_1",
                "parent_task_id": "WAKEUP_SHARED_FRESH",
                "created_at": fresh_time.isoformat(),
                "updated_at": fresh_time.isoformat(),
                "channel_id": "api",
            },
            {
                "task_id": "VERIFY_IDENTITY_OCC2",
                "description": "Occurrence 2 identity",
                "status": "active",
                "agent_occurrence_id": "occurrence_2",
                "parent_task_id": "WAKEUP_SHARED_FRESH",
                "created_at": fresh_time.isoformat(),
                "updated_at": fresh_time.isoformat(),
                "channel_id": "api",
            },
        ],
        "thoughts": [
            {
                "thought_id": "thought_old_shared",
                "source_task_id": "WAKEUP_SHARED_OLD",
                "agent_occurrence_id": "__shared__",
                "status": "pending",
                "created_at": old_time.isoformat(),
                "updated_at": old_time.isoformat(),
                "thought_type": "standard",
                "content": "Old shared thought",
                "context": {
                    "task_id": "WAKEUP_SHARED_OLD",
                    "correlation_id": "test-correlation-1",
                    "round_number": 0,
                    "depth": 0,
                    "agent_occurrence_id": "__shared__",
                },
            },
            {
                "thought_id": "thought_occ1",
                "source_task_id": "VERIFY_IDENTITY_OCC1",
                "agent_occurrence_id": "occurrence_1",
                "status": "pending",
                "created_at": fresh_time.isoformat(),
                "updated_at": fresh_time.isoformat(),
                "thought_type": "standard",
                "content": "Occurrence 1 thought",
                "context": {
                    "task_id": "VERIFY_IDENTITY_OCC1",
                    "correlation_id": "test-correlation-2",
                    "round_number": 0,
                    "depth": 0,
                    "agent_occurrence_id": "occurrence_1",
                },
            },
        ],
        "expected_cleaned_tasks": ["WAKEUP_SHARED_OLD"],
        "expected_preserved_tasks": ["WAKEUP_SHARED_FRESH", "VERIFY_IDENTITY_OCC1", "VERIFY_IDENTITY_OCC2"],
        "expected_cleaned_thoughts": ["thought_old_shared"],
        "expected_preserved_thoughts": ["thought_occ1"],
    }
