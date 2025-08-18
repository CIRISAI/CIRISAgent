# Logging Test Requirements

## Critical: PYTEST_CURRENT_TEST Environment Variable

**MUST ALWAYS** temporarily clear the `PYTEST_CURRENT_TEST` environment variable in logging tests that verify file creation.

### Why This Is Critical

1. When `PYTEST_CURRENT_TEST` is set (which pytest does automatically), our logging initialization code skips file creation to avoid cluttering the filesystem during tests.
2. This caused the v1.4.3 regression where logging wasn't properly tested and broke in production.
3. Tests that verify logging file creation MUST temporarily clear this variable to test the actual production behavior.

### Pattern to Follow

```python
@pytest.mark.asyncio
async def test_logging_creates_files(self):
    """Test that verifies log files are created."""

    # CRITICAL: Temporarily clear PYTEST_CURRENT_TEST to enable logging file creation
    original_pytest_env = os.environ.pop("PYTEST_CURRENT_TEST", None)
    try:
        # Your test code here that expects log files to be created
        runtime = CIRISRuntime(...)
        await runtime.initialize()

        # Verify files were created
        assert Path("logs/latest.log").exists()

    finally:
        # CRITICAL: Restore PYTEST_CURRENT_TEST to not affect other tests
        if original_pytest_env is not None:
            os.environ["PYTEST_CURRENT_TEST"] = original_pytest_env
```

## What the Logging System Should Create

The logging system creates **4 tracking mechanisms** for log files:

1. **`latest.log`** - Symlink to the current main log file
2. **`incidents_latest.log`** - Symlink to the current incident log file
3. **`.current_log`** - Hidden file containing the path to current main log
4. **`.current_incident_log`** - Hidden file containing the path to current incident log

Plus the actual log files:
- `ciris_agent_YYYYMMDD_HHMMSS.log` - Main log file
- `incidents_YYYYMMDD_HHMMSS.log` - Incident log file (warnings and errors only)

## Tests That Must Follow This Pattern

1. `test_logging_creates_all_required_files` - Verifies all files are created
2. `test_logging_creates_actual_files_and_all_symlinks` - Verifies symlinks work
3. `test_logging_symlinks_are_updated_on_restart` - Verifies symlinks update on restart
4. `test_all_four_tracking_mechanisms` - Explicitly tests all 4 tracking mechanisms

## Common Pitfalls to Avoid

1. **Don't forget the try/finally block** - Always restore the env variable
2. **Don't assume log directory exists** - Create it if needed
3. **Don't hardcode log paths** - Use Path objects and glob patterns
4. **Test both existence and validity** - Symlinks should point to real files

## Why We Have 4 Tracking Mechanisms

- **Symlinks** (`latest.log`, `incidents_latest.log`) - Easy for users to tail/view
- **Hidden files** (`.current_log`, `.current_incident_log`) - Reliable fallback if symlinks fail
- This redundancy ensures we can always find the current log files even if symlink creation fails on some systems

## Testing Checklist

- [ ] Test creates actual log files
- [ ] Test creates both visible symlinks
- [ ] Test creates both hidden tracking files
- [ ] Test symlinks point to correct files
- [ ] Test hidden files contain correct paths
- [ ] Test symlinks update on runtime restart
- [ ] Test incident log is created when warnings/errors occur
- [ ] Test graceful handling when symlink creation fails

## Regression Prevention

To prevent another v1.4.3-style regression:

1. **Always run these tests locally** before marking logging changes as complete
2. **Verify in CI** that these tests are actually creating files (check test output)
3. **Never skip these tests** even if they seem slow
4. **Document any changes** to the logging system in this file

## Related Files

- `ciris_engine/logic/runtime/ciris_runtime.py` - Runtime initialization
- `ciris_engine/logic/runtime/logging_setup.py` - Logging configuration
- `tests/logic/runtime/test_ciris_runtime_logging.py` - Logging tests
