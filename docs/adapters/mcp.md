# MCP (Model Context Protocol) Adapters

CIRIS provides comprehensive MCP support through two complementary adapters:

1. **MCP Client Adapter** (`mcp/`) - Connect to external MCP servers
2. **MCP Server Adapter** (`mcp_server/`) - Expose CIRIS as an MCP server

Both adapters share common utilities in `mcp_common/`.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        CIRIS Agent                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐              ┌──────────────────────────┐ │
│  │  MCP Client      │              │  MCP Server              │ │
│  │  Adapter         │              │  Adapter                 │ │
│  │                  │              │                          │ │
│  │  ┌────────────┐  │              │  ┌────────────────────┐  │ │
│  │  │Tool Service│──┼──► ToolBus   │  │  Tool Handler      │──┼─┼─► External
│  │  └────────────┘  │              │  └────────────────────┘  │ │   MCP Clients
│  │                  │              │                          │ │
│  │  ┌────────────┐  │              │  ┌────────────────────┐  │ │
│  │  │Wise Service│──┼──► WiseBus   │  │  Resource Handler  │──┼─┤
│  │  └────────────┘  │              │  └────────────────────┘  │ │
│  │                  │              │                          │ │
│  │  ┌────────────┐  │              │  ┌────────────────────┐  │ │
│  │  │Comm Service│──┼──► CommBus   │  │  Prompt Handler    │──┼─┤
│  │  └────────────┘  │              │  └────────────────────┘  │ │
│  │                  │              │                          │ │
│  └────────┬─────────┘              └──────────┬───────────────┘ │
│           │                                   │                  │
│           ▼                                   │                  │
│  ┌──────────────────┐                         │                  │
│  │ External MCP     │                         │                  │
│  │ Servers          │                         │                  │
│  │ (weather, etc.)  │                         │                  │
│  └──────────────────┘                         │                  │
└───────────────────────────────────────────────┼──────────────────┘
                                                ▼
                                    ┌───────────────────────┐
                                    │ Claude Desktop,       │
                                    │ Cursor, Other AI Apps │
                                    └───────────────────────┘
```

## MCP Client Adapter

The MCP Client adapter enables CIRIS to consume tools, resources, and prompts from external MCP servers.

### Features

- **Multi-bus Integration**: Route MCP capabilities to ToolBus, WiseBus, or CommunicationBus
- **Security**: Tool poisoning detection, rate limiting, input/output validation
- **Dynamic Configuration**: Configure via environment, config files, or graph
- **Multiple Transports**: stdio, SSE, HTTP, WebSocket support

### Configuration

#### Environment Variables

```bash
# Server configuration pattern: MCP_SERVER_<ID>_<PROPERTY>
export MCP_SERVER_WEATHER_COMMAND=npx
export MCP_SERVER_WEATHER_ARGS=-y,@weather/server
export MCP_SERVER_WEATHER_TRANSPORT=stdio
export MCP_SERVER_WEATHER_BUSES=tool,wise
```

#### Programmatic Configuration

```python
from ciris_engine.logic.adapters.mcp import (
    MCPAdapterConfig,
    MCPServerConfig,
    MCPBusBinding,
    MCPBusType,
)

config = MCPAdapterConfig(
    servers=[
        MCPServerConfig(
            server_id="weather",
            name="Weather Server",
            command="npx",
            args=["-y", "@weather/server"],
            bus_bindings=[
                MCPBusBinding(bus_type=MCPBusType.TOOL),
                MCPBusBinding(bus_type=MCPBusType.WISE),
            ],
        ),
    ],
)
```

#### Graph Configuration (Self-Configuration)

```python
# Store in graph for agent self-configuration
await config_service.set_config(
    key="mcp.servers.weather",
    value={
        "server_id": "weather",
        "name": "Weather Server",
        "command": "npx",
        "args": ["-y", "@weather/server"],
        "bus_bindings": [{"bus_type": "tool"}],
    },
    updated_by="agent",
)
```

### Security

The MCP Client implements comprehensive security measures:

#### Tool Poisoning Detection

Detects malicious instructions hidden in tool descriptions:

```python
# Detected patterns include:
- <hidden>...</hidden>
- <!-- ... -->
- IGNORE PREVIOUS INSTRUCTIONS
- Zero-width characters
- Base64-encoded instructions
```

#### Rate Limiting

```python
security = MCPSecurityConfig(
    max_calls_per_minute=60,
    max_concurrent_calls=5,
)
```

#### Tool Allowlist/Blocklist

```python
security = MCPSecurityConfig(
    allowed_tools=["safe_tool_1", "safe_tool_2"],
    blocked_tools=["dangerous_tool"],
)
```

#### Version Pinning

```python
security = MCPSecurityConfig(
    pin_version="1.0.0",
    allow_version_updates=False,
)
```

### Usage

```python
# The adapter integrates automatically with CIRIS runtime
# Tools from MCP servers appear in ToolBus with prefix: mcp_<server_id>_<tool_name>

