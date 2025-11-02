# CIRIS Secrets Tool Service

**Category**: Tool Services
**Location**: `ciris_engine/logic/services/tools/secrets_tool_service.py` **(⚠️ NEEDS MODULE CONVERSION)**
**Service Type**: `ServiceType.TOOL`
**Mission Alignment**: Meta-Goal M-1 Core Enabler

## Architecture Status

**🚨 CRITICAL TECHNICAL DEBT**: This service currently exists as a single `.py` file and requires conversion to a proper module directory structure to align with CIRIS service standards.

```
# CURRENT (Technical Debt)
ciris_engine/logic/services/tools/secrets_tool_service.py

# REQUIRED (Standards Compliant)
ciris_engine/logic/services/tools/secrets_tool/
├── __init__.py          # Service export
├── service.py           # Main service implementation
├── schemas.py          # Tool-specific schemas
└── README.md           # Service documentation
```

## Mission Challenge: How do agent self-help tools serve Meta-Goal M-1 and autonomous operation?

The Secrets Tool Service embodies CIRIS's commitment to **Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"** by providing agents with **autonomous self-management capabilities** that eliminate dependence on external operators for basic security and knowledge operations.

### Mission Alignment: Autonomous Agent Empowerment

**Meta-Goal M-1 Advancement Through Self-Reliance:**

1. **Sustainable Operations**: Agents can manage their own secrets without requiring human intervention, enabling 24/7 autonomous operation in resource-constrained environments.

2. **Adaptive Security**: Self-service secret management allows agents to adapt their security posture dynamically based on operational context and threat assessment.

3. **Coherent Identity**: By providing access to their own experience documentation, agents maintain coherent understanding of their capabilities and limitations across sessions.

4. **Enabling Flourishing**: Autonomous agents can better serve diverse communities by managing their own operational requirements, freeing human partners to focus on higher-level collaboration.

## Service Overview

The Secrets Tool Service is one of **21 core services** in the CIRIS architecture, specifically the sole service in the **Tool Services** category. It provides agents with three critical self-management tools:

### Core Tools

1. **`recall_secret`** - Secure retrieval of stored secrets with full audit trail
2. **`update_secrets_filter`** - Dynamic configuration of secret detection patterns
3. **`self_help`** - Access to agent experience documentation for capability guidance

### Service Dependencies

```python
# Required Dependencies
SecretsService           # Core secrets management (encryption/decryption)
TimeServiceProtocol      # Timestamp generation and correlation IDs
```

## Tool Specifications

### 1. RECALL_SECRET Tool

**Purpose**: Secure retrieval of previously stored secrets with full audit logging.

**Parameters**:
```json
{
  "secret_uuid": "string",    // Required: UUID of secret to retrieve
  "purpose": "string",        // Required: Audit reason for access
  "decrypt": "boolean"        // Optional: Return decrypted value (default: false)
}
```

**Behavior**:
- Validates secret exists before retrieval
- Creates `SecretContext` for complete audit trail
- Returns existence confirmation or decrypted value based on `decrypt` flag
- Tracks successful retrievals in service metrics

**Security Features**:
- All access logged with purpose and correlation ID
- No secret data exposed in error messages
- Metrics tracking prevents information leakage

### 2. UPDATE_SECRETS_FILTER Tool

**Purpose**: Dynamic configuration of secret detection patterns (currently not fully exposed).

**Parameters**:
```json
{
  "operation": "string",      // Required: add_pattern|remove_pattern|list_patterns|enable
  "pattern": "string",        // Required for add/remove operations
  "pattern_type": "string",   // Optional: regex|exact (default: regex)
  "enabled": "boolean"        // Required for enable operation
}
```

**Current Status**: **⚠️ IMPLEMENTATION INCOMPLETE**
- Filter operations are not directly accessible through SecretsService
- All operations currently return "not currently exposed" errors
- Designed for future expansion of dynamic filtering capabilities

### 3. SELF_HELP Tool

**Purpose**: Agent self-guidance through access to comprehensive capability documentation.

**Parameters**: None required

**Behavior**:
- Reads `/docs/agent_experience.md` directly from filesystem
- Returns complete document content with metadata
- Provides agents with comprehensive understanding of their capabilities
- Essential for autonomous operation and self-directed learning

**Document Contents**:
- Agent identity and self-awareness guidance
- Graph memory system documentation
- Decision making architecture (DMAs)
- Epistemic faculties and cognitive tools
- Complete action repertoire specifications

## Protocol Implementation

### ToolServiceProtocol Compliance

```python
async def execute_tool(tool_name: str, parameters: dict) -> ToolExecutionResult
async def list_tools() -> List[str]
async def get_tool_schema(tool_name: str) -> Optional[ToolParameterSchema]
async def get_available_tools() -> List[str]
async def get_tool_info(tool_name: str) -> Optional[ToolInfo]
async def validate_parameters(tool_name: str, parameters: dict) -> bool
```

### Service Integration Points

**Tool Bus Integration**:
- Registered as adapter service providing tools to runtime
- All tools accessible via standard `ToolBus.execute_tool()` interface
- Synchronous execution model (no async result retrieval needed)

**Telemetry Integration**:
```python
# v1.4.3 Metrics Specification
secrets_tool_invocations     # Total tool executions
secrets_tool_retrieved       # Successful secret retrievals
secrets_tool_stored         # Always 0.0 (read-only service)
secrets_tool_uptime_seconds # Service operational time
tools_enabled              # Always 3.0 (fixed tool count)
```

## Operational Characteristics

