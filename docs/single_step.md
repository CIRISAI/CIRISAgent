# CIRIS Agent Single-Step Processing Guide

## Overview

The CIRIS Agent processing pipeline includes **14 distinct step points** where execution can be paused for detailed inspection during demo presentations and debugging. This enables transparent analysis of ethical reasoning and decision-making processes.

## Step Points in Execution Order

The agent processes thoughts through these sequential stages, each with its own pause point and inspection capabilities:

### 1. FINALIZE_TASKS_QUEUE
**Purpose**: Determine which tasks to process in this round  
**Location**: Beginning of round processing  
**What happens**: Agent examines pending tasks and selects which ones to convert into thoughts based on priority, age, channel, and current state.

### 2. POPULATE_THOUGHT_QUEUE  
**Purpose**: Generate thoughts from selected tasks  
**Location**: After task selection  
**What happens**: Selected tasks are converted into specific thoughts with types and processing priorities.

### 3. POPULATE_ROUND
**Purpose**: Select thoughts for the current processing round  
**Location**: Before DMA processing begins  
**What happens**: Agent selects a batch of thoughts from the queue for parallel processing, considering batch size and priority thresholds.

### 4. BUILD_CONTEXT
**Purpose**: Build comprehensive context for DMA processing  
**Location**: Before any DMA execution  
**What happens**: Agent gathers system snapshot, identity data, memory context, permissions, and constraints needed for ethical reasoning.

### 5. PERFORM_DMAS
**Purpose**: Execute parallel base DMAs (Ethical, Common Sense, Domain)  
**Location**: Core ethical reasoning stage  
**What happens**: Three DMAs run in parallel to evaluate the situation from different perspectives before action selection.

### 6. PERFORM_ASPDMA
**Purpose**: Action Selection and Prediction DMA execution  
**Location**: After base DMAs complete  
**What happens**: LLM determines what action to take based on DMA results and context. May involve multiple tries.

### 7. CONSCIENCE_EXECUTION
**Purpose**: Parallel conscience checks on selected action  
**Location**: After action is selected  
**What happens**: Multiple conscience functions evaluate the proposed action for safety, ethics, and appropriateness.

### 8. RECURSIVE_ASPDMA *(conditional)*
**Purpose**: Retry action selection after conscience failure  
**Location**: Only if conscience evaluation fails  
**What happens**: ASPDMA is re-run with conscience feedback to select a different action.

### 9. RECURSIVE_CONSCIENCE *(conditional)*
**Purpose**: Re-check action after recursive ASPDMA  
**Location**: Only if recursive ASPDMA was performed  
**What happens**: Conscience checks run again on the new action selection.

### 10. ACTION_SELECTION
**Purpose**: Finalize the action to be taken  
**Location**: After all conscience processing  
**What happens**: Final action is determined, potentially with overrides or fallbacks to PONDER.

### 11. HANDLER_START
**Purpose**: Begin handler execution  
**Location**: Before any external operations  
**What happens**: Appropriate handler is invoked with the final action and parameters.

### 12. BUS_OUTBOUND
**Purpose**: Process outbound messages to buses  
**Location**: During handler execution  
**What happens**: Handler sends operations to communication, memory, and tool buses.

### 13. PACKAGE_HANDLING
**Purpose**: Edge adapter processing  
**Location**: At system boundaries  
**What happens**: Adapters (Discord, API, CLI) transform and handle packages for external services.

### 14. BUS_INBOUND
**Purpose**: Process responses from buses  
**Location**: After external operations  
**What happens**: Results from bus operations are aggregated and processed.

### 15. HANDLER_COMPLETE
**Purpose**: Complete handler execution  
**Location**: End of thought processing  
**What happens**: Handler finishes, updates thought status, and may trigger new thoughts.

## Step Point Categories

### **Queue Management** (1-3)
- Task prioritization and selection
- Thought generation and queuing
- Round population for batch processing

### **Context Building** (4)
- System state capture
- Identity and permissions gathering
- Memory context assembly

### **Ethical Reasoning** (5-10)  
- Parallel DMA execution for different perspectives
- LLM-driven action selection
- Conscience-based safety checks
- Recursive refinement when needed

### **Action Execution** (11-15)
- Handler invocation and bus operations
- External service interactions
- Response processing and completion

## Demo Applications

### **Ethical Decision Transparency**
Steps 5-10 provide complete visibility into:
- How ethical considerations influence decisions
- Why specific actions are selected or rejected
- How conscience failures trigger refinement
- The complete reasoning chain from context to action

### **System Architecture Understanding**  
Steps 11-15 demonstrate:
- How internal decisions become external actions
- Bus-based architecture and message flow
- Adapter patterns for different interfaces
- Error handling and response processing

### **Performance Analysis**
All steps include timing data for:
- Bottleneck identification
- Processing time analysis
- Resource utilization tracking
- Queue depth monitoring

## Next Steps

1. **Data Inspection Schemas**: Define what data is available at each step point
2. **API Availability Audit**: Determine which data is currently accessible via API
3. **API Extensions**: Design endpoints to expose missing step point data
4. **Demo Integration**: Create presentation-ready views of step point data