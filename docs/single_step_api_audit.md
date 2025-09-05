# Single-Step API Data Availability Audit

## Current API State

### ✅ Available Endpoints

#### 1. **Single-Step Execution**
**Endpoint**: `POST /v1/system/runtime/single-step`  
**Returns**: `RuntimeControlResponse`
- `success`: Whether step succeeded
- `message`: Human-readable status  
- `processor_state`: Current processor state
- `cognitive_state`: Current cognitive state (currently null)
- `queue_depth`: Queue depth (currently hardcoded to 0)

**Current Limitations**: 
- ❌ No step point identification
- ❌ No step-specific data 
- ❌ No detailed results
- ❌ Missing cognitive state and accurate queue depth

#### 2. **Queue Status**
**Endpoint**: `GET /v1/system/runtime/queue`  
**Returns**: `ProcessorQueueStatus`
- `processor_name`: Name of processor
- `queue_size`: Number of items in queue
- `max_size`: Maximum queue capacity
- `processing_rate`: Items per second processing rate
- `average_latency_ms`: Average processing time
- `oldest_message_age_seconds`: Age of oldest queued item

**Current Status**: ✅ Fully functional

#### 3. **Pipeline State Information**
**Endpoint**: `GET /v1/system/processors`  
**Returns**: `List[ProcessorStateInfo]`
- Lists all 6 cognitive states (WAKEUP, WORK, DREAM, PLAY, SOLITUDE, SHUTDOWN)
- Shows which state is currently active
- Includes capabilities for each state

**Current Status**: ✅ Functional but limited

## ❌ Missing Data Points

### Critical Missing Step Point Data

**Currently NO API access to**:
1. **Step Point Identification**: Which step was just executed
2. **Step-Specific Results**: Detailed results from each step point
3. **DMA Results**: Ethical, common sense, domain DMA outputs
4. **LLM Interactions**: Prompts, responses, and reasoning
5. **Conscience Evaluations**: Safety check results and failures
6. **Context Data**: System snapshot, identity, memory context
7. **Pipeline State**: Complete pipeline state with thoughts at each step
8. **Timing Breakdowns**: Per-step timing analysis
9. **Error Details**: Step-specific error information
10. **Recursion Information**: Recursive ASPDMA and conscience data

### Architecture Data Gaps

**Currently NO API access to**:
1. **Bus Operations**: Outbound/inbound bus data
2. **Handler Context**: Handler execution details
3. **Package Handling**: Adapter processing information
4. **Memory Queries**: What memories were accessed during context building
5. **Task-Thought Mapping**: How tasks become thoughts
6. **Resource Consumption**: Token usage, processing resources

## 🎯 Required API Extensions

### **Option 1: Enhanced Single-Step Response**
**Approach**: Extend existing `/v1/system/runtime/single-step` endpoint

**New Response Schema**: `EnhancedSingleStepResponse`
```python
class EnhancedSingleStepResponse(BaseModel):
    # Basic info (existing)
    success: bool
    message: str
    processor_state: str
    cognitive_state: str
    queue_depth: int
    
    # NEW: Step point information
    step_point: Optional[StepPoint] = None
    step_result: Optional[Dict[str, Any]] = None  # Full step result data
    
    # NEW: Pipeline state
    pipeline_state: Optional[PipelineState] = None
    
    # NEW: Performance data
    processing_time_ms: float = 0.0
    tokens_used: Optional[int] = None
    
    # NEW: Context for demo
    demo_data: Optional[Dict[str, Any]] = None
```

**Pros**:
- Single endpoint
- Backward compatible
- All data in one response

**Cons**:
- Large response payload
- May be overwhelming for basic use

### **Option 2: Separate Step Point Data Endpoints**
**Approach**: Add new dedicated endpoints for step point data

#### **A. Step Point History**
**Endpoint**: `GET /v1/system/runtime/steps`  
**Returns**: List of recent step points executed
```python
class StepPointHistory(BaseModel):
    steps: List[StepPointExecution]
    
class StepPointExecution(BaseModel):
    step_point: StepPoint
    thought_id: str
    executed_at: datetime
    duration_ms: float
    success: bool
```

