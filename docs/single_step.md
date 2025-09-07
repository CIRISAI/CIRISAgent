# CIRIS Agent Single-Step Processing Guide

## Overview

The CIRIS Agent H3ERE processing pipeline includes **9 core step points + 2 optional recursive steps** where execution can be paused for detailed inspection during demo presentations and debugging. This enables transparent analysis of ethical reasoning and decision-making processes.

## Step Points in Execution Order (H3ERE Pipeline)

The agent processes thoughts through these sequential stages, each with its own pause point and inspection capabilities:

### 0. START_ROUND
**Purpose**: Setup tasks → thoughts → round queue  
**Location**: Beginning of round processing  
**What happens**: Moves thoughts from PENDING to PROCESSING status, sets up processing round, and prepares thoughts for H3ERE pipeline entry.

### 1. GATHER_CONTEXT  
**Purpose**: Build comprehensive context for DMA processing  
**Location**: After round setup, before DMAs  
**What happens**: Agent gathers system snapshot, identity data, memory context, conversation history, and constraints needed for ethical reasoning.

### 2. PERFORM_DMAS
**Purpose**: Execute parallel multi-perspective DMAs  
**Location**: Core ethical reasoning stage  
**What happens**: Multiple DMAs (Ethical, Common Sense, Domain-specific) run in parallel to evaluate the situation from different perspectives.

### 3. PERFORM_ASPDMA
**Purpose**: LLM-powered action selection  
**Location**: After base DMAs complete  
**What happens**: Large Language Model determines what action to take based on DMA results and context, with full reasoning transparency.

### 4. CONSCIENCE_EXECUTION
**Purpose**: Ethical safety validation  
**Location**: After action is selected  
**What happens**: Multiple conscience functions evaluate the proposed action for safety, ethics, and appropriateness in parallel.

### 3B. RECURSIVE_ASPDMA *(conditional - only if step 4 fails)*
**Purpose**: Re-run action selection if conscience evaluation failed  
**Location**: Only executed when CONSCIENCE_EXECUTION (step 4) rejects the initial action  
**What happens**: ASPDMA is re-run with conscience feedback to select a different, more ethical action. This creates a feedback loop for ethical refinement.

### 4B. RECURSIVE_CONSCIENCE *(conditional - only if step 3B executes)*
**Purpose**: Re-validate the refined action from recursive ASPDMA  
**Location**: Only executed after RECURSIVE_ASPDMA (step 3B) provides a new action  
**What happens**: Conscience checks run again on the new action selection to ensure the refined action meets ethical standards. If this fails, the system may fall back to PONDER action.

### 5. FINALIZE_ACTION
**Purpose**: Final action determination  
**Location**: After all conscience processing  
**What happens**: Final action is determined with any overrides or fallbacks, preparing for handler execution.

### 6. PERFORM_ACTION
**Purpose**: Dispatch action to handler  
**Location**: Action execution phase  
**What happens**: Action is dispatched to the appropriate handler for execution via the message bus system.

### 7. ACTION_COMPLETE
**Purpose**: Action execution completed  
**Location**: After handler completes  
**What happens**: Action results are processed, thought status updated, and any follow-up actions triggered.

### 8. ROUND_COMPLETE
**Purpose**: Processing round completed  
**Location**: End of round processing  
**What happens**: Round cleanup, metrics collection, and preparation for next processing cycle.

## Step Point Categories

### **Setup & Context** (0-1)
- Round initialization and thought status transitions
- System state capture and context building
- Identity, permissions, and memory context assembly

### **Ethical Reasoning Core** (2-4)  
- Parallel multi-perspective DMA execution
- LLM-driven action selection with full transparency
- Conscience-based ethical safety validation

### **Recursive Refinement** (3B-4B) *(optional)*
- Recursive action selection when conscience fails
- Re-validation of refined actions
- Ethical feedback loop for improved decisions

### **Action Execution** (5-8)
- Final action determination and dispatch
- Handler execution via message bus
- Action completion and round cleanup

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