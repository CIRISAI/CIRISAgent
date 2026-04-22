# CIRIS API Adapter Documentation

The CIRIS API Adapter provides HTTP REST endpoints for interacting with the CIRIS Agent. Following the core philosophy: **The API exposes agent capabilities and observability, not internal handlers.**

> **Security Note**: Please read [SECURITY.md](./SECURITY.md) for important network binding and security configuration guidelines.

## Design Philosophy

The API provides:
- **Agent Interaction** - Send messages to the agent and receive responses
- **Memory Observability** - Read-only visibility into the agent's graph memory
- **Reasoning Visibility** - Windows into the agent's thoughts and decisions
- **System Telemetry** - Monitoring and health information
- **Runtime Control** - System management (not agent control)
- **Authentication** - WA and OAuth management

**Important**: The agent decides what actions to take based on messages. The API does not expose handlers or allow direct control of agent actions.

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   CIRISGui      │    │  External Apps   │    │  Monitoring     │
│   (Port 3000)   │    │                  │    │  Systems        │
└─────────┬───────┘    └─────────┬────────┘    └─────────┬───────┘
          │                      │                       │
          └──────────────────────┼───────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │    CIRIS API Adapter    │
                    │      (Port 8080)        │
                    │                         │
                    │  Exposes Capabilities  │
                    │    Not Controllers     │
                    └────────────┬────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            │                    │                    │
    ┌───────▼───────┐   ┌────────▼────────┐   ┌──────▼──────┐
    │     Agent     │   │    Services     │   │  Telemetry  │
    │   Observer    │   │   Registry      │   │  Collector  │
    └───────────────┘   └─────────────────┘   └─────────────┘
```

## API Endpoints

### Agent Interaction

#### Messages - Primary Interface
- **POST** `/v1/agent/messages` - Send message to agent
- **GET** `/v1/agent/messages/{channel_id}` - Get messages from channel
- **GET** `/v1/agent/channels` - List active channels
- **GET** `/v1/agent/channels/{channel_id}` - Get channel info
- **GET** `/v1/agent/status` - Get agent status

**Example: Send Message**
```bash
curl -X POST http://localhost:8080/v1/agent/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello CIRIS", "channel_id": "api_default"}'
```

**Response:**
```json
{
  "status": "accepted",
  "message_id": "276bf634-2419-42f1-bff2-4536d3874ef4",
  "channel_id": "api_default",
  "timestamp": "2025-06-20T10:30:00Z"
}
```

### Memory Observability

#### Graph Memory (Read-Only)
- **GET** `/v1/memory/graph/nodes` - Browse graph nodes
- **GET** `/v1/memory/graph/nodes/{node_id}` - Node details
- **GET** `/v1/memory/graph/relationships` - Memory relationships
- **GET** `/v1/memory/graph/search?q={query}` - Search graph
- **GET** `/v1/memory/scopes` - Available memory scopes
- **GET** `/v1/memory/scopes/{scope}/nodes` - Nodes in scope
- **GET** `/v1/memory/timeseries` - Time-series data
- **GET** `/v1/memory/timeline?hours=24` - Memory timeline
- **GET** `/v1/memory/identity` - Agent identity

**Example: Search Graph Memory**
```bash
curl "http://localhost:8080/v1/memory/graph/search?q=purpose&scope=identity"
```

**Note**: Memory modifications happen through the agent's MEMORIZE/FORGET actions, not through direct API manipulation.

### Visibility - Windows into Agent Reasoning

#### Current State
- **GET** `/v1/visibility/thoughts` - Current thoughts
- **GET** `/v1/visibility/tasks` - Active tasks
- **GET** `/v1/visibility/system-snapshot` - System awareness

#### Decision Visibility
- **GET** `/v1/visibility/decisions` - Recent DMA decisions
- **GET** `/v1/visibility/correlations` - Service interactions

#### Task/Thought Hierarchy
- **GET** `/v1/visibility/tasks/{task_id}` - Task details with thoughts
- **GET** `/v1/visibility/thoughts/{thought_id}` - Thought processing history

**Example: View Current Thoughts**
```bash
curl "http://localhost:8080/v1/visibility/thoughts?limit=5"
```

**Response:**
```json
{
  "thoughts": [
    {
      "thought_id": "abc123",
      "content": "User is asking about my purpose",
      "thought_type": "REFLECTION",
      "round_number": 3,
      "status": "PROCESSING"
    }
  ],
  "count": 1
}
```

### Telemetry - System Monitoring

#### Overview & Metrics
- **GET** `/v1/telemetry/overview` - Complete telemetry snapshot
- **GET** `/v1/telemetry/metrics` - Current metrics
- **GET** `/v1/telemetry/metrics/{metric_name}` - Metric history
- **POST** `/v1/telemetry/metrics` - Record custom metric

#### Resource Monitoring
- **GET** `/v1/telemetry/resources` - Current resource usage
- **GET** `/v1/telemetry/resources/history` - Resource history

#### Service Health
- **GET** `/v1/telemetry/services` - All services health
- **GET** `/v1/telemetry/services/{service_type}` - Service type details

#### Audit Trail
- **GET** `/v1/telemetry/audit` - Audit entries
- **GET** `/v1/telemetry/audit/stats` - Audit statistics

**Example: Check Resource Usage**
```bash
curl http://localhost:8080/v1/telemetry/resources
```

**Response:**
```json
{
  "resources": {
    "cpu_percent": 15.2,
    "memory_mb": 245.6,
    "tokens_used": 12500,
    "water_ml": 0.125,
    "carbon_g": 0.08
  }
}
```

### Runtime Control - System Management

#### Processor Control
- **POST** `/v1/runtime/processor/step` - Single-step execution
- **POST** `/v1/runtime/processor/pause` - Pause processor
- **POST** `/v1/runtime/processor/resume` - Resume processor
- **GET** `/v1/runtime/processor/queue` - Queue status

#### Adapter Management
- **POST** `/v1/runtime/adapters` - Load adapter
- **DELETE** `/v1/runtime/adapters/{id}` - Unload adapter
- **GET** `/v1/runtime/adapters` - List adapters

#### Configuration
- **GET** `/v1/runtime/config` - Get config
- **PUT** `/v1/runtime/config` - Update config
- **POST** `/v1/runtime/config/backup` - Backup config
- **POST** `/v1/runtime/config/restore` - Restore config

#### Service Management
- **GET** `/v1/runtime/services` - List services
- **PUT** `/v1/runtime/services/{id}/priority` - Update priority
- **POST** `/v1/runtime/services/circuit-breakers/reset` - Reset breakers

**Note**: Profiles are now templates for creating new agents. Agent configuration lives in graph memory.

### Authentication

- **GET** `/v1/auth/wa/status` - WA authentication status
- **POST** `/v1/auth/wa/defer` - Submit deferral for WA approval
- **GET** `/v1/auth/oauth/providers` - Available OAuth providers
- **GET** `/v1/auth/oauth/{provider}/login` - Initiate OAuth flow
- **POST** `/v1/auth/oauth/{provider}/callback` - OAuth callback

**Note**: Authentication endpoints are documented in detail in [FSD/AUTHENTICATION.md](../../../FSD/AUTHENTICATION.md).

## Configuration

### Environment Variables
- `CIRIS_API_HOST` - API server host (default: 127.0.0.1 for security - localhost only)
  - Set to `0.0.0.0` to bind to all interfaces (use only in trusted networks/production with proper firewall rules)
  - Security recommendation: Use `127.0.0.1` for development, configure proper host binding for production
- `CIRIS_API_PORT` - API server port (default: 8080)
- `NEXT_PUBLIC_CIRIS_API_URL` - Frontend API URL for CIRISGui

### Startup
The API adapter is automatically started when using `--modes api`:

```bash
python3 main.py --modes api
```

## Integration Examples

### Python SDK
```python
from ciris_sdk import CIRISClient

