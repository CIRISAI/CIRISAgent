# ToolBus

## Overview

The ToolBus is a specialized message bus that coordinates tool execution across all adapters in the CIRIS platform. It provides a unified interface for discovering, validating, and executing tools provided by different adapters (API, Discord, CLI) and core services (SecretsToolService), ensuring secure and reliable tool operations with comprehensive auditing and error handling.

## Mission Alignment

The ToolBus directly supports Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing" by:

- **Enabling Adaptive Capabilities**: Provides a flexible tool ecosystem that allows CIRIS to adapt its functionality based on context and environment
- **Promoting Safe Interactions**: Implements comprehensive security measures, parameter validation, and audit trails for all tool executions
- **Supporting Diverse Contexts**: Seamlessly routes tool requests to appropriate providers based on the execution context (Discord server, API client, CLI session)
- **Ensuring Reliable Service**: Maintains high availability through redundant tool providers and graceful failure handling
- **Facilitating Responsible Intelligence**: All tool operations are tracked, audited, and executed within ethical boundaries

## Architecture

### Service Type Handled
- **Primary**: `ServiceType.TOOL` - Coordinates all ToolService implementations
- **Providers**: Multiple adapter-provided tool services and core tool services

### Tool Execution Patterns
The ToolBus implements a sophisticated tool execution pattern:

1. **Multi-Provider Discovery**: Searches all registered ToolService providers to find which services support a requested tool
2. **Smart Routing**: When multiple services provide the same tool, applies intelligent routing logic (e.g., preferring APIToolService for general tools)
3. **Synchronous Execution**: All tool operations are executed synchronously with immediate results
4. **Result Caching**: Stores execution results by correlation ID for potential future retrieval

### Adapter-Provided Capabilities
- **API Adapter**: HTTP request tools (curl, http_get, http_post)
- **Discord Adapter**: Discord-specific tools for server management and interaction
- **CLI Adapter**: Command-line interface tools for local operations
- **Core Services**: Security tools (SecretsToolService) for secrets management

### Safety and Security Measures
- **Parameter Validation**: Pre-execution validation of all tool parameters against defined schemas
- **Error Isolation**: Comprehensive exception handling prevents tool failures from affecting system stability
- **Audit Trail**: Every tool execution generates telemetry and audit events
- **Service Health Monitoring**: Continuous health checks on all tool providers
- **Timeout Protection**: Configurable timeouts prevent hanging operations

## Tool Operations

### Tool Discovery and Registration
```python
# Get all available tools across all providers
available_tools = await tool_bus.get_available_tools()

# Get detailed information about all tools
all_tool_info = await tool_bus.get_all_tool_info()

# Get information about a specific tool
tool_info = await tool_bus.get_tool_info("curl")
```

### Execution Coordination
The ToolBus provides a unified execution interface that:
- Automatically finds supporting services for each tool
- Selects the most appropriate service when multiple providers exist
- Executes tools with full parameter validation
- Returns standardized `ToolExecutionResult` objects

```python
# Execute a tool with automatic provider selection
result = await tool_bus.execute_tool(
    tool_name="curl",
    parameters={"url": "https://api.example.com", "method": "GET"}
)
```

### Result Handling
- **Immediate Results**: All tools return results immediately via `ToolExecutionResult`
- **Correlation Tracking**: Each execution receives a unique correlation ID for tracking
- **Status Classification**: Results include detailed status information (`COMPLETED`, `FAILED`, `NOT_FOUND`, `UNAUTHORIZED`, `TIMEOUT`)
- **Data Standardization**: All tool output is normalized into consistent data structures

### Error Management
- **Graceful Degradation**: Tool failures don't affect overall system operation
- **Detailed Error Reporting**: Comprehensive error messages and stack traces for debugging
- **Metrics Tracking**: All errors are tracked for monitoring and alerting
- **Service Isolation**: Failures in one tool service don't affect others

## Adapter Integration

### How Different Adapters Provide Tools

#### API Adapter Tools
```python
class APIToolService(BaseService, ToolService):
    """Provides HTTP request functionality"""

    tools = {
        "curl": "Execute HTTP requests with curl-like functionality",
        "http_get": "Perform HTTP GET requests",
        "http_post": "Perform HTTP POST requests"
    }
```

#### Discord Adapter Tools
Discord adapters provide context-aware tools that understand server permissions, user roles, and channel-specific operations.

#### CLI Adapter Tools
CLI adapters provide local system tools for file operations, process management, and system introspection.

#### Core Tool Services
```python
class SecretsToolService(BaseService, ToolService):
    """Provides secure secrets management tools"""

    tools = {
        "recall_secret": "Retrieve stored secrets with audit trail",
        "update_secrets_filter": "Modify secrets detection patterns",
        "self_help": "Access agent experience documentation"
    }
```

### Multi-Provider Routing Logic
When multiple services provide the same tool, the ToolBus uses intelligent routing:
1. **Single Provider**: Direct routing to the only available service
2. **Multiple Providers**: Preference ordering (e.g., APIToolService preferred for HTTP tools)
3. **Context-Aware**: Future enhancement to route based on execution context (Discord guild, API client, etc.)

## Usage Examples

### Basic Tool Execution
```python
from ciris_engine.logic.buses.tool_bus import ToolBus

# Execute an HTTP GET request
result = await tool_bus.execute_tool(
    tool_name="http_get",
    parameters={
        "url": "https://api.github.com/user",
        "headers": {"Authorization": "Bearer token123"}
    }
)

if result.success:
    print(f"Status: {result.data['status_code']}")
    print(f"Response: {result.data['body']}")
else:
    print(f"Error: {result.error}")
```

