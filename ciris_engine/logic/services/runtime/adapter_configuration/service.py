"""
AdapterConfigurationService - Manages interactive configuration workflows for adapters.

This service orchestrates multi-step configuration workflows including:
- Discovery of local services (mDNS, API scanning)
- OAuth authentication flows with PKCE
- Interactive step-by-step configuration
- Configuration validation and application
"""

import asyncio
import base64
import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.protocols.adapters.configurable import ConfigurableAdapterProtocol
from ciris_engine.schemas.runtime.manifest import ConfigurationStep, InteractiveConfiguration

from .session import AdapterConfigSession, SessionStatus

logger = logging.getLogger(__name__)


class StepResult:
    """Result from executing a configuration step.

    Attributes:
        step_id: ID of the step that was executed
        success: Whether step execution succeeded
        data: Data returned by the step (options, URLs, etc.)
        next_step_index: Index of next step to execute (None if staying on current)
        error: Error message if execution failed
        awaiting_callback: Whether step is waiting for external callback (OAuth)
    """

    def __init__(
        self,
        step_id: str,
        success: bool,
        data: Optional[Dict[str, Any]] = None,
        next_step_index: Optional[int] = None,
        error: Optional[str] = None,
        awaiting_callback: bool = False,
    ):
        """Initialize step result.

        Args:
            step_id: ID of the executed step
            success: Whether execution succeeded
            data: Optional data returned by step
            next_step_index: Optional index of next step
            error: Optional error message
            awaiting_callback: Whether waiting for callback
        """
        self.step_id = step_id
        self.success = success
        self.data = data or {}
        self.next_step_index = next_step_index
        self.error = error
        self.awaiting_callback = awaiting_callback


