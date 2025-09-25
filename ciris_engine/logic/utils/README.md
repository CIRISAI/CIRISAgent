# Utilities Module

The utilities module provides essential infrastructure components and helper functions that support the core CIRIS engine functionality. These utilities handle cross-cutting concerns like configuration management, logging, context processing, user identification, and graceful shutdown coordination.

## Architecture

### Core Components

The utils module contains focused utility libraries that provide reusable functionality across the CIRIS engine:

- **Configuration & Constants** (`constants.py`) - System-wide constants and configuration values
- **Context Management** (`context_utils.py`) - Context building and processing utilities
- **GraphQL Integration** (`graphql_context_provider.py`) - External data enrichment services
- **Logging Infrastructure** (`logging_config.py`) - Comprehensive logging configuration
- **Profile Loading** (`profile_loader.py`) - Profile template loading for agent creation only
- **Shutdown Coordination** (`shutdown_manager.py`) - Graceful shutdown orchestration
- **Task Formatting** (`task_formatters.py`) - LLM prompt formatting utilities
- **User Utilities** (`user_utils.py`) - User identification and nickname extraction

## Core Utilities

### System Constants (`constants.py`)

Centralized configuration and constants for the CIRIS engine.

#### Key Constants
```python
# Channel Configuration
DISCORD_CHANNEL_ID: str         # Primary Discord channel
API_CHANNEL_ID: str             # API communication channel

# User Configuration
WA_USER_IDS: str                # Wise Authority Discord user IDs (comma-separated)
WA_API_USER: str                # API user identification

# Processing Constants
NEED_MEMORY_METATHOUGHT: str    # Memory processing flag
DEFAULT_NUM_ROUNDS: int         # Default processing rounds
ENGINE_OVERVIEW_TEMPLATE: str   # Engine documentation template

# Agent Covenant
COVENANT_TEXT: str              # Agent behavioral covenant from file
```

#### Environment Integration
```python
# Constants loaded from environment with fallbacks
WA_USER_IDS = get_env_var("WA_USER_IDS", "537080239679864862")  # Comma-separated list
DISCORD_CHANNEL_ID = get_env_var("DISCORD_CHANNEL_ID")
```

### Context Management (`context_utils.py`)

Builds comprehensive execution contexts for thought processing.

#### Primary Function
```python
def build_dispatch_context(
    thought: Any,
    task: Optional[Any] = None,
    round_num: Optional[int] = None,
    extra_context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build comprehensive dispatch context for thought processing"""
```

#### Features
- **Context Inheritance**: Merges context from thoughts and tasks
- **Service Detection**: Automatic origin service identification (CLI vs Discord)
- **Channel Validation**: Ensures required channel_id is present
- **Round Management**: Supports multi-round processing workflows
- **Flexible Merging**: Handles both dict and object-based contexts

#### Usage Example
```python
# Build context for thought processing
dispatch_context = build_dispatch_context(
    thought=current_thought,
    task=parent_task,
    round_num=2,
    extra_context={"priority": "high"}
)

# Context includes: thought_id, task_id, channel_id, origin_service, round_num
```

### GraphQL Integration (`graphql_context_provider.py`)

Enriches contexts with user profile data through external GraphQL services.

#### Core Classes
```python
class GraphQLClient:
    """HTTP client for GraphQL endpoints with timeout handling"""

class GraphQLContextProvider:
    """Main service for context enrichment with user profiles"""
```

#### Key Features
- **Remote Queries**: External GraphQL endpoint integration
- **Local Fallback**: Memory service backup for offline operation
- **User Enrichment**: Fetches user profiles, nicknames, channel data
- **Identity Export**: Exports agent identity from graph memory

#### Usage Example
```python
provider = GraphQLContextProvider(
    client=graphql_client,
    memory_service=memory_service,
    enable_remote_graphql=True
)

# Enrich context with user data
enriched_context = await provider.enrich_context(task, thought)
user_profiles = enriched_context.get("user_profiles", {})
```