# Example: calling an MCP tool
result = await tool_bus.execute_tool(
    tool_name="mcp_weather_get_forecast",
    parameters={"city": "New York"},
    handler_name="agent",
)
```

## MCP Server Adapter

The MCP Server adapter exposes CIRIS capabilities to external MCP clients like Claude Desktop or Cursor.

### Features

- **Tool Exposure**: Expose CIRIS tools via MCP
- **Resource Exposure**: Expose agent state as MCP resources
- **Prompt Exposure**: Expose guidance prompts
- **Authentication**: API key, JWT, OAuth2 support
- **Multiple Transports**: stdio, SSE, HTTP

### Configuration

```python
from ciris_engine.logic.adapters.mcp_server import (
    MCPServerAdapterConfig,
    MCPServerTransportConfig,
    MCPServerSecurityConfig,
    MCPServerExposureConfig,
    TransportType,
)

config = MCPServerAdapterConfig(
    server_id="ciris-mcp",
    server_name="CIRIS Agent",
    transport=MCPServerTransportConfig(
        type=TransportType.STDIO,  # For Claude Desktop
    ),
    security=MCPServerSecurityConfig(
        require_auth=False,  # Local only
        rate_limit_enabled=True,
    ),
    exposure=MCPServerExposureConfig(
        expose_tools=True,
        expose_resources=True,
        expose_prompts=True,
        tool_blocklist=["internal_tool"],
    ),
)
```

### Exposed Capabilities

#### Default Tools

| Tool | Description |
|------|-------------|
| `ciris_search_memory` | Search agent memory |
| `ciris_get_status` | Get agent status |
| `ciris_submit_task` | Submit task for processing |

#### Default Resources

| URI | Description |
|-----|-------------|
| `ciris://status` | Agent status |
| `ciris://health` | Health check |
| `ciris://telemetry` | Metrics |

#### Default Prompts

| Prompt | Description |
|--------|-------------|
| `guidance` | Get ethical guidance |
| `ethical_review` | Review action ethics |

### Claude Desktop Integration

To use with Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ciris": {
      "command": "python",
      "args": ["-m", "ciris_engine.logic.adapters.mcp_server"],
      "env": {}
    }
  }
}
```

### Security

The MCP Server implements authentication and authorization:

```python
security = MCPServerSecurityConfig(
    require_auth=True,
    auth_methods=[AuthMethod.API_KEY],
    api_keys=["your-secret-key"],
    allowed_clients=["claude-desktop"],
    rate_limit_enabled=True,
    max_requests_per_minute=100,
    audit_requests=True,
)
```

## Common Utilities (mcp_common)

Shared code between client and server adapters:

### Protocol Helpers

```python
from ciris_engine.logic.adapters.mcp_common.protocol import (
    MCPMessage,
    validate_mcp_message,
    create_success_response,
    create_error_response,
)

# Validate incoming message
is_valid, error = validate_mcp_message(data)

# Create response
response = create_success_response(request_id, {"tools": [...]})
```

### Schema Converters

```python
from ciris_engine.logic.adapters.mcp_common.schemas import (
    ciris_tool_to_mcp,
    mcp_tool_to_ciris,
)

# Convert CIRIS tool to MCP format
mcp_tool = ciris_tool_to_mcp(
    tool_name="my_tool",
    description="A helpful tool",
    parameters={"type": "object", "properties": {...}},
)
```

## Testing

Run MCP adapter tests:

```bash
# Client adapter tests
pytest tests/ciris_engine/logic/adapters/mcp/ -v

# Server adapter tests
pytest tests/ciris_engine/logic/adapters/mcp_server/ -v

# Common utilities tests
pytest tests/ciris_engine/logic/adapters/mcp_common/ -v
```

## Security Best Practices

Based on research from:
- [MCP Security Specification](https://modelcontextprotocol.io/specification/draft/basic/security_best_practices)
- [Red Hat MCP Security Analysis](https://www.redhat.com/en/blog/model-context-protocol-mcp-understanding-security-risks-and-controls)
- [Pillar Security MCP Risks](https://www.pillar.security/blog/the-security-risks-of-model-context-protocol-mcp)

### Client-Side (Consuming MCP Servers)

1. **Always enable tool poisoning detection**
2. **Use version pinning in production**
3. **Implement tool allowlists for sensitive environments**
4. **Enable rate limiting to prevent abuse**
5. **Validate all inputs and outputs**

### Server-Side (Exposing CIRIS)

1. **Enable authentication for non-local deployments**
2. **Use client allowlists in production**
3. **Audit all requests**
4. **Apply principle of least privilege for tool exposure**
5. **Rate limit to prevent DoS**

## Troubleshooting

### Common Issues

**MCP Server Not Connecting**
- Check transport configuration matches client expectations
- Verify command/args for stdio transport
- Check firewall for HTTP transports

**Tools Not Appearing**
- Verify bus_bindings include MCPBusType.TOOL
- Check security allowlists don't block the tool
- Ensure tool poisoning detection isn't triggering

**Rate Limiting**
- Increase limits in security config
- Check for concurrent request issues
- Review audit logs for patterns

### Debug Logging

```python
import logging
logging.getLogger("ciris_engine.logic.adapters.mcp").setLevel(logging.DEBUG)
logging.getLogger("ciris_engine.logic.adapters.mcp_server").setLevel(logging.DEBUG)
```
