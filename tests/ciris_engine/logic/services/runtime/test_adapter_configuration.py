"""
Unit tests for AdapterConfigurationService.

Tests the complete interactive configuration workflow including:
- Session management (create, get, expire)
- Step execution (discovery, oauth, select, input, confirm)
- Configuration validation and application
- PKCE generation for OAuth flows
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.runtime.adapter_configuration.service import AdapterConfigurationService, StepResult
from ciris_engine.logic.services.runtime.adapter_configuration.session import AdapterConfigSession, SessionStatus
from ciris_engine.schemas.runtime.manifest import ConfigurationStep, InteractiveConfiguration


class MockConfigurableAdapter:
    """Mock adapter implementing ConfigurableAdapterProtocol for testing."""

    def __init__(self) -> None:
        self.discover_results: List[Dict[str, Any]] = []
        self.oauth_url: str = "https://example.com/oauth"
        self.oauth_tokens: Dict[str, Any] = {"access_token": "test_token"}
        self.config_options: List[Dict[str, Any]] = []
        self.validation_result: Tuple[bool, Optional[str]] = (True, None)
        self.apply_result: bool = True

    async def discover(self, discovery_type: str) -> List[Dict[str, Any]]:
        """Return mock discovery results."""
        return self.discover_results

    async def get_oauth_url(
        self,
        base_url: str,
        state: str,
        code_challenge: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> str:
        """Return mock OAuth URL."""
        return f"{self.oauth_url}?state={state}"

    async def handle_oauth_callback(
        self,
        code: str,
        state: str,
        base_url: str,
        code_verifier: Optional[str] = None,
        callback_base_url: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return mock OAuth tokens."""
        return self.oauth_tokens

    async def get_config_options(self, step_id: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return mock config options."""
        return self.config_options

    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Return mock validation result."""
        return self.validation_result

    async def apply_config(self, config: Dict[str, Any]) -> bool:
        """Return mock apply result."""
        return self.apply_result


def create_test_config() -> InteractiveConfiguration:
    """Create a test interactive configuration with all step types."""
    return InteractiveConfiguration(
        required=True,
        workflow_type="wizard",
        steps=[
            ConfigurationStep(
                step_id="discover",
                step_type="discovery",
                title="Discover Services",
                description="Find local services",
                discovery_method="mdns",
            ),
            ConfigurationStep(
                step_id="oauth",
                step_type="oauth",
                title="Authenticate",
                description="Sign in to the service",
            ),
            ConfigurationStep(
                step_id="select_entities",
                step_type="select",
                title="Select Entities",
                description="Choose which entities to monitor",
            ),
            ConfigurationStep(
                step_id="settings",
                step_type="input",
                title="Additional Settings",
                description="Configure additional options",
            ),
            ConfigurationStep(
                step_id="confirm",
                step_type="confirm",
                title="Confirm",
                description="Review and confirm configuration",
            ),
        ],
        completion_method="apply_config",
    )


class TestAdapterConfigSession:
    """Tests for AdapterConfigSession dataclass."""

    def test_session_creation_defaults(self) -> None:
        """Test session is created with correct defaults."""
        session = AdapterConfigSession(
            session_id="test_123",
            adapter_type="homeassistant",
            user_id="user_456",
        )

        assert session.session_id == "test_123"
        assert session.adapter_type == "homeassistant"
        assert session.user_id == "user_456"
        assert session.current_step_index == 0
        assert session.status == SessionStatus.ACTIVE
        assert session.collected_config == {}
        assert session.step_results == {}
        assert session.pkce_verifier is None

    def test_session_update_timestamp(self) -> None:
        """Test update() changes the updated_at timestamp."""
        session = AdapterConfigSession(
            session_id="test_123",
            adapter_type="homeassistant",
            user_id="user_456",
        )
        original_updated = session.updated_at

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.01)
        session.update()

        assert session.updated_at > original_updated

    def test_session_status_enum(self) -> None:
        """Test all session status values are valid."""
        assert SessionStatus.ACTIVE == "active"
        assert SessionStatus.AWAITING_OAUTH == "awaiting_oauth"
        assert SessionStatus.COMPLETED == "completed"
        assert SessionStatus.FAILED == "failed"
        assert SessionStatus.EXPIRED == "expired"


