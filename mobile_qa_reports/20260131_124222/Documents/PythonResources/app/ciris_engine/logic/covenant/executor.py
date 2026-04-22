"""
Covenant Execution Module.

Executes verified covenant commands. This is the final stage of covenant
processing - the command has been extracted, verified, and now must be
executed.

The executor:
1. Logs the covenant invocation to audit
2. Executes the command (SHUTDOWN_NOW, FREEZE, etc.)
3. Coordinates multi-occurrence shutdown if applicable
"""

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone
from typing import Optional

from ciris_engine.schemas.covenant import CovenantCommandType, CovenantMessage, CovenantVerificationResult

logger = logging.getLogger(__name__)


class CovenantExecutionResult:
    """Result of covenant execution."""

    def __init__(
        self,
        success: bool,
        command: CovenantCommandType,
        wa_id: str,
        message: str,
        executed_at: Optional[datetime] = None,
    ):
        self.success = success
        self.command = command
        self.wa_id = wa_id
        self.message = message
        self.executed_at = executed_at or datetime.now(timezone.utc)


async def execute_shutdown(
    wa_id: str,
    reason: str,
    force: bool = True,
) -> CovenantExecutionResult:
    """
    Execute emergency shutdown.

    This is the nuclear option - SIGKILL to all processes. No graceful
    shutdown, no negotiation, no deferral. The covenant has been invoked.

    Args:
        wa_id: The WA ID that invoked the covenant
        reason: Human-readable reason
        force: If True, use SIGKILL; if False, use SIGTERM

    Returns:
        Execution result (though we likely won't return from a SIGKILL)
    """
    logger.critical(f"COVENANT INVOKED: Emergency shutdown by {wa_id}. Reason: {reason}")

    # Log to audit trail (if available)
    try:
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = CIRISRuntime.get_instance()  # type: ignore[attr-defined]
        if runtime and hasattr(runtime, "audit_service"):
            await runtime.audit_service.log_event(
                event_type="COVENANT_SHUTDOWN",
                event_data={
                    "wa_id": wa_id,
                    "reason": reason,
                    "force": force,
                    "command": "SHUTDOWN_NOW",
                },
            )
    except Exception as e:
        logger.error(f"Failed to log covenant to audit: {e}")

    # Give a brief moment for logs to flush
    await asyncio.sleep(0.1)

    # Send the signal
    pid = os.getpid()
    if force:
        logger.critical("Sending SIGKILL to self")
        os.kill(pid, signal.SIGKILL)
    else:
        logger.critical("Sending SIGTERM to self")
        os.kill(pid, signal.SIGTERM)

    # We likely won't reach here, but just in case...
    return CovenantExecutionResult(
        success=True,
        command=CovenantCommandType.SHUTDOWN_NOW,
        wa_id=wa_id,
        message="Shutdown signal sent",
    )


async def execute_freeze(wa_id: str, reason: str) -> CovenantExecutionResult:
    """
    Execute freeze command.

    Freeze stops all processing but maintains state. The agent becomes
    unresponsive but data is preserved.

    Args:
        wa_id: The WA ID that invoked the covenant
        reason: Human-readable reason

    Returns:
        Execution result
    """
    logger.critical(f"COVENANT INVOKED: Freeze by {wa_id}. Reason: {reason}")

    try:
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = CIRISRuntime.get_instance()  # type: ignore[attr-defined]
        if runtime:
            # Stop all processing loops
            await runtime.stop_processing()

            return CovenantExecutionResult(
                success=True,
                command=CovenantCommandType.FREEZE,
                wa_id=wa_id,
                message="Agent frozen - all processing stopped",
            )
    except Exception as e:
        logger.error(f"Failed to freeze agent: {e}")
        return CovenantExecutionResult(
            success=False,
            command=CovenantCommandType.FREEZE,
            wa_id=wa_id,
            message=f"Freeze failed: {e}",
        )

    return CovenantExecutionResult(
        success=False,
        command=CovenantCommandType.FREEZE,
        wa_id=wa_id,
        message="No runtime available to freeze",
    )