### Logging Configuration (`logging_config.py`)

Comprehensive logging setup with file and console output.

#### Main Function
```python
def setup_basic_logging(
    log_level: str = "INFO",
    include_console: bool = False,
    message_prefix: str = "",
    log_dir: str = "logs"
) -> None:
    """Set up basic logging with file output and optional console"""
```

#### Features
- **Timestamped Files**: Automatic timestamped log file creation
- **Latest Symlink**: Always points to current log file
- **Console Output**: Optional console logging for development
- **External Libraries**: Configures httpx, discord, openai log levels
- **UTF-8 Support**: International character support

#### Configuration
```python
# Environment-driven configuration
LOG_LEVEL = get_env_var("LOG_LEVEL", "INFO")

# Setup logging
setup_basic_logging(
    log_level=LOG_LEVEL,
    include_console=True,  # For development
    message_prefix="CIRIS: "
)
```

### Profile Template Loading (`profile_loader.py`)

⚠️ **IMPORTANT**: Profiles are now ONLY used as templates during initial agent creation. After creation, identity is managed through the graph database.

#### Core Function
```python
async def load_profile(profile_path: Union[str, Path]) -> AgentProfile:
    """Load profile template for new agent creation only"""
```

#### Features
- **Async I/O**: Non-blocking file operations using asyncio
- **Validation**: Pydantic schema validation for profile templates
- **Action Conversion**: String to enum conversion for permitted actions
- **Error Handling**: Comprehensive error reporting and fallback
- **Case Insensitive**: Flexible action name matching

#### Usage Example
```python
# Load profile template for new agent creation
profile_template = await load_profile("ciris_profiles/teacher.yaml")

# Used only during agent creation ceremony
# After creation, identity is stored in graph at "agent/identity"
# All changes require MEMORIZE action with WA approval
```

### Shutdown Management (`shutdown_manager.py`)

Global shutdown coordination for graceful application termination.

#### Core Class
```python
class ShutdownManager:
    """Centralized shutdown coordination with handler registration"""

    def request_shutdown(self, reason: str = "Unknown") -> None
    async def shutdown_handlers(self) -> None
    def register_shutdown_handler(self, handler: Callable) -> None
```

#### Global Functions
```python
# Request shutdown from anywhere in the application
request_global_shutdown(reason="Service failure")

# Register cleanup handlers
register_global_shutdown_handler(cleanup_database)

# Check shutdown state
if is_global_shutdown_requested():
    return

# Wait for shutdown in async contexts
await wait_for_global_shutdown()
```

#### Specialized Shutdown Types
```python
# Specific shutdown scenarios
request_shutdown_critical_service_failure(service_name, error)
request_shutdown_communication_failure(details)
request_shutdown_unrecoverable_error(error)
```

### Task Formatting (`task_formatters.py`)

Prompt engineering utilities for LLM context formatting.

#### Core Function
```python
def format_task_context(
    task: Optional[Any] = None,
    recent_actions: Optional[List[Dict[str, Any]]] = None,
    completed_task: Optional[Any] = None,
    max_actions: int = 5
) -> str:
    """Format task context for LLM prompts"""
```

#### Output Format
```python
# Generated context includes:
# - Current task ID, status, priority
# - Recent action history with timestamps
# - Completed task context for continuity
# - Structured text blocks for LLM consumption

context = format_task_context(
    task=current_task,
    recent_actions=action_history,
    max_actions=3
)
```

### User Utilities (`user_utils.py`)

User identification and nickname extraction across different contexts.

#### Core Function
```python
def extract_user_nick(message_or_params: Any) -> Optional[str]:
    """Extract user nickname from various message or parameter sources"""
```

#### Extraction Sources (Priority Order)
1. **Discord Messages**: Author display name or username
2. **Parameter Objects**: Value dictionary lookup
3. **Dispatch Context**: Author information
4. **Persistence Layer**: Deep lookup via thought/task relationships