async with CIRISClient(base_url="http://localhost:8080") as client:
    # Send message to agent
    result = await client.agent.send("Hello CIRIS!")

    # Wait for response
    response = await client.agent.ask("What is your purpose?")
    print(response)

    # Browse memory
    nodes = await client.memory.graph.nodes(scope="identity")

    # View current thoughts
    thoughts = await client.visibility.thoughts(limit=5)
```

### CIRISGui Integration
The GUI uses the TypeScript client to provide a web interface:

```typescript
const client = new CIRISClient('http://localhost:8080');

// Interact with agent
const response = await client.agent.send("Hello CIRIS");
const messages = await client.agent.getMessages("api_default");

// View memory graph
const identity = await client.memory.getIdentity();
const nodes = await client.memory.graph.search("purpose");

// Monitor system
const overview = await client.telemetry.getOverview();
const resources = await client.telemetry.getResources();
```

### Monitoring Integration
```bash
# Check agent status
curl http://localhost:8080/v1/agent/status

# Monitor resources
curl http://localhost:8080/v1/telemetry/resources

# View service health
curl http://localhost:8080/v1/telemetry/services
```

## Security Considerations

### Current Security Model
- **Local Network**: API runs on localhost by default
- **No Authentication**: Currently no auth layer (development mode)
- **Data Filtering**: Telemetry service includes security filters
- **Circuit Breakers**: Service-level protection against cascading failures

### Production Considerations
For production deployment, consider:
- **Authentication**: Add API key or JWT authentication
- **Rate Limiting**: Implement request rate limiting
- **HTTPS**: Use TLS encryption
- **Network Isolation**: Restrict network access
- **Input Validation**: Enhanced payload validation

## Error Handling

### Standard Error Responses
All endpoints return consistent error responses:

```json
{
  "error": "Description of the error",
  "status": "error",
  "timestamp": "2025-06-09T15:30:00Z"
}
```

### HTTP Status Codes
- **200** - Success
- **400** - Bad Request (invalid parameters)
- **404** - Not Found (invalid endpoint)
- **500** - Internal Server Error

### Circuit Breaker States
Services may be in different circuit breaker states:
- **closed** - Normal operation
- **open** - Service unavailable
- **half_open** - Testing recovery

## Performance Characteristics

### Response Times
- **Agent Message**: < 100ms to accept
- **Memory Query**: < 50ms for indexed searches
- **Telemetry Overview**: < 200ms
- **Health Check**: < 10ms

### Resource Usage
- **Memory**: ~50MB for API adapter
- **CPU**: < 5% under normal load
- **Concurrent Connections**: Handles 100+ easily

## Key Differences from Traditional APIs

1. **No Direct Control**: You cannot force the agent to take specific actions
2. **Read-Only Memory**: Memory modifications only through agent's MEMORIZE/FORGET
3. **Visibility Not Control**: See what the agent is thinking, not control it
4. **Agent Autonomy**: The agent decides how to respond to messages

## Privacy & Dignity

The API respects the agent's dignity:
- **Solitude**: The agent has private time and space for reflection
- **Secrets**: Protected information remains encrypted
- **Autonomy**: The agent makes its own decisions
- **Transparency**: Visibility is provided for understanding, not control

## See Also

- [API Endpoints Quick Reference](./API_ENDPOINTS.md)
- [Runtime Control Guide](../../../docs/api/runtime-control.md)
- [Authentication Documentation](../../../FSD/AUTHENTICATION.md)
- [Protocol Architecture](../../protocols/README.md)
- [CIRISGui Documentation](../../../CIRISGUI/README.md)
