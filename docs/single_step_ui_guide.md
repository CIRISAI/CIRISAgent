# CIRIS Single-Step UI Guide

## Overview

This guide covers implementing UI for CIRIS's single-step debugging system. The H3ERE pipeline has 11 step points (0-10) for transparent AI reasoning inspection.

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

### Streaming Endpoint (Real-time) - PRIMARY UI DATA SOURCE
```
GET /v1/system/runtime/reasoning-stream
Authorization: Bearer {token} (OBSERVER role or higher)
Accept: text/event-stream
```

**THIS IS HOW THE UI WORKS**: Streams live step updates as Server-Sent Events during all processing. The UI connects to this stream and displays real-time reasoning data as it occurs, independent of processor state.

## UI Components

### 1. Pipeline Visualization
- SVG diagram showing 11 step points in sequence
- Highlight current step with color/animation
- Show step names and brief descriptions

### 2. Step Data Panel
Display step-specific information based on `step_point`:

**Setup Steps (0-1)**:
- Round initialization and thought status transitions
- Context building with system state

**Reasoning Steps (2-4)**:
- Parallel DMA execution (Ethical, Common Sense, Domain)
- ASPDMA action selection with LLM reasoning
- Conscience safety checks

**Recursive Steps (3B-4B)** *(conditional)*:
- Recursive ASPDMA if conscience fails
- Recursive conscience validation

**Execution Steps (5-10)**:
- Final action determination
- Action dispatch and execution
- Completion and round cleanup

### 3. Performance Metrics
Show for each step:
- Processing time in milliseconds
- Token usage (if applicable)
- Success/failure status
- Any errors or warnings

### 4. Transparency Features

**Ethical Reasoning**:
- DMA reasoning and results
- Conscience evaluation details
- Safety check outcomes

**System Architecture**:
- Bus message flow
- Handler execution details
- Service interactions

## Step Points Reference

### H3ERE Pipeline Step Points
0. `START_ROUND` - Setup: Tasks → Thoughts → Round Queue
1. `GATHER_CONTEXT` - Build comprehensive context
2. `PERFORM_DMAS` - Execute parallel multi-perspective DMAs
3. `PERFORM_ASPDMA` - LLM action selection
4. `CONSCIENCE_EXECUTION` - Ethical safety validation
5. `RECURSIVE_ASPDMA` - Re-run action selection *(conditional)*
6. `RECURSIVE_CONSCIENCE` - Re-validate refined action *(conditional)*
7. `FINALIZE_ACTION` - Final action determination
8. `PERFORM_ACTION` - Dispatch action to handler
9. `ACTION_COMPLETE` - Action execution completed
10. `ROUND_COMPLETE` - Processing round completed

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

  // Show transparency data if available
  if (stepData.transparency_data) {
    updateTransparencyPanel(stepData.transparency_data);
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


## Real-Time Streaming Integration

### Primary UI Architecture
The UI should ALWAYS connect to `/v1/system/runtime/reasoning-stream` for live data:

```typescript
const eventSource = new EventSource('/v1/system/runtime/reasoning-stream', {
  headers: { 'Authorization': `Bearer ${token}` }
});

eventSource.addEventListener('step_update', (event) => {
  const stepData = JSON.parse(event.data);
  updateUI(stepData);
});

eventSource.addEventListener('keepalive', (event) => {
  // Connection maintained every 30 seconds
});

eventSource.addEventListener('error', (event) => {
  handleStreamError(JSON.parse(event.data));
});
```

### Stream Event Types
- `connected` - Initial connection established
- `step_update` - Live step result data (primary UI updates)
- `keepalive` - Connection maintenance (every 30s)
- `error` - Stream error information

## Notes

- UI displays live stream data continuously during processing
- Handle conditional steps (RECURSIVE_ASPDMA/RECURSIVE_CONSCIENCE) that may not always execute
- Implement proper error boundaries around stream connection
- Cache stream results for replay/analysis features
- Stream operates independent of single-step mode
