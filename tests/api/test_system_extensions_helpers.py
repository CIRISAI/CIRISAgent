"""Comprehensive tests for system_extensions.py helper functions."""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.adapters.api.routes.system_extensions import (
    _batch_fetch_task_channel_ids,
    _determine_user_role,
    _filter_events_by_channel_access,
    _get_latest_step_data,
    _get_pipeline_controller,
    _get_pipeline_state,
    _get_processing_metrics,
    _get_user_allowed_channel_ids,
)


class TestPipelineHelpers:
    """Test pipeline extraction helper functions."""

    def test_get_pipeline_controller_success(self):
        """Test successful pipeline controller extraction."""
        mock_controller = Mock()
        runtime = Mock(pipeline_controller=mock_controller)

        result = _get_pipeline_controller(runtime)

        assert result == mock_controller

    def test_get_pipeline_controller_no_runtime(self):
        """Test pipeline controller extraction with no runtime."""
        result = _get_pipeline_controller(None)
        assert result is None

    def test_get_pipeline_controller_no_attribute(self):
        """Test pipeline controller extraction when attribute missing."""
        runtime = Mock(spec=[])  # No pipeline_controller attribute
        result = _get_pipeline_controller(runtime)
        assert result is None

    def test_get_pipeline_state_success(self):
        """Test successful pipeline state retrieval."""
        mock_state = {"is_paused": True, "current_round": 5}
        controller = Mock()
        controller.get_current_state = Mock(return_value=mock_state)

        result = _get_pipeline_state(controller)

        assert result == mock_state
        controller.get_current_state.assert_called_once()

    def test_get_pipeline_state_no_controller(self):
        """Test pipeline state with no controller."""
        result = _get_pipeline_state(None)
        assert result is None

    def test_get_pipeline_state_exception(self):
        """Test pipeline state handles exceptions."""
        controller = Mock()
        controller.get_current_state = Mock(side_effect=Exception("Error"))

        result = _get_pipeline_state(controller)

        assert result is None

    def test_get_latest_step_data_success(self):
        """Test successful step data extraction."""
        mock_step_result = Mock()
        mock_step_result.step_point = "PERFORM_DMAS"
        mock_step_result.model_dump = Mock(return_value={"step": "data"})

        controller = Mock()
        controller.get_latest_step_result = Mock(return_value=mock_step_result)

        step_point, step_result = _get_latest_step_data(controller)

        assert step_point == "PERFORM_DMAS"
        assert step_result == {"step": "data"}

    def test_get_latest_step_data_no_model_dump(self):
        """Test step data extraction falls back to dict()."""
        mock_step_result = MagicMock()
        mock_step_result.step_point = "BUILD_CONTEXT"
        # Remove model_dump so it falls back to dict()
        delattr(mock_step_result, "model_dump")
        # Make it dict-able
        mock_step_result.__iter__ = MagicMock(return_value=iter([("key", "value")]))

        controller = Mock()
        controller.get_latest_step_result = Mock(return_value=mock_step_result)

        step_point, step_result = _get_latest_step_data(controller)

        assert step_point == "BUILD_CONTEXT"
        assert isinstance(step_result, dict)

    def test_get_latest_step_data_no_result(self):
        """Test step data extraction when no result available."""
        controller = Mock()
        controller.get_latest_step_result = Mock(return_value=None)

        step_point, step_result = _get_latest_step_data(controller)

        assert step_point is None
        assert step_result is None

    def test_get_latest_step_data_exception(self):
        """Test step data handles exceptions."""
        controller = Mock()
        controller.get_latest_step_result = Mock(side_effect=Exception("Error"))

        step_point, step_result = _get_latest_step_data(controller)

        assert step_point is None
        assert step_result is None

    def test_get_processing_metrics_success(self):
        """Test successful metrics extraction."""
        metrics = {"total_processing_time_ms": 1250.0, "tokens_used": 150}
        controller = Mock()
        controller.get_processing_metrics = Mock(return_value=metrics)

        time_ms, tokens = _get_processing_metrics(controller)

        assert time_ms == 1250.0
        assert tokens == 150

    def test_get_processing_metrics_no_tokens(self):
        """Test metrics extraction with missing tokens."""
        metrics = {"total_processing_time_ms": 500.0}
        controller = Mock()
        controller.get_processing_metrics = Mock(return_value=metrics)

        time_ms, tokens = _get_processing_metrics(controller)

        assert time_ms == 500.0
        assert tokens is None

    def test_get_processing_metrics_no_metrics(self):
        """Test metrics extraction when no metrics available."""
        controller = Mock()
        controller.get_processing_metrics = Mock(return_value=None)

        time_ms, tokens = _get_processing_metrics(controller)

        assert time_ms == 0.0
        assert tokens is None

    def test_get_processing_metrics_exception(self):
        """Test metrics handles exceptions."""
        controller = Mock()
        controller.get_processing_metrics = Mock(side_effect=Exception("Error"))

        time_ms, tokens = _get_processing_metrics(controller)

        assert time_ms == 0.0
        assert tokens is None


