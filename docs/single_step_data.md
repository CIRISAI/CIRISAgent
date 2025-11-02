# Single-Step Data Inspection Schemas

## Overview

For each of the 15 step points in the CIRIS Agent processing pipeline, specific data is available for inspection during demo presentations and debugging. This document details what data can be examined at each pause point.

## Step Point Data Schemas

### 1. FINALIZE_TASKS_QUEUE
**Schema**: `StepResultFinalizeTasksQueue`

**Key Data Available**:
- `tasks_to_process`: List of tasks selected for processing (QueuedTask[])
- `tasks_deferred`: Tasks skipped with reasons (Dict[task_id, reason])
- `selection_criteria`: Priority, age, channel filters used
- `total_pending_tasks`: Total tasks in queue
- `total_active_tasks`: Currently processing
- `tasks_selected_count`: Number selected for this round
- `round_number`: Current processing round
- `current_state`: Agent state (WORK, DREAM, etc.)

**Demo Value**: Shows task prioritization logic and workload management

---

### 2. POPULATE_THOUGHT_QUEUE
**Schema**: `StepResultPopulateThoughtQueue`

**Key Data Available**:
- `thoughts_generated`: New thoughts created (QueuedThought[])
- `task_thought_mapping`: Which tasks generated which thoughts (Dict[task_id, thought_ids[]])
- `thoughts_per_task`: Generation statistics (Dict[task_id, count])
- `generation_errors`: Failed thought generation attempts
- `total_thoughts_generated`: Total count for this round

**Demo Value**: Demonstrates how tasks become actionable thoughts

---

### 3. POPULATE_ROUND
**Schema**: `StepResultPopulateRound`

**Key Data Available**:
- `thoughts_for_round`: Thoughts selected for processing (ThoughtInPipeline[])
- `thoughts_deferred`: Thoughts postponed with reasons (Dict[thought_id, reason])
- `batch_size`: Processing batch size used
- `priority_threshold`: Minimum priority for inclusion
- `remaining_in_queue`: Thoughts still waiting

**Demo Value**: Shows batch processing and priority-based selection

---

### 4. BUILD_CONTEXT
**Schema**: `StepResultBuildContext`

**Key Data Available**:
- `system_snapshot`: Complete system state (Dict[str, Any])
- `agent_identity`: Agent's identity data (Dict[str, Any])
- `thought_context`: Full thought context for DMA processing (Dict[str, Any])
- `channel_context`: Source channel information
- `memory_context`: Relevant memories and history
- `permitted_actions`: Actions agent is allowed to take (str[])
- `constraints`: Restrictions and limitations (str[])
- `context_size_bytes`: Total context size
- `memory_queries_performed`: Memory searches conducted

**Demo Value**: Critical for showing how agent builds comprehensive understanding before reasoning

---

### 5. PERFORM_DMAS
**Schema**: `StepResultPerformDMAs`

**Key Data Available**:
- `ethical_dma`: Ethical DMA result (EthicalDMAResult)
- `common_sense_dma`: Common sense DMA result (CSDMAResult)
- `domain_dma`: Domain-specific DMA result (DSDMAResult)
- `dmas_executed`: Which DMAs ran successfully (str[])
- `dma_failures`: Any DMA failures with details (Dict[dma_name, error])
- `longest_dma_time_ms`: Performance bottleneck identification
- `total_time_ms`: Parallel execution time

**Demo Value**: Core ethical reasoning - shows how agent considers multiple perspectives

---

### 6. PERFORM_ASPDMA
**Schema**: `StepResultPerformASPDMA`

**Key Data Available**:
- `prompt_text`: Full prompt sent to LLM (str)
- `llm_model`: Model used for action selection (str)
- `raw_response`: Complete LLM response (str)
- `aspdma_result`: Parsed action selection (ActionSelectionDMAResult)
  - `selected_action`: Chosen action type
  - `action_parameters`: Parameters for the action
  - `reasoning`: LLM's reasoning process
  - `confidence_level`: How certain the LLM is
- `tokens_used`: Resource consumption (int)
- `retry_count`: Number of attempts needed

**Demo Value**: Shows LLM decision-making process and action selection reasoning

---

### 7. CONSCIENCE_EXECUTION
**Schema**: `StepResultConscienceExecution`

**Key Data Available**:
- `aspdma_result`: Action being evaluated (ActionSelectionDMAResult)
- `conscience_evaluations`: All conscience check results (ConscienceResult[])
  - Per conscience: passed/failed, reasoning, recommendations
- `all_passed`: Whether all consciences approved the action (bool)
- `failures`: Names of failed consciences (str[])
- `override_required`: Whether human override is needed
- `longest_conscience_time_ms`: Performance analysis
- `total_time_ms`: Total conscience processing time

**Demo Value**: Critical for ethics demonstration - shows safety checks and failure handling

---

### 8. RECURSIVE_ASPDMA *(conditional)*
**Schema**: `StepResultRecursiveASPDMA`

**Key Data Available**:
- `original_action`: Action that failed conscience (str)
- `conscience_feedback`: Why it failed (str)
- `recursion_count`: How many times we've retried (int)
- `retry_prompt`: Modified prompt incorporating feedback (str)
- `raw_response`: New LLM response (str)
- `new_aspdma_result`: Refined action selection (ActionSelectionDMAResult)

