"""Unit tests for RedditObserver agent_occurrence_id propagation.

Tests verify that RedditObserver correctly propagates agent_occurrence_id
through the initialization chain to ensure tasks/thoughts are created with
the correct occurrence_id in multi-occurrence deployments.

P0 Fix: https://github.com/CIRISAI/CIRISAgent/pull/467
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_modular_services.reddit.observer import RedditObserver
from ciris_modular_services.reddit.schemas import RedditCredentials
from ciris_modular_services.reddit.service import RedditCommunicationService


class TestRedditObserverOccurrenceID:
    """Test RedditObserver occurrence_id propagation."""

    @pytest.fixture
    def mock_credentials(self):
        """Mock Reddit credentials."""
        return RedditCredentials(
            client_id="test_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            user_agent="test_agent",
            subreddit="ciris",
        )

    @pytest.fixture
    def mock_bus_manager(self):
        """Mock BusManager."""
        mock = MagicMock()
        mock.get_bus = MagicMock(return_value=None)
        return mock

    @pytest.fixture
    def mock_memory_service(self):
        """Mock memory service."""
        return MagicMock()

    def test_observer_default_occurrence_id(self, mock_credentials, mock_bus_manager, mock_memory_service):
        """Test that RedditObserver defaults to 'default' occurrence_id when not specified."""
        observer = RedditObserver(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
        )

        # Verify the observer has the default occurrence_id
        assert observer.agent_occurrence_id == "default"

    def test_observer_custom_occurrence_id(self, mock_credentials, mock_bus_manager, mock_memory_service):
        """Test that RedditObserver accepts and stores custom occurrence_id."""
        observer = RedditObserver(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            agent_occurrence_id="003",
        )

        # Verify the observer has the custom occurrence_id
        assert observer.agent_occurrence_id == "003"

    def test_observer_occurrence_id_propagation_to_base(self, mock_credentials, mock_bus_manager, mock_memory_service):
        """Test that occurrence_id is passed to BaseObserver.__init__()."""
        with patch("ciris_modular_services.reddit.observer.BaseObserver.__init__") as mock_base_init:
            mock_base_init.return_value = None

            observer = RedditObserver(
                credentials=mock_credentials,
                bus_manager=mock_bus_manager,
                memory_service=mock_memory_service,
                agent_occurrence_id="test_occurrence",
            )

            # Verify BaseObserver.__init__ was called with agent_occurrence_id
            mock_base_init.assert_called_once()
            call_kwargs = mock_base_init.call_args[1]
            assert "agent_occurrence_id" in call_kwargs
            assert call_kwargs["agent_occurrence_id"] == "test_occurrence"

    def test_communication_service_default_occurrence_id(self, mock_credentials):
        """Test that RedditCommunicationService defaults to 'default' occurrence_id."""
        service = RedditCommunicationService(
            credentials=mock_credentials,
        )

        # Verify the service has the default occurrence_id
        assert service._agent_occurrence_id == "default"

    def test_communication_service_custom_occurrence_id(self, mock_credentials):
        """Test that RedditCommunicationService accepts custom occurrence_id."""
        service = RedditCommunicationService(
            credentials=mock_credentials,
            agent_occurrence_id="002",
        )

        # Verify the service has the custom occurrence_id
        assert service._agent_occurrence_id == "002"

    @pytest.mark.asyncio
    async def test_communication_service_passes_occurrence_to_observer(
        self, mock_credentials, mock_bus_manager, mock_memory_service
    ):
        """Test that RedditCommunicationService passes occurrence_id to observer."""
        service = RedditCommunicationService(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            agent_occurrence_id="scout_003",
        )

        # Mock the RedditObserver to capture initialization parameters
        with patch("ciris_modular_services.reddit.observer.RedditObserver") as mock_observer_class:
            mock_observer_instance = MagicMock()
            mock_observer_instance.start = AsyncMock()
            mock_observer_class.return_value = mock_observer_instance

            # Mock the client start to avoid Reddit authentication
            with patch.object(service._client, "start", new_callable=AsyncMock):
                # Start the service (which creates the observer)
                await service.start()

                # Verify RedditObserver was instantiated with correct occurrence_id
                mock_observer_class.assert_called_once()
                call_kwargs = mock_observer_class.call_args[1]
                assert "agent_occurrence_id" in call_kwargs
                assert call_kwargs["agent_occurrence_id"] == "scout_003"

    @pytest.mark.asyncio
    async def test_end_to_end_occurrence_propagation(self, mock_credentials, mock_bus_manager, mock_memory_service):
        """Test end-to-end occurrence_id propagation from service to observer."""
        # Create service with specific occurrence_id
        service = RedditCommunicationService(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            agent_occurrence_id="end_to_end_test",
        )

        # Mock the API client to avoid actual Reddit authentication
        with patch.object(service._client, "start", new_callable=AsyncMock):
            # Mock observer's API client start (observer has its own client)
            with patch("ciris_modular_services.reddit.service.RedditAPIClient.start", new_callable=AsyncMock):
                # Start the service (creates observer)
                await service.start()

                # Verify the observer was created and has correct occurrence_id
                assert service._observer is not None
                assert service._observer.agent_occurrence_id == "end_to_end_test"

                # Clean up
                await service.stop()

    def test_multiple_observers_different_occurrence_ids(self, mock_credentials, mock_bus_manager, mock_memory_service):
        """Test that multiple observer instances can have different occurrence_ids."""
        observer_001 = RedditObserver(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            agent_occurrence_id="001",
        )

        observer_002 = RedditObserver(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            agent_occurrence_id="002",
        )

        observer_003 = RedditObserver(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            agent_occurrence_id="003",
        )

        # Verify each observer has its own occurrence_id
        assert observer_001.agent_occurrence_id == "001"
        assert observer_002.agent_occurrence_id == "002"
        assert observer_003.agent_occurrence_id == "003"

    def test_observer_occurrence_id_stored_correctly(self, mock_credentials, mock_bus_manager, mock_memory_service):
        """Test that occurrence_id is properly stored and accessible."""
        observer = RedditObserver(
            credentials=mock_credentials,
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            agent_occurrence_id="original",
        )

        # Verify the occurrence_id is properly stored and accessible
        assert observer.agent_occurrence_id == "original"

        # Verify it's stored in BaseObserver (not just RedditObserver)
        assert hasattr(observer, "agent_occurrence_id")
        assert observer.agent_occurrence_id == "original"