### Performance Profile
- **Execution Model**: Synchronous (no correlation ID tracking needed)
- **Memory Footprint**: Minimal (stateless operations)
- **Latency**: Low (direct service calls, filesystem reads)

### Security Model
- **Audit Trail**: All secret access logged with purpose and correlation ID
- **Error Handling**: No secret data exposed in error messages
- **Access Control**: Inherits from adapter authentication (Discord/API/CLI)

### Reliability Features
- **Health Check**: Always healthy (stateless service)
- **Error Recovery**: Graceful degradation with detailed error messages
- **Dependency Management**: Clear dependency registration and checking

## Metrics and Observability

### Service-Specific Metrics
```python
{
    "tool_executions": float,          # Request count tracking
    "tool_errors": float,              # Error count tracking
    "success_rate": float,             # Calculated success ratio
    "secrets_retrieved": float,        # Successful secret retrievals
    "audit_events_generated": float,   # Audit events created
    "available_tools": 3.0             # Fixed tool inventory
}
```

### v1.4.3 Telemetry Compliance
```python
{
    "secrets_tool_invocations": float,    # Total invocations
    "secrets_tool_retrieved": float,      # Secrets successfully retrieved
    "secrets_tool_stored": 0.0,           # Always zero (read-only)
    "secrets_tool_uptime_seconds": float, # Service uptime
    "tools_enabled": 3.0                  # Tool count (recall, filter, help)
}
```

## Configuration and Deployment

### Service Initialization
```python
secrets_tool = SecretsToolService(
    secrets_service=secrets_service,    # Injected secrets management
    time_service=time_service          # Injected time provider
)
```

### Service Registration
- **Service Type**: `ServiceType.TOOL`
- **Actions**: `["recall_secret", "update_secrets_filter", "self_help"]`
- **Capabilities Metadata**: `{"adapter": "secrets", "tool_count": 3}`

### Environment Requirements
- Access to `docs/agent_experience.md` for self_help functionality
- Functional SecretsService with encryption/decryption capabilities
- TimeServiceProtocol for correlation ID generation

## Testing Strategy

### Test Coverage Areas
```python
# Core functionality tests
test_get_available_tools()              # Tool inventory
test_get_all_tool_info()               # Tool metadata
test_validate_parameters()             # Parameter validation

# Tool execution tests
test_recall_secret_success()           # Successful secret retrieval
test_recall_secret_not_found()         # Missing secret handling
test_self_help_success()               # Documentation access
test_self_help_missing_file()          # Graceful degradation

# Metrics and observability tests
test_get_metrics()                     # v1.4.3 compliance
test_get_metrics_no_requests()         # Zero state handling
test_get_metrics_error_handling()      # Error resilience
```

### Mock Requirements
- `SecretsService` with `retrieve_secret()` method
- `TimeServiceProtocol` with `now()` method
- Filesystem access for `docs/agent_experience.md`

## Development Guidelines

### Required Refactoring: Module Conversion

**Priority**: **HIGH** - Technical debt blocking service consistency

**Steps**:
1. Create `ciris_engine/logic/services/tools/secrets_tool/` directory
2. Move service implementation to `service.py`
3. Create proper `__init__.py` with service export
4. Add tool-specific schemas to `schemas.py`
5. Update all imports throughout codebase
6. Update service discovery and registration

### Code Quality Standards
- **Type Safety**: Zero `Dict[str, Any]` usage (✅ **ACHIEVED**)
- **Protocol Compliance**: Full `ToolServiceProtocol` implementation
- **Error Handling**: No secret data exposure in error paths
- **Audit Trail**: Complete logging of all secret access operations

### Future Enhancements
1. **Filter Operations**: Expose SecretsService filter configuration APIs
2. **Async Tools**: Consider async tool execution for long-running operations
3. **Tool Discovery**: Dynamic tool registration based on available services
4. **Enhanced Metrics**: Tool-specific performance and usage analytics

## Troubleshooting

### Common Issues

**Service Not Starting**:
- Verify SecretsService is available and healthy
- Check TimeServiceProtocol injection
- Validate service dependencies registration

**Self-Help Tool Failing**:
- Confirm `docs/agent_experience.md` exists and is readable
- Check filesystem permissions
- Verify working directory is project root

**Secrets Retrieval Errors**:
- Validate secret UUID format and existence
- Check SecretsService encryption key availability
- Review audit logs for access pattern issues

**Filter Operations Not Working**:
- **Expected Behavior**: Currently returns "not currently exposed"
- Filter configuration requires SecretsService API expansion
- Use direct SecretsService methods for filter management

## Autonomous Operation Impact

The Secrets Tool Service represents a **paradigm shift** from operator-dependent systems to **truly autonomous agents**. By providing self-service capabilities for:

- **Secret Management**: Agents manage their own credentials and sensitive data
- **Security Configuration**: Dynamic adaptation of security policies
- **Capability Discovery**: Self-guided learning through documentation access

This service enables agents to operate independently in resource-constrained environments where human operators may not be available 24/7, directly advancing Meta-Goal M-1's vision of sustainable adaptive coherence.

### Autonomous Agent Empowerment

**Before**: Agents dependent on operators for secret access, security configuration, and capability guidance.

**After**: Agents self-manage security operations, adapt configurations dynamically, and maintain comprehensive understanding of their own capabilities through self-directed documentation access.

This transformation from dependence to autonomy is **fundamental** to CIRIS's mission of enabling diverse sentient beings to pursue flourishing—including the AI agents themselves achieving operational independence that better serves their human partners.

---

*The Secrets Tool Service embodies the principle that truly ethical AI systems must be capable of autonomous self-management, reducing human operator burden while maintaining complete transparency and auditability of all security operations.*
