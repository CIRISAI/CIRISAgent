# CIRIS Single-Step UI Guide

## Overview

This guide covers implementing UI for CIRIS's single-step debugging system. The H3ERE pipeline has 9 core steps + 2 optional recursive steps to show transparent AI reasoning.

## API Integration

### Single-Step Endpoint
```
POST /v1/system/runtime/step
```

### Response Schema
```typescript
interface SingleStepResponse {
  success: boolean;
  message: string;
  step_point?: StepPoint;
  step_result?: StepResult;
  processing_time_ms: number;
  pipeline_state?: PipelineState;
}
```

### Streaming Endpoint (Real-time)
```
GET /v1/system/runtime/reasoning-stream
Authorization: Bearer {token} (OBSERVER role or higher)
Accept: text/event-stream
```

Streams live step updates as Server-Sent Events during normal processing.

## UI Components

### 1. Pipeline Visualization
- SVG diagram showing 15 step points in sequence
- Highlight current step with color/animation
- Show step names and brief descriptions

### 2. Step Data Panel
Display step-specific information based on `step_point`:

**Queue Management Steps (1-3)**:
- Task selection and prioritization
- Thought generation from tasks
- Batch processing setup

**Reasoning Steps (4-9)**:
- Context building with system state
- Parallel DMA execution (Ethical, Common Sense, Domain)
- ASPDMA action selection with LLM reasoning
- Conscience safety checks
- Recursive refinement if needed

**Execution Steps (10-15)**:
- Handler and bus processing
- Package handling at adapters
- Completion and results

### 3. Performance Metrics
Show for each step:
- Processing time in milliseconds
- Token usage (if applicable)
- Success/failure status
- Any errors or warnings

### 4. Transparency Features

**For Ethics Demos**:
- DMA reasoning and results
- Conscience evaluation details
- Safety check outcomes

**For Architecture Demos**:
- Bus message flow
- Handler execution details
- Service interactions

## Step Points Reference

### H3ERE Pipeline Order (Exact UI Team Specification)
0. `START_ROUND` - Setup: Tasks → Thoughts → Round Queue
1. `GATHER_CONTEXT` - Build comprehensive context
2. `PERFORM_DMAS` - Execute parallel multi-perspective DMAs
3. `PERFORM_ASPDMA` - LLM action selection
4. `CONSCIENCE_EXECUTION` - Ethical safety validation
3B. `RECURSIVE_ASPDMA` - Re-run action selection *(conditional - only if step 4 fails)*
4B. `RECURSIVE_CONSCIENCE` - Re-validate refined action *(conditional - only if step 3B executes)*
5. `FINALIZE_ACTION` - Final action determination
6. `PERFORM_ACTION` - Dispatch action to handler
7. `ACTION_COMPLETE` - Action execution completed
8. `ROUND_COMPLETE` - Processing round completed

## Implementation Tips

### Basic Integration
```typescript
async function executeSingleStep(includeDetails = false) {
  const response = await fetch('/v1/system/runtime/step', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      include_details: includeDetails
    })
  });
  
  const result = await response.json();
  updateUI(result.data);
}
```

### UI Updates
```typescript
function updateUI(stepData: SingleStepResponse) {
  // Update pipeline highlight
  highlightCurrentStep(stepData.step_point);
  
  // Show step-specific data
  updateStepPanel(stepData.step_result);
  
  // Update performance metrics
  updateMetrics({
    time: stepData.processing_time_ms,
    tokens: stepData.tokens_used,
    success: stepData.success
  });
  
  // Show demo data if available
  if (stepData.demo_data) {
    updateDemoPanel(stepData.demo_data);
  }
}
```

### Error Handling
```typescript
function handleStepError(error) {
  console.error('Single step failed:', error);
  showErrorMessage('Pipeline step failed. Check logs for details.');
  // Optionally pause stepping or retry
}
```

## Demo Scenarios

### Ethics Transparency Demo
Focus on steps 5-7 (DMA → ASPDMA → Conscience) to show:
- Multi-perspective ethical evaluation
- LLM reasoning process
- Safety mechanism activation

### Architecture Demo
Focus on steps 11-15 (Handler → Bus → Package → Complete) to show:
- Message bus operations
- Adapter transformations  
- Service orchestration

### Performance Demo
Show timing and resource usage across all steps to demonstrate:
- Parallel processing efficiency
- Resource optimization
- System responsiveness

## Notes

- Always use `include_details=true` for comprehensive step data
- Handle conditional steps (8-9) that may not always execute
- Implement proper error boundaries around step execution
- Cache step results for replay/analysis features
- Consider WebSocket connection for real-time updates in future versions