### Tool Discovery and Validation
```python
# Discover available tools
tools = await tool_bus.get_available_tools()
print(f"Available tools: {tools}")

# Get detailed information
for tool_name in tools:
    info = await tool_bus.get_tool_info(tool_name)
    print(f"{info.name}: {info.description}")
    print(f"  Category: {info.category}")
    print(f"  Parameters: {info.parameters.required}")

# Validate parameters before execution
is_valid = await tool_bus.validate_parameters(
    "curl",
    {"url": "https://example.com", "method": "POST"}
)
```

### Secrets Management Tools
```python
# Securely retrieve a stored secret
result = await tool_bus.execute_tool(
    tool_name="recall_secret",
    parameters={
        "secret_uuid": "uuid-here",
        "purpose": "API authentication",
        "decrypt": True
    }
)

if result.success:
    secret_value = result.data["value"]
    # Use secret value securely...
```

### Error Handling and Monitoring
```python
# Execute with comprehensive error handling
try:
    result = await tool_bus.execute_tool("unknown_tool", {})

    if result.status == ToolExecutionStatus.NOT_FOUND:
        print(f"Tool not available: {result.error}")
    elif result.status == ToolExecutionStatus.FAILED:
        print(f"Execution failed: {result.error}")
    elif result.status == ToolExecutionStatus.UNAUTHORIZED:
        print(f"Access denied: {result.error}")

except Exception as e:
    print(f"Unexpected error: {e}")

# Check service health
is_healthy = await tool_bus.is_healthy()
print(f"ToolBus health: {'OK' if is_healthy else 'DEGRADED'}")
```

## Quality Assurance

### Type Safety Measures
- **Strict Typing**: All operations use strongly-typed Pydantic models
- **Parameter Schemas**: Tools define precise JSON schemas for parameter validation
- **Result Standardization**: All results conform to `ToolExecutionResult` schema
- **Protocol Compliance**: All tool services implement the `ToolServiceProtocol`

### Security Considerations
- **Input Validation**: Comprehensive parameter validation before tool execution
- **Access Control**: Integration with authentication and authorization systems
- **Audit Logging**: Complete audit trail for all tool operations
- **Error Sanitization**: Error messages are sanitized to prevent information leakage
- **Timeout Protection**: All operations have configurable timeout limits
- **Resource Limits**: Memory and CPU usage monitoring for tool operations

### Performance Features
- **Parallel Discovery**: Tool discovery across multiple providers runs in parallel
- **Connection Pooling**: HTTP tools use connection pooling for efficiency
- **Metrics Collection**: Comprehensive performance metrics for monitoring
- **Circuit Breaking**: Automatic service isolation when failures exceed thresholds
- **Result Caching**: Intelligent caching of tool results when appropriate

### Audit Trail Integration
Every tool execution generates comprehensive audit events:
```python
{
    "correlation_id": "uuid-here",
    "tool_name": "curl",
    "parameters": {"url": "https://example.com"},
    "provider": "APIToolService",
    "execution_time_ms": 234,
    "status": "COMPLETED",
    "success": true,
    "user_context": {...},
    "timestamp": "2025-01-15T10:30:00Z"
}
```

## Service Provider Requirements

### Implementing ToolServiceProtocol
All tool services must implement the complete `ToolServiceProtocol`:

```python
class YourToolService(BaseService, ToolService):

    async def execute_tool(self, tool_name: str, parameters: dict) -> ToolExecutionResult:
        """Execute a tool with validated parameters."""

    async def get_available_tools(self) -> List[str]:
        """Get list of all available tools."""

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific tool."""

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get information about all available tools."""

    async def validate_parameters(self, tool_name: str, parameters: dict) -> bool:
        """Validate parameters for a tool."""

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of an async tool execution."""

    async def list_tools(self) -> List[str]:
        """List available tools - legacy compatibility."""

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool."""
```

### Tool Information Requirements
Each tool must provide comprehensive information:
- **Name**: Unique identifier for the tool
- **Description**: Clear explanation of what the tool does
- **Parameters**: JSON schema defining required and optional parameters
- **Category**: Tool category for organization ("general", "security", "network", etc.)
- **Cost**: Execution cost (CPU, memory, external API calls)
- **Usage Guidance**: When and how to use the tool effectively

### Error Handling Standards
- Return structured `ToolExecutionResult` objects for all operations
- Use appropriate `ToolExecutionStatus` values
- Provide meaningful error messages without exposing sensitive information
- Log errors appropriately for debugging while maintaining security
- Handle timeouts gracefully with proper cleanup

### Performance Requirements
- Tool execution should complete within reasonable timeouts (default 30s)
- Memory usage should be bounded and predictable
- Network tools should implement connection pooling
- CPU-intensive tools should be designed for asynchronous operation
- All tools should provide telemetry data for monitoring

### Security Requirements
- Validate all input parameters against defined schemas
- Sanitize outputs to prevent information leakage
- Generate appropriate audit events for security-sensitive operations
- Respect user permissions and access controls
- Handle secrets and sensitive data according to CIRIS security policies

---

*The ToolBus serves as the central nervous system for CIRIS tool operations, ensuring that all tool executions are secure, reliable, auditable, and aligned with the platform's ethical principles.*