class TestStepResult:
    """Tests for StepResult class."""

    def test_step_result_creation(self) -> None:
        """Test StepResult is created with correct values."""
        result = StepResult(
            step_id="discover",
            success=True,
            data={"items": [1, 2, 3]},
            next_step_index=1,
        )

        assert result.step_id == "discover"
        assert result.success is True
        assert result.data == {"items": [1, 2, 3]}
        assert result.next_step_index == 1
        assert result.error is None
        assert result.awaiting_callback is False

    def test_step_result_failure(self) -> None:
        """Test StepResult for failed step."""
        result = StepResult(
            step_id="oauth",
            success=False,
            error="Authentication failed",
        )

        assert result.success is False
        assert result.error == "Authentication failed"
        assert result.data == {}

    def test_step_result_awaiting_callback(self) -> None:
        """Test StepResult for OAuth awaiting callback."""
        result = StepResult(
            step_id="oauth",
            success=True,
            data={"oauth_url": "https://example.com/oauth"},
            awaiting_callback=True,
        )

        assert result.success is True
        assert result.awaiting_callback is True


class TestAdapterConfigurationService:
    """Tests for AdapterConfigurationService."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = AdapterConfigurationService()
        self.mock_adapter = MockConfigurableAdapter()
        self.test_config = create_test_config()

    def test_register_adapter_config(self) -> None:
        """Test registering an adapter's interactive configuration."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        adapters = self.service.get_configurable_adapters()
        assert "homeassistant" in adapters

    def test_get_configurable_adapters_empty(self) -> None:
        """Test getting configurable adapters when none registered."""
        adapters = self.service.get_configurable_adapters()
        assert adapters == []

    @pytest.mark.asyncio
    async def test_start_session(self) -> None:
        """Test starting a new configuration session."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session(
            adapter_type="homeassistant",
            user_id="user_123",
        )

        assert session.adapter_type == "homeassistant"
        assert session.user_id == "user_123"
        assert session.status == SessionStatus.ACTIVE
        assert session.current_step_index == 0

    @pytest.mark.asyncio
    async def test_start_session_unknown_adapter(self) -> None:
        """Test starting session for unknown adapter raises error."""
        with pytest.raises(ValueError, match="does not support"):
            await self.service.start_session(
                adapter_type="unknown",
                user_id="user_123",
            )

    def test_get_session(self) -> None:
        """Test retrieving a session by ID."""
        # Create session directly
        session = AdapterConfigSession(
            session_id="test_session",
            adapter_type="homeassistant",
            user_id="user_123",
        )
        self.service._sessions["test_session"] = session

        retrieved = self.service.get_session("test_session")
        assert retrieved is session

    def test_get_session_not_found(self) -> None:
        """Test retrieving non-existent session returns None."""
        retrieved = self.service.get_session("nonexistent")
        assert retrieved is None

    def test_get_session_expired(self) -> None:
        """Test expired session is marked as EXPIRED."""
        session = AdapterConfigSession(
            session_id="test_session",
            adapter_type="homeassistant",
            user_id="user_123",
        )
        # Set updated_at to past the timeout
        session.updated_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        self.service._sessions["test_session"] = session

        retrieved = self.service.get_session("test_session")
        assert retrieved is not None
        assert retrieved.status == SessionStatus.EXPIRED

    @pytest.mark.asyncio
    async def test_execute_step_discovery(self) -> None:
        """Test executing a discovery step."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        # Set up mock discovery results
        self.mock_adapter.discover_results = [
            {"id": "ha_1", "label": "Home Assistant 1", "description": "192.168.1.50"}
        ]

        session = await self.service.start_session("homeassistant", "user_123")
        result = await self.service.execute_step(session.session_id, {})

        assert result.success is True
        assert result.step_id == "discover"
        assert "discovered_items" in result.data
        assert len(result.data["discovered_items"]) == 1
        assert result.next_step_index == 1

    @pytest.mark.asyncio
    async def test_execute_step_discovery_empty(self) -> None:
        """Test discovery step with no results stays on current step."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        self.mock_adapter.discover_results = []

        session = await self.service.start_session("homeassistant", "user_123")
        result = await self.service.execute_step(session.session_id, {})

        assert result.success is True
        assert result.next_step_index is None  # Stay on current step

    @pytest.mark.asyncio
    async def test_execute_step_oauth_generate_url(self) -> None:
        """Test OAuth step generates authorization URL."""
        # Use a config that starts with OAuth
        oauth_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="oauth",
                    step_type="oauth",
                    title="Authenticate",
                    description="Sign in",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_oauth",
            interactive_config=oauth_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_oauth", "user_123")
        # Pre-populate base_url which is required for OAuth URL generation
        session.collected_config["base_url"] = "http://localhost:8123"
        result = await self.service.execute_step(session.session_id, {})

        assert result.success is True
        assert result.awaiting_callback is True
        assert "oauth_url" in result.data
        assert session.status == SessionStatus.AWAITING_OAUTH
        assert session.pkce_verifier is not None

    @pytest.mark.asyncio
    async def test_execute_step_oauth_callback(self) -> None:
        """Test OAuth step handles callback with authorization code."""
        oauth_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="oauth",
                    step_type="oauth",
                    title="Authenticate",
                    description="Sign in",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_oauth",
            interactive_config=oauth_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_oauth", "user_123")
        # Pre-populate base_url which is required for OAuth URL generation
        session.collected_config["base_url"] = "http://localhost:8123"

        # First call generates URL
        await self.service.execute_step(session.session_id, {})

        # Second call handles callback
        result = await self.service.execute_step(
            session.session_id,
            {"code": "auth_code_123", "state": session.session_id},
        )

        assert result.success is True
        assert session.status == SessionStatus.ACTIVE
        assert "oauth_tokens" in session.collected_config

    @pytest.mark.asyncio
    async def test_execute_step_select_get_options(self) -> None:
        """Test select step returns options when no selection provided."""
        select_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="select_item",
                    step_type="select",
                    title="Select Item",
                    description="Choose an item",
                ),
            ],
            completion_method="apply_config",
        )

        self.mock_adapter.config_options = [
            {"id": "opt1", "label": "Option 1"},
            {"id": "opt2", "label": "Option 2"},
        ]

        self.service.register_adapter_config(
            adapter_type="test_select",
            interactive_config=select_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_select", "user_123")
        result = await self.service.execute_step(session.session_id, {})

        assert result.success is True
        assert "options" in result.data
        assert len(result.data["options"]) == 2

    @pytest.mark.asyncio
    async def test_execute_step_select_with_selection(self) -> None:
        """Test select step advances when selection is provided."""
        select_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="select_item",
                    step_type="select",
                    title="Select Item",
                    description="Choose an item",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_select",
            interactive_config=select_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_select", "user_123")
        result = await self.service.execute_step(session.session_id, {"selection": "opt1"})

        assert result.success is True
        assert result.next_step_index == 1
        assert session.collected_config["select_item"] == "opt1"

    @pytest.mark.asyncio
    async def test_execute_step_select_with_selected_parameter(self) -> None:
        """Test select step advances when 'selected' parameter is provided (Android compatibility).

        The Android client sends 'selected' instead of 'selection' for compatibility.
        The service should accept both parameter names.
        """
        select_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="select_features",
                    step_type="select",
                    title="Select Features",
                    description="Choose features to enable",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_select_android",
            interactive_config=select_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_select_android", "user_123")
        # Use 'selected' parameter like Android client does
        result = await self.service.execute_step(session.session_id, {"selected": ["feature1", "feature2"]})

        assert result.success is True
        assert result.next_step_index == 1
        assert session.collected_config["select_features"] == ["feature1", "feature2"]

    @pytest.mark.asyncio
    async def test_execute_step_select_prefers_selection_over_selected(self) -> None:
        """Test that 'selection' takes priority when both parameters are provided."""
        select_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="select_item",
                    step_type="select",
                    title="Select Item",
                    description="Choose an item",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_select_both",
            interactive_config=select_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_select_both", "user_123")
        # Provide both parameters - 'selection' should take priority
        result = await self.service.execute_step(session.session_id, {"selection": "opt1", "selected": "opt2"})

        assert result.success is True
        assert session.collected_config["select_item"] == "opt1"

    @pytest.mark.asyncio
    async def test_execute_step_input(self) -> None:
        """Test input step collects configuration data."""
        input_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="settings",
                    step_type="input",
                    title="Settings",
                    description="Enter settings",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_input",
            interactive_config=input_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_input", "user_123")
        result = await self.service.execute_step(session.session_id, {"poll_interval": 60, "timeout": 30})

        assert result.success is True
        assert result.next_step_index == 1
        assert session.collected_config["poll_interval"] == 60
        assert session.collected_config["timeout"] == 30

    @pytest.mark.asyncio
    async def test_execute_step_input_empty(self) -> None:
        """Test input step returns awaiting_input when no data provided."""
        input_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="settings",
                    step_type="input",
                    title="Settings",
                    description="Enter settings",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_input",
            interactive_config=input_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_input", "user_123")
        result = await self.service.execute_step(session.session_id, {})

        assert result.success is True
        assert result.data.get("awaiting_input") is True

    @pytest.mark.asyncio
    async def test_execute_step_confirm(self) -> None:
        """Test confirm step returns config summary."""
        confirm_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="confirm",
                    step_type="confirm",
                    title="Confirm",
                    description="Review configuration",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_confirm",
            interactive_config=confirm_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_confirm", "user_123")
        session.collected_config = {"setting1": "value1", "setting2": "value2"}

        result = await self.service.execute_step(session.session_id, {})

        assert result.success is True
        assert "config_summary" in result.data
        assert result.data["config_summary"]["setting1"] == "value1"

    @pytest.mark.asyncio
    async def test_execute_step_session_not_found(self) -> None:
        """Test execute_step with non-existent session."""
        result = await self.service.execute_step("nonexistent", {})

        assert result.success is False
        assert result.error == "Session not found"

    @pytest.mark.asyncio
    async def test_execute_step_session_expired(self) -> None:
        """Test execute_step with expired session."""
        session = AdapterConfigSession(
            session_id="test_session",
            adapter_type="homeassistant",
            user_id="user_123",
        )
        session.updated_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        self.service._sessions["test_session"] = session

        result = await self.service.execute_step("test_session", {})

        assert result.success is False
        assert result.error == "Session expired"

    @pytest.mark.asyncio
    async def test_execute_step_no_more_steps(self) -> None:
        """Test execute_step when all steps completed."""
        single_step_config = InteractiveConfiguration(
            required=True,
            workflow_type="wizard",
            steps=[
                ConfigurationStep(
                    step_id="confirm",
                    step_type="confirm",
                    title="Confirm",
                    description="Done",
                ),
            ],
            completion_method="apply_config",
        )

        self.service.register_adapter_config(
            adapter_type="test_done",
            interactive_config=single_step_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("test_done", "user_123")
        session.current_step_index = 1  # Past the only step

        result = await self.service.execute_step(session.session_id, {})

        assert result.success is False
        assert result.error == "No more steps"

    @pytest.mark.asyncio
    async def test_complete_session_success(self) -> None:
        """Test successfully completing a configuration session."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("homeassistant", "user_123")
        session.collected_config = {
            "base_url": "https://ha.local:8123",
            "access_token": "test_token",
        }

        success = await self.service.complete_session(session.session_id)

        assert success is True
        assert session.status == SessionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_complete_session_validation_failed(self) -> None:
        """Test completing session when validation fails."""
        self.mock_adapter.validation_result = (False, "Invalid configuration")

        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("homeassistant", "user_123")
        success = await self.service.complete_session(session.session_id)

        assert success is False
        assert session.status == SessionStatus.FAILED

    @pytest.mark.asyncio
    async def test_complete_session_apply_failed(self) -> None:
        """Test completing session when apply fails."""
        self.mock_adapter.apply_result = False

        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("homeassistant", "user_123")
        success = await self.service.complete_session(session.session_id)

        assert success is False
        assert session.status == SessionStatus.FAILED

    @pytest.mark.asyncio
    async def test_complete_session_not_found(self) -> None:
        """Test completing non-existent session."""
        success = await self.service.complete_session("nonexistent")
        assert success is False

    def test_cleanup_expired_sessions(self) -> None:
        """Test cleanup removes expired sessions."""
        # Create active session
        active_session = AdapterConfigSession(
            session_id="active",
            adapter_type="homeassistant",
            user_id="user_123",
        )
        self.service._sessions["active"] = active_session

        # Create expired session
        expired_session = AdapterConfigSession(
            session_id="expired",
            adapter_type="homeassistant",
            user_id="user_456",
        )
        expired_session.updated_at = datetime.now(timezone.utc) - timedelta(minutes=60)
        self.service._sessions["expired"] = expired_session

        count = self.service.cleanup_expired_sessions()

        assert count == 1
        assert "active" in self.service._sessions
        assert "expired" not in self.service._sessions

    def test_pkce_challenge_generation(self) -> None:
        """Test PKCE code challenge is generated correctly."""
        verifier = "test_verifier_string_123"
        challenge = self.service._generate_pkce_challenge(verifier)

        # Challenge should be base64url encoded SHA256
        assert challenge is not None
        assert len(challenge) > 0
        # Should not have padding characters
        assert "=" not in challenge

        # Same verifier should produce same challenge
        challenge2 = self.service._generate_pkce_challenge(verifier)
        assert challenge == challenge2

        # Different verifier should produce different challenge
        challenge3 = self.service._generate_pkce_challenge("different_verifier")
        assert challenge != challenge3