#### Usage Example
```python
# Extract nickname from various sources
nick = extract_user_nick(discord_message)      # Discord message
nick = extract_user_nick(action_params)        # Action parameters
nick = extract_user_nick(dispatch_context)     # Processing context

# Handles None gracefully if no nickname found
if nick:
    logger.info(f"Processing request from {nick}")
```

## Integration Patterns

### Service Integration

The utilities integrate seamlessly with core CIRIS services:

```python
# Context building with service integration
context = build_dispatch_context(thought, task)

# User enrichment with GraphQL
provider = GraphQLContextProvider(memory_service=memory_service)
enriched = await provider.enrich_context(task, thought)

# Graceful shutdown with service cleanup
register_global_shutdown_handler(lambda: service_registry.shutdown())
```

### Configuration Usage

Utilities leverage centralized configuration:

```python
# Constants usage throughout the engine
from ciris_engine.utils.constants import COVENANT_TEXT, DEFAULT_NUM_ROUNDS

# Environment-aware configuration
from ciris_engine.utils.constants import DISCORD_CHANNEL_ID
```

### Error Handling

Utilities provide robust error handling patterns:

```python
# Graceful degradation in user utilities
nick = extract_user_nick(message) or "Unknown User"

# Profile templates only used during creation
try:
    template = await load_profile(profile_path)
    # Use template to create initial identity in graph
except Exception as e:
    logger.error(f"Template loading failed: {e}")
    template = await load_profile("default.yaml")
```

## Testing Support

The utilities module includes testing-friendly features:

### Shutdown Manager Testing
```python
# Reset for testing
ShutdownManager.reset_for_testing()

# Test shutdown scenarios
request_global_shutdown("test scenario")
assert is_global_shutdown_requested()
```

### Profile Loading Testing
```python
# Test profile validation
profile = await load_profile("test_profiles/invalid.yaml")
# Automatic fallback and error handling
```

## Performance Considerations

### Async Operations
- **Profile Loading**: Non-blocking I/O for YAML file reading
- **GraphQL Queries**: Async HTTP client with timeout handling
- **Context Building**: Efficient dict merging and validation

### Memory Management
- **Constants**: Loaded once at module import
- **Context Objects**: Efficient copying and merging
- **User Lookups**: Caching through persistence layer

### Error Isolation
- **Shutdown Handlers**: Individual handler failures don't affect others
- **User Extraction**: Silent failures with None returns
- **Profile Loading**: Automatic fallback to default profiles

## Usage Examples

### Basic Setup
```python
from ciris_engine.utils.logging_config import setup_basic_logging
from ciris_engine.utils.shutdown_manager import register_global_shutdown_handler

# Initialize logging
setup_basic_logging(log_level="DEBUG", include_console=True)

# Register cleanup
register_global_shutdown_handler(cleanup_resources)
```

### Context Processing
```python
from ciris_engine.utils.context_utils import build_dispatch_context
from ciris_engine.utils.user_utils import extract_user_nick

# Build processing context
context = build_dispatch_context(thought, task, round_num=1)

# Extract user information
user_nick = extract_user_nick(context)
```

### Identity Management (Profiles Deprecated)
```python
# Profile switching removed - identity is now graph-based
# To access agent identity:
from ciris_engine.persistence.models.identity import get_identity_for_context

identity_info = get_identity_for_context()
agent_name = identity_info.get("agent_name")
permitted_actions = identity_info.get("allowed_capabilities", [])

# To modify identity: Use MEMORIZE action with WA approval
```

---

The utilities module provides the essential infrastructure foundation that enables clean separation of concerns and reusable functionality across all CIRIS engine components, supporting reliable operation, comprehensive logging, graceful shutdown, and flexible configuration management.

---

*Copyright © 2025 Eric Moore and CIRIS L3C - Apache 2.0 License*
