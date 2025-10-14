# Multi-Occurrence QA Test Module

## Overview

The multi-occurrence QA test module validates the multi-occurrence functionality that enables multiple API instances to run against the same SQLite database with proper isolation between instances.

## Purpose

This test suite ensures:
- Each runtime instance only processes tasks/thoughts with its own `agent_occurrence_id`
- Tasks and thoughts are properly stamped with the creating instance's occurrence ID
- Database queries correctly filter by occurrence ID
- System telemetry and health reports reflect only the current occurrence's state
- Memory operations maintain occurrence context
- Audit trails correctly track occurrence information

## Test Coverage

### Configuration Tests (2 tests)
- **Verify occurrence_id in config**: Ensures `agent_occurrence_id` is present in system configuration
- **Verify default occurrence_id value**: Validates backward compatibility with "default" value

### Task Isolation Tests (2 tests)
- **Create task - verify occurrence stamping**: Submits message and verifies task is stamped with correct occurrence ID
- **Query tasks - verify occurrence filtering**: Validates queue status only shows tasks for the current occurrence

### Agent Interaction Tests (1 test)
- **Agent interaction - occurrence context**: Tests that agent interactions maintain proper occurrence context

### Telemetry & Monitoring Tests (2 tests)
- **Telemetry - occurrence metrics**: Verifies telemetry reports metrics for the current occurrence only
- **System health - occurrence context**: Validates system health reflects the current occurrence state

### Memory Tests (2 tests)
- **Memory store - occurrence context**: Tests memory storage in occurrence context
- **Memory query - occurrence isolation**: Verifies memory queries respect occurrence boundaries

### Audit Tests (1 test)
- **Audit entries - occurrence filtering**: Ensures audit entries are tagged with occurrence ID

### History Tests (1 test)
- **Interaction history - occurrence scope**: Validates interaction history is scoped to the current occurrence

### Concurrent Processing Tests (4 tests)
- **Concurrent message 1-3**: Tests concurrent message handling with occurrence isolation
- **Queue verification after concurrent operations**: Verifies queue correctly shows only this occurrence's tasks

## Running the Tests

### Run the full multi-occurrence test suite:
```bash
python -m tools.qa_runner multi_occurrence
```

### Run with verbose output:
```bash
python -m tools.qa_runner multi_occurrence --verbose
```

## Test Results

All 15 tests should pass with 100% success rate:

```
     QA Test Summary
┏━━━━━━━━━━━━━━┳━━━━━━━━┓
┃ Metric       ┃ Value  ┃
┡━━━━━━━━━━━━━━╇━━━━━━━━┩
│ Total Tests  │ 15     │
│ Passed       │ 15     │
│ Failed       │ 0      │
│ Success Rate │ 100.0% │
│ Duration     │ ~27s   │
└──────────────┴────────┘
```

## Additional Test Suites

The module also includes:
- **Stress tests**: 10 rapid message submissions to test occurrence isolation under load

### Run stress tests:
```python
from tools.qa_runner.modules.multi_occurrence_tests import MultiOccurrenceTestModule

# Get stress test suite
stress_tests = MultiOccurrenceTestModule.get_occurrence_stress_tests()

# Get full suite (standard + stress)
full_suite = MultiOccurrenceTestModule.get_full_test_suite()
```

## Architecture Validation

This test suite validates the complete multi-occurrence architecture:

1. **Schema Level**: Database schema with `agent_occurrence_id` columns
2. **Domain Level**: Task, Thought, and Context models include occurrence ID
3. **Persistence Level**: All queries filter by occurrence ID
4. **Service Level**: TaskManager and ThoughtManager respect occurrence boundaries
5. **Processor Level**: MainProcessor and state processors pass occurrence ID through
6. **Configuration Level**: EssentialConfig exposes `agent_occurrence_id` setting
7. **Runtime Level**: Occurrence ID threads through entire initialization

## Integration with CI/CD

This test suite can be integrated into CI/CD pipelines to ensure multi-occurrence functionality remains stable across releases.

## Future Enhancements

Potential future test additions:
- Cross-occurrence database integrity verification
- Occurrence ID collision handling
- Dynamic occurrence ID changes (if supported)
- Multi-occurrence coordination tests (if applicable)
- Performance benchmarks for multi-occurrence vs single-occurrence

## Related Documentation

- `/home/emoore/CIRISAgent/docs/multi_occurrence_implementation_plan.md` - Implementation plan
- `/home/emoore/CIRISAgent/tests/test_multi_occurrence_isolation.py` - Unit tests
- `/home/emoore/CIRISAgent/ciris_engine/schemas/config/essential.py` - Configuration schema
