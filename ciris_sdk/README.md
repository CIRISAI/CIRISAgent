# CIRIS SDK - v1 API (Pre-Beta)

⚠️ **WARNING: Pre-Beta Software** ⚠️

This SDK is for the CIRIS v1 API which is in **pre-beta** stage. The API and SDK interfaces may change significantly without notice. No backwards compatibility is guaranteed between releases.

Async client library for interacting with a running CIRIS Engine instance.

## Installation

```bash
pip install ciris-sdk
```

## API Version

This SDK targets the CIRIS v1 API specification. The v1 API represents a major simplification from v2, consolidating ~140 endpoints down to ~35 core endpoints while maintaining all essential functionality.

## Quick Start

```python
from ciris_sdk import CIRISClient

# Note: Using v1 API endpoints (all under /v1/ prefix)
async def main():
    async with CIRISClient(base_url="http://localhost:8080") as client:
        # Simple interaction - no auth required for OBSERVER access
        response = await client.interact("Hello, CIRIS!")
        print(response.response)

        # Get agent status
        status = await client.status()
        print(f"Agent state: {status.cognitive_state}")

        # Ask a question (returns just the text)
        answer = await client.ask("What is 2 + 2?")
        print(answer)  # "4"
```

## Primary Agent Endpoints

The SDK provides simplified access to the core agent interaction endpoints:

### Interact with the Agent
```python
# Send message and get response with metadata
response = await client.interact("Tell me about quantum computing")
print(f"Response: {response.response}")
print(f"Processing time: {response.processing_time_ms}ms")
print(f"Agent state: {response.state}")

# Include context for more targeted responses
response = await client.interact(
    "Help me debug this",
    context={"code": "def foo(): return bar", "error": "NameError"}
)
```

### Get Conversation History
```python
# Get recent conversation history
history = await client.history(limit=50)
for msg in history.messages:
    author = "Agent" if msg.is_agent else "User"
    print(f"[{author}] {msg.content}")
```

### Check Agent Status
```python
# Get comprehensive status
status = await client.status()
print(f"Agent: {status.name} ({status.agent_id})")
print(f"State: {status.cognitive_state}")
print(f"Uptime: {status.uptime_seconds}s")
print(f"Memory: {status.memory_usage_mb}MB")
```

### Get Agent Identity
```python
# Get identity and capabilities
identity = await client.identity()
print(f"Purpose: {identity.purpose}")
print(f"Tools: {identity.tools}")
print(f"Permissions: {identity.permissions}")
```

## 🚀 NEW: Unified Telemetry Access

The SDK now provides **easy access to ALL 436+ metrics** through the unified telemetry endpoint:

### Get All Metrics with One Call
```python
# Get ALL metrics from 21 services
all_metrics = await client.telemetry.get_all_metrics()
print(f"System healthy: {all_metrics['system_healthy']}")
print(f"LLM requests: {all_metrics['buses']['llm_bus']['request_count']}")

# Access specific metrics by path
cpu = await client.telemetry.get_metric_by_path(
    "infrastructure.resource_monitor.cpu_percent"
)
print(f"CPU usage: {cpu}%")

# Quick health check
health = await client.telemetry.check_system_health()
if not health['healthy']:
    print(f"Alerts: {health['alerts']}")
```

### Flexible View Options
```python
# Executive summary
summary = await client.telemetry.get_unified_telemetry()

# Operational view with live data
ops = await client.telemetry.get_unified_telemetry(
    view="operational",
    live=True  # Bypass cache
)

# Performance metrics only
perf = await client.telemetry.get_unified_telemetry(view="performance")

# Filter by category
buses = await client.telemetry.get_unified_telemetry(
    view="detailed",
    category="buses"
)

# Export for Prometheus
prometheus = await client.telemetry.get_unified_telemetry(
    format="prometheus"
)
```

See `examples/unified_telemetry_examples.py` for comprehensive examples.

## Authentication

The SDK provides comprehensive authentication support with role-based access control.
Many endpoints work without authentication (OBSERVER access), but some operations require login:

### Login
```python
# Login with username/password
await client.login("root", "changeme")

# The client automatically manages the token
# Now you can access protected endpoints
response = await client.interact("What admin functions are available?")
```

### Get Current User
```python
# Get current user info including permissions
user = await client.auth.get_current_user()
print(f"User: {user.username}")
print(f"Role: {user.role}")
print(f"Permissions: {user.permissions}")
```

### Check Permissions
```python
# Check if authenticated
is_auth = await client.auth.is_authenticated()

# Check specific permission
can_manage = await client.auth.has_permission("manage_config")

# Get current role
role = await client.auth.get_role()
```

### Token Management
```python
# Refresh token before expiry
refresh_response = await client.auth.refresh_token()

# Logout when done
await client.logout()
```

## Complete Example

```python
import asyncio
from ciris_sdk import CIRISClient

async def main():
    async with CIRISClient() as client:
        # Basic interaction (no auth needed)
        response = await client.interact("Hello!")
        print(f"Agent: {response.response}")

        # Check status
        status = await client.status()
        print(f"State: {status.cognitive_state}")

        # Login for admin functions
        await client.login("admin", "password")

        # Access protected resources
        # ... admin operations ...

        # Logout
        await client.logout()

if __name__ == "__main__":
    asyncio.run(main())
```

## Role Hierarchy

CIRIS uses a 4-role model with increasing privileges:

1. **OBSERVER**: Read-only access to system state
   - View messages, telemetry, reasoning, configuration
   - Monitor system health and activity

2. **ADMIN**: Operational control
   - All OBSERVER permissions
   - Manage configuration, incidents, tasks
   - Runtime control (pause/resume)
   - Trigger analysis

3. **AUTHORITY**: Strategic decisions
   - All ADMIN permissions
   - Resolve deferrals
   - Provide guidance
   - Grant permissions

4. **ROOT**: Full system access
   - Complete control
   - Emergency shutdown
   - Sensitive configuration access

## Resource-Specific Clients

The SDK also provides access to all system resources:

- `client.agent` - Agent interaction (primary interface)
- `client.memory` - Graph memory operations
- `client.system` - System operations (health, time, resources, runtime, services, shutdown)
- `client.telemetry` - Metrics and observability
- `client.auth` - Authentication management
- `client.audit` - Audit trail access
- `client.wa` - Wise Authority operations
- `client.config` - Configuration management (with PATCH support)
- `client.emergency` - Emergency shutdown with cryptographic signatures
- `client.jobs` - Async job management for expensive operations
- WebSocket streaming - Real-time updates with channel filters

## Migration from v2 API

The v1 API consolidates many endpoints:

- `/v1/runtime/*` → Use `client.system`
- `/v1/services/*` → Use `client.system.services()`
- `/v1/logs/*` → Use `client.telemetry.logs()`
- `/v1/visibility/*` → Use `client.telemetry.traces()`
- `/v1/tools/*` → Part of `client.agent.identity()`

For backward compatibility:

```python
# Old way (deprecated)
await client.agent.send_message("Hello")
messages = await client.agent.get_messages("channel_id")

# New way (preferred)
response = await client.interact("Hello")
history = await client.history()
```

Deprecated methods will show warnings but continue to work.