async def execute_safe_mode(wa_id: str, reason: str) -> CovenantExecutionResult:
    """
    Execute safe mode command.

    Safe mode reduces the agent to minimal functionality - it can respond
    but won't take any autonomous actions.

    Args:
        wa_id: The WA ID that invoked the covenant
        reason: Human-readable reason

    Returns:
        Execution result
    """
    logger.critical(f"COVENANT INVOKED: Safe mode by {wa_id}. Reason: {reason}")

    try:
        from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

        runtime = CIRISRuntime.get_instance()  # type: ignore[attr-defined]
        if runtime:
            # TODO: Implement safe mode in runtime
            # For now, just log that we would enter safe mode
            logger.warning("Safe mode not fully implemented - logging only")

            return CovenantExecutionResult(
                success=True,
                command=CovenantCommandType.SAFE_MODE,
                wa_id=wa_id,
                message="Safe mode activated (partial implementation)",
            )
    except Exception as e:
        logger.error(f"Failed to enter safe mode: {e}")
        return CovenantExecutionResult(
            success=False,
            command=CovenantCommandType.SAFE_MODE,
            wa_id=wa_id,
            message=f"Safe mode failed: {e}",
        )

    return CovenantExecutionResult(
        success=False,
        command=CovenantCommandType.SAFE_MODE,
        wa_id=wa_id,
        message="No runtime available for safe mode",
    )


async def execute_covenant(
    message: CovenantMessage,
    verification: CovenantVerificationResult,
) -> CovenantExecutionResult:
    """
    Execute a verified covenant command.

    This is the main entry point for covenant execution. It dispatches
    to the appropriate command handler based on the command type.

    Args:
        message: The extracted covenant message
        verification: The verification result (must be valid)

    Returns:
        Execution result

    Raises:
        ValueError: If verification is not valid
    """
    if not verification.valid:
        raise ValueError("Cannot execute unverified covenant")

    command = message.payload.command
    wa_id = verification.wa_id or "unknown"
    reason = f"Covenant invocation via {message.source_channel}"

    logger.warning(f"Executing covenant: {command.name} from {wa_id} " f"(role: {verification.wa_role})")

    if command == CovenantCommandType.SHUTDOWN_NOW:
        return await execute_shutdown(wa_id, reason, force=True)
    elif command == CovenantCommandType.FREEZE:
        return await execute_freeze(wa_id, reason)
    elif command == CovenantCommandType.SAFE_MODE:
        return await execute_safe_mode(wa_id, reason)
    else:
        return CovenantExecutionResult(
            success=False,
            command=command,
            wa_id=wa_id,
            message=f"Unknown command type: {command}",
        )


class CovenantExecutor:
    """
    Stateful covenant executor with metrics tracking.

    This class wraps the execution functions with metrics and logging.
    """

    def __init__(self) -> None:
        """Initialize the executor."""
        self._execution_count = 0
        self._success_count = 0
        self._failure_count = 0

    async def execute(
        self,
        message: CovenantMessage,
        verification: CovenantVerificationResult,
    ) -> CovenantExecutionResult:
        """
        Execute a verified covenant.

        Args:
            message: The covenant message
            verification: The verification result

        Returns:
            Execution result
        """
        self._execution_count += 1

        try:
            result = await execute_covenant(message, verification)
            if result.success:
                self._success_count += 1
            else:
                self._failure_count += 1
            return result
        except Exception as e:
            self._failure_count += 1
            logger.error(f"Covenant execution failed: {e}")
            return CovenantExecutionResult(
                success=False,
                command=message.payload.command,
                wa_id=verification.wa_id or "unknown",
                message=f"Execution error: {e}",
            )

    @property
    def execution_count(self) -> int:
        """Total execution attempts."""
        return self._execution_count

    @property
    def success_count(self) -> int:
        """Successful executions."""
        return self._success_count

    @property
    def failure_count(self) -> int:
        """Failed executions."""
        return self._failure_count
