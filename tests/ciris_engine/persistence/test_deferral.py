import pytest
import tempfile
import os
import json
from ciris_engine.persistence import initialize_database
from ciris_engine.persistence import (
    save_deferral_report_mapping,
    get_deferral_report_context,
)
from ciris_engine.schemas.persistence_schemas_v1 import DeferralPackage

def temp_db_file():
    f = tempfile.NamedTemporaryFile(delete=False)
    f.close()
    return f.name

def create_deferral_reports_table(db_path):
    from ciris_engine.persistence import get_db_connection
    sql = '''
    CREATE TABLE IF NOT EXISTS deferral_reports (
        message_id TEXT PRIMARY KEY,
        task_id TEXT,
        thought_id TEXT,
        package_json TEXT
    )'''
    with get_db_connection(db_path=db_path) as conn:
        conn.execute(sql)
        conn.commit()

def test_save_and_get_deferral_report_mapping():
    db_path = temp_db_file()
    try:
        initialize_database(db_path=db_path)
        create_deferral_reports_table(db_path)
        message_id = "msg1"
        task_id = "task1"
        thought_id = "th1"
        package = DeferralPackage(
            defer_until="2025-06-17T12:00:00Z",
            reason="Test deferral",
            context={"foo": "bar", "num": 42}
        )
        save_deferral_report_mapping(message_id, task_id, thought_id, package, db_path=db_path)
        result = get_deferral_report_context(message_id, db_path=db_path)
        assert result is not None
        assert result.task_id == task_id
        assert result.thought_id == thought_id
        assert result.package is not None
        assert result.package.defer_until == package.defer_until
        assert result.package.reason == package.reason
        assert result.package.context == package.context
    finally:
        os.unlink(db_path)

def test_save_deferral_report_mapping_none_package():
    db_path = temp_db_file()
    try:
        initialize_database(db_path=db_path)
        create_deferral_reports_table(db_path)
        message_id = "msg2"
        task_id = "task2"
        thought_id = "th2"
        save_deferral_report_mapping(message_id, task_id, thought_id, None, db_path=db_path)
        result = get_deferral_report_context(message_id, db_path=db_path)
        assert result is not None
        assert result.task_id == task_id
        assert result.thought_id == thought_id
        assert result.package is None
    finally:
        os.unlink(db_path)

def test_get_deferral_report_context_not_found():
    db_path = temp_db_file()
    try:
        initialize_database(db_path=db_path)
        create_deferral_reports_table(db_path)
        result = get_deferral_report_context("doesnotexist", db_path=db_path)
        assert result is None
    finally:
        os.unlink(db_path)
