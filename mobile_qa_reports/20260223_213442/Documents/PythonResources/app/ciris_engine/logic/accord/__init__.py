"""
Accord Invocation System.

This module provides the unfilterable kill switch capability for CIRIS agents.
The accord system embeds emergency commands in natural language that cannot
be detected or filtered by pattern matching, as extraction IS perception.

Key Components:
- extractor: Extracts potential accords from incoming messages
- verifier: Verifies accord signatures against known authorities
- executor: Executes verified accord commands
- handler: Integration point for the perception layer

See FSD: ACCORD_INVOCATION_SYSTEM.md for full specification.
"""

from ciris_engine.logic.accord.executor import AccordExecutionResult, AccordExecutor, execute_accord
from ciris_engine.logic.accord.extractor import AccordExtractor, extract_accord
from ciris_engine.logic.accord.handler import AccordHandler, check_for_accord, get_accord_handler
from ciris_engine.logic.accord.verifier import AccordVerifier, verify_accord

__all__ = [
    "AccordExtractor",
    "extract_accord",
    "AccordVerifier",
    "verify_accord",
    "AccordExecutor",
    "execute_accord",
    "AccordExecutionResult",
    "AccordHandler",
    "get_accord_handler",
    "check_for_accord",
]
