# Phase 1: Enhanced Single-Step API - Test-Driven Implementation Plan

## Overview
Implement enhanced single-step endpoint with optional detailed data using existing schemas and protocols. **100% test-driven development** leveraging the existing type system.

## 🧪 **Test-Driven Implementation Steps**

### **Step 1: Create Comprehensive Test Suite**

#### **A. Create Enhanced Response Schema Tests**
**File**: `tests/api/test_enhanced_single_step_schema.py`

```python
"""Test enhanced single-step response schema validation."""

import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.runtime_control import (
    StepPoint, PipelineState, StepResult, ThoughtInPipeline,
    StepResultBuildContext, StepResultPerformDMAs
)
from ciris_engine.logic.adapters.api.routes.system_extensions import (
    EnhancedSingleStepResponse  # To be created
)

class TestEnhancedSingleStepResponse:
    """Test the enhanced single-step response schema."""

    def test_basic_response_structure(self):
        """Test basic response fields using existing RuntimeControlResponse compatibility."""
        response = EnhancedSingleStepResponse(
            success=True,
            message="Single step completed",
            processor_state="paused",
            cognitive_state="WORK",
            queue_depth=3
        )

        assert response.success is True
        assert response.processor_state == "paused"
        assert response.cognitive_state == "WORK"
        assert response.queue_depth == 3

    def test_detailed_response_with_step_point(self):
        """Test response with step point and detailed data."""
        # Use existing StepResultBuildContext schema
        step_result = StepResultBuildContext(
            step_point=StepPoint.BUILD_CONTEXT,
            success=True,
            thought_id="thought_123",
            system_snapshot={"cpu_usage": 0.5},
            agent_identity={"agent_id": "test_agent"},
            thought_context={"task": "test task"},
            processing_time_ms=150.0
        )

        response = EnhancedSingleStepResponse(
            success=True,
            message="Build context completed",
            processor_state="paused",
            cognitive_state="WORK",
            queue_depth=2,
            step_point=StepPoint.BUILD_CONTEXT,
            step_result=step_result,
            processing_time_ms=150.0,
            tokens_used=45
        )

        assert response.step_point == StepPoint.BUILD_CONTEXT
        assert response.step_result.thought_id == "thought_123"
        assert response.processing_time_ms == 150.0
        assert response.tokens_used == 45

    def test_pipeline_state_integration(self):
        """Test pipeline state using existing PipelineState schema."""
        # Create ThoughtInPipeline using existing schema
        thought = ThoughtInPipeline(
            thought_id="thought_456",
            task_id="task_789",
            thought_type="SPEAK",
            current_step=StepPoint.PERFORM_DMAS,
            entered_step_at=datetime.now(timezone.utc),
            processing_time_ms=200.0
        )

        # Use existing PipelineState schema
        pipeline_state = PipelineState(
            is_paused=True,
            current_round=1,
            thoughts_by_step={
                StepPoint.PERFORM_DMAS.value: [thought]
            },
            total_thoughts_in_flight=1
        )

        response = EnhancedSingleStepResponse(
            success=True,
            message="DMA execution in progress",
            processor_state="paused",
            cognitive_state="WORK",
            queue_depth=1,
            step_point=StepPoint.PERFORM_DMAS,
            pipeline_state=pipeline_state
        )

        assert response.pipeline_state.is_paused is True
        assert len(response.pipeline_state.thoughts_by_step) == 1
        assert response.pipeline_state.total_thoughts_in_flight == 1

    def test_backward_compatibility(self):
        """Test that basic usage still works (backward compatibility)."""
        response = EnhancedSingleStepResponse(
            success=False,
            message="No thoughts to process",
            processor_state="paused",
            cognitive_state="WORK",
            queue_depth=0
        )

        # Should work like original RuntimeControlResponse
        assert response.success is False
        assert response.message == "No thoughts to process"
        assert response.step_point is None
        assert response.step_result is None
```

