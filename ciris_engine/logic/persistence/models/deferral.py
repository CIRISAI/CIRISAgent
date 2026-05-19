"""Deferral report persistence — routes through ciris-persist substrate APIs.

Public function signatures preserved verbatim for backward-compat. Internals
swapped from raw sqlite3 (`deferral_reports` table) to `engine.deferral_*`
substrate (CIRISAgent#763, CIRISPersist#58).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ciris_engine.schemas.persistence.core import DeferralPackage, DeferralReportContext

logger = logging.getLogger(__name__)


def _get_engine() -> Any:
    """Return the wired persist engine; raise if not yet bootstrapped."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "persist engine not initialized — call initialize_database() "
            "before any deferral operation"
        )
    return engine


def save_deferral_report_mapping(
    message_id: str,
    task_id: str,
    thought_id: str,
    package: Optional[DeferralPackage] = None,
) -> None:
    """Persist a deferral report mapping via persist's deferral substrate."""
    engine = _get_engine()

    payload: dict[str, Any] = {
        "message_id": message_id,
        "task_id": task_id,
        "thought_id": thought_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if package is not None:
        # Persist accepts a nested dict for `package`; agent's pydantic dump
        # uses mode="json" so datetimes become RFC-3339 strings.
        payload["package"] = package.model_dump(mode="json")

    try:
        engine.deferral_record(json.dumps(payload))
        logger.debug(
            "Saved deferral report mapping: %s -> task %s, thought %s",
            message_id,
            task_id,
            thought_id,
        )
    except Exception as e:
        logger.exception(
            "Failed to save deferral report mapping for message %s: %s",
            message_id,
            e,
        )


def _parse_package(raw: Any) -> Optional[DeferralPackage]:
    """Coerce a persist `package` field into a DeferralPackage, lenient on errors."""
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("Failed to parse deferral package JSON: %s", e)
            return None
    if not isinstance(raw, dict):
        return None
    try:
        return DeferralPackage(**raw)
    except Exception as e:
        logger.warning("Failed to coerce deferral package payload: %s", e)
        return None


def get_deferral_report_context(message_id: str) -> Optional[DeferralReportContext]:
    """Return DeferralReportContext for `message_id` or None."""
    try:
        engine = _get_engine()
        raw = engine.deferral_get(message_id)
        if raw is None:
            return None
        row = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(row, dict):
            return None
        return DeferralReportContext(
            task_id=str(row["task_id"]),
            thought_id=str(row["thought_id"]),
            package=_parse_package(row.get("package")),
        )
    except Exception as e:
        logger.exception(
            "Failed to fetch deferral report context for message %s: %s",
            message_id,
            e,
        )
        return None
