"""
Consent Service Module - FAIL FAST, FAIL LOUD, NO FAKE DATA.

Governance Service #5: Manages user consent for the Consensual Evolution Protocol.
Default: TEMPORARY (14 days) unless explicitly changed.
This is the 22nd core CIRIS service.

Module Structure:
- service.py: Core ConsentService implementation
- exceptions.py: Custom exceptions (ConsentNotFoundError, ConsentValidationError, etc.)
- metrics.py: Metrics collection (ConsentMetricsCollector)
- partnership.py: Partnership management (PartnershipManager)
- decay.py: Decay protocol (DecayProtocolManager)
- air.py: Artificial Interaction Reminder (ArtificialInteractionReminder)
"""

from .air import ArtificialInteractionReminder
from .decay import DecayProtocolManager
from .dsar_automation import DSARAutomationService
from .exceptions import (
    ConsentExpiredError,
    ConsentNotFoundError,
    ConsentValidationError,
    DecayInProgressError,
    DSARAutomationError,
    PartnershipPendingError,
)
from .metrics import ConsentMetricsCollector
from .partnership import PartnershipManager
from .service import ConsentService, logger

# Version for consent service module
__version__ = "0.3.0"

__all__ = [
    # Core service
    "ConsentService",
    # Exceptions
    "ConsentNotFoundError",
    "ConsentValidationError",
    "ConsentExpiredError",
    "PartnershipPendingError",
    "DecayInProgressError",
    "DSARAutomationError",
    # Managers
    "ConsentMetricsCollector",
    "PartnershipManager",
    "DecayProtocolManager",
    "ArtificialInteractionReminder",
    "DSARAutomationService",
    # Logger
    "logger",
]
