import sqlite3
import logging
from ciris_engine.config.config_manager import get_sqlite_db_full_path
from ciris_engine.schemas.db_tables_v1 import tasks_table_v1, thoughts_table_v1, feedback_mappings_table_v1

logger = logging.getLogger(__name__)

def get_db_connection(db_path=None) -> sqlite3.Connection:
    """Establishes a connection to the SQLite database with foreign key support."""
    if db_path is None:
        db_path = get_sqlite_db_full_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def get_task_table_schema_sql() -> str:
    return tasks_table_v1

def get_thought_table_schema_sql() -> str:
    return thoughts_table_v1

def get_feedback_mappings_table_schema_sql() -> str:
    return feedback_mappings_table_v1

def initialize_database(db_path=None):
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(get_task_table_schema_sql())
            cursor.execute(get_thought_table_schema_sql())
            cursor.execute(get_feedback_mappings_table_schema_sql())
            conn.commit()
        logger.info(f"Database tables ensured at {db_path or get_sqlite_db_full_path()}")
    except sqlite3.Error as e:
        logger.exception(f"Database error during table creation: {e}")
        raise

def get_all_tasks(db_path=None):
    """Returns all tasks from the tasks table as a list of dicts."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_tasks_by_status(status: str, db_path=None):
    """Returns all tasks with the given status from the tasks table as a list of dicts."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE status = ?", (status,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_thoughts_by_status(status: str, db_path=None):
    """Returns all thoughts with the given status from the thoughts table as a list of dicts."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM thoughts WHERE status = ?", (status,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_tasks_older_than(older_than_timestamp: str, db_path=None):
    """Returns all tasks with created_at older than the given ISO timestamp."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE created_at < ?", (older_than_timestamp,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

def get_thoughts_older_than(older_than_timestamp: str, db_path=None):
    """Returns all thoughts with created_at older than the given ISO timestamp."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM thoughts WHERE created_at < ?", (older_than_timestamp,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
