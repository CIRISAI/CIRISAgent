"""Did interact() return the agent's reply, or a placeholder? (#1059)

`POST /v1/agent/interact` answers HTTP 200 in every case and always puts text
in `response` — the agent's reply, or, when the deadline passes first, the
localized "still processing" placeholder. A check that grades
`bool(response_text)` therefore counts a timeout as a pass, and a check that
matches the English placeholder misses it for every non-English agent.

Servers from #1186 on say which it was in `outcome` (`complete` / `timeout` /
`paused`) and name the still-running task in `task_id`. For servers that
predate the field, the fallback is: no `task_id` AND the text is the
placeholder in any of the agent's locales — loaded from the same localized
string tables the server renders it from, never hardcoded.

One helper for every QA module, so the rule is decided once.
"""

from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, FrozenSet, Mapping, Optional

#: Where the server's localized UI strings live (`agent.still_processing`).
LOCALIZED_DIR = Path(__file__).resolve().parents[3] / "ciris_engine" / "data" / "localized"

#: Last-resort English placeholder, used only if the tables cannot be read.
_ENGLISH_PLACEHOLDER = "Still processing. Check back later. Agent response is not guaranteed."


class InteractNonReply(str, Enum):
    """Why an interact() body is not the agent's reply. The value is the
    `error` string QA modules record."""

    TIMEOUT = "interact timeout"
    PAUSED = "interact paused"


@lru_cache(maxsize=1)
def still_processing_placeholders() -> FrozenSet[str]:
    """Every locale's rendering of `agent.still_processing`."""
    found = {_ENGLISH_PLACEHOLDER}
    try:
        files = sorted(LOCALIZED_DIR.glob("*.json"))
    except OSError:
        return frozenset(found)
    for path in files:
        try:
            table = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        agent = table.get("agent") if isinstance(table, dict) else None
        text = agent.get("still_processing") if isinstance(agent, dict) else None
        if isinstance(text, str) and text.strip():
            found.add(text.strip())
    return frozenset(found)


def is_still_processing_text(text: Optional[str]) -> bool:
    """True if `text` is (or begins with) the placeholder in any locale."""
    if not text:
        return False
    stripped = text.strip()
    return any(stripped.startswith(p) for p in still_processing_placeholders())


def interact_non_reply(data: Mapping[str, Any]) -> Optional[InteractNonReply]:
    """Why this interact() `data` payload is not a reply, or None if it is one.

    `data` is the unwrapped body (`body["data"]`); a flat body works too.
    """
    outcome = data.get("outcome")
    if isinstance(outcome, str) and outcome:
        if outcome == "timeout":
            return InteractNonReply.TIMEOUT
        if outcome == "paused":
            return InteractNonReply.PAUSED
        return None
    # Pre-#1186 server: no outcome field. A timed-out interaction could not
    # name its task, so a missing task_id plus placeholder text is the tell.
    if not data.get("task_id") and is_still_processing_text(data.get("response")):
        return InteractNonReply.TIMEOUT
    return None


def interact_timed_out(data: Mapping[str, Any]) -> bool:
    """True when the server's deadline passed before the agent replied."""
    return interact_non_reply(data) is InteractNonReply.TIMEOUT


__all__ = [
    "InteractNonReply",
    "interact_non_reply",
    "interact_timed_out",
    "is_still_processing_text",
    "still_processing_placeholders",
]