class TestInteractiveConfigurationSchema:
    """Tests for the InteractiveConfiguration schema."""

    def test_schema_creation(self) -> None:
        """Test InteractiveConfiguration schema is created correctly."""
        config = create_test_config()

        assert config.required is True
        assert config.workflow_type == "wizard"
        assert len(config.steps) == 5
        assert config.completion_method == "apply_config"

    def test_configuration_step_types(self) -> None:
        """Test all step types are valid."""
        config = create_test_config()

        step_types = [step.step_type for step in config.steps]
        assert "discovery" in step_types
        assert "oauth" in step_types
        assert "select" in step_types
        assert "input" in step_types
        assert "confirm" in step_types

    def test_configuration_step_fields(self) -> None:
        """Test ConfigurationStep has required fields."""
        step = ConfigurationStep(
            step_id="test_step",
            step_type="discovery",
            title="Test Step",
            description="Test description",
            discovery_method="mdns",
            depends_on=["other_step"],
        )

        assert step.step_id == "test_step"
        assert step.step_type == "discovery"
        assert step.title == "Test Step"
        assert step.description == "Test description"
        assert step.discovery_method == "mdns"
        assert step.depends_on == ["other_step"]


class TestConfigurationSessionStatusEndpoint:
    """Tests for configuration session status response field requirements.

    These tests verify that session status responses include all required
    fields for proper wizard navigation on mobile clients.
    """

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = AdapterConfigurationService()
        self.mock_adapter = MockConfigurableAdapter()
        self.test_config = create_test_config()

    def test_session_has_created_at(self) -> None:
        """Test session includes created_at timestamp."""
        session = AdapterConfigSession(
            session_id="test_session",
            adapter_type="homeassistant",
            user_id="user_123",
        )

        assert session.created_at is not None
        assert isinstance(session.created_at, datetime)

    def test_manifest_provides_total_steps(self) -> None:
        """Test manifest steps list provides total_steps count."""
        config = create_test_config()

        assert config.steps is not None
        assert len(config.steps) == 5  # discover, oauth, select_entities, settings, confirm

    def test_get_current_step_from_manifest(self) -> None:
        """Test getting current step from manifest by index."""
        config = create_test_config()

        # Verify we can access step by index
        assert config.steps[0].step_id == "discover"
        assert config.steps[0].step_type == "discovery"
        assert config.steps[1].step_id == "oauth"
        assert config.steps[1].step_type == "oauth"

    @pytest.mark.asyncio
    async def test_session_status_after_oauth_step(self) -> None:
        """Test session tracks step progression correctly after OAuth."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        # Start session
        session = await self.service.start_session("homeassistant", "user_123")
        assert session.current_step_index == 0

        # Execute discovery step
        self.mock_adapter.discover_results = [{"id": "ha_1", "label": "Home Assistant", "description": "192.168.1.50"}]
        result = await self.service.execute_step(session.session_id, {})
        assert result.success is True

        # Session should advance
        updated_session = self.service.get_session(session.session_id)
        assert updated_session is not None
        assert updated_session.current_step_index == 1

    def test_session_tracks_completed_steps(self) -> None:
        """Test session step_results tracks completed step IDs."""
        session = AdapterConfigSession(
            session_id="test_session",
            adapter_type="homeassistant",
            user_id="user_123",
        )

        # Simulate completing steps
        session.step_results["discover"] = {"items": []}
        session.step_results["oauth"] = {"access_token": "token123"}

        # Verify step tracking
        completed_step_ids = list(session.step_results.keys())
        assert "discover" in completed_step_ids
        assert "oauth" in completed_step_ids
        assert len(completed_step_ids) == 2

    @pytest.mark.asyncio
    async def test_session_status_contains_all_required_fields(self) -> None:
        """Test that session status provides all fields needed for UI."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("homeassistant", "user_123")
        manifest = self.service._adapter_manifests.get("homeassistant")

        # Verify all required fields are available
        assert session.session_id is not None
        assert session.adapter_type == "homeassistant"
        assert session.status == SessionStatus.ACTIVE
        assert session.current_step_index == 0
        assert session.created_at is not None
        assert manifest is not None
        assert len(manifest.steps) > 0

        # Current step should be accessible
        current_step = manifest.steps[session.current_step_index]
        assert current_step.step_id == "discover"

    @pytest.mark.asyncio
    async def test_manifest_access_for_total_steps(self) -> None:
        """Test that manifest provides total_steps for status response."""
        self.service.register_adapter_config(
            adapter_type="homeassistant",
            interactive_config=self.test_config,
            adapter_instance=self.mock_adapter,
        )

        session = await self.service.start_session("homeassistant", "user_123")

        # Get manifest for total_steps
        manifest = self.service._adapter_manifests.get(session.adapter_type)
        assert manifest is not None

        total_steps = len(manifest.steps)
        assert total_steps == 5

        # Verify step index is within bounds
        assert session.current_step_index < total_steps


