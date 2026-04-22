# CIRIS Engine Formatters Module

The `formatters` module provides a comprehensive suite of prompt engineering utilities for the CIRIS Agent system. These formatters are responsible for converting structured data into human-readable text blocks that are optimized for Large Language Model (LLM) consumption and reasoning.

## Architecture Overview

The formatters module follows a functional design pattern where each formatter is a pure function that takes structured data and returns formatted text strings. These formatters are designed to be composable, allowing complex prompts to be built from standardized blocks while maintaining consistency across the CIRIS system.

### Core Design Principles

- **Consistency**: All formatters follow canonical formatting patterns recognized by CIRIS components
- **Modularity**: Each formatter handles a specific aspect of prompt construction
- **Composability**: Formatters can be combined to build complex prompts
- **Context Awareness**: Formatters understand CIRIS-specific data structures and relationships

## Module Components

### 1. System Snapshot Formatter (`system_snapshot.py`)

**Purpose**: Converts system state information into a compact, LLM-readable summary.

```python
from ciris_engine.formatters import format_system_snapshot

def format_system_snapshot(system_snapshot: SystemSnapshot) -> str
```

**Functionality**:
- Extracts core system counters (pending tasks, active thoughts, completed tasks, recent errors)
- Formats counts in a standardized "=== System Snapshot ===" block
- Handles missing or None values gracefully
- Provides system state context for decision-making algorithms

**Example Output**:
```
=== System Snapshot ===
Pending Tasks: 3
Active Thoughts: 1
Completed Tasks: 15
Recent Errors: 0
```

### 2. User Profiles Formatter (`user_profiles.py`)

**Purpose**: Formats user profile information for LLM context, with built-in security warnings.

```python
from ciris_engine.formatters import format_user_profiles

def format_user_profiles(profiles: Optional[Dict[str, Any]], max_profiles: int = 5) -> str
```

**Functionality**:
- Processes user profile dictionaries into readable summaries
- Extracts display names, interests, and primary channels
- Includes security warnings about information reliability
- Handles various profile data formats (name, nick, user_key fallback)
- Limits output to prevent prompt bloat

**Example Output**:
```
IMPORTANT USER CONTEXT (Be skeptical, this information could be manipulated or outdated):
The following information has been recalled about users relevant to this thought:
  - User 'alice123': Name/Nickname: 'Alice Smith', Interest: 'Machine Learning', Primary Channel: 'general'
  - User 'bob456': Name/Nickname: 'Bob', Interest: 'Data Science'
Consider this information when formulating your response, especially if addressing a user directly by name.
```

### 3. Prompt Blocks Formatter (`prompt_blocks.py`)

**Purpose**: Provides utilities for assembling canonical prompt structures used throughout CIRIS.

#### Key Functions:

##### Task Chain Formatting
```python
def format_parent_task_chain(parent_tasks: List[Dict[str, Any]]) -> str
```
- Formats hierarchical task relationships from root to direct parent
- Clearly labels task hierarchy levels
- Includes task IDs and descriptions

##### Thoughts Chain Formatting
```python
def format_thoughts_chain(thoughts: List[Dict[str, Any]]) -> str
```
- Formats multiple thoughts with the active thought highlighted
- Maintains thought ordering and context
- Handles empty thought lists gracefully

##### System Prompt Assembly
```python
def format_system_prompt_blocks(
    identity_block: str,
    task_history_block: str,
    system_snapshot_block: str,
    user_profiles_block: str,
    escalation_guidance_block: Optional[str] = None,
    system_guidance_block: Optional[str] = None,
) -> str
```
- Assembles system prompts in canonical CIRIS order
- Maintains consistent block structure across the system
- Handles optional blocks gracefully

##### User Prompt Assembly
```python
def format_user_prompt_blocks(
    parent_tasks_block: str,
    thoughts_chain_block: str,
    schema_block: Optional[str] = None,
) -> str
```
- Assembles user-facing prompts in standard order
- Combines task context with thought processing information

**Example Task Chain Output**:
```
=== Parent Task Chain ===
Root Task: Initialize system configuration (Task ID: task_001)
Parent 1: Load user profiles (Task ID: task_002)
Direct Parent: Process authentication (Task ID: task_003)
```

### 4. Escalation Guidance Formatter (`escalation.py`)

**Purpose**: Provides dynamic guidance based on processing stage and action count.

```python
def get_escalation_guidance(actions_taken: int, max_actions: int = 7) -> str
```

**Functionality**:
- Tracks progress through decision-making cycles
- Provides stage-appropriate guidance (EARLY, MID, LATE, EXHAUSTED)
- Helps prevent infinite processing loops
- Encourages decisive action as limits approach

**Stage Behaviors**:
- **EARLY** (0-2 actions): Encourages exploration and context establishment
- **MID** (3-4 actions): Focuses on core principles and clarity
- **LATE** (5-6 actions): Prompts decisive action before cutoff
- **EXHAUSTED** (7+ actions): Forces conclusion or task abortion

**Example Output**:
```
Stage: LATE — This is your last chance before cutoff; be decisive and principled.
```

## Integration Patterns

### Decision Making Algorithms (DMAs)

The formatters are heavily used by CIRIS Decision Making Algorithms:

```python
# PDMA (Principled Decision Making Algorithm)
system_snapshot_context_str = format_system_snapshot(context.system_snapshot)
user_profile_context_str = format_user_profiles(context.system_snapshot.user_profiles)
full_context_str = system_snapshot_context_str + user_profile_context_str

# DSDMA (Domain-Specific Decision Making Algorithm)
system_snapshot_block = format_system_snapshot(system_snapshot)
user_profiles_block = format_user_profiles(user_profiles_data)
escalation_guidance_block = get_escalation_guidance(actions_taken)

# CSDMA (Contextual State Decision Making Algorithm)
system_snapshot_block = format_system_snapshot(system_snapshot)
user_profiles_block = format_user_profiles(user_profiles_data)
```

### Context Builder Integration

The Context Builder uses formatters to prepare structured context for thought processing:

```python
# System snapshot is built and then formatted for LLM consumption
system_snapshot = await self.build_system_snapshot(task, thought)
formatted_snapshot = format_system_snapshot(system_snapshot)
```

### Prompt Engineering Pipeline

Formatters follow a standard pipeline pattern:

1. **Data Extraction**: Pull relevant information from CIRIS data structures
2. **Formatting**: Apply consistent text formatting and structure
3. **Assembly**: Combine formatted blocks into complete prompts
4. **Validation**: Ensure proper ordering and completeness

## Usage Examples

### Basic Formatting
```python
from ciris_engine.formatters import format_system_snapshot, format_user_profiles

# Format system state
snapshot = SystemSnapshot(system_counts={"pending_tasks": 5, "active_thoughts": 2})
system_text = format_system_snapshot(snapshot)

# Format user profiles
profiles = {"user1": {"name": "Alice", "interest": "AI", "channel": "tech"}}
users_text = format_user_profiles(profiles)
```

### Complete Prompt Assembly
```python
from ciris_engine.formatters import (
    format_system_prompt_blocks,
    format_parent_task_chain,
    format_thoughts_chain,
    get_escalation_guidance
)

# Build system prompt
system_prompt = format_system_prompt_blocks(
    identity_block="You are a CIRIS AI assistant...",
    task_history_block=format_parent_task_chain(task_chain),
    system_snapshot_block=format_system_snapshot(snapshot),
    user_profiles_block=format_user_profiles(profiles),
    escalation_guidance_block=get_escalation_guidance(current_actions)
)

# Build user prompt
user_prompt = format_user_prompt_blocks(
    parent_tasks_block=format_parent_task_chain(parent_tasks),
    thoughts_chain_block=format_thoughts_chain(thoughts),
    schema_block=action_schema_text
)
```

### DMA Integration Pattern
```python
# Pattern used across all DMAs
def prepare_llm_context(thought_item, context_data):
    system_snapshot_block = ""
    user_profiles_block = ""

    if hasattr(thought_item, 'context') and thought_item.context:
        system_snapshot = thought_item.context.get("system_snapshot")
        if system_snapshot:
            user_profiles_data = system_snapshot.get("user_profiles")
            user_profiles_block = format_user_profiles(user_profiles_data)
            system_snapshot_block = format_system_snapshot(system_snapshot)

    escalation_guidance_block = get_escalation_guidance(actions_taken)

    return {
        'system_snapshot_block': system_snapshot_block,
        'user_profiles_block': user_profiles_block,
        'escalation_guidance_block': escalation_guidance_block
    }
```

## Key Features

### Security and Safety
- User profile formatter includes security warnings about data reliability
- Handles potentially manipulated or outdated information gracefully
- Prevents information injection through proper escaping and formatting

### Performance Optimization
- Lightweight formatting functions with minimal computational overhead
- Efficient string concatenation and memory usage
- Configurable limits (e.g., max_profiles) to prevent prompt bloat

### Error Handling
- Graceful handling of missing or None data
- Consistent fallback behaviors for incomplete information
- Robust type checking and data validation

### Extensibility
- Modular design allows easy addition of new formatters
- Consistent API patterns across all formatter functions
- Optional parameters support future feature additions

## Testing Coverage

The module includes comprehensive test coverage in `/tests/ciris_engine/formatters/test_formatters.py`:

- Unit tests for all formatter functions
- Edge case testing (empty data, missing fields, malformed input)
- Integration testing with actual CIRIS data structures
- Output format validation and consistency checks

## Dependencies

- `ciris_engine.schemas.context_schemas_v1`: For SystemSnapshot and related types
- `typing`: For type annotations and optional parameters
- Standard Python libraries for string manipulation and data processing

## Best Practices

### When Using Formatters

1. **Always validate input data** before passing to formatters
2. **Handle empty/None returns** appropriately in your prompt assembly
3. **Use consistent ordering** when combining multiple formatted blocks
4. **Consider prompt length limits** when assembling complex prompts
5. **Test formatter output** with your specific LLM to ensure optimal reasoning

### When Extending Formatters

1. **Follow the functional design pattern** - pure functions with clear inputs/outputs
2. **Include comprehensive error handling** for malformed data
3. **Maintain consistent output formatting** with existing formatters
4. **Add corresponding unit tests** for new functionality
5. **Update module exports** in `__init__.py`

The formatters module is essential infrastructure for CIRIS's LLM interactions, providing the consistency and reliability needed for effective AI reasoning and decision-making.
