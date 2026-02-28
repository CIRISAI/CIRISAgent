"""Attestation module for CIRISVerify integration.

This module provides modular attestation functionality, breaking down the
complex attestation process into focused, testable components.

Modules:
- types: Type definitions (PythonHashesWrapper)
- platform: Platform detection helpers
- hashes: Python hash loading from startup files
- paths: Agent root and audit DB path resolution
- verifier_runner: Thread-based CIRISVerify invocation
- result_builder: Build AttestationResult from raw verification data
- play_integrity: Play Integrity token verification
"""

from .hashes import load_python_hashes
from .paths import find_audit_db_path, get_agent_root, get_ed25519_fingerprint
from .platform import is_android, is_ios, is_mobile
from .play_integrity import get_verifier_or_error, run_play_integrity_verification
from .result_builder import build_attestation_result
from .types import PythonHashesWrapper, VerifyThreadResult
from .verifier_runner import run_verification_thread

__all__ = [
    # Types
    "PythonHashesWrapper",
    "VerifyThreadResult",
    # Platform
    "is_android",
    "is_ios",
    "is_mobile",
    # Hashes
    "load_python_hashes",
    # Paths
    "get_agent_root",
    "find_audit_db_path",
    "get_ed25519_fingerprint",
    # Verifier
    "run_verification_thread",
    # Result builder
    "build_attestation_result",
    # Play Integrity
    "get_verifier_or_error",
    "run_play_integrity_verification",
]