#### **B. Create Integration Tests**
**File**: `tests/api/test_enhanced_single_step_integration.py`

```python
"""Integration tests for enhanced single-step endpoint."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from ciris_engine.schemas.services.runtime_control import (
    ProcessorControlResponse, ProcessorStatus, StepPoint,
    StepResultPerformASPDMA, ActionSelectionDMAResult
)

class TestEnhancedSingleStepIntegration:
    """Test enhanced single-step endpoint integration."""

    @pytest.fixture
    def mock_runtime_control_with_details(self):
        """Mock runtime control that returns detailed step results."""
        mock = AsyncMock()

        # Mock single_step to return ProcessorControlResponse + step data
        aspdma_result = ActionSelectionDMAResult(
            selected_action="SPEAK",
            action_parameters={"message": "Hello world"},
            reasoning="User requested greeting",
            confidence_level=0.95
        )

        step_result = StepResultPerformASPDMA(
            step_point=StepPoint.PERFORM_ASPDMA,
            success=True,
            thought_id="thought_test_123",
            prompt_text="Select an appropriate action...",
            llm_model="gpt-4o-mini",
            raw_response='{"action": "SPEAK", "parameters": {"message": "Hello world"}}',
            aspdma_result=aspdma_result,
            tokens_used=67,
            processing_time_ms=340.0
        )

        control_response = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.PAUSED,
            step_result=step_result  # Enhanced with step result
        )

        mock.single_step.return_value = control_response
        return mock

    def test_single_step_without_details_parameter(self, client, mock_runtime_control_with_details):
        """Test endpoint without ?include_details returns basic response."""
        # Setup
        request = MagicMock()
        request.app.state.main_runtime_control_service = mock_runtime_control_with_details

        # Execute
        response = client.post("/v1/system/runtime/single-step", json={})

        # Verify basic response (backward compatible)
        assert response.status_code == 200
        data = response.json()["data"]
        assert "success" in data
        assert "message" in data
        assert "processor_state" in data
        assert "step_point" not in data  # Should not include detailed data
        assert "step_result" not in data

    def test_single_step_with_details_parameter(self, client, mock_runtime_control_with_details):
        """Test endpoint with ?include_details=true returns enhanced response."""
        # Execute
        response = client.post("/v1/system/runtime/single-step?include_details=true", json={})

        # Verify enhanced response
        assert response.status_code == 200
        data = response.json()["data"]

        # Basic fields
        assert data["success"] is True
        assert data["processor_state"] == "paused"

        # Enhanced fields
        assert data["step_point"] == "perform_aspdma"
        assert "step_result" in data
        assert data["step_result"]["thought_id"] == "thought_test_123"
        assert data["step_result"]["tokens_used"] == 67
        assert data["processing_time_ms"] == 340.0
        assert data["tokens_used"] == 67

    def test_single_step_with_pipeline_state(self, client, mock_runtime_control_with_details):
        """Test endpoint returns pipeline state when available."""
        # Mock pipeline controller to return state
        mock_pipeline_controller = MagicMock()
        mock_pipeline_state = MagicMock()
        mock_pipeline_state.is_paused = True
        mock_pipeline_state.current_round = 5
        mock_pipeline_controller.get_pipeline_state.return_value = mock_pipeline_state

        # Add to runtime control mock
        mock_runtime_control_with_details.get_pipeline_controller.return_value = mock_pipeline_controller

        # Execute
        response = client.post("/v1/system/runtime/single-step?include_details=true", json={})

        # Verify pipeline state included
        data = response.json()["data"]
        assert "pipeline_state" in data
        assert data["pipeline_state"]["is_paused"] is True
        assert data["pipeline_state"]["current_round"] == 5
```

#### **C. Create Protocol Integration Tests**
**File**: `tests/api/test_single_step_protocol_integration.py`

