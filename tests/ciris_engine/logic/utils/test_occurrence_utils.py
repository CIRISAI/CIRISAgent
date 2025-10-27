"""
Unit tests for occurrence discovery and coordination utilities.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from ciris_engine.logic.persistence.db import get_db_connection, initialize_database
from ciris_engine.logic.utils.occurrence_utils import (
    discover_active_occurrences,
    get_current_occurrence_id,
    get_occurrence_count,
    get_occurrence_info,
    is_multi_occurrence_deployment,
)
from ciris_engine.schemas.runtime.enums import TaskStatus


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    initialize_database(db_path)
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


def create_task_for_occurrence(
    occurrence_id: str, db_path: str, minutes_ago: int = 0
) -> None:
    """Helper to create a task for a given occurrence."""
    now = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    sql = """
        INSERT INTO tasks
        (task_id, channel_id, agent_occurrence_id, description, status, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_db_connection(db_path) as conn:
        conn.execute(
            sql,
            (
                f"test_{occurrence_id}_{minutes_ago}",
                "test_channel",
                occurrence_id,
                "Test task",
                TaskStatus.PENDING.value,
                5,
                now.isoformat(),
                now.isoformat(),
            ),
        )
        conn.commit()


def test_get_occurrence_count_from_env():
    """Test getting occurrence count from environment variable."""
    with patch.dict(os.environ, {"AGENT_OCCURRENCE_COUNT": "9"}):
        assert get_occurrence_count() == 9


def test_get_occurrence_count_invalid_env():
    """Test handling invalid environment variable value."""
    with patch.dict(os.environ, {"AGENT_OCCURRENCE_COUNT": "invalid"}):
        # Should fall back to default of 1
        assert get_occurrence_count() == 1


def test_get_occurrence_count_from_database(temp_db: str):
    """Test discovering occurrence count from database activity."""
    # Create tasks for 3 different occurrences
    create_task_for_occurrence("occurrence-1", temp_db, minutes_ago=5)
    create_task_for_occurrence("occurrence-2", temp_db, minutes_ago=3)
    create_task_for_occurrence("occurrence-3", temp_db, minutes_ago=1)

    with patch.dict(os.environ, {}, clear=True):
        # Should discover 3 occurrences from database
        count = get_occurrence_count(db_path=temp_db)
        assert count == 3


def test_get_occurrence_count_no_data():
    """Test occurrence count defaults to 1 when no data available."""
    with patch.dict(os.environ, {}, clear=True):
        assert get_occurrence_count() == 1


def test_discover_active_occurrences_multiple(temp_db: str):
    """Test discovering multiple active occurrences."""
    create_task_for_occurrence("occurrence-1", temp_db, minutes_ago=2)
    create_task_for_occurrence("occurrence-2", temp_db, minutes_ago=1)
    create_task_for_occurrence("default", temp_db, minutes_ago=0)

    discovered = discover_active_occurrences(within_minutes=10, db_path=temp_db)

    assert len(discovered) == 3
    assert "occurrence-1" in discovered
    assert "occurrence-2" in discovered
    assert "default" in discovered
    # Should be sorted alphabetically
    assert discovered == sorted(discovered)


def test_discover_active_occurrences_excludes_shared(temp_db: str):
    """Test that shared tasks are excluded from occurrence discovery."""
    create_task_for_occurrence("occurrence-1", temp_db, minutes_ago=1)
    create_task_for_occurrence("__shared__", temp_db, minutes_ago=0)

    discovered = discover_active_occurrences(within_minutes=10, db_path=temp_db)

    assert len(discovered) == 1
    assert "occurrence-1" in discovered
    assert "__shared__" not in discovered


def test_discover_active_occurrences_time_window(temp_db: str):
    """Test that time window correctly filters old occurrences."""
    # Recent activity
    create_task_for_occurrence("occurrence-1", temp_db, minutes_ago=5)
    # Old activity (outside window)
    create_task_for_occurrence("occurrence-2", temp_db, minutes_ago=15)

    discovered = discover_active_occurrences(within_minutes=10, db_path=temp_db)

    assert len(discovered) == 1
    assert "occurrence-1" in discovered
    assert "occurrence-2" not in discovered


def test_discover_active_occurrences_empty(temp_db: str):
    """Test discovering occurrences when database is empty."""
    discovered = discover_active_occurrences(within_minutes=10, db_path=temp_db)
    assert discovered == []


def test_get_current_occurrence_id_from_env():
    """Test getting occurrence ID from environment."""
    with patch.dict(os.environ, {"AGENT_OCCURRENCE_ID": "occurrence-42"}):
        assert get_current_occurrence_id() == "occurrence-42"


def test_get_current_occurrence_id_default():
    """Test getting default occurrence ID."""
    with patch.dict(os.environ, {}, clear=True):
        assert get_current_occurrence_id() == "default"


def test_is_multi_occurrence_deployment_true():
    """Test detecting multi-occurrence deployment."""
    with patch.dict(os.environ, {"AGENT_OCCURRENCE_COUNT": "5"}):
        assert is_multi_occurrence_deployment() is True


def test_is_multi_occurrence_deployment_false():
    """Test detecting single occurrence deployment."""
    with patch.dict(os.environ, {"AGENT_OCCURRENCE_COUNT": "1"}):
        assert is_multi_occurrence_deployment() is False


def test_is_multi_occurrence_deployment_default():
    """Test multi-occurrence detection with no environment variable."""
    with patch.dict(os.environ, {}, clear=True):
        # Default is single occurrence
        assert is_multi_occurrence_deployment() is False


def test_get_occurrence_info_complete(temp_db: str):
    """Test getting complete occurrence information."""
    # Create some database activity
    create_task_for_occurrence("occurrence-1", temp_db, minutes_ago=1)
    create_task_for_occurrence("occurrence-2", temp_db, minutes_ago=2)

    with patch.dict(os.environ, {"AGENT_OCCURRENCE_ID": "occurrence-1", "AGENT_OCCURRENCE_COUNT": "2"}):
        info = get_occurrence_info(db_path=temp_db)

        assert info["occurrence_id"] == "occurrence-1"
        assert info["occurrence_count"] == 2
        assert info["is_multi_occurrence"] is True
        assert "occurrence-1" in info["discovered_occurrences"]
        assert "occurrence-2" in info["discovered_occurrences"]
        assert info["discovery_source"] == "environment"


def test_get_occurrence_info_database_fallback(temp_db: str):
    """Test occurrence info falling back to database discovery."""
    create_task_for_occurrence("occurrence-1", temp_db, minutes_ago=1)

    with patch.dict(os.environ, {}, clear=True):
        info = get_occurrence_info()

        assert info["occurrence_id"] == "default"
        assert info["occurrence_count"] == 1  # Discovered from database
        assert info["is_multi_occurrence"] is False
        assert info["discovery_source"] == "database"


def test_get_occurrence_info_minimal():
    """Test occurrence info with no additional data."""
    with patch.dict(os.environ, {}, clear=True):
        info = get_occurrence_info()

        assert info["occurrence_id"] == "default"
        assert info["occurrence_count"] == 1
        assert info["is_multi_occurrence"] is False
        assert isinstance(info["discovered_occurrences"], list)
        assert info["discovery_source"] == "database"
