# Database Retry Mechanism Migration Guide

## Overview

A minimal retry mechanism has been added to handle SQLite busy errors that occur during concurrent database access. This guide shows how to migrate existing persistence code to use the retry mechanism.

## Quick Start

### Option 1: Minimal Change - Add Busy Timeout

For simple cases, just add a busy timeout to your connection:

```python
# Before
with get_db_connection(db_path) as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ...", params)
    conn.commit()

# After - Add busy timeout (5 seconds)
with get_db_connection(db_path, busy_timeout=5000) as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ...", params)
    conn.commit()
```

### Option 2: Use Retry Context Manager

For better reliability, use the retry-enabled connection:

```python
from ciris_engine.logic.persistence.db import get_db_connection_with_retry

# Automatically includes WAL mode and busy timeout
with get_db_connection_with_retry(db_path) as conn:
    cursor = conn.cursor()
    cursor.execute("INSERT INTO ...", params)
    conn.commit()
```

### Option 3: Full Retry Logic

For critical operations, use the full retry wrapper:

```python
from ciris_engine.logic.persistence.db import execute_with_retry

def add_task(task: Task, db_path: Optional[str] = None) -> str:
    def _insert(conn):
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (...) VALUES (...)",
            params
        )
        conn.commit()
        return task.task_id

    return execute_with_retry(_insert, db_path)
```

### Option 4: Decorator for Methods

Use the retry decorator for class methods:

```python
from ciris_engine.logic.persistence.db import with_retry

class TaskPersistence:
    @with_retry(max_retries=3)
    def update_status(self, task_id: str, status: TaskStatus):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE tasks SET status = ? WHERE task_id = ?",
                (status.value, task_id)
            )
            conn.commit()
```

## Migration Strategy

1. **Start with Option 1** - Add busy timeout to high-contention operations
2. **Use Option 2** for new code
3. **Apply Option 3** to critical write operations that must succeed
4. **Use Option 4** sparingly for entire methods

## Best Practices

1. **Don't retry everything** - Only database busy errors are retryable
2. **Keep transactions small** - Reduces chance of conflicts
3. **Use WAL mode** - Better concurrent access (included in retry utilities)
4. **Set reasonable timeouts** - Default is 5 seconds busy timeout
5. **Log retry attempts** - The retry module logs at DEBUG level

## Configuration

Default retry settings:
- Max retries: 3
- Base delay: 100ms
- Max delay: 1 second
- Exponential backoff: 2x

These can be customized:

```python
execute_with_retry(
    operation,
    max_retries=5,
    base_delay=0.2  # 200ms initial delay
)
```

## Testing

The retry mechanism is designed to be transparent. Existing tests should continue to work. For testing retry behavior specifically:

```python
# Force a busy error in tests
with mock.patch('sqlite3.Connection.execute') as mock_exec:
    mock_exec.side_effect = [
        sqlite3.OperationalError("database is locked"),
        None  # Success on retry
    ]
    # Your test here
```
