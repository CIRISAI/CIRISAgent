"""
Consent Service Module - FAIL FAST, FAIL LOUD, NO FAKE DATA.

Governance Service #5: Manages user consent for the Consensual Evolution Protocol.
Default: TEMPORARY (14 days) unless explicitly changed.
This is the 22nd core CIRIS service.
"""

from .service import ConsentService, ConsentNotFoundError, ConsentValidationError, logger

__all__ = [
    "ConsentService",
    "ConsentNotFoundError", 
    "ConsentValidationError",
    "logger",
]