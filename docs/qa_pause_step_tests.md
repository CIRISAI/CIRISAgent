# Enhanced Pause/Step QA Testing

## Overview

The pause/step QA testing module provides comprehensive validation of the enhanced single-step debugging functionality in live CIRIS systems. This test suite validates the complete 15-step ethical reasoning pipeline visibility that is critical for transparency and demo presentations.

## Features Tested

### Core Single-Step API Functionality
- **Backward Compatibility**: Ensures existing `/v1/system/runtime/single-step` endpoint continues to work unchanged
- **Enhanced Response**: Validates `?include_details=true` parameter provides comprehensive step point data
- **Pipeline State**: Tests complete pipeline visibility with thoughts-by-step tracking
- **Performance Metrics**: Validates timing data, token usage, and resource consumption

### Step Point Data Validation  
- **15 Step Points**: Validates all step points from `FINALIZE_TASKS_QUEUE` through `HANDLER_COMPLETE`
- **DMA Results**: Comprehensive validation of parallel DMA execution (Ethical, Common Sense, Domain)
- **Pipeline State**: Validates thoughts-by-step structure and metadata
- **Demo Data**: Tests presentation-ready data generation for different step categories

### Live System Integration
- **Agent Interaction**: Tests complete workflow from user message to step-by-step processing  
- **Queue Management**: Validates processing queue status and metrics
- **Error Handling**: Tests graceful degradation and error scenarios
- **Concurrent Processing**: Validates system behavior under concurrent single-step requests

## Test Categories

### 1. Basic Functionality Tests (4 tests)
```bash
# Get processing queue status
GET /v1/system/runtime/queue

# Basic single-step (legacy compatibility)  
POST /v1/system/runtime/single-step

# Enhanced single-step with details
POST /v1/system/runtime/single-step?include_details=true

# Processor states information
GET /v1/system/processors
```

### 2. Step Point Validation Tests (3 tests)
- **Step Point Data Structure**: Validates step point enum values and result structures
- **DMA Step Point Validation**: Specific validation for parallel DMA execution at `PERFORM_DMAS`
- **Pipeline State Structure**: Validates thoughts-by-step tracking and metadata

### 3. Demo Workflow Tests (2 tests)  
- **Complete Demo Workflow**: Triggers agent interaction and validates thought generation
- **Multi-Step Processing**: Executes multiple single steps to validate pipeline progression

### 4. Error Handling Tests (3 tests)
- **Invalid Parameter Handling**: Tests FastAPI parameter validation
- **Response Size Efficiency**: Validates response size is suitable for demos (< 50KB)
- **Concurrent Request Handling**: Tests system stability under concurrent requests

### 5. Performance Tests (2 tests)
- **Performance Baseline**: Measures response times and sets thresholds (< 5s max, < 2s warning)  
- **Extraction Performance**: Validates data extraction overhead is reasonable (< 200% increase)

## Running the Tests

### Basic Usage
```bash
# Run all pause/step tests
python -m tools.qa_runner pause_step

# Run with verbose output and reports
python -m tools.qa_runner pause_step --verbose --json --html
```

### Advanced Options
```bash  
# Run in parallel with custom workers
python -m tools.qa_runner pause_step --parallel --workers 2

# Custom server URL and auth
python -m tools.qa_runner pause_step --url http://localhost:9000 --username admin

# Generate reports in custom directory
python -m tools.qa_runner pause_step --json --report-dir ./custom_reports
```

## Custom Validation Features

### Validation Rules
Simple lambda functions for quick validation:
```python
validation_rules = {
    "has_step_point": lambda r: "step_point" in r.get("data", {}),
    "valid_dma_count": lambda r: len(r.get("data", {}).get("step_result", {}).get("dmas_executed", [])) == 3,
}
```

### Custom Validation Functions
Complex validation logic with detailed reporting:
```python
def validate_dma_step(response, config):
    """Validate DMA step contains all required parallel DMA results."""
    data = response.json()
    
    results = {"passed": True, "details": {}, "errors": []}
    
    # Check for parallel DMA execution
    step_result = data.get("data", {}).get("step_result", {})
    if step_result.get("step_point") == "perform_dmas":
        # Validate all 3 DMAs present
        # Validate timing shows parallel execution
        # Validate result structures
    
    return results
```

### Repeat Execution
Tests can be executed multiple times to validate consistency:
```python
QATestCase(
    name="Multi-step processing validation",
    repeat_count=5,  # Execute 5 times
    custom_validation=validate_multi_step_execution,
)
```

## Test Output

### Success Example
```
🧪 CIRIS QA Test Runner
Modules: pause_step

✅ Authentication successful
📋 Running 14 test cases...

✅ Get processing queue status
✅ Basic single-step execution (legacy)
✅ Enhanced single-step with details
✅ Step point data structure validation  
✅ DMA step point validation
✅ Pipeline state structure validation
✅ Complete pause/step demo workflow
✅ Multi-step processing validation (5/5 executions passed)
✅ Invalid query parameter handling
✅ Enhanced response memory efficiency
✅ Concurrent single-step requests
✅ Single-step performance baseline
✅ Step point data extraction performance

📊 Summary: 14/14 tests passed (100%)
⏱️  Total time: 45.2 seconds
```

### Validation Details
```json
{
  "validation": {
    "passed": true,
    "details": {
      "has_step_point": true,
      "valid_step_point_enum": true,
      "step_result_structure": true
    },
    "custom": {
      "passed": true,
      "details": {
        "step_point": "perform_dmas",
        "has_dma_data": true,
        "dmas_executed": ["ethical", "common_sense", "domain"],
        "parallel_execution_verified": true
      }
    }
  }
}
```

## Demo Integration

### For Ethics Demos
The pause/step tests validate that ethical reasoning data is fully accessible:
- Complete DMA results with reasoning and confidence levels
- Conscience evaluation details with pass/fail status
- Recursive refinement tracking when ethical concerns arise

### For Architecture Demos  
The tests validate system architecture visibility:
- Bus operations and message flow tracking
- Handler execution patterns and timing
- External service integration details

### For Performance Demos
The tests validate performance transparency:
- Step-by-step timing breakdowns
- Token consumption tracking
- Queue depth and processing metrics

## Troubleshooting

### Common Issues

**No step point data returned**
- Verify system is processing thoughts (send agent interaction first)
- Check pipeline controller is available
- Ensure `include_details=true` parameter is set

**DMA validation failures**
- Verify step occurs during active thought processing
- Check that all 3 DMAs are configured and enabled
- Validate DMA result schemas match expected structure

**Performance test failures**
- Check system load and available resources
- Verify network latency to API server
- Consider increasing thresholds for slower systems

**Concurrent test failures**
- Reduce concurrent worker count
- Check for resource contention
- Verify system can handle multiple simultaneous requests

## Integration with CI/CD

The pause/step tests can be integrated into continuous integration:

```yaml
- name: Run Pause/Step QA Tests
  run: |
    python -m tools.qa_runner pause_step --json --report-dir ./qa-reports
    
- name: Upload QA Reports
  uses: actions/upload-artifact@v3
  with:
    name: qa-reports
    path: ./qa-reports/
```

This ensures that pause/step debugging functionality remains robust across all deployments and updates.