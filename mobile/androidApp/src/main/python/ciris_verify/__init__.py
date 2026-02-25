"""CIRISVerify Python bindings.

Hardware-rooted license verification for the CIRIS ecosystem.
Provides cryptographic proof of license status to prevent capability spoofing.

Usage:
    from ciris_verify import CIRISVerify, LicenseStatus

    verifier = CIRISVerify()
    status = verifier.get_license_status(challenge_nonce=os.urandom(32))

    if status.allows_licensed_operation():
        # Professional capabilities available
        pass
    else:
        # Community mode only
        disclosure = status.mandatory_disclosure
        print(disclosure.text)

Logging:
    # Enable internal logging via callback
    verifier.set_log_callback(lambda lvl, target, msg: print(f"[{lvl}] {msg}"))

    # Or integrate with Python logging
    from ciris_verify import setup_logging
    setup_logging(verifier, level="DEBUG")
"""

import logging as _logging

from .client import CIRISVerify, MockCIRISVerify
from .types import (
    LicenseStatus,
    LicenseTier,
    LicenseDetails,
    MandatoryDisclosure,
    DisclosureSeverity,
    LicenseStatusResponse,
    CapabilityCheckResult,
    FileIntegrityResult,
    FileCheckStatus,
    BinaryIntegrityStatus,
    HardwareType,
    ValidationStatus,
    PythonModuleHashes,
    PythonIntegrityResult,
)
from .exceptions import (
    CIRISVerifyError,
    BinaryNotFoundError,
    BinaryTamperedError,
    VerificationFailedError,
    TimeoutError,
    CommunicationError,
)


def setup_logging(verifier: CIRISVerify, level: str = "INFO", logger_name: str = "ciris_verify"):
    """Configure CIRISVerify to forward internal logs to Python logging.

    Args:
        verifier: CIRISVerify instance to configure.
        level: Minimum log level: "ERROR", "WARN", "INFO", "DEBUG", "TRACE".
        logger_name: Python logger name to use.

    Example:
        import logging
        logging.basicConfig(level=logging.DEBUG)

        verifier = CIRISVerify()
        setup_logging(verifier, level="DEBUG")

        # Now CIRISVerify internal logs appear in Python logging
        status = verifier.get_license_status(...)
    """
    logger = _logging.getLogger(logger_name)

    # Map Rust levels to Python logging levels
    level_map = {
        1: _logging.ERROR,    # ERROR
        2: _logging.WARNING,  # WARN
        3: _logging.INFO,     # INFO
        4: _logging.DEBUG,    # DEBUG
        5: _logging.DEBUG,    # TRACE (Python has no TRACE, use DEBUG)
    }

    # Map level string to Rust level int
    rust_level_map = {
        "ERROR": 1,
        "WARN": 2,
        "WARNING": 2,
        "INFO": 3,
        "DEBUG": 4,
        "TRACE": 5,
    }
    rust_level = rust_level_map.get(level.upper(), 3)

    def log_callback(lvl: int, target: str, message: str):
        py_level = level_map.get(lvl, _logging.DEBUG)
        logger.log(py_level, "[%s] %s", target, message)

    verifier.set_log_callback(log_callback, level=rust_level)


__version__ = "0.9.6"
__all__ = [
    "CIRISVerify",
    "MockCIRISVerify",
    "setup_logging",
    "LicenseStatus",
    "LicenseTier",
    "LicenseDetails",
    "MandatoryDisclosure",
    "DisclosureSeverity",
    "LicenseStatusResponse",
    "CapabilityCheckResult",
    "FileIntegrityResult",
    "FileCheckStatus",
    "BinaryIntegrityStatus",
    "HardwareType",
    "ValidationStatus",
    "PythonModuleHashes",
    "PythonIntegrityResult",
    "CIRISVerifyError",
    "BinaryNotFoundError",
    "BinaryTamperedError",
    "VerificationFailedError",
    "TimeoutError",
    "CommunicationError",
]
