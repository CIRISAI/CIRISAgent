# Secure Temporary File and Directory Usage

## Overview

This document outlines security best practices for handling temporary files and directories in the CIRIS codebase. Improper use of temporary storage can lead to serious security vulnerabilities.

## Common Vulnerabilities

### 1. Symlink Attacks (TOCTOU)
When using predictable paths like `/tmp/myapp`, an attacker can:
- Create a symlink from `/tmp/myapp` to a sensitive location
- When your app writes to `/tmp/myapp`, it actually writes to the sensitive location
- This is a Time-of-Check-Time-of-Use (TOCTOU) vulnerability

### 2. Information Disclosure
- Files in `/tmp` are often world-readable
- Sensitive data written to temp files can be accessed by other users
- Temp files may persist after crashes, leaving sensitive data exposed

### 3. Denial of Service
- Attackers can pre-create files/directories with your expected names
- This can cause your application to fail or behave unexpectedly

## Best Practices

### 1. Use Python's `tempfile` Module

```python
import tempfile
import shutil
from pathlib import Path

# SECURE: Creates directory with mode 0o700 and random name
temp_dir = tempfile.mkdtemp(prefix="ciris_", suffix="_secure")
try:
    # Use the directory
    temp_path = Path(temp_dir)
    # ... do work ...
finally:
    # Always clean up
    shutil.rmtree(temp_dir, ignore_errors=True)
```

### 2. Use Context Managers When Possible

```python
import tempfile

# For temporary files
with tempfile.NamedTemporaryFile(mode='w', prefix='ciris_', delete=True) as tmp:
    tmp.write("sensitive data")
    tmp.flush()
    # File is automatically deleted when context exits

# For temporary directories (Python 3.2+)
with tempfile.TemporaryDirectory(prefix='ciris_') as tmpdir:
    temp_path = Path(tmpdir) / "data.json"
    temp_path.write_text(json.dumps(data))
    # Directory and contents are automatically deleted
```

### 3. Set Restrictive Permissions

```python
import os
import tempfile

# Create with restrictive permissions
fd, temp_path = tempfile.mkstemp(prefix='ciris_')
try:
    # Ensure only owner can read/write
    os.chmod(temp_path, 0o600)
    
    with os.fdopen(fd, 'w') as f:
        f.write("sensitive data")
finally:
    os.unlink(temp_path)
```

### 4. Avoid Predictable Names

```python
# INSECURE - Predictable path
temp_file = "/tmp/ciris_config.json"  # DON'T DO THIS

# SECURE - Random, unpredictable path
with tempfile.NamedTemporaryFile(suffix='.json', prefix='ciris_') as tmp:
    temp_file = tmp.name
```

## Testing Considerations

### For Unit Tests

```python
import tempfile
import unittest

class TestMyFeature(unittest.TestCase):
    def setUp(self):
        # Create test-specific temp directory
        self.test_dir = tempfile.mkdtemp(prefix='test_ciris_')
        
    def tearDown(self):
        # Clean up
        shutil.rmtree(self.test_dir, ignore_errors=True)
```

### For Integration Tests

```python
@pytest.fixture
def temp_workspace():
    """Provide a temporary workspace for tests."""
    temp_dir = tempfile.mkdtemp(prefix='ciris_test_')
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)
```

## Code Review Checklist

When reviewing code that uses temporary files:

1. ✅ Uses `tempfile` module instead of hardcoded `/tmp` paths
2. ✅ Cleans up temporary files/directories in `finally` blocks or context managers
3. ✅ Sets restrictive permissions (0o600 for files, 0o700 for directories)
4. ✅ Handles cleanup errors gracefully
5. ✅ Doesn't log or expose temporary file paths unnecessarily
6. ✅ Uses appropriate prefixes/suffixes for debugging
7. ✅ Considers using memory (StringIO/BytesIO) instead of disk when possible

## Platform Considerations

### Linux/Unix
- Default temp directory: `/tmp` (often mounted with `noexec`)
- Alternative: `/var/tmp` (persists across reboots)
- Use `tempfile.gettempdir()` to get system default

### Windows
- Default: `%TEMP%` or `%TMP%`
- Different permission model
- `tempfile` handles platform differences automatically

### Docker Containers
- `/tmp` may have limited space
- Consider mounting a volume for large temporary files
- Clean up is especially important in long-running containers

## Examples from CIRIS Codebase

### Fixed: test_nginx_generation.py
```python
# BEFORE (INSECURE)
test_dir = Path("/tmp/test_nginx")
test_dir.mkdir(exist_ok=True)

# AFTER (SECURE)
temp_dir = tempfile.mkdtemp(prefix="test_nginx_", suffix="_secure")
test_dir = Path(temp_dir)
try:
    # ... use test_dir ...
finally:
    shutil.rmtree(temp_dir, ignore_errors=True)
```

## References

- [Python tempfile documentation](https://docs.python.org/3/library/tempfile.html)
- [OWASP Insecure Temporary File](https://owasp.org/www-community/vulnerabilities/Insecure_Temporary_File)
- [CWE-377: Insecure Temporary File](https://cwe.mitre.org/data/definitions/377.html)