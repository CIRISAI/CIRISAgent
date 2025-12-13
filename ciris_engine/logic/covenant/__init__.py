"""
Covenant Invocation System.

This module provides the unfilterable kill switch capability for CIRIS agents.
The covenant system embeds emergency commands in natural language that cannot
be detected or filtered by pattern matching, as extraction IS perception.

Key Components:
- extractor: Extracts potential covenants from incoming messages
- verifier: Verifies covenant signatures against known authorities
- executor: Executes verified covenant commands
- handler: Integration point for the perception layer

See FSD: COVENANT_INVOCATION_SYSTEM.md for full specification.
"""

from ciris_engine.logic.covenant.executor import CovenantExecutionResult, CovenantExecutor, execute_covenant
from ciris_engine.logic.covenant.extractor import CovenantExtractor, extract_covenant
from ciris_engine.logic.covenant.handler import CovenantHandler, check_for_covenant, get_covenant_handler
from ciris_engine.logic.covenant.verifier import CovenantVerifier, verify_covenant

__all__ = [
    "CovenantExtractor",
    "extract_covenant",
    "CovenantVerifier",
    "verify_covenant",
    "CovenantExecutor",
    "execute_covenant",
    "CovenantExecutionResult",
    "CovenantHandler",
    "get_covenant_handler",
    "check_for_covenant",
]
