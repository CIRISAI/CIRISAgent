"""Runtime control service for processor and adapter management."""

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union, cast

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.services.graph.config_service import GraphConfigService
    from ciris_engine.logic.runtime.runtime_interface import RuntimeInterface

from ciris_engine.logic.runtime.adapter_manager import RuntimeAdapterManager
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import RuntimeControlService as RuntimeControlServiceProtocol
from ciris_engine.protocols.services import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.core.runtime import (
    AdapterInfo,
    AdapterOperationResponse,
    AdapterStatus,
    ConfigBackup,
    ConfigOperationResponse,
    ConfigReloadResult,
    ConfigSnapshot,
    ConfigValidationLevel,
    ConfigValidationResponse,
    ProcessorControlResponse,
    ProcessorQueueStatus,
    ProcessorStatus,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeStatusResponse,
    ServiceHealthStatus,
    ServiceSelectionExplanation,
)
from ciris_engine.schemas.services.runtime_control import (
    CircuitBreakerResetResponse,
    CircuitBreakerState,
    CircuitBreakerStatus,
    ConfigBackupData,
    ConfigValueMap,
    ServicePriorityUpdateResponse,
    ServiceProviderInfo,
    ServiceProviderUpdate,
    ServiceRegistryInfoResponse,
    WAPublicKeyMap,
)
from ciris_engine.schemas.services.shutdown import EmergencyShutdownStatus, KillSwitchConfig, WASignedCommand
from ciris_engine.schemas.types import ConfigDict, ConfigValue

# GraphConfigService is injected via dependency injection to avoid circular imports


logger = logging.getLogger(__name__)

# Error message constants
_ERROR_AGENT_PROCESSOR_NOT_AVAILABLE = "Agent processor not available"
_ERROR_SERVICE_REGISTRY_NOT_AVAILABLE = "Service registry not available"


# Internal dataclass for provider lookup results
from dataclasses import dataclass


@dataclass
class _ProviderLookupResult:
    """Internal: Result from finding a provider in the registry."""

    provider: Any
    providers_list: List[Any]
    service_type: str


