"""
Shared startup logging utilities for service initialization.

Extracted to avoid circular imports between module_loader and service_initializer.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Total core services for startup logging (22 per architecture)
TOTAL_CORE_SERVICES = 22

# First-run minimal services (10 services needed to serve setup wizard)
FIRST_RUN_SERVICES = 10

# Services started during resume_from_first_run (remaining 12)
RESUME_SERVICES = 12

# Track services started for iOS file-based status
_services_started: set[int] = set()

# Service names in initialization order for UI display
SERVICE_NAMES = [
    "TimeService",  # 1 - Infrastructure
    "ShutdownService",  # 2 - Infrastructure
    "InitializationService",  # 3 - Infrastructure
    "ResourceMonitor",  # 4 - Infrastructure
    "SecretsService",  # 5 - Memory Foundation
    "MemoryService",  # 6 - Memory Foundation
    "ConfigService",  # 7 - Graph Services
    "AuditService",  # 8 - Graph Services
    "TelemetryService",  # 9 - Graph Services
    "IncidentManagement",  # 10 - Graph Services
    "TSDBConsolidation",  # 11 - Graph Services
    "ConsentService",  # 12 - Graph Services
    "WiseAuthority",  # 13 - Security
    "LLMService",  # 14 - Runtime
    "AuthenticationService",  # 15 - Runtime (adapter-provided)
    "DatabaseMaintenance",  # 16 - Infrastructure
    "RuntimeControl",  # 17 - Runtime (adapter-provided)
    "TaskScheduler",  # 18 - Lifecycle
    "AdaptiveFilter",  # 19 - Governance
    "VisibilityService",  # 20 - Governance
    "SelfObservation",  # 21 - Governance
    "SecretsToolService",  # 22 - Tool Services
]

# Track which phase we're in for logging clarity
_current_phase: str = "STARTUP"


def _set_service_phase(phase: str) -> None:
    """Set the current service initialization phase for logging."""
    global _current_phase
    _current_phase = phase
    logger.warning(f"[SERVICES] === {phase} PHASE ===")
    print(f"[SERVICES] === {phase} PHASE ===")


def _write_service_status_file() -> None:
    """Write service status to a JSON file for iOS to read.

    iOS cannot read logcat like Android, so we write to a file instead.
    The file is written to ~/Documents/ciris/service_status.json
    """
    import sys

    # Only write file on iOS/Darwin platforms (mobile)
    if sys.platform not in ("ios", "darwin"):
        return

    try:
        status_dir = Path.home() / "Documents" / "ciris"
        status_dir.mkdir(parents=True, exist_ok=True)
        status_file = status_dir / "service_status.json"

        status_data = {
            "services_online": len(_services_started),
            "services_total": TOTAL_CORE_SERVICES,
            "phase": _current_phase,
        }

        with open(status_file, "w") as f:
            json.dump(status_data, f)
    except Exception as e:
        # Don't fail startup over status file issues
        logger.debug(f"Could not write service status file: {e}")


def _log_service_started(service_num: int, service_name: str, success: bool = True) -> None:
    """Log service startup status in a format parseable by the UI."""
    global _services_started

    status = "STARTED" if success else "FAILED"
    phase_prefix = f"[{_current_phase}] " if _current_phase != "STARTUP" else ""
    msg = f"{phase_prefix}[SERVICE {service_num}/{TOTAL_CORE_SERVICES}] {service_name} {status}"
    # Use WARNING level so it shows up in incident logs for easy parsing
    logger.warning(msg)
    # Also print to console/stdout for Android logcat visibility
    print(msg)

    # Track service for iOS file-based status
    if success:
        _services_started.add(service_num)
    _write_service_status_file()


def get_current_phase() -> str:
    """Get the current service initialization phase."""
    return _current_phase


def get_services_started() -> set[int]:
    """Get the set of service numbers that have started."""
    return _services_started