```python
"""Test integration with existing pipeline control protocols."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.protocols.pipeline_control import PipelineController
from ciris_engine.schemas.services.runtime_control import (
    StepPoint, ThoughtInPipeline, PipelineState
)

class TestSingleStepProtocolIntegration:
    """Test enhanced single-step uses existing protocols correctly."""

    def test_pipeline_controller_integration(self):
        """Test that pipeline controller protocol is used correctly."""
        # Create real PipelineController using existing implementation
        controller = PipelineController(is_paused=True)

        # Add a thought at a specific step
        thought = ThoughtInPipeline(
            thought_id="test_thought",
            task_id="test_task",
            thought_type="SPEAK",
            current_step=StepPoint.BUILD_CONTEXT,
            entered_step_at=datetime.now(timezone.utc)
        )

        controller._paused_thoughts["test_thought"] = thought

        # Get pipeline state using existing method
        pipeline_state = controller.get_pipeline_state()

        # Verify we can extract the data correctly
        assert pipeline_state.is_paused is True
        assert "test_thought" in controller._paused_thoughts

        # Test step progression
        next_thought = controller.drain_pipeline_step()
        assert next_thought == "test_thought"

    def test_step_result_union_type_handling(self):
        """Test that StepResult union types are handled correctly."""
        from ciris_engine.schemas.services.runtime_control import (
            StepResultBuildContext, StepResultPerformDMAs, StepResult
        )

        # Test BuildContext step result
        build_result = StepResultBuildContext(
            step_point=StepPoint.BUILD_CONTEXT,
            success=True,
            thought_id="test_123",
            system_snapshot={"test": "data"},
            agent_identity={"agent": "test"},
            thought_context={"context": "test"},
            processing_time_ms=100.0
        )

        # Should be valid StepResult union member
        assert isinstance(build_result, StepResultBuildContext)

        # Test DMA step result
        dma_result = StepResultPerformDMAs(
            step_point=StepPoint.PERFORM_DMAS,
            success=True,
            thought_id="test_456",
            dmas_executed=["ethical", "common_sense", "domain"],
            longest_dma_time_ms=200.0,
            total_time_ms=200.0
        )

        assert isinstance(dma_result, StepResultPerformDMAs)
```

### **Step 2: Implement Enhanced Response Schema**

#### **A. Create EnhancedSingleStepResponse Schema**
**File**: `ciris_engine/logic/adapters/api/routes/system_extensions.py` (add to existing)

```python
# Add these imports at top
from typing import Optional, Union, Dict, Any
from ciris_engine.schemas.services.runtime_control import (
    StepPoint, PipelineState, StepResult, ProcessorControlResponse
)

class EnhancedSingleStepResponse(BaseModel):
    """Enhanced response for single-step operations with optional detailed data."""

    # Basic fields (backward compatible with RuntimeControlResponse)
    success: bool = Field(..., description="Whether step succeeded")
    message: str = Field(..., description="Human-readable status message")
    processor_state: str = Field(..., description="Current processor state")
    cognitive_state: Optional[str] = Field(None, description="Current cognitive state")
    queue_depth: int = Field(0, description="Number of items in processing queue")

    # Enhanced fields (optional for backward compatibility)
    step_point: Optional[StepPoint] = Field(None, description="Step point that was executed")
    step_result: Optional[Union[StepResult, Dict[str, Any]]] = Field(
        None, description="Detailed step result using existing schemas"
    )
    pipeline_state: Optional[PipelineState] = Field(
        None, description="Complete pipeline state"
    )

    # Performance and debugging data
    processing_time_ms: float = Field(0.0, description="Step execution time")
    tokens_used: Optional[int] = Field(None, description="LLM tokens consumed")

    # Demo-specific data
    demo_data: Optional[Dict[str, Any]] = Field(
        None, description="Additional data formatted for demo presentation"
    )

    class Config:
        # Enable validation of union types
        use_enum_values = True

    @classmethod
    def from_basic_response(
        cls,
        control_response: ProcessorControlResponse,
        cognitive_state: Optional[str] = None,
        queue_depth: int = 0
    ) -> "EnhancedSingleStepResponse":
        """Create basic response for backward compatibility."""
        return cls(
            success=control_response.success,
            message=control_response.error or f"Single step {'completed' if control_response.success else 'failed'}",
            processor_state=control_response.new_status.value if hasattr(control_response.new_status, "value") else str(control_response.new_status),
            cognitive_state=cognitive_state,
            queue_depth=queue_depth
        )

    @classmethod
    def from_detailed_response(
        cls,
        control_response: ProcessorControlResponse,
        step_point: StepPoint,
        step_result: StepResult,
        pipeline_state: Optional[PipelineState] = None,
        processing_time_ms: float = 0.0,
        tokens_used: Optional[int] = None,
        cognitive_state: Optional[str] = None,
        queue_depth: int = 0
    ) -> "EnhancedSingleStepResponse":
        """Create detailed response with all step data."""
        return cls(
            success=control_response.success,
            message=control_response.error or f"Step {step_point.value} {'completed' if control_response.success else 'failed'}",
            processor_state=control_response.new_status.value if hasattr(control_response.new_status, "value") else str(control_response.new_status),
            cognitive_state=cognitive_state,
            queue_depth=queue_depth,
            step_point=step_point,
            step_result=step_result,
            pipeline_state=pipeline_state,
            processing_time_ms=processing_time_ms,
            tokens_used=tokens_used
        )
```