class AdapterConfigurationService:
    """Manages interactive configuration workflows for adapters.

    This service provides the runtime infrastructure for executing multi-step
    configuration workflows defined by adapters. It handles session management,
    step execution, OAuth flows, and configuration persistence.

    Example:
        >>> service = AdapterConfigurationService()
        >>> service.register_adapter_config(
        ...     adapter_type="homeassistant",
        ...     interactive_config=ha_config,
        ...     adapter_instance=ha_adapter
        ... )
        >>> session = await service.start_session("homeassistant", "user_123")
        >>> result = await service.execute_step(
        ...     session.session_id,
        ...     {"discovery_type": "mdns"}
        ... )
    """

    SESSION_TIMEOUT_MINUTES = 30

    def __init__(self) -> None:
        """Initialize the configuration service."""
        self._sessions: Dict[str, AdapterConfigSession] = {}
        self._adapter_manifests: Dict[str, InteractiveConfiguration] = {}
        self._adapter_instances: Dict[str, ConfigurableAdapterProtocol] = {}

    def register_adapter_config(
        self,
        adapter_type: str,
        interactive_config: InteractiveConfiguration,
        adapter_instance: ConfigurableAdapterProtocol,
    ) -> None:
        """Register an adapter's interactive configuration capability.

        Args:
            adapter_type: Type identifier for the adapter
            interactive_config: Configuration workflow definition
            adapter_instance: Adapter instance implementing ConfigurableAdapterProtocol
        """
        self._adapter_manifests[adapter_type] = interactive_config
        self._adapter_instances[adapter_type] = adapter_instance
        logger.info(f"Registered interactive config for adapter: {adapter_type}")

    def get_configurable_adapters(self) -> List[str]:
        """Get list of adapters that support interactive configuration.

        Returns:
            List of adapter type identifiers
        """
        return list(self._adapter_manifests.keys())

    async def start_session(
        self,
        adapter_type: str,
        user_id: str,
    ) -> AdapterConfigSession:
        """Start a new configuration session for an adapter.

        Args:
            adapter_type: Type of adapter to configure
            user_id: ID of user performing configuration

        Returns:
            New configuration session

        Raises:
            ValueError: If adapter doesn't support interactive configuration
        """
        if adapter_type not in self._adapter_manifests:
            raise ValueError(f"Adapter '{adapter_type}' does not support interactive configuration")

        session = AdapterConfigSession(
            session_id=str(uuid.uuid4()),
            adapter_type=adapter_type,
            user_id=user_id,
        )
        self._sessions[session.session_id] = session
        logger.info(f"Started config session {session.session_id} for {adapter_type}")
        return session

    def get_session(self, session_id: str) -> Optional[AdapterConfigSession]:
        """Get a configuration session by ID.

        Args:
            session_id: Session identifier

        Returns:
            Session if found, None otherwise. Expired sessions are marked as EXPIRED.
        """
        session = self._sessions.get(session_id)
        if session:
            # Check for expiration
            if self._is_session_expired(session):
                session.status = SessionStatus.EXPIRED
        return session

    async def execute_step(
        self,
        session_id: str,
        step_data: Dict[str, Any],
    ) -> StepResult:
        """Execute the current configuration step.

        Args:
            session_id: Session identifier
            step_data: Data for step execution (user input, selections, etc.)

        Returns:
            Result of step execution
        """
        session = self.get_session(session_id)
        if not session:
            return StepResult(step_id="", success=False, error="Session not found")

        if session.status == SessionStatus.EXPIRED:
            return StepResult(step_id="", success=False, error="Session expired")

        config = self._adapter_manifests[session.adapter_type]
        if session.current_step_index >= len(config.steps):
            return StepResult(step_id="", success=False, error="No more steps")

        step = config.steps[session.current_step_index]
        adapter = self._adapter_instances[session.adapter_type]

        try:
            result = await self._execute_step_type(session, step, adapter, step_data)
            session.update()
            return result
        except Exception as e:
            logger.error(f"Step execution failed: {e}")
            return StepResult(step_id=step.step_id, success=False, error=str(e))

    async def _execute_discovery_step(
        self, session: AdapterConfigSession, step: ConfigurationStep, adapter: ConfigurableAdapterProtocol
    ) -> StepResult:
        """Execute a discovery step."""
        items = await adapter.discover(step.discovery_method or "default")
        session.step_results[step.step_id] = items
        logger.info(f"[DISCOVERY STEP] Returning {len(items)} discovered items to client")
        for item in items:
            logger.info(
                f"[DISCOVERY STEP]   → {item.get('label', 'unknown')} - {item.get('metadata', {}).get('url', 'no url')}"
            )

        if items:
            session.current_step_index += 1
            logger.info(f"[DISCOVERY STEP] Advanced to step index {session.current_step_index}")

        next_idx = session.current_step_index if items else None
        logger.info(
            f"[DISCOVERY STEP] next_step_index={next_idx} (advancing={'yes' if items else 'no - no items found'})"
        )
        return StepResult(
            step_id=step.step_id, success=True, data={"discovered_items": items}, next_step_index=next_idx
        )

    async def _handle_oauth_callback(
        self,
        session: AdapterConfigSession,
        step: ConfigurationStep,
        adapter: ConfigurableAdapterProtocol,
        step_data: Dict[str, Any],
    ) -> StepResult:
        """Handle OAuth callback with authorization code."""
        logger.info("[OAUTH STEP] Processing OAuth callback with code")
        tokens = await adapter.handle_oauth_callback(
            code=step_data["code"],
            state=step_data.get("state", ""),
            base_url=session.collected_config.get("base_url", ""),
            callback_base_url=session.collected_config.get("callback_base_url"),
            redirect_uri=session.collected_config.get("redirect_uri"),
            platform=session.collected_config.get("platform"),
        )
        session.collected_config["oauth_tokens"] = tokens
        session.status = SessionStatus.ACTIVE
        session.current_step_index += 1
        logger.info(f"[OAUTH STEP] Callback processed, advancing to step {session.current_step_index}")
        return StepResult(step_id=step.step_id, success=True, next_step_index=session.current_step_index)

    def _store_oauth_step_data(self, session: AdapterConfigSession, step_data: Dict[str, Any]) -> None:
        """Store OAuth-related data from step_data into session."""
        if "base_url" in step_data and step_data["base_url"]:
            session.collected_config["base_url"] = step_data["base_url"]
            logger.info(f"[OAUTH STEP] Stored base_url from step_data: {step_data['base_url']}")

        if step_data.get("callback_base_url"):
            session.collected_config["callback_base_url"] = step_data["callback_base_url"]
            logger.info(f"[OAUTH STEP] Using local callback base URL: {step_data['callback_base_url']}")

        if step_data.get("redirect_uri"):
            session.collected_config["redirect_uri"] = step_data["redirect_uri"]
            session.collected_config["platform"] = step_data.get("platform")
            logger.info(f"[OAUTH STEP] Using custom redirect URI: {step_data['redirect_uri']}")

    async def _generate_oauth_url(
        self,
        session: AdapterConfigSession,
        step: ConfigurationStep,
        adapter: ConfigurableAdapterProtocol,
        step_data: Dict[str, Any],
    ) -> StepResult:
        """Generate OAuth authorization URL."""
        base_url = session.collected_config.get("base_url", "")
        logger.info(f"[OAUTH STEP] Generating OAuth URL with base_url={base_url}")

        if not base_url:
            logger.error("[OAUTH STEP] ERROR: No base_url in collected_config!")
            return StepResult(
                step_id=step.step_id,
                success=False,
                error="No base_url configured. Please select a Home Assistant instance first.",
            )

        session.pkce_verifier = secrets.token_urlsafe(32)
        code_challenge = self._generate_pkce_challenge(session.pkce_verifier)

        try:
            oauth_url = await adapter.get_oauth_url(
                base_url=base_url,
                state=session.session_id,
                callback_base_url=step_data.get("callback_base_url"),
                redirect_uri=step_data.get("redirect_uri"),
                platform=step_data.get("platform"),
            )
            logger.info(f"[OAUTH STEP] Generated OAuth URL: {oauth_url}")
        except Exception as e:
            logger.error(f"[OAUTH STEP] Failed to generate OAuth URL: {e}")
            return StepResult(step_id=step.step_id, success=False, error=f"Failed to get OAuth URL: {str(e)}")

        session.status = SessionStatus.AWAITING_OAUTH
        return StepResult(
            step_id=step.step_id,
            success=True,
            data={"oauth_url": oauth_url, "code_challenge": code_challenge},
            awaiting_callback=True,
        )

    async def _execute_oauth_step(
        self,
        session: AdapterConfigSession,
        step: ConfigurationStep,
        adapter: ConfigurableAdapterProtocol,
        step_data: Dict[str, Any],
    ) -> StepResult:
        """Execute an OAuth step."""
        logger.info(f"[OAUTH STEP] Executing OAuth step for session {session.session_id}")
        logger.info(f"[OAUTH STEP] step_data keys: {list(step_data.keys())}")
        logger.info(f"[OAUTH STEP] collected_config before: {session.collected_config}")

        self._store_oauth_step_data(session, step_data)
        logger.info(f"[OAUTH STEP] collected_config after: {session.collected_config}")

        if "code" in step_data:
            return await self._handle_oauth_callback(session, step, adapter, step_data)
        return await self._generate_oauth_url(session, step, adapter, step_data)

    async def _execute_select_step(
        self,
        session: AdapterConfigSession,
        step: ConfigurationStep,
        adapter: ConfigurableAdapterProtocol,
        step_data: Dict[str, Any],
    ) -> StepResult:
        """Execute a select step."""
        logger.info(
            f"[SELECT STEP] Processing step {step.step_id}, step_data keys: {list(step_data.keys()) if step_data else 'None'}"
        )
        logger.info(f"[SELECT STEP] Raw step_data: {step_data}")

        selection = step_data.get("selection") or step_data.get("selected")
        logger.info(f"[SELECT STEP] Extracted selection: {selection}")

        if selection:
            session.collected_config[step.step_id] = selection
            session.current_step_index += 1
            logger.info(
                f"[SELECT STEP] Stored selection for {step.step_id}: {selection}, advancing to step {session.current_step_index}"
            )
            return StepResult(step_id=step.step_id, success=True, next_step_index=session.current_step_index)

        logger.info(f"[SELECT STEP] No selection provided, fetching options for {step.step_id}")
        options = await adapter.get_config_options(step.step_id, session.collected_config)
        logger.info(f"[SELECT STEP] Got {len(options) if options else 0} options for {step.step_id}")
        return StepResult(step_id=step.step_id, success=True, data={"options": options})

    def _execute_input_step(
        self, session: AdapterConfigSession, step: ConfigurationStep, step_data: Dict[str, Any]
    ) -> StepResult:
        """Execute an input step."""
        if step_data:
            session.collected_config.update(step_data)
            session.current_step_index += 1
            return StepResult(step_id=step.step_id, success=True, next_step_index=session.current_step_index)
        return StepResult(step_id=step.step_id, success=True, data={"awaiting_input": True})

    def _execute_confirm_step(self, session: AdapterConfigSession, step: ConfigurationStep) -> StepResult:
        """Execute a confirm step."""
        session.current_step_index += 1
        return StepResult(
            step_id=step.step_id,
            success=True,
            data={"config_summary": session.collected_config},
            next_step_index=session.current_step_index,
        )

    async def _execute_step_type(
        self,
        session: AdapterConfigSession,
        step: ConfigurationStep,
        adapter: ConfigurableAdapterProtocol,
        step_data: Dict[str, Any],
    ) -> StepResult:
        """Execute step based on its type."""
        if step.step_type == "discovery":
            return await self._execute_discovery_step(session, step, adapter)
        elif step.step_type == "oauth":
            return await self._execute_oauth_step(session, step, adapter, step_data)
        elif step.step_type == "select":
            return await self._execute_select_step(session, step, adapter, step_data)
        elif step.step_type == "input":
            return self._execute_input_step(session, step, step_data)
        elif step.step_type == "confirm":
            return self._execute_confirm_step(session, step)

        return StepResult(step_id=step.step_id, success=False, error=f"Unknown step type: {step.step_type}")

    async def complete_session(self, session_id: str) -> bool:
        """Complete the configuration and apply it to the adapter.

        Args:
            session_id: Session identifier

        Returns:
            True if configuration was applied successfully, False otherwise
        """
        session = self.get_session(session_id)
        if not session:
            return False

        adapter = self._adapter_instances.get(session.adapter_type)
        if not adapter:
            return False

        # Validate configuration
        is_valid, error = await adapter.validate_config(session.collected_config)
        if not is_valid:
            logger.error(f"Config validation failed: {error}")
            session.status = SessionStatus.FAILED
            return False

        # Apply configuration
        success = await adapter.apply_config(session.collected_config)
        if success:
            session.status = SessionStatus.COMPLETED
            logger.info(f"Configuration applied for session {session_id}")
        else:
            session.status = SessionStatus.FAILED

        return success

    def _is_session_expired(self, session: AdapterConfigSession) -> bool:
        """Check if a session has expired.

        Args:
            session: Session to check

        Returns:
            True if session has exceeded timeout
        """
        timeout = timedelta(minutes=self.SESSION_TIMEOUT_MINUTES)
        return datetime.now(timezone.utc) - session.updated_at > timeout

    def _generate_pkce_challenge(self, verifier: str) -> str:
        """Generate PKCE code challenge from verifier.

        Args:
            verifier: PKCE code verifier

        Returns:
            Base64 URL-encoded SHA256 hash of verifier
        """
        digest = hashlib.sha256(verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions from memory.

        Returns:
            Count of sessions that were removed
        """
        expired = [sid for sid, session in self._sessions.items() if self._is_session_expired(session)]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)