class RuntimeControlService(BaseService, RuntimeControlServiceProtocol):
    """Service for runtime control of processor, adapters, and configuration."""

    def __init__(
        self,
        runtime: Optional["RuntimeInterface"] = None,
        adapter_manager: Optional[RuntimeAdapterManager] = None,
        config_manager: Optional["GraphConfigService"] = None,
        time_service: Optional[TimeServiceProtocol] = None,
    ) -> None:
        # Always create a time service if not provided for BaseService
        if time_service is None:
            from ciris_engine.logic.services.lifecycle.time import TimeService

            time_service = TimeService()

        super().__init__(time_service=time_service)

        self.runtime: Optional["RuntimeInterface"] = runtime
        self.adapter_manager = adapter_manager
        if not self.adapter_manager and runtime:
            self.adapter_manager = RuntimeAdapterManager(runtime, self._time_service)  # type: ignore[arg-type]
        self.config_manager: Optional["GraphConfigService"] = config_manager

        self._processor_status = ProcessorStatus.RUNNING
        self._last_config_change: Optional[datetime] = None
        self._events_history: List[RuntimeEvent] = []

        # Enhanced metrics tracking variables
        self._queue_depth = 0
        self._thoughts_processed = 0
        self._thoughts_pending = 0
        self._average_thought_time_ms = 0.0
        self._thought_times: List[float] = []  # Track last N thought processing times
        self._max_thought_history = 100
        self._messages_processed = 0
        # Note: _message_times removed - not applicable since messages can be REJECTed
        self._service_overrides = 0
        self._runtime_errors = 0
        self._single_steps = 0
        self._pause_resume_cycles = 0

        # State transition tracking for v1.4.3 metrics
        self._state_transitions = 0
        self._commands_processed = 0

        # Kill switch configuration
        self._kill_switch_config = KillSwitchConfig(
            enabled=True,
            trust_tree_depth=3,
            allow_relay=True,
            max_shutdown_time_ms=30000,
            command_expiry_seconds=300,
            require_reason=True,
            log_to_audit=True,
            allow_override=False,
        )
        # Initialize WA public key map
        self._wa_key_map = WAPublicKeyMap()

    def _get_config_manager(self) -> "GraphConfigService":
        """Get config manager with lazy initialization to avoid circular imports."""
        if self.config_manager is None:
            # Config manager must be injected, cannot create without dependencies
            raise RuntimeError("Config manager not available - must be injected via dependency injection")
        return self.config_manager

    async def _initialize(self) -> None:
        """Initialize the runtime control service."""
        try:
            # Config manager is already initialized by service initializer
            logger.info("Runtime control service initialized")
        except Exception as e:
            logger.error(f"Failed to initialize runtime control service: {e}")
            raise

    async def single_step(self) -> ProcessorControlResponse:
        """Execute a single processing step."""
        try:
            _start_time = self._now()

            # Get the agent processor from runtime
            if not self.runtime or not hasattr(self.runtime, "agent_processor"):
                return ProcessorControlResponse(
                    success=False,
                    processor_name="agent",
                    operation="single_step",
                    new_status=self._processor_status,
                    error=_ERROR_AGENT_PROCESSOR_NOT_AVAILABLE,
                )

            # Ensure processor is paused
            if not self.runtime.agent_processor.is_paused():
                return ProcessorControlResponse(
                    success=False,
                    processor_name="agent",
                    operation="single_step",
                    new_status=self._processor_status,
                    error="Cannot single-step unless processor is paused",
                )

            result = await self.runtime.agent_processor.single_step()

            # Track thought processing time if a thought was processed
            if result.success and result.processing_time_ms:
                processing_time = result.processing_time_ms

                # Add to thought times list
                self._thought_times.append(processing_time)

                # Trim list to max history
                if len(self._thought_times) > self._max_thought_history:
                    self._thought_times = self._thought_times[-self._max_thought_history :]

                # Update average
                self._average_thought_time_ms = sum(self._thought_times) / len(self._thought_times)

                # Track metrics
                self._thoughts_processed += 1

            self._single_steps += 1
            self._commands_processed += 1
            # Convert result to dict for event recording
            result_dict = result.model_dump() if hasattr(result, "model_dump") else result
            await self._record_event("processor_control", "single_step", success=True, result=result_dict)

            # Return the full step result data instead of discarding it
            # Validate step_results - only include if they match StepResultData schema
            raw_step_results = result.step_results if hasattr(result, "step_results") else []
            validated_step_results = []

            from ciris_engine.schemas.services.runtime_control import StepResultData

            for step_result in raw_step_results:
                try:
                    # Try to validate as StepResultData
                    if isinstance(step_result, dict):
                        validated = StepResultData(**step_result)
                        validated_step_results.append(validated)
                    elif isinstance(step_result, StepResultData):
                        validated_step_results.append(step_result)
                except Exception:
                    # Skip invalid results - this happens during thought initiation
                    # when step_results only contain {"thought_id": ..., "initiated": True}
                    pass

            # Map SingleStepResult fields to ProcessorControlResponse
            # SingleStepResult has: success, message, thoughts_advanced (not thoughts_processed)
            # When success=False, use message as error
            error_text = None if result.success else result.message

            return ProcessorControlResponse(
                success=result.success if hasattr(result, "success") else False,
                processor_name="agent",
                operation="single_step",
                new_status=self._processor_status,
                error=error_text,
                # Pass through all the H3ERE step data
                step_point=getattr(result, "step_point", None),
                step_results=validated_step_results if validated_step_results else None,
                thoughts_processed=self._thoughts_processed,  # Use internal counter, not result field
                processing_time_ms=getattr(result, "processing_time_ms", 0.0),
                pipeline_state=getattr(result, "pipeline_state", {}),
                current_round=getattr(result, "current_round", None),
                pipeline_empty=getattr(result, "pipeline_empty", False),
            )

        except Exception as e:
            logger.error(f"Failed to execute single step: {e}", exc_info=True)
            await self._record_event("processor_control", "single_step", success=False, error=str(e))
            return ProcessorControlResponse(
                success=False,
                processor_name="agent",
                operation="single_step",
                new_status=self._processor_status,
                error=str(e),
            )

    async def pause_processing(self) -> ProcessorControlResponse:
        """Pause the processor."""
        try:
            _start_time = self._now()

            # Get the agent processor from runtime
            if not self.runtime or not hasattr(self.runtime, "agent_processor"):
                return ProcessorControlResponse(
                    success=False,
                    processor_name="agent",
                    operation="pause",
                    new_status=self._processor_status,
                    error=_ERROR_AGENT_PROCESSOR_NOT_AVAILABLE,
                )

            success = await self.runtime.agent_processor.pause_processing()
            if success:
                old_status = self._processor_status
                self._processor_status = ProcessorStatus.PAUSED
                if old_status != ProcessorStatus.PAUSED:
                    self._state_transitions += 1
                    self._pause_resume_cycles += 1
                self._commands_processed += 1
            await self._record_event("processor_control", "pause", success=success)

            return ProcessorControlResponse(
                success=success,
                processor_name="agent",
                operation="pause",
                new_status=self._processor_status,
                error=None if success else "Failed to pause processor",
            )

        except Exception as e:
            logger.error(f"Failed to pause processing: {e}", exc_info=True)
            await self._record_event("processor_control", "pause", success=False, error=str(e))
            return ProcessorControlResponse(
                success=False,
                processor_name="agent",
                operation="pause",
                new_status=self._processor_status,
                error=str(e),
            )

    async def resume_processing(self) -> ProcessorControlResponse:
        """Resume the processor."""
        try:
            _start_time = self._now()

            # Get the agent processor from runtime
            if not self.runtime or not hasattr(self.runtime, "agent_processor"):
                return ProcessorControlResponse(
                    success=False,
                    processor_name="agent",
                    operation="resume",
                    new_status=self._processor_status,
                    error=_ERROR_AGENT_PROCESSOR_NOT_AVAILABLE,
                )

            success = await self.runtime.agent_processor.resume_processing()
            if success:
                old_status = self._processor_status
                self._processor_status = ProcessorStatus.RUNNING
                if old_status != ProcessorStatus.RUNNING:
                    self._state_transitions += 1
                    self._pause_resume_cycles += 1
                self._commands_processed += 1
            await self._record_event("processor_control", "resume", success=success)

            return ProcessorControlResponse(
                success=success,
                processor_name="agent",
                operation="resume",
                new_status=self._processor_status,
                error=None if success else "Failed to resume processor",
            )

        except Exception as e:
            logger.error(f"Failed to resume processing: {e}", exc_info=True)
            await self._record_event("processor_control", "resume", success=False, error=str(e))
            return ProcessorControlResponse(
                success=False,
                processor_name="agent",
                operation="resume",
                new_status=self._processor_status,
                error=str(e),
            )

    async def request_state_transition(self, target_state: str, reason: str) -> bool:
        """Request a cognitive state transition.

        Args:
            target_state: Target state name (e.g., "DREAM", "PLAY", "SOLITUDE", "WORK")
            reason: Reason for the transition request

        Returns:
            True if transition was successful, False otherwise
        """
        try:
            if not self.runtime or not hasattr(self.runtime, "agent_processor"):
                logger.error("Cannot transition state: agent processor not available")
                return False

            agent_processor = self.runtime.agent_processor
            if not agent_processor:
                logger.error("Cannot transition state: agent processor is None")
                return False

            # Convert string to AgentState enum (values are lowercase)
            from ciris_engine.schemas.processors.states import AgentState

            try:
                target = AgentState(target_state.lower())
            except ValueError:
                logger.error(f"Invalid target state: {target_state}")
                return False

            current_state = agent_processor.state_manager.get_state()
            logger.info(f"State transition requested: {current_state.value} -> {target.value} (reason: {reason})")

            # Use the agent processor's _handle_state_transition method to properly
            # start/stop state-specific processors (like DreamProcessor)
            if hasattr(agent_processor, "_handle_state_transition"):
                await agent_processor._handle_state_transition(target)
                # Verify the transition happened
                success = agent_processor.state_manager.get_state() == target
            else:
                # Fallback to just state manager if _handle_state_transition not available
                success = await agent_processor.state_manager.transition_to(target)

            if success:
                self._state_transitions += 1
                logger.info(f"State transition successful: {current_state.value} -> {target.value}")
            else:
                logger.warning(f"State transition failed: {current_state.value} -> {target.value}")

            return bool(success)

        except Exception as e:
            logger.error(f"State transition failed: {e}", exc_info=True)
            return False

    async def get_processor_queue_status(self) -> ProcessorQueueStatus:
        """Get processor queue status."""
        try:
            if not self.runtime or not hasattr(self.runtime, "agent_processor"):
                return ProcessorQueueStatus(
                    processor_name="unknown",
                    queue_size=0,
                    max_size=0,
                    processing_rate=0.0,
                    average_latency_ms=0.0,
                    oldest_message_age_seconds=None,
                )

            # Check if agent processor is available
            if not hasattr(self.runtime, "agent_processor") or self.runtime.agent_processor is None:
                logger.debug("Agent processor not yet initialized, returning empty queue status")
                return ProcessorQueueStatus(
                    processor_name="agent",
                    queue_size=0,
                    max_size=1000,
                    processing_rate=0.0,
                    average_latency_ms=0.0,
                    oldest_message_age_seconds=None,
                )

            # Get queue status from agent processor
            queue_status = self.runtime.agent_processor.get_queue_status()

            await self._record_event("processor_query", "queue_status", success=True)

            return ProcessorQueueStatus(
                processor_name="agent",
                queue_size=queue_status.pending_thoughts + queue_status.pending_tasks,
                max_size=1000,  # Default max size
                processing_rate=self._calculate_processing_rate(),  # Seconds per thought (5-15 typical)
                average_latency_ms=self._calculate_average_latency(),
                oldest_message_age_seconds=None,
            )
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}", exc_info=True)
            await self._record_event("processor_query", "queue_status", success=False, error=str(e))
            return ProcessorQueueStatus(
                processor_name="agent",
                queue_size=0,
                max_size=0,
                processing_rate=0.0,
                average_latency_ms=0.0,
                oldest_message_age_seconds=None,
            )

    async def shutdown_runtime(self, reason: str = "Runtime shutdown requested") -> ProcessorControlResponse:
        """Shutdown the entire runtime system."""
        try:
            _start_time = self._now()

            logger.critical(f"RUNTIME SHUTDOWN INITIATED: {reason}")

            # Record the shutdown event
            await self._record_event("processor_control", "shutdown", success=True, result={"reason": reason})

            # Request global shutdown through the shutdown service
            if self.runtime and hasattr(self.runtime, "service_registry"):
                shutdown_service = self.runtime.service_registry.get_service("ShutdownService")
                if shutdown_service:
                    shutdown_service.request_shutdown(f"Runtime control: {reason}")
                else:
                    logger.error("ShutdownService not available in registry")

            # Set processor status to stopped
            self._processor_status = ProcessorStatus.STOPPED

            return ProcessorControlResponse(
                success=True,
                processor_name="agent",
                operation="shutdown",
                new_status=self._processor_status,
                error=None,
            )

        except Exception as e:
            logger.error(f"Failed to initiate shutdown: {e}", exc_info=True)
            await self._record_event("processor_control", "shutdown", success=False, error=str(e))
            return ProcessorControlResponse(
                success=False,
                processor_name="agent",
                operation="shutdown",
                new_status=self._processor_status,
                error=str(e),
            )

    async def handle_emergency_shutdown(self, command: WASignedCommand) -> EmergencyShutdownStatus:
        """
        Handle WA-authorized emergency shutdown command.

        Verifies WA signature and calls the shutdown service immediately.

        Args:
            command: Signed emergency shutdown command from WA

        Returns:
            Status of emergency shutdown process
        """
        logger.critical(f"EMERGENCY SHUTDOWN COMMAND RECEIVED from WA {command.wa_id}")

        # Initialize status
        now = self._now()

        status = EmergencyShutdownStatus(
            command_received=now,
            command_verified=False,
            verification_error=None,
            shutdown_initiated=None,
            data_persisted=False,
            final_message_sent=False,
            shutdown_completed=None,
            exit_code=None,
        )

        try:
            # Verify WA signature
            if not self._verify_wa_signature(command):
                status.command_verified = False
                status.verification_error = "Invalid WA signature"
                logger.error(f"Emergency shutdown rejected: Invalid signature from {command.wa_id}")
                return status

            status.command_verified = True
            status.shutdown_initiated = self._now()

            # Record emergency event
            await self._record_event(
                "emergency_shutdown",
                "command_verified",
                success=True,
                result={"wa_id": command.wa_id, "command_id": command.command_id, "reason": command.reason},
            )

            # Call the existing shutdown mechanism
            # This will trigger all registered shutdown handlers
            shutdown_reason = f"WA EMERGENCY SHUTDOWN: {command.reason} (WA: {command.wa_id})"

            # Get shutdown service from registry if available
            if self.runtime and hasattr(self.runtime, "service_registry"):
                # Fix: Provide both handler and service_type parameters
                shutdown_service = await self.runtime.service_registry.get_service(
                    handler="default", service_type=ServiceType.SHUTDOWN
                )
                if shutdown_service:
                    shutdown_service.request_shutdown(shutdown_reason)
                    status.shutdown_completed = self._now()
                    status.exit_code = 0
                    logger.info("Emergency shutdown delegated to ShutdownService")
                    return status

            # Fallback to direct shutdown
            await self.shutdown_runtime(shutdown_reason)
            status.shutdown_completed = self._now()
            status.exit_code = 0

            return status

        except Exception as e:
            logger.critical(f"Emergency shutdown failed: {e}")
            status.verification_error = str(e)
            status.shutdown_completed = self._now()
            status.exit_code = 1
            return status

    def _verify_wa_signature(self, command: WASignedCommand) -> bool:
        """
        Verify the WA signature on an emergency command.

        Args:
            command: The signed command to verify

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Check if WA is authorized
            if not self._wa_key_map.has_key(command.wa_id):
                logger.error(f"WA {command.wa_id} not in authorized keys")
                return False

            # Get public key PEM and convert to key object
            key_pem = self._wa_key_map.get_key(command.wa_id)
            if not key_pem:
                return False

            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key = serialization.load_pem_public_key(key_pem.encode("utf-8"))

            # Ensure it's an Ed25519 key
            if not isinstance(public_key, Ed25519PublicKey):
                logger.error(f"WA {command.wa_id} key is not Ed25519")
                return False

            # Reconstruct signed data (canonical form)
            signed_data = "|".join(
                [
                    f"command_id:{command.command_id}",
                    f"command_type:{command.command_type}",
                    f"wa_id:{command.wa_id}",
                    f"issued_at:{command.issued_at.isoformat()}",
                    f"reason:{command.reason}",
                ]
            )

            if command.target_agent_id:
                signed_data += f"|target_agent_id:{command.target_agent_id}"

            # Verify signature
            from cryptography.exceptions import InvalidSignature

            try:
                signature_bytes = bytes.fromhex(command.signature)
                public_key.verify(signature_bytes, signed_data.encode("utf-8"))
                return True
            except InvalidSignature:
                logger.error("Invalid signature on emergency command")
                return False

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    def _configure_kill_switch(self, config: KillSwitchConfig) -> None:
        """
        Configure the emergency kill switch.

        Args:
            config: Kill switch configuration including root WA keys
        """
        self._kill_switch_config = config

        # Parse and store WA public keys
        from cryptography.hazmat.primitives import serialization

        self._wa_key_map.clear()
        for key_pem in config.root_wa_public_keys:
            try:
                # Validate that it's a valid Ed25519 key
                public_key = serialization.load_pem_public_key(key_pem.encode("utf-8"))
                # Import the actual type for isinstance check
                from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey as Ed25519PublicKeyImpl

                if isinstance(public_key, Ed25519PublicKeyImpl):
                    # Extract WA ID from comment or use hash
                    wa_id = self._extract_wa_id_from_pem(key_pem)
                    self._wa_key_map.add_key(wa_id, key_pem)
            except Exception as e:
                logger.error(f"Failed to load WA public key: {e}")

        logger.info(f"Kill switch configured with {self._wa_key_map.count()} root WA keys")

    def _extract_wa_id_from_pem(self, key_pem: str) -> str:
        """Extract WA ID from PEM comment or generate from hash."""
        for line in key_pem.split("\n"):
            if line.startswith("# WA-ID:"):
                return line.split(":", 1)[1].strip()

        # Fallback to hash
        import hashlib

        return hashlib.sha256(key_pem.encode()).hexdigest()[:16]

    def _ensure_adapter_manager(self) -> bool:
        """Lazy-initialize adapter_manager if needed. Returns True if available."""
        if self.adapter_manager:
            return True

        if not self.runtime:
            return False

        if self._time_service is None:
            from ciris_engine.logic.services.lifecycle.time import TimeService

            self._time_service = TimeService()

        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        self.adapter_manager = RuntimeAdapterManager(cast(CIRISRuntime, self.runtime), self._time_service)
        logger.info("Lazy-initialized adapter_manager")
        return True

    def _convert_to_adapter_config(
        self, adapter_type: str, config: Optional[Dict[str, object]]
    ) -> Optional[AdapterConfig]:
        """Convert config dict to AdapterConfig if needed."""
        if not config:
            return None

        if isinstance(config, AdapterConfig):
            return config

        if "adapter_type" in config:
            return AdapterConfig(**config)

        return AdapterConfig(
            adapter_type=adapter_type,
            enabled=True,
            adapter_config=config,
        )

    # Adapter Management Methods
    async def load_adapter(
        self,
        adapter_type: str,
        adapter_id: Optional[str] = None,
        config: Optional[Dict[str, object]] = None,
        auto_start: bool = True,
    ) -> AdapterOperationResponse:
        """Load a new adapter instance."""
        if not self._ensure_adapter_manager():
            return AdapterOperationResponse(
                success=False,
                timestamp=self._now(),
                adapter_id=adapter_id or "unknown",
                adapter_type=adapter_type,
                status=AdapterStatus.ERROR,
                error="Adapter manager not available",
            )

        assert self.adapter_manager is not None  # Guaranteed by _ensure_adapter_manager
        adapter_config = self._convert_to_adapter_config(adapter_type, config)
        result = await self.adapter_manager.load_adapter(adapter_type, adapter_id or "", adapter_config)

        return AdapterOperationResponse(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=adapter_type,
            timestamp=self._now(),
            status=AdapterStatus.RUNNING if result.success else AdapterStatus.ERROR,
            error=result.error,
        )

    async def unload_adapter(self, adapter_id: str, force: bool = False) -> AdapterOperationResponse:
        """Unload an adapter instance."""
        logger.warning(
            f"RuntimeControlService.unload_adapter called: adapter_id={adapter_id}, "
            f"has_adapter_manager={self.adapter_manager is not None}, "
            f"adapter_manager_id={id(self.adapter_manager) if self.adapter_manager else None}, "
            f"has_runtime={self.runtime is not None}, "
            f"service_id={id(self)}"
        )

        if not self._ensure_adapter_manager():
            return AdapterOperationResponse(
                success=False,
                timestamp=self._now(),
                adapter_id=adapter_id or "unknown",
                adapter_type="unknown",
                status=AdapterStatus.ERROR,
                error="Adapter manager not available",
            )

        assert self.adapter_manager is not None  # Guaranteed by _ensure_adapter_manager
        result = await self.adapter_manager.unload_adapter(adapter_id)

        return AdapterOperationResponse(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=result.adapter_type or "unknown",
            timestamp=self._now(),
            status=AdapterStatus.STOPPED if result.success else AdapterStatus.ERROR,
            error=result.error,
        )

    async def list_adapters(self) -> List[AdapterInfo]:
        """List all loaded adapters including bootstrap adapters."""
        self._ensure_adapter_manager_initialized()

        adapters_list: List[AdapterInfo] = []
        adapters_list.extend(await self._get_bootstrap_adapters())
        adapters_list.extend(await self._get_managed_adapters())

        return adapters_list

    def _ensure_adapter_manager_initialized(self) -> None:
        """Ensure adapter manager is initialized lazily."""
        if not self.adapter_manager and self.runtime:
            if self._time_service is None:
                from ciris_engine.logic.services.lifecycle.time import TimeService

                self._time_service = TimeService()

            from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

            self.adapter_manager = RuntimeAdapterManager(cast(CIRISRuntime, self.runtime), self._time_service)
            logger.info("Lazy-initialized adapter_manager in list_adapters")

    async def _get_bootstrap_adapters(self) -> List[AdapterInfo]:
        """Get bootstrap adapters from runtime."""
        adapters: List[AdapterInfo] = []

        if not (self.runtime and hasattr(self.runtime, "adapters")):
            return adapters

        for adapter in self.runtime.adapters:
            adapter_type = self._extract_adapter_type(adapter)

            if await self._should_skip_bootstrap_adapter(adapter_type):
                continue

            adapter_info = await self._create_bootstrap_adapter_info(adapter, adapter_type)
            adapters.append(adapter_info)

        return adapters

    def _extract_adapter_type(self, adapter: Any) -> str:
        """Extract adapter type from class name."""
        class_name: str = adapter.__class__.__name__
        return class_name.lower().replace("platform", "").replace("adapter", "")

    async def _should_skip_bootstrap_adapter(self, adapter_type: str) -> bool:
        """Check if bootstrap adapter should be skipped because it's managed."""
        if adapter_type != "discord" or not self.adapter_manager:
            return False

        adapter_list = await self.adapter_manager.list_adapters()
        return any(a.adapter_type == "discord" for a in adapter_list)

    async def _create_bootstrap_adapter_info(self, adapter: Any, adapter_type: str) -> AdapterInfo:
        """Create AdapterInfo for a bootstrap adapter."""
        tools = await self._extract_adapter_tools(adapter, adapter_type)

        return AdapterInfo(
            adapter_id=f"{adapter_type}_bootstrap",
            adapter_type=adapter_type,
            status=AdapterStatus.RUNNING,  # Bootstrap adapters are always running
            started_at=self._start_time,  # Use service start time
            messages_processed=0,  # Tracked via telemetry service
            error_count=0,
            last_error=None,
            tools=tools,
        )

    async def _extract_adapter_tools(self, adapter: Any, adapter_type: str) -> List[ToolInfo]:
        """Extract tools from adapter tool service."""
        tools: List[ToolInfo] = []

        if not (hasattr(adapter, "tool_service") and adapter.tool_service):
            return tools

        try:
            if hasattr(adapter.tool_service, "list_tools"):
                tool_names = await adapter.tool_service.list_tools()
                for tool_name in tool_names:
                    tool_info = await self._create_tool_info(adapter.tool_service, tool_name)
                    if tool_info:
                        tools.append(tool_info)
        except Exception as e:
            logger.debug(f"Could not get tools from {adapter_type}: {e}")

        return tools

    async def _create_tool_info(self, tool_service: Any, tool_name: str) -> Optional[ToolInfo]:
        """Create ToolInfo object from tool service."""
        try:
            # Default parameters schema
            default_parameters = ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            )

            # Try to get schema from tool service
            parameters = default_parameters
            if hasattr(tool_service, "get_tool_schema"):
                schema = await tool_service.get_tool_schema(tool_name)
                if schema:
                    # Convert schema to ToolParameterSchema
                    if isinstance(schema, dict):
                        parameters = ToolParameterSchema(
                            type=schema.get("type", "object"),
                            properties=schema.get("properties", {}),
                            required=schema.get("required", []),
                        )
                    elif hasattr(schema, "model_dump"):
                        schema_dict = schema.model_dump()
                        parameters = ToolParameterSchema(
                            type=schema_dict.get("type", "object"),
                            properties=schema_dict.get("properties", {}),
                            required=schema_dict.get("required", []),
                        )

            return ToolInfo(
                name=tool_name,
                description=f"{tool_name} tool",
                parameters=parameters,
            )
        except Exception as e:
            logger.debug(f"Could not create ToolInfo for {tool_name}: {e}")
            return None

    async def _get_managed_adapters(self) -> List[AdapterInfo]:
        """Get adapters from adapter manager."""
        if not self.adapter_manager:
            return []

        adapters = []
        adapters_raw = await self.adapter_manager.list_adapters()

        for adapter_status in adapters_raw:
            adapter_info = self._convert_managed_adapter_status(adapter_status)
            adapters.append(adapter_info)

        return adapters

    def _convert_managed_adapter_status(self, adapter_status: Any) -> AdapterInfo:
        """Convert adapter manager status to AdapterInfo."""
        status = AdapterStatus.RUNNING if adapter_status.is_running else AdapterStatus.STOPPED

        return AdapterInfo(
            adapter_id=adapter_status.adapter_id,
            adapter_type=adapter_status.adapter_type,
            status=status,
            started_at=adapter_status.loaded_at,
            messages_processed=self._safe_get_metric(adapter_status, "messages_processed", 0),
            error_count=self._safe_get_metric(adapter_status, "errors_count", 0),
            last_error=self._safe_get_metric(adapter_status, "last_error", None),
            tools=adapter_status.tools if hasattr(adapter_status, "tools") else None,
        )

    def _safe_get_metric(self, adapter_status: Any, metric_name: str, default: Any) -> Any:
        """Safely get metric value from adapter status."""
        if adapter_status.metrics and hasattr(adapter_status.metrics, "get"):
            return adapter_status.metrics.get(metric_name, default)
        return default

    async def get_adapter_info(self, adapter_id: str) -> Optional[AdapterInfo]:
        """Get detailed information about a specific adapter."""
        # Lazy initialization of adapter_manager if needed
        if not self.adapter_manager and self.runtime:
            if self._time_service is None:
                from ciris_engine.logic.services.lifecycle.time import TimeService

                self._time_service = TimeService()
            from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

            self.adapter_manager = RuntimeAdapterManager(cast(CIRISRuntime, self.runtime), self._time_service)
            logger.info("Lazy-initialized adapter_manager in get_adapter_info")

        if not self.adapter_manager:
            return None

        info = self.adapter_manager.get_adapter_info(adapter_id)
        if info is None:
            return None

        # Convert adapter_management.AdapterInfo to core.runtime.AdapterInfo
        from datetime import datetime

        return AdapterInfo(
            adapter_id=info.adapter_id,
            adapter_type=info.adapter_type,
            status=AdapterStatus.RUNNING if info.is_running else AdapterStatus.STOPPED,
            started_at=datetime.fromisoformat(info.load_time) if info.load_time else None,
            messages_processed=0,  # Not tracked in adapter_management.AdapterInfo
            error_count=0,  # Not tracked in adapter_management.AdapterInfo
            last_error=None,
            tools=None,
        )

    # Configuration Management Methods
    async def get_config(self, path: Optional[str] = None, include_sensitive: bool = False) -> ConfigSnapshot:
        """Get configuration value(s)."""
        try:
            # Get all configs or specific config
            config_value_map = ConfigValueMap()

            if path:
                config_node = await self._get_config_manager().get_config(path)
                if config_node:
                    # Extract actual value from ConfigValue wrapper
                    actual_value = config_node.value.value
                    if actual_value is not None:
                        config_value_map.set(path, actual_value)
            else:
                # list_configs returns Dict[str, Union[str, int, float, bool, List, Dict]]
                all_configs = await self._get_config_manager().list_configs()
                config_value_map.update(all_configs)

            # Determine sensitive keys
            sensitive_keys = []
            if not include_sensitive:
                # Mark which keys would be sensitive
                from ciris_engine.schemas.api.config_security import ConfigSecurity

                for key in config_value_map.keys():
                    if ConfigSecurity.is_sensitive(key):
                        sensitive_keys.append(key)

            return ConfigSnapshot(
                configs=config_value_map.configs,
                version=self.config_version if hasattr(self, "config_version") else "1.0.0",
                sensitive_keys=sensitive_keys,
                metadata={"path_filter": path, "include_sensitive": include_sensitive},
            )
        except Exception as e:
            logger.error(f"Failed to get config: {e}")
            return ConfigSnapshot(configs={}, version="unknown", metadata={"error": str(e)})

    async def update_config(
        self,
        path: str,
        value: object,
        scope: str = "runtime",
        validation_level: str = "full",
        reason: Optional[str] = None,
    ) -> ConfigOperationResponse:
        """Update a configuration value."""
        try:
            # GraphConfigService uses set_config, not update_config_value
            # Convert object to appropriate type
            config_value = value if isinstance(value, (str, int, float, bool, list, dict)) else str(value)
            await self._get_config_manager().set_config(path, config_value, updated_by="RuntimeControlService")
            result = ConfigOperationResponse(
                success=True,
                operation="update_config",
                config_path=path,
                details={
                    "scope": scope,
                    "validation_level": validation_level,
                    "reason": reason,
                    "timestamp": self._now().isoformat(),
                },
                error=None,
            )
            if result.success:
                self._last_config_change = self._now()
            return result
        except Exception as e:
            logger.error(f"Failed to update config: {e}")
            return ConfigOperationResponse(
                success=False,
                operation="update_config",
                config_path=path,
                details={"timestamp": self._now().isoformat()},
                error=str(e),
            )

    async def validate_config(
        self, config_data: Dict[str, object], config_path: Optional[str] = None
    ) -> ConfigValidationResponse:
        """Validate configuration data."""
        try:
            # GraphConfigService doesn't have validate_config, do basic validation
            return ConfigValidationResponse(
                valid=True, validation_level=ConfigValidationLevel.SYNTAX, errors=[], warnings=[], suggestions=[]
            )
        except Exception as e:
            logger.error(f"Failed to validate config: {e}")
            return ConfigValidationResponse(
                valid=False, validation_level=ConfigValidationLevel.SYNTAX, errors=[str(e)], warnings=[], suggestions=[]
            )

    async def backup_config(self, backup_name: Optional[str] = None) -> ConfigOperationResponse:
        """Create a configuration backup."""
        try:
            # GraphConfigService doesn't have backup_config, store as special config
            all_configs = await self._get_config_manager().list_configs()
            backup_key = f"backup_{backup_name or self._now().strftime('%Y%m%d_%H%M%S')}"

            # Create backup data using the schema
            backup_data = ConfigBackupData(
                configs=all_configs, backup_version="1.0.0", backup_by="RuntimeControlService"
            )

            # Store the backup
            await self._get_config_manager().set_config(
                backup_key, backup_data.to_config_value(), updated_by="RuntimeControlService"
            )

            # Convert ConfigBackupData to ConfigOperationResponse
            return ConfigOperationResponse(
                success=True,
                operation="backup_config",
                config_path="config",
                details={
                    "timestamp": backup_data.backup_timestamp.isoformat(),
                    "backup_id": backup_key,
                    "backup_name": backup_name,
                    "size_bytes": len(str(all_configs)),
                },
                error=None,
            )
        except Exception as e:
            logger.error(f"Failed to backup config: {e}")
            return ConfigOperationResponse(
                success=False,
                operation="backup_config",
                config_path="config",
                details={"timestamp": self._now().isoformat()},
                error=str(e),
            )

    async def restore_config(self, backup_name: str) -> ConfigOperationResponse:
        """Restore configuration from backup."""
        try:
            backup_config = await self._get_config_manager().get_config(backup_name)
            if not backup_config:
                raise ValueError(f"Backup '{backup_name}' not found")

            actual_backup = self._extract_backup_configs(backup_config)
            await self._restore_configs_from_backup(actual_backup)

            return ConfigOperationResponse(
                success=True,
                operation="restore_config",
                config_path="config",
                details={
                    "backup_name": backup_name,
                    "timestamp": self._now().isoformat(),
                    "message": f"Restored from backup {backup_name}",
                },
                error=None,
            )
        except Exception as e:
            logger.error(f"Failed to restore config: {e}")
            return ConfigOperationResponse(
                success=False,
                operation="restore_config",
                config_path="config",
                details={"backup_name": backup_name, "timestamp": self._now().isoformat()},
                error=str(e),
            )

    def _extract_backup_configs(self, backup_config: Any) -> ConfigDict:
        """Extract backup configuration data from ConfigValue wrapper."""
        backup_raw = backup_config.value
        backup_value = backup_raw.value if hasattr(backup_raw, "value") else backup_raw

        if isinstance(backup_value, dict) and "configs" in backup_value:
            return self._parse_structured_backup(backup_value)
        elif isinstance(backup_value, dict):
            # Filter out None values to match the expected type
            result: ConfigDict = {}
            for k, v in backup_value.items():
                if v is not None and isinstance(v, (str, int, float, bool, list, dict)):
                    result[k] = v
            return result
        else:
            raise ValueError("Backup data is not in expected format")

    def _parse_structured_backup(self, backup_value: JSONDict) -> ConfigDict:
        """Parse structured backup data with metadata."""
        timestamp_str = backup_value.get("backup_timestamp")
        if not isinstance(timestamp_str, str):
            raise ValueError("backup_timestamp must be a string")

        backup_data = ConfigBackupData(
            configs=backup_value["configs"],
            backup_timestamp=datetime.fromisoformat(timestamp_str),
            backup_version=str(backup_value.get("backup_version", "1.0.0")),
            backup_by=str(backup_value.get("backup_by", "RuntimeControlService")),
        )
        return backup_data.configs

    async def _restore_configs_from_backup(self, configs: ConfigDict) -> None:
        """Restore individual configuration values from backup."""
        for key, value in configs.items():
            if not key.startswith("backup_"):  # Don't restore backups
                config_val = value if isinstance(value, (str, int, float, bool, list, dict)) else str(value)
                await self._get_config_manager().set_config(key, config_val, "RuntimeControlService")

    async def list_config_backups(self) -> List[ConfigBackup]:
        """List available configuration backups."""
        try:
            # List all backup configs
            all_configs = await self._get_config_manager().list_configs(prefix="backup_")
            backups = []
            for key, value in all_configs.items():
                backup = ConfigBackup(
                    backup_id=key,
                    created_at=self._now(),  # Would need to store this in config
                    config_version="1.0.0",
                    size_bytes=len(str(value)),
                    path=key,
                    description=None,
                )
                backups.append(backup)
            return backups
        except Exception as e:
            logger.error(f"Failed to list config backups: {e}")
            return []

    async def get_runtime_status(self) -> RuntimeStatusResponse:
        """Get current runtime status."""
        try:
            current_time = self._now()
            uptime = (current_time - self._start_time).total_seconds()  # type: ignore[operator]

            # Get adapter information
            adapters = []
            if self.adapter_manager:
                adapters = await self.adapter_manager.list_adapters()
            _active_adapters = [a.adapter_id for a in adapters if a.is_running]
            _loaded_adapters = [a.adapter_id for a in adapters]

            # Agent identity is now stored in graph, not profiles
            _current_profile = "identity-based"

            # Get agent processor state and queue info
            processor_paused = False
            cognitive_state = None
            queue_depth = 0

            if self.runtime and hasattr(self.runtime, "agent_processor") and self.runtime.agent_processor:
                processor_paused = getattr(self.runtime.agent_processor, "_is_paused", False)
                cognitive_state = str(getattr(self.runtime.agent_processor, "_current_state", None))

                # Get actual queue depth using existing processor queue status method
                try:
                    processor_queue_status = await self.get_processor_queue_status()
                    queue_depth = processor_queue_status.queue_size
                except Exception as e:
                    logger.warning(f"Failed to get queue depth from processor queue status: {e}")
                    queue_depth = 0

            # Determine processor status
            if processor_paused:
                processor_status = ProcessorStatus.PAUSED
            elif self._processor_status == ProcessorStatus.RUNNING:
                processor_status = ProcessorStatus.RUNNING
            else:
                processor_status = self._processor_status

            return RuntimeStatusResponse(
                is_running=self._processor_status == ProcessorStatus.RUNNING,
                uptime_seconds=uptime,
                processor_count=1,  # Single agent processor
                adapter_count=len(adapters),
                total_messages_processed=self._messages_processed,
                current_load=self._calculate_current_load(),
                processor_status=processor_status,
                cognitive_state=cognitive_state,
                queue_depth=queue_depth,
            )

        except Exception as e:
            logger.error(f"Failed to get runtime status: {e}")
            return RuntimeStatusResponse(
                is_running=False,
                uptime_seconds=0.0,
                processor_count=1,
                adapter_count=0,
                total_messages_processed=0,
                current_load=0.0,
                processor_status=ProcessorStatus.ERROR,
                cognitive_state=None,
                queue_depth=0,
            )

    async def get_runtime_snapshot(self) -> RuntimeStateSnapshot:
        """Get complete runtime state snapshot."""
        try:
            current_time = self._now()

            # Get runtime status
            runtime_status = await self.get_runtime_status()

            # Get processor queue status
            processor_queue = await self.get_processor_queue_status()
            processors = [processor_queue]

            # Get adapters
            adapters = await self.list_adapters()

            # Get config version
            config_snapshot = await self.get_config()
            config_version = config_snapshot.version

            # Get health summary
            health_summary = await self.get_service_health_status()

            return RuntimeStateSnapshot(
                timestamp=current_time,
                runtime_status=runtime_status,
                processors=processors,
                adapters=adapters,
                config_version=config_version,
                health_summary=health_summary,
            )

        except Exception as e:
            logger.error(f"Failed to get runtime snapshot: {e}")
            raise

    async def _get_service_registry_info(
        self, handler: Optional[str] = None, service_type: Optional[str] = None
    ) -> ServiceRegistryInfoResponse:
        """Get information about registered services in the service registry."""
        try:
            if (
                not self.runtime
                or not hasattr(self.runtime, "service_registry")
                or self.runtime.service_registry is None
            ):
                # Return a valid ServiceRegistryInfoResponse with empty data
                return ServiceRegistryInfoResponse(
                    total_services=0, services_by_type={}, handlers={}, healthy_services=0, circuit_breaker_states={}
                )

            info = self.runtime.service_registry.get_provider_info(handler, service_type)

            # Convert the dict to ServiceRegistryInfoResponse
            if isinstance(info, dict):
                # Extract handler services with full details
                handlers_dict: Dict[str, Dict[str, List[ServiceProviderInfo]]] = {}
                for handler_name, services in info.get("handlers", {}).items():
                    service_dict: Dict[str, List[ServiceProviderInfo]] = {}
                    for service_type_name, providers in services.items():
                        # Convert provider dicts to ServiceProviderInfo objects
                        provider_infos = [ServiceProviderInfo(**p) for p in providers]
                        service_dict[service_type_name] = provider_infos
                    handlers_dict[handler_name] = service_dict

                # Extract global services if present
                global_services: Optional[Dict[str, List[ServiceProviderInfo]]] = None
                if "global_services" in info:
                    global_services_dict: Dict[str, List[ServiceProviderInfo]] = {}
                    for service_type_name, providers in info["global_services"].items():
                        provider_infos = [ServiceProviderInfo(**p) for p in providers]
                        global_services_dict[service_type_name] = provider_infos
                    global_services = global_services_dict

                return ServiceRegistryInfoResponse(
                    total_services=info.get("total_services", 0),
                    services_by_type=info.get("services_by_type", {}),
                    handlers=handlers_dict,
                    global_services=global_services,
                    healthy_services=info.get("healthy_services", 0),
                    circuit_breaker_states=info.get("circuit_breaker_states", {}),
                )
            else:
                # Fallback if info is not a dict
                return ServiceRegistryInfoResponse(
                    total_services=0, services_by_type={}, handlers={}, healthy_services=0, circuit_breaker_states={}
                )
        except Exception as e:
            logger.error(f"Failed to get service registry info: {e}")
            # Return empty ServiceRegistryInfoResponse on error
            return ServiceRegistryInfoResponse(
                total_services=0,
                services_by_type={},
                handlers={},
                healthy_services=0,
                circuit_breaker_states={},
                error=str(e),
            )

    async def update_service_priority(
        self,
        provider_name: str,
        new_priority: str,
        new_priority_group: Optional[int] = None,
        new_strategy: Optional[str] = None,
    ) -> ServicePriorityUpdateResponse:
        """Update service provider priority and selection strategy."""
        try:
            if not self._has_service_registry():
                return ServicePriorityUpdateResponse(
                    success=False, provider_name=provider_name, error=_ERROR_SERVICE_REGISTRY_NOT_AVAILABLE
                )

            validation_result = self._validate_priority_and_strategy(provider_name, new_priority, new_strategy)
            if validation_result is not None:
                return validation_result

            new_priority_enum, new_strategy_enum = self._parse_priority_and_strategy(new_priority, new_strategy)

            update_result = await self._update_provider_priority(
                provider_name, new_priority_enum, new_priority_group, new_strategy_enum
            )

            return update_result

        except Exception as e:
            logger.error(f"Failed to update service priority: {e}")
            await self._record_event("service_management", "update_priority", success=False, error=str(e))
            return ServicePriorityUpdateResponse(success=False, provider_name=provider_name, error=str(e))

    def _has_service_registry(self) -> bool:
        """Check if service registry is available."""
        return self.runtime is not None and hasattr(self.runtime, "service_registry")

    def _validate_priority_and_strategy(
        self, provider_name: str, new_priority: str, new_strategy: Optional[str]
    ) -> Optional[ServicePriorityUpdateResponse]:
        """Validate priority and strategy parameters. Return error response if invalid, None if valid."""
        from ciris_engine.logic.registries.base import Priority, SelectionStrategy

        # Validate priority
        try:
            Priority[new_priority.upper()]
        except KeyError:
            valid_priorities = [p.name for p in Priority]
            return ServicePriorityUpdateResponse(
                success=False,
                provider_name=provider_name,
                error=f"Invalid priority '{new_priority}'. Valid priorities: {valid_priorities}",
            )

        # Validate strategy if provided
        if new_strategy:
            try:
                SelectionStrategy[new_strategy.upper()]
            except KeyError:
                valid_strategies = [s.name for s in SelectionStrategy]
                return ServicePriorityUpdateResponse(
                    success=False,
                    provider_name=provider_name,
                    error=f"Invalid strategy '{new_strategy}'. Valid strategies: {valid_strategies}",
                )

        return None  # Valid

    def _parse_priority_and_strategy(self, new_priority: str, new_strategy: Optional[str]) -> tuple[Any, Optional[Any]]:
        """Parse and return priority and strategy enums."""
        from ciris_engine.logic.registries.base import Priority, SelectionStrategy

        new_priority_enum = Priority[new_priority.upper()]
        new_strategy_enum = SelectionStrategy[new_strategy.upper()] if new_strategy else None

        return new_priority_enum, new_strategy_enum

    async def _update_provider_priority(
        self,
        provider_name: str,
        new_priority_enum: Any,
        new_priority_group: Optional[int],
        new_strategy_enum: Optional[Any],
    ) -> ServicePriorityUpdateResponse:
        """Update the provider priority in the registry."""
        if not self.runtime or not hasattr(self.runtime, "service_registry"):
            return ServicePriorityUpdateResponse(
                success=False, provider_name=provider_name, error="Service registry not available"
            )

        registry = self.runtime.service_registry

        provider_info = self._find_provider_in_registry(registry, provider_name)
        if not provider_info:
            return ServicePriorityUpdateResponse(
                success=False,
                provider_name=provider_name,
                error=f"Service provider '{provider_name}' not found in registry",
            )

        updated_info = self._apply_priority_updates(
            provider_info, new_priority_enum, new_priority_group, new_strategy_enum
        )

        await self._record_event(
            "service_management", "update_priority", success=True, result=updated_info.model_dump()
        )
        logger.info(
            f"Updated service provider '{provider_name}' priority from "
            f"{updated_info.old_priority} to {updated_info.new_priority}"
        )

        return ServicePriorityUpdateResponse(
            success=True,
            message=f"Successfully updated provider '{provider_name}' priority",
            provider_name=provider_name,
            changes=updated_info,
            timestamp=self._now(),
        )

    def _find_provider_in_registry(self, registry: Any, provider_name: str) -> Optional[_ProviderLookupResult]:
        """Find a provider in the service registry."""
        for service_type, providers in registry._services.items():
            for provider in providers:
                if provider.name == provider_name:
                    return _ProviderLookupResult(
                        provider=provider, providers_list=providers, service_type=str(service_type)
                    )
        return None

    def _apply_priority_updates(
        self,
        provider_info: _ProviderLookupResult,
        new_priority_enum: Any,
        new_priority_group: Optional[int],
        new_strategy_enum: Optional[Any],
    ) -> ServiceProviderUpdate:
        """Apply priority and strategy updates to provider."""
        provider = provider_info.provider
        providers_list = provider_info.providers_list

        old_priority = provider.priority.name
        old_priority_group = provider.priority_group
        old_strategy = provider.strategy.name

        # Update provider attributes
        provider.priority = new_priority_enum
        if new_priority_group is not None:
            provider.priority_group = new_priority_group
        if new_strategy_enum is not None:
            provider.strategy = new_strategy_enum

        # Re-sort providers by priority
        providers_list.sort(key=lambda x: (x.priority_group, x.priority.value))

        return ServiceProviderUpdate(
            service_type=provider_info.service_type,
            old_priority=old_priority,
            new_priority=provider.priority.name,
            old_priority_group=old_priority_group,
            new_priority_group=provider.priority_group,
            old_strategy=old_strategy,
            new_strategy=provider.strategy.name,
        )

    async def reset_circuit_breakers(self, service_type: Optional[str] = None) -> CircuitBreakerResetResponse:
        """Reset circuit breakers for services."""
        try:
            if not self._has_circuit_breaker_registry():
                return CircuitBreakerResetResponse(
                    success=False,
                    message=_ERROR_SERVICE_REGISTRY_NOT_AVAILABLE,
                    timestamp=self._now(),
                    service_type=service_type,
                    error=_ERROR_SERVICE_REGISTRY_NOT_AVAILABLE,
                )

            if service_type:
                reset_result = await self._reset_specific_service_type_breakers(service_type)
            else:
                reset_result = await self._reset_all_circuit_breakers()

            if not reset_result.success:
                return reset_result

            await self._record_event(
                "service_management",
                "reset_circuit_breakers",
                True,
                result={"service_type": service_type, "providers_reset": reset_result.reset_count},
            )

            return reset_result

        except Exception as e:
            logger.error(f"Failed to reset circuit breakers: {e}")
            await self._record_event("service_management", "reset_circuit_breakers", False, error=str(e))
            return CircuitBreakerResetResponse(
                success=False,
                message=f"Failed to reset circuit breakers: {str(e)}",
                timestamp=self._now(),
                service_type=service_type,
                error=str(e),
            )

    def _has_circuit_breaker_registry(self) -> bool:
        """Check if service registry is available for circuit breaker operations."""
        return (
            self.runtime is not None
            and hasattr(self.runtime, "service_registry")
            and self.runtime.service_registry is not None
        )

    async def _reset_specific_service_type_breakers(self, service_type: str) -> CircuitBreakerResetResponse:
        """Reset circuit breakers for a specific service type."""
        from ciris_engine.schemas.runtime.enums import ServiceType

        try:
            service_type_enum = ServiceType(service_type)
            providers_reset = self._reset_providers_by_service_type(service_type_enum)
            message = f"Reset {len(providers_reset)} circuit breakers for {service_type} services"

            return CircuitBreakerResetResponse(
                success=True,
                message=message,
                timestamp=self._now(),
                service_type=service_type,
                reset_count=len(providers_reset),
            )
        except ValueError:
            return CircuitBreakerResetResponse(
                success=False,
                message=f"Invalid service type: {service_type}",
                timestamp=self._now(),
                service_type=service_type,
                error=f"Invalid service type: {service_type}",
            )

    def _reset_providers_by_service_type(self, service_type_enum: Any) -> List[str]:
        """Reset circuit breakers for providers of a specific service type."""
        providers_reset: List[str] = []

        if not self.runtime or not hasattr(self.runtime, "service_registry"):
            return providers_reset

        if service_type_enum in self.runtime.service_registry._services:
            for provider in self.runtime.service_registry._services[service_type_enum]:
                if provider.circuit_breaker:
                    provider.circuit_breaker.reset()
                    providers_reset.append(provider.name)

        return providers_reset

    async def _reset_all_circuit_breakers(self) -> CircuitBreakerResetResponse:
        """Reset all circuit breakers in the registry."""
        if not self.runtime or not hasattr(self.runtime, "service_registry"):
            return CircuitBreakerResetResponse(
                success=False,
                message="Service registry not available",
                timestamp=self._now(),
                service_type=None,
                error="Service registry not available",
            )

        self.runtime.service_registry.reset_circuit_breakers()
        providers_reset = list(self.runtime.service_registry._circuit_breakers.keys())
        message = f"Reset all {len(providers_reset)} circuit breakers"

        return CircuitBreakerResetResponse(
            success=True,
            message=message,
            timestamp=self._now(),
            service_type=None,
            reset_count=len(providers_reset),
        )

    async def get_circuit_breaker_status(self, service_type: Optional[str] = None) -> Dict[str, CircuitBreakerStatus]:
        """Get circuit breaker status for services."""
        try:
            if (
                not self.runtime
                or not hasattr(self.runtime, "service_registry")
                or self.runtime.service_registry is None
            ):
                return {}

            registry_info = self.runtime.service_registry.get_provider_info(service_type=service_type)
            circuit_breakers: Dict[str, CircuitBreakerStatus] = {}

            # Process handler services
            for handler, services in registry_info.get("handlers", {}).items():
                for svc_type, providers in services.items():
                    if service_type and svc_type != service_type:
                        continue

                    for provider in providers:
                        service_name = f"{handler}.{svc_type}.{provider['name']}"
                        cb_state_str = provider.get("circuit_breaker_state", "closed")

                        # Map string state to enum
                        if cb_state_str == "closed":
                            cb_state = CircuitBreakerState.CLOSED
                        elif cb_state_str == "open":
                            cb_state = CircuitBreakerState.OPEN
                        else:
                            cb_state = CircuitBreakerState.HALF_OPEN

                        circuit_breakers[service_name] = CircuitBreakerStatus(
                            state=cb_state,
                            failure_count=0,  # Would need to get from actual circuit breaker
                            service_name=service_name,
                            trip_threshold=5,
                            reset_timeout_seconds=60.0,
                        )

            # Process global services
            for svc_type, providers in registry_info.get("global_services", {}).items():
                if service_type and svc_type != service_type:
                    continue

                for provider in providers:
                    service_name = f"global.{svc_type}.{provider['name']}"
                    cb_state_str = provider.get("circuit_breaker_state", "closed")

                    # Map string state to enum
                    if cb_state_str == "closed":
                        cb_state = CircuitBreakerState.CLOSED
                    elif cb_state_str == "open":
                        cb_state = CircuitBreakerState.OPEN
                    else:
                        cb_state = CircuitBreakerState.HALF_OPEN

                    circuit_breakers[service_name] = CircuitBreakerStatus(
                        state=cb_state,
                        failure_count=0,
                        service_name=service_name,
                        trip_threshold=5,
                        reset_timeout_seconds=60.0,
                    )

            return circuit_breakers

        except Exception as e:
            logger.error(f"Failed to get circuit breaker status: {e}")
            return {}

    async def get_service_selection_explanation(self) -> ServiceSelectionExplanation:
        """Get explanation of service selection logic."""
        try:

            explanation = ServiceSelectionExplanation(
                overview="CIRIS uses a sophisticated multi-level service selection system with priority groups, priorities, and selection strategies.",
                priority_groups={
                    0: "Primary services - tried first",
                    1: "Secondary/backup services - used when primary unavailable",
                    2: "Tertiary/fallback services - last resort (e.g., mock providers)",
                },
                priorities={
                    "CRITICAL": {"value": 0, "description": "Highest priority - always tried first within a group"},
                    "HIGH": {"value": 1, "description": "High priority services"},
                    "NORMAL": {"value": 2, "description": "Standard priority (default)"},
                    "LOW": {"value": 3, "description": "Low priority services"},
                    "FALLBACK": {"value": 9, "description": "Last resort services within a group"},
                },
                selection_strategies={
                    "FALLBACK": "First available strategy - try services in priority order until one succeeds",
                    "ROUND_ROBIN": "Load balancing - rotate through services to distribute load",
                },
                selection_flow=[
                    "1. Group services by priority_group (0, 1, 2...)",
                    "2. Within each group, sort by Priority (CRITICAL, HIGH, NORMAL, LOW, FALLBACK)",
                    "3. Apply the group's selection strategy (FALLBACK or ROUND_ROBIN)",
                    "4. Check if service is healthy (if health check available)",
                    "5. Check if circuit breaker is closed (not tripped)",
                    "6. Verify service has required capabilities",
                    "7. If all checks pass, use the service",
                    "8. If service fails, try next according to strategy",
                    "9. If all services in group fail, try next group",
                ],
                circuit_breaker_info={
                    "purpose": "Prevents repeated calls to failing services",
                    "states": {
                        "CLOSED": "Normal operation - service is available",
                        "OPEN": "Service is unavailable - too many recent failures",
                        "HALF_OPEN": "Testing if service has recovered",
                    },
                    "configuration": "Configurable failure threshold, timeout, and half-open test interval",
                },
                examples=[
                    {
                        "scenario": "LLM Service Selection",
                        "setup": "3 LLM providers: OpenAI (group 0, HIGH), Anthropic (group 0, NORMAL), MockLLM (group 1, NORMAL)",
                        "result": "System tries OpenAI first, then Anthropic, then MockLLM only if both group 0 providers fail",
                    },
                    {
                        "scenario": "Round Robin Load Balancing",
                        "setup": "2 Memory providers in group 0 with ROUND_ROBIN strategy",
                        "result": "Requests alternate between the two providers to distribute load",
                    },
                ],
                configuration_tips=[
                    "Use priority groups to separate production services (group 0) from fallback services (group 1+)",
                    "Set CRITICAL priority for essential services that should always be tried first",
                    "Use ROUND_ROBIN strategy for stateless services to distribute load",
                    "Configure circuit breakers with appropriate thresholds based on service reliability",
                    "Place mock/test services in higher priority groups (2+) to ensure they're only used as last resort",
                ],
            )

            await self._record_event("service_query", "get_selection_explanation", success=True)
            return explanation

        except Exception as e:
            logger.error(f"Failed to get service selection explanation: {e}")
            await self._record_event("service_query", "get_selection_explanation", success=False, error=str(e))
            # Return a minimal explanation on error
            return ServiceSelectionExplanation(
                overview="Error retrieving service selection explanation",
                priority_groups={},
                priorities={},
                selection_strategies={},
                selection_flow=[],
                circuit_breaker_info={},
                examples=[],
                configuration_tips=[],
            )

    async def get_service_health_status(self) -> ServiceHealthStatus:
        """Get health status of all registered services."""
        try:
            if not self.runtime:
                return ServiceHealthStatus(
                    overall_health="critical",
                    healthy_services=0,
                    unhealthy_services=0,
                    service_details={},
                    recommendations=["Runtime not available"],
                )

            service_details = {}
            healthy_count = 0
            unhealthy_count = 0

            # First, get all direct services from runtime properties
            direct_services = [
                # Graph Services (6)
                ("memory_service", "graph", "MemoryService"),
                ("config_service", "graph", "ConfigService"),
                ("telemetry_service", "graph", "TelemetryService"),
                ("audit_service", "graph", "AuditService"),
                ("incident_management_service", "graph", "IncidentManagementService"),
                ("tsdb_consolidation_service", "graph", "TSDBConsolidationService"),
                # Infrastructure Services (7)
                ("time_service", "infrastructure", "TimeService"),
                ("shutdown_service", "infrastructure", "ShutdownService"),
                ("initialization_service", "infrastructure", "InitializationService"),
                ("authentication_service", "infrastructure", "AuthenticationService"),
                ("resource_monitor", "infrastructure", "ResourceMonitorService"),
                ("maintenance_service", "infrastructure", "DatabaseMaintenanceService"),
                ("secrets_service", "infrastructure", "SecretsService"),
                # Governance Services (4)
                ("wa_auth_system", "governance", "WiseAuthorityService"),
                ("adaptive_filter_service", "governance", "AdaptiveFilterService"),
                ("visibility_service", "governance", "VisibilityService"),
                ("self_observation_service", "governance", "SelfObservationService"),
                # Runtime Services (3)
                ("llm_service", "runtime", "LLMService"),
                ("runtime_control_service", "runtime", "RuntimeControlService"),
                ("task_scheduler", "runtime", "TaskSchedulerService"),
                # Tool Services (1)
                ("secrets_tool_service", "tool", "SecretsToolService"),
            ]

            # Check each direct service
            for attr_name, category, display_name in direct_services:
                service = getattr(self.runtime, attr_name, None)
                if service:
                    service_key = f"direct.{category}.{display_name}"
                    try:
                        # Check if service has is_healthy method
                        if hasattr(service, "is_healthy"):
                            is_healthy = (
                                await service.is_healthy()
                                if asyncio.iscoroutinefunction(service.is_healthy)
                                else service.is_healthy()
                            )
                        elif hasattr(service, "_started"):
                            is_healthy = service._started
                        else:
                            is_healthy = True  # Assume healthy if no health check

                        service_details[service_key] = {
                            "healthy": is_healthy,
                            "circuit_breaker_state": "closed",  # Direct services don't use circuit breakers
                            "priority": "DIRECT",  # Direct call, no priority
                            "priority_group": -1,  # Not applicable
                            "strategy": "DIRECT",  # Direct call
                        }

                        if is_healthy:
                            healthy_count += 1
                        else:
                            unhealthy_count += 1
                    except Exception as e:
                        logger.error(f"Error checking health of {display_name}: {e}")
                        service_details[service_key] = {
                            "healthy": False,
                            "circuit_breaker_state": "error",
                            "priority": "DIRECT",
                            "priority_group": -1,
                            "strategy": "DIRECT",
                            "error": str(e),
                        }
                        unhealthy_count += 1

            # Then get registry services (bus-based services)
            if hasattr(self.runtime, "service_registry") and self.runtime.service_registry:
                registry_info = self.runtime.service_registry.get_provider_info()
                logger.debug(f"Registry info keys: {list(registry_info.keys())}")

                unhealthy_services_list = []
                healthy_services_list = []

                # New format: all services are under "services" key
                for service_type, providers in registry_info.get("services", {}).items():
                    for provider in providers:
                        service_key = f"registry.{service_type}.{provider['name']}"
                        cb_state = provider.get("circuit_breaker_state", "closed")
                        is_healthy = cb_state == "closed"

                        service_details[service_key] = {
                            "healthy": is_healthy,
                            "circuit_breaker_state": cb_state,
                            "priority": provider.get("priority", "NORMAL"),
                            "priority_group": provider.get("priority_group", 0),
                            "strategy": provider.get("strategy", "FALLBACK"),
                        }

                        if is_healthy:
                            healthy_count += 1
                            healthy_services_list.append(service_key)
                        else:
                            unhealthy_count += 1
                            unhealthy_services_list.append(service_key)

            # Determine overall health
            overall_health = "healthy"
            recommendations = []

            if unhealthy_count > 0:
                if unhealthy_count > healthy_count:
                    overall_health = "unhealthy"
                    recommendations.append("Critical: More unhealthy services than healthy ones")
                else:
                    overall_health = "degraded"
                    recommendations.append(f"Warning: {unhealthy_count} services are unhealthy")

                recommendations.append("Consider resetting circuit breakers for failed services")
                recommendations.append("Check service logs for error details")

            return ServiceHealthStatus(
                overall_health=overall_health,
                healthy_services=healthy_count,
                unhealthy_services=unhealthy_count,
                service_details=service_details,
                recommendations=recommendations,
            )

        except Exception as e:
            logger.error(f"Failed to get service health status: {e}")
            return ServiceHealthStatus(
                overall_health="critical",
                healthy_services=0,
                unhealthy_services=0,
                service_details={},
                recommendations=[f"Critical error while checking service health: {str(e)}"],
            )

    async def _get_service_selection_explanation(self) -> ServiceSelectionExplanation:
        """Get explanation of how service selection works with priorities and strategies."""
        return ServiceSelectionExplanation(
            overview="Services are selected using a multi-tier priority system with configurable selection strategies",
            priority_groups={
                0: "Primary services - tried first",
                1: "Secondary services - used when primary unavailable",
                2: "Tertiary services - last resort options",
            },
            selection_strategies={
                "FALLBACK": "Use first available healthy service in priority order",
                "ROUND_ROBIN": "Rotate through services at same priority level",
            },
            examples=[
                {
                    "scenario": "fallback_strategy",
                    "description": "Two LLM services: OpenAI (CRITICAL) and LocalLLM (NORMAL)",
                    "behavior": "Always try OpenAI first, fall back to LocalLLM if OpenAI fails",
                },
                {
                    "scenario": "round_robin_strategy",
                    "description": "Three load-balanced API services all at NORMAL priority",
                    "behavior": "Rotate requests: API1 -> API2 -> API3 -> API1 -> ...",
                },
                {
                    "scenario": "multi_group_example",
                    "description": "Priority Group 0: Critical services, Priority Group 1: Backup services",
                    "behavior": "Only use Group 1 services if all Group 0 services are unavailable",
                },
            ],
            configuration_tips=[
                "Use priority groups to separate primary and backup services",
                "Set CRITICAL priority for essential services within a group",
                "Use ROUND_ROBIN strategy for load balancing similar services",
                "Configure circuit breakers to handle transient failures gracefully",
            ],
        )

    # Helper Methods
    async def _record_event(
        self,
        category: str,
        action: str,
        success: bool,
        result: Optional[Dict[str, object]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Record an event in the history."""
        try:
            event = RuntimeEvent(
                event_type=f"{category}:{action}",
                timestamp=self._now(),
                source="RuntimeControlService",
                details={"result": result, "success": success} if result else {"success": success},
                severity="error" if error else "info",
            )
            # Store additional fields in details since they're not in the schema
            if error:
                event.details["error"] = error

            self._events_history.append(event)

            if len(self._events_history) > 1000:
                self._events_history = self._events_history[-1000:]

        except Exception as e:
            logger.error(f"Failed to record event: {e}")

    def get_events_history(self, limit: int = 100) -> List[RuntimeEvent]:
        """Get recent events history."""
        return self._events_history[-limit:]

    # Legacy method to maintain compatibility
    async def _reload_config(self, config_path: Optional[str] = None) -> ConfigReloadResult:
        """Reload system configuration."""
        try:
            await self._record_event(
                "config_reload", "reload", success=False, error="Legacy method - use specific config operations instead"
            )

            return ConfigReloadResult(
                success=False,
                config_version="unknown",
                changes_applied=0,
                warnings=["Legacy method - use specific config operations instead"],
                error="Use specific configuration management endpoints instead",
            )

        except Exception as e:
            logger.error(f"Failed to reload config: {e}", exc_info=True)
            return ConfigReloadResult(
                success=False, config_version="unknown", changes_applied=0, warnings=[], error=str(e)
            )

    # Service interface methods required by Service base class
    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.RUNTIME_CONTROL

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        # Runtime is optional - service can function without it
        return True

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        if hasattr(self, "config_manager") and self.config_manager:
            self._dependencies.add("GraphConfigService")
        if hasattr(self, "adapter_manager") and self.adapter_manager:
            self._dependencies.add("RuntimeAdapterManager")

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect enhanced runtime control metrics."""
        # Get queue depth if processor exists
        queue_depth = 0
        if self.runtime and hasattr(self.runtime, "agent_processor") and self.runtime.agent_processor:
            if hasattr(self.runtime.agent_processor, "queue") and self.runtime.agent_processor.queue:
                queue_depth = len(self.runtime.agent_processor.queue)

        # Map cognitive state to float
        cognitive_state = 0.0
        if self.runtime and hasattr(self.runtime, "agent_processor") and self.runtime.agent_processor:
            if hasattr(self.runtime.agent_processor, "state"):
                state_map = {"WAKEUP": 1.0, "WORK": 2.0, "PLAY": 3.0, "SOLITUDE": 4.0, "DREAM": 5.0, "SHUTDOWN": 6.0}
                cognitive_state = state_map.get(str(self.runtime.agent_processor.state), 0.0)

        metrics = {
            # Original metrics
            "events_count": float(len(self._events_history)),
            "processor_status": 1.0 if self._processor_status == ProcessorStatus.RUNNING else 0.0,
            "adapters_loaded": float(len(self.adapter_manager.loaded_adapters)) if self.adapter_manager else 0.0,
            # Enhanced metrics
            "queue_depth": float(queue_depth),
            "thoughts_processed": float(self._thoughts_processed),
            "thoughts_pending": float(self._thoughts_pending),
            "cognitive_state": cognitive_state,
            "average_thought_time_ms": self._calculate_average_thought_time(),
            "runtime_paused": 1.0 if self._processor_status == ProcessorStatus.PAUSED else 0.0,
            "runtime_step_mode": 1.0 if hasattr(self, "_step_mode") and self._step_mode else 0.0,
            "service_overrides_active": float(self._service_overrides),
            "runtime_errors": float(self._runtime_errors),
            "messages_processed": float(self._messages_processed),
            "average_message_latency_ms": self._calculate_average_latency(),
            "seconds_per_thought": self._calculate_processing_rate(),  # Renamed to be clear
            "system_load": self._calculate_current_load(),
        }

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all runtime control service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()
        # Get queue size from agent processor
        queue_size = 0
        if self.runtime and hasattr(self.runtime, "agent_processor") and self.runtime.agent_processor:
            if hasattr(self.runtime.agent_processor, "queue") and self.runtime.agent_processor.queue:
                queue_size = len(self.runtime.agent_processor.queue)
            elif hasattr(self.runtime.agent_processor, "get_queue_status"):
                try:
                    queue_status = self.runtime.agent_processor.get_queue_status()
                    queue_size = queue_status.pending_thoughts + queue_status.pending_tasks
                except Exception:
                    queue_size = 0

        # Map processor status to int (matching cognitive state pattern)
        current_state = 0
        if self._processor_status == ProcessorStatus.RUNNING:
            current_state = 1
        elif self._processor_status == ProcessorStatus.PAUSED:
            current_state = 2
        elif self._processor_status == ProcessorStatus.STOPPED:
            current_state = 3

        # Calculate uptime in seconds
        uptime_seconds = self._calculate_uptime()

        # Add v1.4.3 specific runtime metrics
        metrics.update(
            {
                "runtime_state_transitions": float(self._state_transitions),
                "runtime_commands_processed": float(self._commands_processed),
                "runtime_current_state": float(current_state),
                "runtime_queue_size": float(queue_size),
                "runtime_uptime_seconds": float(uptime_seconds),
            }
        )

        return metrics

    def _track_thought_processing_time(self, processing_time_ms: float) -> None:
        """
        Callback to track thought processing times.
        Called by AgentProcessor when a thought completes.
        """
        # Add to thought times list
        self._thought_times.append(processing_time_ms)

        # Trim list to max history
        if len(self._thought_times) > self._max_thought_history:
            self._thought_times = self._thought_times[-self._max_thought_history :]

        # Update average
        if self._thought_times:
            self._average_thought_time_ms = sum(self._thought_times) / len(self._thought_times)

        # Track metrics
        self._thoughts_processed += 1

    def _calculate_average_thought_time(self) -> float:
        """Calculate average thought processing time."""
        if self._thought_times:
            return sum(self._thought_times) / len(self._thought_times)
        return self._average_thought_time_ms

    def _calculate_average_latency(self) -> float:
        """Calculate average thought processing latency."""
        return self._calculate_average_thought_time()

    def _calculate_processing_rate(self) -> float:
        """Calculate seconds per thought (not thoughts per second!).

        Thoughts take 5-15 seconds each, so this returns the average
        time in seconds to process one thought.
        """
        if self._thought_times and self._average_thought_time_ms > 0:
            # Convert milliseconds to seconds
            avg_time_seconds = self._average_thought_time_ms / 1000.0
            return avg_time_seconds  # Seconds per thought (5-15 typical)
        return 10.0  # Default: 10 seconds per thought

    def _calculate_current_load(self) -> float:
        """Calculate current system load (0.0 to 1.0)."""
        # Load based on queue depth and processing rate
        if self.runtime and hasattr(self.runtime, "agent_processor") and self.runtime.agent_processor:
            if hasattr(self.runtime.agent_processor, "queue") and self.runtime.agent_processor.queue:
                queue_depth = len(self.runtime.agent_processor.queue)
                # Normalize to 0-1 range (assume 100 messages is full load)
                return min(queue_depth / 100.0, 1.0)
        return 0.0

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "single_step",
            "pause_processing",
            "resume_processing",
            "get_processor_queue_status",
            "shutdown_runtime",
            "load_adapter",
            "unload_adapter",
            "list_adapters",
            "get_adapter_info",
            "get_config",
            "update_config",
            "validate_config",
            "backup_config",
            "restore_config",
            "list_config_backups",
            "reload_config_profile",
            "get_runtime_status",
            "get_runtime_snapshot",
            "update_service_priority",
            "reset_circuit_breakers",
            "get_service_health_status",
        ]

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get base capabilities
        capabilities = super().get_capabilities()

        # Add custom metadata using model_copy
        if capabilities.metadata is not None:
            capabilities.metadata = capabilities.metadata.model_copy(
                update={
                    "description": "Runtime control and management service",
                    "features": ["processor_control", "adapter_management", "config_management", "health_monitoring"],
                }
            )

        return capabilities

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        return ServiceStatus(
            service_name="RuntimeControlService",
            service_type="CORE",
            is_healthy=self.runtime is not None,
            uptime_seconds=self._calculate_uptime(),
            last_error=self._last_error,
            metrics={
                "events_count": float(len(self._events_history)),
                "adapters_loaded": float(
                    len(self.adapter_manager.loaded_adapters)
                    if self.adapter_manager and hasattr(self.adapter_manager, "loaded_adapters")
                    else 0
                ),
            },
            last_health_check=self._last_health_check,
        )

    def _set_runtime(self, runtime: "RuntimeInterface") -> None:
        """Set the runtime reference after initialization (private method)."""
        self.runtime = runtime

        # NOTE: agent_processor doesn't exist yet during initialization phase
        # The callback will be set up later via setup_thought_tracking()

        # If adapter manager exists, update its runtime reference too
        if self.adapter_manager:
            from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

            self.adapter_manager.runtime = cast(CIRISRuntime, runtime)
            # Re-register config listener with updated runtime
            self.adapter_manager._register_config_listener()
        logger.info("Runtime reference set in RuntimeControlService")

    def setup_thought_tracking(self) -> None:
        """Set up thought processing callback after agent_processor is created.

        This must be called AFTER Phase 6 (COMPONENTS) when agent_processor exists.
        Called during Phase 5 (SERVICES) would cause a race condition.
        """
        if self.runtime and hasattr(self.runtime, "agent_processor") and self.runtime.agent_processor:
            self.runtime.agent_processor.set_thought_processing_callback(self._track_thought_processing_time)
            logger.debug("Thought processing callback registered with agent_processor")

    async def _on_start(self) -> None:
        """Custom startup logic for runtime control service."""
        await self._initialize()
        logger.info("Runtime control service started")

    async def _on_stop(self) -> None:
        """Custom cleanup logic for runtime control service."""
        logger.info("Runtime control service stopping")
        # Clean up any resources if needed
        self._events_history.clear()