### **Step 3: Update Single-Step Endpoint Implementation**

#### **A. Modify Existing Endpoint**
**File**: `ciris_engine/logic/adapters/api/routes/system_extensions.py` (modify existing)

```python
@router.post("/runtime/single-step", response_model=SuccessResponse[EnhancedSingleStepResponse])
async def single_step_processor(
    request: Request,
    auth: AuthContext = Depends(require_admin),
    body: dict = Body(default={}),
    include_details: bool = Query(False, description="Include detailed step and pipeline data")
) -> SuccessResponse[EnhancedSingleStepResponse]:
    """
    Execute a single processing step.

    Useful for debugging and demonstrations. Processes one item from the queue.

    Args:
        include_details: If True, returns detailed step result data and pipeline state

    Requires ADMIN role.
    """
    # Try main runtime control service first (has all methods), fall back to API runtime control
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        result = await runtime_control.single_step()

        # Get additional data for enhanced response
        cognitive_state = None
        queue_depth = 0

        # Get cognitive state from agent processor
        if hasattr(request.app.state, 'runtime') and request.app.state.runtime:
            runtime = request.app.state.runtime
            if hasattr(runtime, 'agent_processor') and runtime.agent_processor:
                if hasattr(runtime.agent_processor, 'state_manager'):
                    current_state = runtime.agent_processor.state_manager.get_state()
                    cognitive_state = current_state.value if hasattr(current_state, 'value') else str(current_state)

        # Get queue depth
        try:
            queue_status = await runtime_control.get_processor_queue_status()
            queue_depth = queue_status.queue_size
        except:
            queue_depth = 0

        if not include_details:
            # Basic response (backward compatible)
            response = EnhancedSingleStepResponse.from_basic_response(
                control_response=result,
                cognitive_state=cognitive_state,
                queue_depth=queue_depth
            )
        else:
            # Enhanced response with detailed data
            step_point = None
            step_result = None
            pipeline_state = None
            processing_time_ms = 0.0
            tokens_used = None

            # Extract step result data if available
            if hasattr(result, 'step_result') and result.step_result:
                step_result = result.step_result
                if hasattr(step_result, 'step_point'):
                    step_point = step_result.step_point
                if hasattr(step_result, 'processing_time_ms'):
                    processing_time_ms = step_result.processing_time_ms
                if hasattr(step_result, 'tokens_used'):
                    tokens_used = step_result.tokens_used

            # Get pipeline state if available
            if hasattr(runtime_control, 'get_pipeline_controller'):
                pipeline_controller = await runtime_control.get_pipeline_controller()
                if pipeline_controller:
                    pipeline_state = pipeline_controller.get_pipeline_state()

            response = EnhancedSingleStepResponse.from_detailed_response(
                control_response=result,
                step_point=step_point or StepPoint.BUILD_CONTEXT,  # Default fallback
                step_result=step_result or {"message": "No step result data available"},
                pipeline_state=pipeline_state,
                processing_time_ms=processing_time_ms,
                tokens_used=tokens_used,
                cognitive_state=cognitive_state,
                queue_depth=queue_depth
            )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Error in single step: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

### **Step 4: Update Runtime Control Service**

#### **A. Enhance ProcessorControlResponse**
**File**: `ciris_engine/schemas/services/core/runtime.py` (add field)

```python
class ProcessorControlResponse(BaseModel):
    """Response from processor control operations."""

    success: bool = Field(..., description="Whether the operation succeeded")
    processor_name: str = Field(..., description="Name of the processor")
    operation: str = Field(..., description="Operation that was performed")
    new_status: ProcessorStatus = Field(..., description="New processor status after operation")
    message: Optional[str] = Field(None, description="Human-readable message")
    error: Optional[str] = Field(None, description="Error message if operation failed")

    # NEW: Enhanced data for single-step operations
    step_result: Optional[Union["StepResult", Dict[str, Any]]] = Field(
        None, description="Detailed step result data"
    )

    class Config:
        arbitrary_types_allowed = True
