"""Shared boolean-environment-variable parsing.

The repo had four different conventions for reading a boolean env var
(``== "true"``, ``in ("true","1","yes","on")``, ``in ("true","1","yes")``, and
presence-only). Presence-only is the dangerous one: ``CIRIS_MOCK_LLM=false``
evaluates *True* at ``adapters/api/routes/agent.py:959``.

This module is the one convention. It is deliberately tiny and dependency-free
so anything can import it without a cycle.
"""

import os
from typing import Final, FrozenSet

#: The accepted truthy spellings. Promoted from
#: ``adapters/api/routes/setup/config.py:196``, which was module-private with a
#: single consumer.
TRUTHY: Final[FrozenSet[str]] = frozenset({"true", "1", "yes", "on"})


def env_is_true(name: str, default: str = "") -> bool:
    """Return True iff env var ``name`` holds a truthy spelling.

    Absence is False. Presence with any other value (including ``"false"``,
    ``""``, ``"0"``) is False — never presence-only.
    """
    return os.getenv(name, default).strip().lower() in TRUTHY