class TestUserRoleHelpers:
    """Test user role and authorization helper functions."""

    def test_determine_user_role_enum(self):
        """Test role determination with UserRole enum."""
        from ciris_engine.schemas.api.auth import UserRole

        current_user = {"role": UserRole.ADMIN}
        result = _determine_user_role(current_user)

        assert result == UserRole.ADMIN

    def test_determine_user_role_string(self):
        """Test role determination with string role."""
        current_user = {"role": "ADMIN"}  # Must be uppercase to match enum
        result = _determine_user_role(current_user)

        from ciris_engine.schemas.api.auth import UserRole

        assert result == UserRole.ADMIN

    def test_determine_user_role_invalid_string(self):
        """Test role determination with invalid string defaults to OBSERVER."""
        current_user = {"role": "invalid_role"}
        result = _determine_user_role(current_user)

        from ciris_engine.schemas.api.auth import UserRole

        assert result == UserRole.OBSERVER

    def test_determine_user_role_missing(self):
        """Test role determination with missing role defaults to OBSERVER."""
        current_user = {}
        result = _determine_user_role(current_user)

        from ciris_engine.schemas.api.auth import UserRole

        assert result == UserRole.OBSERVER

    @pytest.mark.asyncio
    async def test_get_user_allowed_channel_ids_no_oauth(self):
        """Test channel IDs with no OAuth links."""
        auth_service = Mock()
        mock_db = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn.execute_fetchall = AsyncMock(return_value=[])
        mock_db.connection = AsyncMock(return_value=mock_conn)
        auth_service.db_manager = mock_db

        result = await _get_user_allowed_channel_ids(auth_service, "user123")

        assert result == {"user123"}

    @pytest.mark.asyncio
    async def test_get_user_allowed_channel_ids_with_oauth(self):
        """Test channel IDs with OAuth links."""
        from unittest.mock import MagicMock

        auth_service = Mock()
        mock_conn = MagicMock()
        mock_conn.execute_fetchall = AsyncMock(
            return_value=[
                ("discord", "discord123"),
                ("google", "google456"),
            ]
        )
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_db = Mock()
        mock_db.connection = Mock(return_value=mock_conn)
        auth_service.db_manager = mock_db

        result = await _get_user_allowed_channel_ids(auth_service, "user123")

        expected = {"user123", "discord:discord123", "discord123", "google:google456", "google456"}
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_user_allowed_channel_ids_exception(self):
        """Test channel IDs handles exceptions gracefully."""
        auth_service = Mock()
        mock_db = AsyncMock()
        mock_db.connection = AsyncMock(side_effect=Exception("DB Error"))
        auth_service.db_manager = mock_db

        result = await _get_user_allowed_channel_ids(auth_service, "user123")

        # Should still return user_id even on error
        assert result == {"user123"}

    @pytest.mark.asyncio
    async def test_batch_fetch_task_channel_ids_success(self):
        """Test batch fetching task channel IDs."""
        from unittest.mock import MagicMock

        auth_service = Mock()
        mock_conn = MagicMock()
        mock_conn.execute_fetchall = AsyncMock(
            return_value=[
                ("task1", "channel1"),
                ("task2", "channel2"),
                ("task3", "channel1"),
            ]
        )
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_db = Mock()
        mock_db.connection = Mock(return_value=mock_conn)
        auth_service.db_manager = mock_db

        result = await _batch_fetch_task_channel_ids(auth_service, ["task1", "task2", "task3"])

        assert result == {"task1": "channel1", "task2": "channel2", "task3": "channel1"}

    @pytest.mark.asyncio
    async def test_batch_fetch_task_channel_ids_empty(self):
        """Test batch fetching with empty task list."""
        auth_service = Mock()

        result = await _batch_fetch_task_channel_ids(auth_service, [])

        assert result == {}

    @pytest.mark.asyncio
    async def test_batch_fetch_task_channel_ids_exception(self):
        """Test batch fetching handles exceptions."""
        auth_service = Mock()
        mock_db = AsyncMock()
        mock_db.connection = AsyncMock(side_effect=Exception("DB Error"))
        auth_service.db_manager = mock_db

        result = await _batch_fetch_task_channel_ids(auth_service, ["task1"])

        assert result == {}

    def test_filter_events_by_channel_access_allowed(self):
        """Test event filtering allows authorized events."""
        events = [
            {"task_id": "task1", "data": "event1"},
            {"task_id": "task2", "data": "event2"},
            {"task_id": "task3", "data": "event3"},
        ]
        allowed_channels = {"channel1", "channel2"}
        task_cache = {"task1": "channel1", "task2": "channel2", "task3": "channel3"}

        result = _filter_events_by_channel_access(events, allowed_channels, task_cache)

        assert len(result) == 2
        assert result[0]["task_id"] == "task1"
        assert result[1]["task_id"] == "task2"

    def test_filter_events_by_channel_access_no_task_id(self):
        """Test event filtering skips events without task_id."""
        events = [
            {"task_id": "task1", "data": "event1"},
            {"data": "system_event"},  # No task_id
        ]
        allowed_channels = {"channel1"}
        task_cache = {"task1": "channel1"}

        result = _filter_events_by_channel_access(events, allowed_channels, task_cache)

        assert len(result) == 1
        assert result[0]["task_id"] == "task1"

    def test_filter_events_by_channel_access_uncached_task(self):
        """Test event filtering skips uncached tasks."""
        events = [
            {"task_id": "task1", "data": "event1"},
            {"task_id": "task_unknown", "data": "event2"},
        ]
        allowed_channels = {"channel1"}
        task_cache = {"task1": "channel1"}  # task_unknown not in cache

        result = _filter_events_by_channel_access(events, allowed_channels, task_cache)

        assert len(result) == 1
        assert result[0]["task_id"] == "task1"

    def test_filter_events_by_channel_access_all_denied(self):
        """Test event filtering returns empty when all denied."""
        events = [
            {"task_id": "task1", "data": "event1"},
            {"task_id": "task2", "data": "event2"},
        ]
        allowed_channels = {"channel_other"}
        task_cache = {"task1": "channel1", "task2": "channel2"}

        result = _filter_events_by_channel_access(events, allowed_channels, task_cache)

        assert len(result) == 0