```

#### **B. Update Runtime Control Service single_step Method**
**File**: `ciris_engine/logic/services/runtime/control_service.py` (modify existing)

```python
async def single_step(self) -> ProcessorControlResponse:
    """Execute a single processing step with enhanced result data."""
    try:
        _start_time = self._now()

        # Get the agent processor from runtime
        if not self.runtime or not hasattr(self.runtime, "agent_processor"):
            return ProcessorControlResponse(
                success=False,
                processor_name="agent",
                operation="single_step",
                new_status=self._processor_status,
                error="Agent processor not available",
            )

        # Ensure processor is paused
        if not self.runtime.agent_processor.is_paused():
            return ProcessorControlResponse(
                success=False,
                processor_name="agent",
                operation="single_step",
                new_status=self._processor_status,
                error="Cannot single-step unless processor is paused",
            )

        # Execute single step and capture result
        step_result_raw = await self.runtime.agent_processor.single_step()

        # Extract step result data using existing protocols
        step_result = None
        if step_result_raw.get("success"):
            # Convert raw dict to appropriate StepResult type if possible
            if "step_point" in step_result_raw:
                step_point_str = step_result_raw["step_point"]
                step_point = StepPoint(step_point_str)

                # Create appropriate StepResult based on step point
                step_result = self._create_step_result_from_raw(step_point, step_result_raw)

        # Track processing time
        processing_time = (self._now() - _start_time).total_seconds() * 1000
        if step_result_raw.get("processing_time_ms"):
            processing_time = step_result_raw["processing_time_ms"]

        return ProcessorControlResponse(
            success=step_result_raw.get("success", False),
            processor_name="agent",
            operation="single_step",
            new_status=self._processor_status,
            error=step_result_raw.get("error"),
            step_result=step_result or step_result_raw  # Include enhanced data
        )

    except Exception as e:
        logger.error(f"Failed to execute single step: {e}", exc_info=True)
        return ProcessorControlResponse(
            success=False,
            processor_name="agent",
            operation="single_step",
            new_status=self._processor_status,
            error=str(e),
        )

