import logging
from typing import Optional

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.schemas.persistence.core import DeferralPackage, DeferralReportContext

logger = logging.getLogger(__name__)


def save_deferral_report_mapping(
    message_id: str,
    task_id: str,
    thought_id: str,
    package: Optional[DeferralPackage] = None,
    db_path: Optional[str] = None,
) -> None:
    adapter = get_adapter()
    columns = ["message_id", "task_id", "thought_id", "package_json"]
    sql = adapter.upsert(table="deferral_reports", columns=columns, conflict_columns=["message_id"])

    package_json = package.model_dump_json() if package is not None else None
    try:
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, (message_id, task_id, thought_id, package_json))
            conn.commit()
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


def get_deferral_report_context(message_id: str, db_path: Optional[str] = None) -> Optional[DeferralReportContext]:
    sql = "SELECT task_id, thought_id, package_json FROM deferral_reports WHERE message_id = ?"
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (message_id,))
            row = cursor.fetchone()
            if row:
                pkg = None
                if row["package_json"]:
                    try:
                        # Validate package data through model
                        from pydantic import TypeAdapter

                        pkg = TypeAdapter(DeferralPackage).validate_json(row["package_json"])
                    except Exception as e:
                        logger.warning(f"Failed to parse deferral package: {e}")
                        pkg = None

                return DeferralReportContext(task_id=row["task_id"], thought_id=row["thought_id"], package=pkg)
            return None
    except Exception as e:
        logger.exception(
            "Failed to fetch deferral report context for message %s: %s",
            message_id,
            e,
        )
        return None