class TestEdgeCasesAndCoverage:
    """Edge case tests to increase coverage to 80%+."""

    def test_get_processing_metrics_partial_data(self):
        """Test metrics with only partial data."""
        metrics = {}  # Empty metrics dict
        controller = Mock()
        controller.get_processing_metrics = Mock(return_value=metrics)

        time_ms, tokens = _get_processing_metrics(controller)

        assert time_ms == 0.0
        assert tokens is None

    def test_filter_events_empty_list(self):
        """Test filtering with empty event list."""
        result = _filter_events_by_channel_access([], {"channel1"}, {})
        assert result == []

    def test_filter_events_empty_cache_and_channels(self):
        """Test filtering with no cache or allowed channels."""
        events = [
            {"task_id": "task1", "data": "event1"},
        ]
        result = _filter_events_by_channel_access(events, set(), {})
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_batch_fetch_none_results(self):
        """Test batch fetch when query returns None."""
        from unittest.mock import MagicMock

        auth_service = Mock()
        mock_conn = MagicMock()
        mock_conn.execute_fetchall = AsyncMock(return_value=None)
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_db = Mock()
        mock_db.connection = Mock(return_value=mock_conn)
        auth_service.db_manager = mock_db

        # Should handle None gracefully
        result = await _batch_fetch_task_channel_ids(auth_service, ["task1"])

        # Function should handle this gracefully
        assert isinstance(result, dict)