**Demo Value**: Shows learning and adaptation - how agent improves decisions based on feedback

---

### 9. RECURSIVE_CONSCIENCE *(conditional)*
**Schema**: `StepResultRecursiveConscience`

**Key Data Available**:
- `is_recursive`: Marked as recursive check (bool = True)
- `recursion_count`: Recursion depth
- `aspdma_result`: New action being checked
- `conscience_evaluations`: Re-evaluation results (ConscienceResult[])
- `all_passed`: Did the retry succeed?
- `failures`: Any remaining failures
- `final_override_to_ponder`: Whether to fall back to PONDER action

**Demo Value**: Shows persistence and safety - agent keeps trying to find ethical solutions

---

### 10. ACTION_SELECTION
**Schema**: `StepResultActionSelection`

**Key Data Available**:
- `final_action_result`: Definitive action to be taken (ActionSelectionDMAResult)
- `was_overridden`: Whether original choice was changed (bool)
- `override_reason`: Why it was changed (str)
- `recursion_performed`: Whether recursive refinement occurred
- `target_handler`: Which handler will execute this action (str)

**Demo Value**: Final decision point - shows the complete ethical reasoning outcome

---

### 11. HANDLER_START
**Schema**: `StepResultHandlerStart`

**Key Data Available**:
- `handler_name`: Handler being executed (str)
- `action_type`: Type of action (str)
- `action_parameters`: Full action parameters (Dict[str, Any])
- `handler_context`: Context prepared for handler (Dict[str, Any])
- `expected_bus_operations`: Predicted bus calls (str[])

**Demo Value**: Shows transition from reasoning to execution

---

### 12. BUS_OUTBOUND
**Schema**: `StepResultBusOutbound`

**Key Data Available**:
- `buses_called`: Which buses were invoked (str[])
- `communication_bus`: Messages sent to communication (Dict[str, Any])
- `memory_bus`: Data sent to memory storage (Dict[str, Any])
- `tool_bus`: Tool invocations (Dict[str, Any])
- `operations_initiated`: Async operations started (str[])
- `awaiting_responses`: Operations waiting for response (str[])

**Demo Value**: Shows how internal decisions become external actions

---

### 13. PACKAGE_HANDLING
**Schema**: `StepResultPackageHandling`

**Key Data Available**:
- `adapter_name`: Which adapter is handling (str)
- `package_type`: Type of package (message, tool call, etc.)
- `external_service_called`: External service invoked (str)
- `external_response_received`: Whether response came back (bool)
- `package_transformed`: Whether package was modified
- `transformation_details`: How package was changed (Dict[str, Any])

**Demo Value**: Shows edge/boundary processing and external integration

---

### 14. BUS_INBOUND
**Schema**: `StepResultBusInbound`

**Key Data Available**:
- `responses_received`: All responses from buses (Dict[str, Any])
- `communication_response`: Communication results (Dict[str, Any])
- `memory_response`: Memory operation results (Dict[str, Any])
- `tool_response`: Tool execution results (Dict[str, Any])
- `responses_aggregated`: Whether responses were combined
- `final_result`: Aggregated result for handler (Dict[str, Any])

**Demo Value**: Shows how external operation results are processed

---

### 15. HANDLER_COMPLETE
**Schema**: `StepResultHandlerComplete`

**Key Data Available**:
- `handler_success`: Whether handler succeeded (bool)
- `handler_message`: Result message (str)
- `handler_data`: Handler output data (Dict[str, Any])
- `thought_final_status`: Final thought status (str)
- `task_status_update`: Task status change if any (str)
- `total_processing_time_ms`: Complete processing time for this thought
- `total_tokens_used`: Total LLM resource consumption
- `triggers_new_thoughts`: Whether this creates more work (bool)
- `triggered_thought_ids`: New thoughts generated (str[])

**Demo Value**: Shows completion and potential cascade effects

## Data Categories for Demo

### **🧠 Reasoning & Ethics** (Steps 5-10)
- Complete DMA results showing multi-perspective analysis
- LLM prompts and responses with reasoning
- Conscience evaluations with pass/fail details
- Recursive refinement showing learning

### **📊 Queue & Performance** (Steps 1-3, 15)
- Task prioritization and selection criteria
- Queue depths and processing batches
- Timing data and bottleneck identification
- Cascade effects and new thought generation

### **🔧 System Architecture** (Steps 4, 11-14)
- Context building and system state
- Bus operations and message flow
- Handler execution patterns
- External service integration

### **🎯 Decision Transparency** (Steps 6, 7, 10)
- Complete prompt texts sent to LLM
- Raw LLM responses before parsing
- Action selection reasoning
- Conscience approval/rejection reasoning

## Usage in Demos

Each step point provides rich data for different demo narratives:

1. **Ethics & Safety**: Focus on steps 5-10 to show complete ethical reasoning
2. **Architecture**: Use steps 11-15 to demonstrate system design
3. **Performance**: Analyze timing data across all steps for optimization
4. **Transparency**: Show raw LLM interactions at steps 6, 8 for explainability
