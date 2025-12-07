"""
Initialization Service for CIRIS Trinity Architecture.

Manages system initialization coordination with verification at each phase.
This replaces the initialization_manager.py utility with a proper service.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Awaitable, Callable, Dict, List, Optional

from ciris_engine.logic.services.base_infrastructure_service import BaseInfrastructureService
from ciris_engine.protocols.services import InitializationServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.lifecycle.initialization import InitializationStatus, InitializationVerification
from ciris_engine.schemas.services.metadata import ServiceMetadata
from ciris_engine.schemas.services.operations import InitializationPhase

logger = logging.getLogger(__name__)


@dataclass
class InitializationStep:
    """Represents a single initialization step."""

    phase: InitializationPhase
    name: str
    handler: Callable[[], Awaitable[None]]
    verifier: Optional[Callable[[], Awaitable[bool]]] = None
    critical: bool = True
    timeout: float = 30.0


class InitializationService(BaseInfrastructureService, InitializationServiceProtocol):
    """Service for coordinating system initialization."""

    def __init__(self, time_service: TimeServiceProtocol) -> None:
        """Initialize the initialization service."""
        # Initialize base class with time_service
        super().__init__(service_name="InitializationService", version="1.0.0", time_service=time_service)

        # Store time_service reference
        self.time_service = time_service

        # Initialization-specific attributes
        self._steps: List[InitializationStep] = []
        self._completed_steps: List[str] = []
        self._phase_status: Dict[InitializationPhase, str] = {}
        self._start_time: Optional[datetime] = None
        self._initialization_complete = False
        self._error: Optional[Exception] = None

    # Required abstract methods from BaseService

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.INITIALIZATION

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["register_step", "initialize", "is_initialized", "get_initialization_status", "verify_initialization"]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        # Check if time service is available
        return self.time_service is not None

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get metadata from parent's _get_metadata()
        service_metadata = self._get_metadata()

        # Set infrastructure-specific fields
        if service_metadata:
            service_metadata.category = "infrastructure"
            service_metadata.critical = True
            service_metadata.description = "Manages system initialization coordination"

        return ServiceCapabilities(
            service_name=self.service_name,
            actions=self._get_actions(),
            version=self._version,
            dependencies=list(self._dependencies),
            metadata=service_metadata,
        )

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect initialization-specific metrics."""
        metrics = super()._collect_custom_metrics()

        duration = None
        if self._start_time:
            duration = (self.time_service.now() - self._start_time).total_seconds()

        metrics.update(
            {
                "initialization_complete": float(self._initialization_complete),
                "has_error": float(self._error is not None),
                "completed_steps": float(len(self._completed_steps)),
                "total_steps": float(len(self._steps)),
                "initialization_duration": duration or 0.0,
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """Get all initialization service metrics including base, custom, and v1.4.3 specific."""
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Calculate init time in milliseconds
        init_time_ms = 0.0
        if self._start_time:
            duration = (self.time_service.now() - self._start_time).total_seconds()
            init_time_ms = duration * 1000

        # Calculate uptime in seconds since initialization started
        uptime_seconds = 0.0
        if self._start_time:
            uptime_seconds = (self.time_service.now() - self._start_time).total_seconds()

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "init_services_started": float(len(self._completed_steps)),
                "init_errors_total": float(1 if self._error else 0),
                "init_time_ms": init_time_ms,
                "init_uptime_seconds": uptime_seconds,
            }
        )

        return metrics

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        # Call parent is_healthy first
        base_healthy = await super().is_healthy()
        # Service is healthy if base is healthy AND (init complete OR no error)
        return base_healthy and (self._initialization_complete or self._error is None)

    def register_step(
        self,
        phase: InitializationPhase,
        name: str,
        handler: Callable[[], Awaitable[None]],
        verifier: Optional[Callable[[], Awaitable[bool]]] = None,
        critical: bool = True,
        timeout: float = 30.0,
    ) -> None:
        """
        Register an initialization step.

        Args:
            phase: Initialization phase
            name: Step name
            handler: Async function to execute
            verifier: Optional async function to verify step
            critical: If True, failure stops initialization
            timeout: Maximum time for step execution
        """
        step = InitializationStep(
            phase=phase, name=name, handler=handler, verifier=verifier, critical=critical, timeout=timeout
        )
        self._steps.append(step)
        logger.debug(f"Registered initialization step: {phase.value}/{name}")

    async def initialize(self) -> bool:
        """Initialize the entire system."""
        self._start_time = self.time_service.now()
        logger.info("=" * 60)
        logger.info("CIRIS Agent Initialization Sequence Starting")
        logger.info("=" * 60)

        try:
            # Group steps by phase
            phases: Dict[InitializationPhase, List[InitializationStep]] = {}
            for step in self._steps:
                if step.phase not in phases:
                    phases[step.phase] = []
                phases[step.phase].append(step)

            logger.info(f"[InitializationService] Registered {len(self._steps)} steps across {len(phases)} phases")

            # Execute phases in order
            for phase in list(InitializationPhase):
                if phase not in phases:
                    logger.debug(f"[InitializationService] Skipping phase {phase.value} - no steps registered")
                    continue

                logger.info(f"[InitializationService] Executing phase {phase.value} with {len(phases[phase])} steps")
                await self._execute_phase(phase, phases[phase])

                if self._error and phase != InitializationPhase.VERIFICATION:
                    logger.error(f"[InitializationService] Error in phase {phase.value}: {self._error}")
                    raise self._error

            # Set initialization complete
            self._initialization_complete = True
            duration = (self.time_service.now() - self._start_time).total_seconds()

            logger.info("=" * 60)
            logger.info(f"✓ CIRIS Agent Initialization Complete ({duration:.1f}s)")
            logger.info("=" * 60)

        except Exception as e:
            duration = (self.time_service.now() - self._start_time).total_seconds()
            logger.error("=" * 60)
            logger.error(f"✗ CIRIS Agent Initialization Failed ({duration:.1f}s)")
            logger.error(f"Error: {e}")
            logger.error("=" * 60)
            self._error = e
            return False

        return True

    async def verify_initialization(self) -> InitializationVerification:
        """Verify all components are initialized."""
        # Check each phase
        phase_results = {}
        for phase, status in self._phase_status.items():
            phase_results[phase.value] = status == "completed"

        # Check all registered steps completed
        total_steps = len(self._steps)
        completed_steps = len(self._completed_steps)

        return InitializationVerification(
            system_initialized=self._initialization_complete,
            no_errors=(self._error is None),
            all_steps_completed=(total_steps == completed_steps),
            phase_results=phase_results,
        )

    def _is_initialized(self) -> bool:
        """Check if initialization is complete (internal)."""
        return self._initialization_complete

    async def get_initialization_status(self) -> InitializationStatus:
        """Get detailed initialization status."""
        duration = None
        if self._start_time:
            duration = (self.time_service.now() - self._start_time).total_seconds()

        return InitializationStatus(
            complete=self._initialization_complete,
            start_time=self._start_time,
            duration_seconds=duration,
            completed_steps=self._completed_steps,
            phase_status={phase.value: status for phase, status in self._phase_status.items()},
            error=str(self._error) if self._error else None,
            total_steps=len(self._steps),
        )

    async def _execute_phase(self, phase: InitializationPhase, steps: List[InitializationStep]) -> None:
        """Execute all steps in a phase."""
        logger.info("-" * 60)
        logger.info(f"Phase: {phase.value.upper()}")
        logger.info("-" * 60)

        self._phase_status[phase] = "running"
        phase_start = self.time_service.now()

        for step in steps:
            await self._execute_step(step)

            if self._error and step.critical:
                self._phase_status[phase] = "failed"
                return

        phase_duration = (self.time_service.now() - phase_start).total_seconds()
        self._phase_status[phase] = "completed"
        logger.info(f"✓ Phase {phase.value} completed successfully ({phase_duration:.1f}s)")

    async def _execute_step(self, step: InitializationStep) -> None:
        """Execute a single initialization step with timeout and verification."""
        step_name = f"{step.phase.value}/{step.name}"
        logger.info(f"→ {step.name}...")

        try:
            # Execute the step with timeout
            await asyncio.wait_for(step.handler(), timeout=step.timeout)

            # Verify if provided
            if step.verifier:
                logger.debug(f"  Verifying {step.name}...")
                verified = await asyncio.wait_for(step.verifier(), timeout=10.0)

                if not verified:
                    raise Exception(f"Verification failed for {step.name}")

            self._completed_steps.append(step_name)
            logger.info(f"  ✓ {step.name} initialized")

        except asyncio.TimeoutError:
            error_msg = f"{step.name} timed out after {step.timeout}s"
            logger.error(f"  ✗ {error_msg}")

            if step.critical:
                self._error = Exception(error_msg)
                raise self._error

        except Exception as e:
            logger.error(f"  ✗ {step.name} failed: {e}")

            if step.critical:
                self._error = e
                raise