#### **B. Latest Step Details**  
**Endpoint**: `GET /v1/system/runtime/steps/latest`  
**Returns**: Detailed data from most recent step
```python
class LatestStepDetails(BaseModel):
    step_point: StepPoint
    thought_id: str
    step_result: StepResult  # Union of all step result types
    pipeline_state: PipelineState
    timing: StepTiming
```

#### **C. Specific Step Data**
**Endpoint**: `GET /v1/system/runtime/steps/{step_point}/latest`  
**Returns**: Latest data for a specific step point type

#### **D. Pipeline State**
**Endpoint**: `GET /v1/system/runtime/pipeline`  
**Returns**: Complete current pipeline state
```python
class PipelineStateResponse(BaseModel):
    is_paused: bool
    current_round: int
    thoughts_by_step: Dict[str, List[ThoughtInPipeline]]
    task_queue: List[QueuedTask]
    thought_queue: List[QueuedThought]
    metrics: PipelineMetrics
```

**Pros**:
- Granular access
- Smaller payloads
- Specific use cases
- Better caching

**Cons**:
- Multiple API calls needed
- More complex client code

### **Option 3: WebSocket Stream** 
**Approach**: Real-time step point streaming

**Endpoint**: `WS /v1/system/runtime/steps/stream`  
**Stream Format**:
```python
class StepPointStreamMessage(BaseModel):
    type: Literal["step_start", "step_complete", "step_error"]
    step_point: StepPoint
    thought_id: str
    timestamp: datetime
    data: Optional[Dict[str, Any]] = None
```

**Pros**:
- Real-time updates
- Perfect for demos
- Low latency
- Event-driven

**Cons**:
- More complex implementation
- WebSocket infrastructure needed

## 🔧 Recommended Implementation Plan

### **Phase 1: Enhanced Single-Step** (Immediate)
1. Extend existing single-step endpoint with optional detailed data
2. Add query parameter `?include_details=true` for full step data
3. Backward compatible - existing clients unaffected

### **Phase 2: Pipeline State Endpoints** (Short-term)  
1. Add `/v1/system/runtime/pipeline` for complete state
2. Add `/v1/system/runtime/steps/latest` for most recent step details
3. Integrate with existing queue status endpoint

### **Phase 3: WebSocket Streaming** (Future)
1. Add real-time step point streaming
2. Perfect for live demos and monitoring dashboards

## 📊 Implementation Priority Matrix

| Feature | Demo Value | Implementation Effort | Priority |
|---------|------------|---------------------|----------|
| Enhanced single-step response | High | Low | 🔴 Critical |
| Latest step details endpoint | High | Medium | 🟡 High |  
| Pipeline state endpoint | Medium | Medium | 🟡 High |
| Step point history | Medium | Low | 🟢 Medium |
| WebSocket streaming | High | High | 🔵 Future |
| Specific step data endpoints | Low | High | 🔵 Future |

## 🎬 Demo-Specific Enhancements

### **For Ethics Demo**:
- Focus on steps 5-10 data (DMA, ASPDMA, Conscience)
- Need raw LLM prompts and responses
- Conscience evaluation details
- Recursion information

### **For Architecture Demo**:  
- Focus on steps 11-15 data (Handler, Bus operations)
- Bus message contents
- Adapter transformation details
- External service interactions

### **For Performance Demo**:
- Timing breakdowns for all steps
- Token consumption tracking
- Queue depth changes
- Resource utilization metrics

## Next Steps

1. **Implement Phase 1**: Enhanced single-step endpoint with `?include_details=true`
2. **Add Pipeline State Access**: Complete pipeline visibility 
3. **Design Demo Views**: Transform technical data into presentation-ready format
4. **Create SDK Methods**: Make data easily accessible from TypeScript SDK
5. **Build Demo Interface**: Real-time step visualization for presentations