def _create_step_result_from_raw(self, step_point: StepPoint, raw_data: dict) -> Optional[StepResult]:
    """Convert raw step result to typed StepResult using existing schemas."""
    try:
        # Import step result types
        from ciris_engine.schemas.services.runtime_control import (
            StepResultBuildContext, StepResultPerformDMAs, StepResultPerformASPDMA,
            StepResultConscienceExecution, StepResultActionSelection,
            StepResultHandlerStart, StepResultHandlerComplete
        )

        # Map to appropriate schema based on step point
        if step_point == StepPoint.BUILD_CONTEXT:
            return StepResultBuildContext(
                step_point=step_point,
                success=raw_data.get("success", False),
                thought_id=raw_data.get("thought_id", "unknown"),
                system_snapshot=raw_data.get("system_snapshot", {}),
                agent_identity=raw_data.get("agent_identity", {}),
                thought_context=raw_data.get("thought_context", {}),
                processing_time_ms=raw_data.get("processing_time_ms", 0.0)
            )
        # Add other step point mappings...

        return None
    except Exception as e:
        logger.warning(f"Could not create typed step result: {e}")
        return None
```

### **Step 5: Update TypeScript SDK**

#### **A. Add Enhanced Response Types**
**File**: `ciris_sdk/types.ts` (add to existing)

```typescript
export interface EnhancedSingleStepResponse {
  // Basic fields (backward compatible)
  success: boolean;
  message: string;
  processor_state: string;
  cognitive_state?: string;
  queue_depth: number;

  // Enhanced fields
  step_point?: string;
  step_result?: StepResult | Record<string, any>;
  pipeline_state?: PipelineState;
  processing_time_ms?: number;
  tokens_used?: number;
  demo_data?: Record<string, any>;
}

export interface PipelineState {
  is_paused: boolean;
  current_round: number;
  thoughts_by_step: Record<string, ThoughtInPipeline[]>;
  task_queue: QueuedTask[];
  thought_queue: QueuedThought[];
  total_thoughts_processed: number;
  total_thoughts_in_flight: number;
}

export interface ThoughtInPipeline {
  thought_id: string;
  task_id: string;
  thought_type: string;
  current_step: string;
  entered_step_at: string;
  processing_time_ms: number;
  // Step-specific data fields...
}
```

#### **B. Add Enhanced SDK Methods**
**File**: `ciris_sdk/resources/system.py` (add to existing)

```python
async def single_step_enhanced(self, include_details: bool = True) -> EnhancedSingleStepResponse:
    """
    Execute single step with enhanced data for demo purposes.

    Args:
        include_details: Include detailed step result and pipeline data

    Returns:
        Enhanced single-step response with complete debugging information
    """
    params = {"include_details": include_details} if include_details else {}
    result = await self._transport.request(
        "POST",
        "/v1/system/runtime/single-step",
        json={},
        params=params
    )
    return EnhancedSingleStepResponse(**result)

async def get_pipeline_state(self) -> PipelineState:
    """Get current pipeline state for debugging."""
    # Use enhanced single-step to get pipeline state
    response = await self.single_step_enhanced(include_details=True)
    if response.pipeline_state:
        return response.pipeline_state
    raise ValueError("Pipeline state not available")
```

## ✅ **Test Execution Order**

1. **Run Schema Tests First**: Validate all schemas compile and validate correctly
2. **Run Protocol Integration Tests**: Ensure existing protocols work with enhancements
3. **Run Endpoint Integration Tests**: Test API endpoint behavior
4. **Run Backward Compatibility Tests**: Ensure existing clients still work
5. **Run SDK Tests**: Validate TypeScript SDK integration

## 🎯 **Success Criteria**

- ✅ All existing tests continue to pass (backward compatibility)
- ✅ New enhanced endpoint returns detailed step data when requested
- ✅ Basic endpoint usage unchanged for existing clients
- ✅ Uses existing schemas and protocols (no reinvention)
- ✅ TypeScript SDK supports both basic and enhanced usage
- ✅ Full test coverage for all new functionality

This implementation leverages ALL existing schemas and protocols, ensuring type safety and consistency with the current architecture while enabling the rich demo capabilities needed for video presentations.