class TestPersistedConfigMethods:
    """Tests for load_persisted_configs and remove_persisted_config methods."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.service = AdapterConfigurationService()

    @pytest.mark.asyncio
    async def test_load_persisted_configs_empty(self) -> None:
        """Test load_persisted_configs returns empty dict when no configs exist."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(return_value={})

        result = await self.service.load_persisted_configs(mock_config_service)

        assert result == {}
        mock_config_service.list_configs.assert_called_once_with(prefix="adapter_config:")

    @pytest.mark.asyncio
    async def test_load_persisted_configs_single_adapter(self) -> None:
        """Test load_persisted_configs loads a single adapter config."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter_config:homeassistant:ha_instance_1": {
                    "base_url": "http://localhost:8123",
                    "access_token": "test_token",
                }
            }
        )

        result = await self.service.load_persisted_configs(mock_config_service)

        assert "homeassistant" in result
        assert "ha_instance_1" in result["homeassistant"]
        assert result["homeassistant"]["ha_instance_1"]["base_url"] == "http://localhost:8123"

    @pytest.mark.asyncio
    async def test_load_persisted_configs_multiple_adapters(self) -> None:
        """Test load_persisted_configs loads multiple adapter types."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter_config:homeassistant:ha_1": {"base_url": "http://ha1.local"},
                "adapter_config:homeassistant:ha_2": {"base_url": "http://ha2.local"},
                "adapter_config:weather:weather_1": {"api_key": "test_key"},
            }
        )

        result = await self.service.load_persisted_configs(mock_config_service)

        assert len(result) == 2
        assert "homeassistant" in result
        assert "weather" in result
        assert len(result["homeassistant"]) == 2
        assert len(result["weather"]) == 1

    @pytest.mark.asyncio
    async def test_load_persisted_configs_non_dict_value(self) -> None:
        """Test load_persisted_configs handles non-dict values."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(return_value={"adapter_config:simple:instance_1": "simple_value"})

        result = await self.service.load_persisted_configs(mock_config_service)

        assert "simple" in result
        assert result["simple"]["instance_1"] == {"value": "simple_value"}

    @pytest.mark.asyncio
    async def test_load_persisted_configs_malformed_key(self) -> None:
        """Test load_persisted_configs ignores malformed keys."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter_config:homeassistant:ha_1": {"base_url": "http://ha.local"},
                "adapter_config:malformed": {"should": "be ignored"},  # Missing adapter_id
                "other_prefix:something": {"also": "ignored"},  # Wrong prefix
            }
        )

        result = await self.service.load_persisted_configs(mock_config_service)

        assert len(result) == 1
        assert "homeassistant" in result
        assert "malformed" not in result

    @pytest.mark.asyncio
    async def test_load_persisted_configs_exception_handling(self) -> None:
        """Test load_persisted_configs returns empty dict on exception."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(side_effect=Exception("Database error"))

        result = await self.service.load_persisted_configs(mock_config_service)

        assert result == {}

    @pytest.mark.asyncio
    async def test_remove_persisted_config_success(self) -> None:
        """Test remove_persisted_config removes configs for adapter type."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter_config:homeassistant:ha_1": {"base_url": "http://ha1.local"},
                "adapter_config:homeassistant:ha_2": {"base_url": "http://ha2.local"},
            }
        )
        mock_config_service.set_config = AsyncMock()

        result = await self.service.remove_persisted_config("homeassistant", mock_config_service)

        assert result is True
        mock_config_service.list_configs.assert_called_once_with(prefix="adapter_config:homeassistant:")
        assert mock_config_service.set_config.call_count == 2

    @pytest.mark.asyncio
    async def test_remove_persisted_config_no_configs(self) -> None:
        """Test remove_persisted_config returns False when no configs exist."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(return_value={})

        result = await self.service.remove_persisted_config("nonexistent", mock_config_service)

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_persisted_config_partial_failure(self) -> None:
        """Test remove_persisted_config handles partial failures."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter_config:homeassistant:ha_1": {"base_url": "http://ha1.local"},
                "adapter_config:homeassistant:ha_2": {"base_url": "http://ha2.local"},
            }
        )
        # First call succeeds, second fails
        mock_config_service.set_config = AsyncMock(side_effect=[None, Exception("Delete failed")])

        result = await self.service.remove_persisted_config("homeassistant", mock_config_service)

        # Should still return True because at least one was removed
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_persisted_config_exception_handling(self) -> None:
        """Test remove_persisted_config returns False on exception."""
        mock_config_service = AsyncMock()
        mock_config_service.list_configs = AsyncMock(side_effect=Exception("Database error"))

        result = await self.service.remove_persisted_config("homeassistant", mock_config_service)

        assert result is False
