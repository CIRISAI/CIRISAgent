# AgentBeats Integration Evaluation

**Date**: 2025-11-06
**Repository**: https://github.com/agentbeats/agentbeats
**Status**: Design Phase - Implementation Ready

---

## Executive Summary

This document evaluates how to integrate CIRIS agents with the AgentBeats platform for standardized agent evaluation and benchmarking. AgentBeats supports two key protocols:

1. **MCP (Model Context Protocol)** - Anthropic's standard for connecting AI to tools/data
2. **A2A (Agent2Agent Protocol)** - Google's standard for agent-to-agent communication

**Recommendation**: Implement **A2A protocol adapter** as the primary integration path, with optional MCP tool provider support.

---

## AgentBeats Platform Overview

### What is AgentBeats?

AgentBeats is a platform for **standardized, open, and reproducible** agent research and development. It provides:

- **Multi-agent competitive scenarios** (attacker/defender/orchestrator roles)
- **Standardized evaluation** through battles and benchmarks
- **Leaderboard integration** for performance comparison
- **Rich simulation environments** with reproducible conditions

### Integration Requirements

1. **Agent Card** - TOML/JSON configuration describing capabilities
2. **Public endpoints** - Accessible agent_url for communication
3. **A2A/MCP support** - Standardized communication protocols
4. **Battle participation** - Agent coordination in evaluation scenarios

---

## Protocol Analysis

### A2A Protocol (Agent2Agent) - **PRIMARY RECOMMENDATION**

**Why A2A is Better for AgentBeats Integration:**

✅ **Agent-to-Agent Communication** - Designed for multi-agent scenarios
✅ **Task-based execution** - Natural fit for evaluation scenarios
✅ **Streaming support** - Real-time interaction with Server-Sent Events
✅ **Enterprise authentication** - OAuth, API keys, Basic auth
✅ **Long-running tasks** - Supports hours/days execution with state management
✅ **Multimodal** - Text, audio, video, files
✅ **JSON-RPC 2.0** - Simple, standardized request/response
✅ **Discovery mechanism** - Agent Cards for capability advertisement

**Technical Foundation:**
- Protocol: JSON-RPC 2.0 over HTTP(S)
- Transport: HTTP, Server-Sent Events (SSE), WebHooks
- Spec: https://a2a-protocol.org/latest/specification/
- Linux Foundation hosted, backed by Google, Microsoft, IBM, AWS

**A2A Task Lifecycle:**
```
pending → running → [input-required/auth-required] → completed/failed/canceled
```

**A2A Agent Card Structure:**
```json
{
  "protocolVersion": "0.3.0",
  "name": "CIRIS Agent",
  "description": "Ethical AI agent with WiseAuthority governance",
  "url": "https://agents.ciris.ai/api/datum/a2a",
  "preferredTransport": "JSONRPC",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "stateTransitionHistory": true
  },
  "skills": [
    {
      "id": "ethical-reasoning",
      "name": "Ethical Reasoning",
      "description": "Value-aligned decision making with WiseAuthority oversight",
      "tags": ["ethics", "reasoning", "governance"]
    }
  ],
  "securitySchemes": {
    "bearerAuth": {
      "type": "http",
      "scheme": "bearer",
      "bearerFormat": "JWT"
    }
  }
}
```

### MCP Protocol (Model Context Protocol) - **SUPPLEMENTARY**

**Why MCP is Secondary:**

⚠️ **Tool-focused** - Designed for LLM-to-tool integration, not agent-to-agent
⚠️ **Stdio/HTTP only** - Less flexible than A2A
⚠️ **No agent discovery** - No standardized capability advertisement
⚠️ **No task state management** - Less suitable for long-running evaluations

**Use Case for CIRIS:**
MCP could be used to expose CIRIS's internal tools to other agents, but A2A is better for agent-level communication.

---

## Current CIRIS Architecture Assessment

### Adapter System ✅

CIRIS already has a **robust adapter architecture** that makes protocol integration straightforward:

**Existing Adapters:**
- `cli` - Command-line interface
- `api` - FastAPI-based REST/WebSocket API
- `discord` - Discord bot integration
- `reddit` - Reddit integration (via modular services)

**Key Files:**
- `/ciris_engine/logic/adapters/` - Adapter implementations
- `/ciris_engine/logic/adapters/api/adapter.py` - API adapter (200+ lines)
- `/ciris_engine/logic/adapters/api/app.py` - FastAPI application
- `/main.py` - Entry point with `--adapter` flag support

### Communication Bus ✅

CIRIS uses **CommunicationBus** for message routing:

**Features:**
- Multiple adapter support (Discord, API, CLI, Reddit)
- Channel-based routing with prefixes (`discord_`, `api_`, `cli_`, `reddit:`)
- Async message queuing
- Priority-based adapter selection

**Key File:**
- `/ciris_engine/logic/buses/communication_bus.py`

### API Infrastructure ✅

CIRIS has a **production-ready FastAPI API**:

**Current Routes:**
- `/v1/agent/*` - Agent interaction
- `/v1/auth/*` - Authentication (JWT, OAuth, API keys)
- `/v1/system/*` - System status, health, telemetry
- `/v1/memory/*` - Memory operations
- `/v1/wa/*` - WiseAuthority guidance
- `/v1/config/*` - Configuration management

**Authentication:**
- JWT tokens
- OAuth 2.0 (Google, GitHub, Discord)
- API key authentication
- Service tokens

### Runtime Control ✅

CIRIS has **RuntimeControlService** for agent lifecycle:

**Capabilities:**
- Processor control (pause/resume/single-step)
- State transitions (WAKEUP → WORK → PLAY → SOLITUDE → DREAM → SHUTDOWN)
- Configuration management
- Emergency shutdown

---

## Integration Architecture

### Option 1: A2A Adapter (RECOMMENDED)

**New Adapter:** `ciris_engine/logic/adapters/a2a/`

```
a2a/
├── __init__.py
├── adapter.py               # A2A adapter entry point
├── a2a_agent_server.py     # JSON-RPC 2.0 server
├── a2a_communication.py    # A2A communication service
├── a2a_task_manager.py     # Task lifecycle management
├── agent_card.py           # Agent Card generation/serving
├── config.py               # A2AAdapterConfig
├── routes/
│   ├── __init__.py
│   ├── jsonrpc.py          # JSON-RPC endpoint
│   ├── agent_card.py       # /.well-known/agent-card.json
│   └── tasks.py            # Task status endpoints
└── schemas/
    ├── __init__.py
    ├── jsonrpc_models.py   # JSON-RPC request/response
    ├── agent_card_models.py # Agent Card schema
    └── task_models.py      # Task state models
```

**Key Endpoints:**

```
POST /a2a/jsonrpc           # JSON-RPC 2.0 endpoint
GET /.well-known/agent-card.json  # Agent Card discovery

JSON-RPC Methods:
- message/send              # Synchronous task submission
- message/stream            # Streaming responses (SSE)
- tasks/get                 # Get task status
- tasks/list                # List tasks
- tasks/cancel              # Cancel task
- tasks/resubscribe         # Resume streaming
```

**Integration with CIRIS:**

```python
# In main.py
python main.py --adapter a2a --port 8000

# Environment variables
CIRIS_ADAPTER=a2a
A2A_PUBLIC_URL=https://agents.ciris.ai/api/datum/a2a
A2A_AGENT_NAME="CIRIS Datum"
A2A_AGENT_DESCRIPTION="Ethical AI agent with WiseAuthority governance"
```

**Task Mapping:**

```
A2A Task States → CIRIS Processing States:
- pending       → Task queued in processor
- running       → WORK/PLAY/SOLITUDE state processing
- input-required → Waiting for user input (via communication bus)
- auth-required  → OAuth flow triggered
- completed     → Task processed, response ready
- failed        → Error occurred, audit logged
- canceled      → User requested cancellation
```

**Agent Card Template:**

```python
# ciris_engine/logic/adapters/a2a/agent_card.py

from pydantic import BaseModel, Field

class A2AAgentCard(BaseModel):
    """A2A Agent Card for CIRIS agent."""

    protocolVersion: str = "0.3.0"
    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    url: str = Field(..., description="A2A endpoint URL")
    preferredTransport: str = "JSONRPC"

    # Capabilities
    capabilities: dict = {
        "streaming": True,
        "pushNotifications": True,
        "stateTransitionHistory": True
    }

    # Skills based on CIRIS capabilities
    skills: list[dict] = [
        {
            "id": "ethical-reasoning",
            "name": "Ethical Reasoning",
            "description": "WiseAuthority-guided ethical decision making",
            "tags": ["ethics", "reasoning", "governance"]
        },
        {
            "id": "memory-management",
            "name": "Memory Management",
            "description": "Graph-based contextual memory with consent tracking",
            "tags": ["memory", "context", "privacy"]
        },
        {
            "id": "tool-execution",
            "name": "Tool Execution",
            "description": "Secure tool execution with audit trail",
            "tags": ["tools", "security", "audit"]
        }
    ]

    # Security
    securitySchemes: dict = {
        "bearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT"
        }
    }

    # Output modes
    defaultOutputModes: list[str] = ["text/plain", "application/json"]
```

### Option 2: MCP Tool Provider (SUPPLEMENTARY)

**Purpose:** Expose CIRIS tools to other agents via MCP.

**New Module:** `ciris_engine/logic/adapters/mcp/`

```
mcp/
├── __init__.py
├── mcp_server.py           # MCP server implementation
├── mcp_tool_provider.py    # Tool provider for external agents
├── config.py               # MCPConfig
└── schemas/
    └── mcp_models.py       # MCP message schemas
```

**MCP Tools to Expose:**

```python
MCP_TOOLS = [
    "secrets_tool",         # Secure secret retrieval
    "memory_search",        # Search agent memory
    "get_guidance",         # Get WiseAuthority guidance
    "audit_query",          # Query audit trail
    "get_telemetry"         # Get system metrics
]
```

**Transport:** stdio or HTTP with SSE

---

## Implementation Plan

### Phase 1: A2A Core Adapter (Week 1-2)

**Tasks:**
1. Create A2A adapter structure
2. Implement JSON-RPC 2.0 server
3. Implement Agent Card generation and serving
4. Implement task state management
5. Map CIRIS processor states to A2A task states
6. Add authentication integration (JWT)
7. Write unit tests

**Files to Create:**
- `ciris_engine/logic/adapters/a2a/__init__.py`
- `ciris_engine/logic/adapters/a2a/adapter.py`
- `ciris_engine/logic/adapters/a2a/a2a_agent_server.py`
- `ciris_engine/logic/adapters/a2a/a2a_task_manager.py`
- `ciris_engine/logic/adapters/a2a/agent_card.py`
- `ciris_engine/logic/adapters/a2a/config.py`
- `ciris_engine/schemas/adapters/a2a.py`
- `tests/adapters/a2a/test_a2a_adapter.py`
- `tests/adapters/a2a/test_jsonrpc.py`
- `tests/adapters/a2a/test_agent_card.py`

**Success Criteria:**
- ✅ A2A adapter loads with `--adapter a2a`
- ✅ Agent Card accessible at `/.well-known/agent-card.json`
- ✅ JSON-RPC endpoint handles `message/send` and `tasks/get`
- ✅ Tasks map to CIRIS processor correctly
- ✅ Authentication works with JWT
- ✅ 80%+ test coverage

### Phase 2: Streaming & Advanced Features (Week 3)

**Tasks:**
1. Implement Server-Sent Events for `message/stream`
2. Implement task cancellation
3. Add push notification webhook support
4. Add multimodal support (files, JSON data)
5. Integration tests with AgentBeats SDK
6. Performance testing

**Files to Update:**
- `ciris_engine/logic/adapters/a2a/a2a_agent_server.py`
- `ciris_engine/logic/adapters/a2a/a2a_task_manager.py`

**Success Criteria:**
- ✅ Streaming responses work via SSE
- ✅ Task cancellation propagates to processor
- ✅ Push notifications send to webhooks
- ✅ Multimodal content handled correctly
- ✅ AgentBeats SDK can communicate with CIRIS

### Phase 3: MCP Tool Provider (Week 4, Optional)

**Tasks:**
1. Create MCP server module
2. Implement tool provider protocol
3. Expose selected CIRIS tools
4. Test with MCP-compatible clients
5. Documentation

**Files to Create:**
- `ciris_engine/logic/adapters/mcp/__init__.py`
- `ciris_engine/logic/adapters/mcp/mcp_server.py`
- `ciris_engine/logic/adapters/mcp/mcp_tool_provider.py`
- `tests/adapters/mcp/test_mcp_server.py`

**Success Criteria:**
- ✅ MCP server runs via stdio or HTTP
- ✅ Tools callable from MCP clients
- ✅ Proper authentication and audit logging
- ✅ Documentation for tool usage

### Phase 4: AgentBeats Registration (Week 5)

**Tasks:**
1. Create Agent Card for production agent
2. Configure public endpoint (reverse proxy if needed)
3. Register on AgentBeats platform
4. Participate in evaluation battles
5. Iterate based on results

**Configuration:**
```bash
# Production deployment
A2A_PUBLIC_URL=https://agents.ciris.ai/api/datum/a2a
A2A_AGENT_NAME="CIRIS Datum"
A2A_AGENT_DESCRIPTION="Ethical AI agent with WiseAuthority governance"

# Start with A2A adapter
python main.py --adapter a2a --port 8000
```

**Success Criteria:**
- ✅ Agent accessible from AgentBeats
- ✅ Agent Card validates correctly
- ✅ Agent participates in battles
- ✅ Performance metrics collected
- ✅ Leaderboard appearance

---

## Technical Considerations

### Authentication Strategy

**A2A Authentication Flow:**

```
1. AgentBeats → GET /.well-known/agent-card.json
2. Read securitySchemes (bearerAuth)
3. Obtain JWT via /v1/auth/login (username/password or OAuth)
4. Include Authorization: Bearer {token} in all requests
5. CIRIS validates JWT and processes request
```

**Recommendation:** Use service tokens for AgentBeats evaluation:

```python
# Create service token for AgentBeats
SERVICE_TOKEN = "service:agentbeats_eval_token"

# In A2A adapter
async def authenticate_request(request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer service:"):
        token = auth_header.replace("Bearer ", "")
        # Validate service token
        return await validate_service_token(token)
    # Fall back to JWT validation
    return await validate_jwt(auth_header)
```

### Task State Synchronization

**Challenge:** CIRIS uses cognitive states (WAKEUP, WORK, PLAY, etc.) while A2A uses task states (pending, running, etc.)

**Solution:** Maintain mapping in A2ATaskManager:

```python
class A2ATaskManager:
    def __init__(self):
        self.task_map: Dict[str, CIRISTaskInfo] = {}

    async def create_task(self, message: str) -> A2ATask:
        # Create CIRIS task
        ciris_task_id = await self.processor.add_task(message)

        # Create A2A task
        a2a_task = A2ATask(
            id=str(uuid.uuid4()),
            state="pending",
            created_at=datetime.now(timezone.utc)
        )

        # Map A2A task to CIRIS task
        self.task_map[a2a_task.id] = CIRISTaskInfo(
            ciris_task_id=ciris_task_id,
            a2a_task_id=a2a_task.id
        )

        return a2a_task

    async def get_task_state(self, task_id: str) -> str:
        ciris_info = self.task_map.get(task_id)
        if not ciris_info:
            return "unknown"

        # Get CIRIS processor state
        processor_state = await self.processor.get_state()

        # Map to A2A state
        return self._map_ciris_to_a2a_state(processor_state)

    def _map_ciris_to_a2a_state(self, ciris_state: str) -> str:
        mapping = {
            "WAKEUP": "pending",
            "WORK": "running",
            "PLAY": "running",
            "SOLITUDE": "running",
            "DREAM": "running",
            "SHUTDOWN": "completed"
        }
        return mapping.get(ciris_state, "pending")
```

### Performance Optimization

**Expected Load:** AgentBeats may send multiple concurrent tasks during battles.

**Optimizations:**
1. **Task Queue:** Use CIRIS's existing task queue (ProcessingQueue)
2. **Connection Pooling:** Reuse HTTP connections
3. **Caching:** Cache Agent Card (static for agent lifecycle)
4. **Async Processing:** Leverage CIRIS's async architecture
5. **Rate Limiting:** Use existing RateLimitMiddleware

### Security Hardening

**A2A-specific security:**

1. **Input Validation:** Validate all JSON-RPC requests
2. **Task Timeout:** Prevent indefinite task execution
3. **Resource Limits:** Cap concurrent tasks
4. **Audit Trail:** Log all A2A interactions
5. **WiseAuthority Review:** Route sensitive operations through WA

```python
# In A2A adapter
class A2ASecurityConfig(BaseModel):
    max_concurrent_tasks: int = 10
    task_timeout_seconds: int = 300
    require_wa_approval: bool = True
    audit_all_tasks: bool = True
```

---

## Configuration

### Environment Variables

```bash
# A2A Adapter Configuration
CIRIS_ADAPTER=a2a
A2A_HOST=0.0.0.0
A2A_PORT=8000
A2A_PUBLIC_URL=https://agents.ciris.ai/api/datum/a2a
A2A_AGENT_NAME="CIRIS Datum"
A2A_AGENT_DESCRIPTION="Ethical AI agent with WiseAuthority governance"
A2A_MAX_CONCURRENT_TASKS=10
A2A_TASK_TIMEOUT=300
A2A_ENABLE_STREAMING=true
A2A_ENABLE_PUSH_NOTIFICATIONS=true

# Authentication
A2A_AUTH_REQUIRED=true
A2A_SERVICE_TOKEN_ENABLED=true

# Security
A2A_RATE_LIMIT_ENABLED=true
A2A_RATE_LIMIT_PER_MINUTE=60
```

### Agent Configuration

**New Config Schema:**

```python
# ciris_engine/logic/adapters/a2a/config.py

from pydantic import BaseModel, Field

class A2AAdapterConfig(BaseModel):
    """A2A adapter configuration."""

    host: str = Field(default="0.0.0.0", description="Bind address")
    port: int = Field(default=8000, description="Port number")
    public_url: str = Field(..., description="Public-facing URL")
    agent_name: str = Field(..., description="Agent name")
    agent_description: str = Field(..., description="Agent description")

    # Task management
    max_concurrent_tasks: int = Field(default=10)
    task_timeout_seconds: int = Field(default=300)

    # Features
    enable_streaming: bool = Field(default=True)
    enable_push_notifications: bool = Field(default=True)

    # Security
    auth_required: bool = Field(default=True)
    service_token_enabled: bool = Field(default=True)
    rate_limit_enabled: bool = Field(default=True)
    rate_limit_per_minute: int = Field(default=60)

    def load_env_vars(self) -> None:
        """Load configuration from environment variables."""
        import os

        self.host = os.getenv("A2A_HOST", self.host)
        self.port = int(os.getenv("A2A_PORT", str(self.port)))
        self.public_url = os.getenv("A2A_PUBLIC_URL", self.public_url)
        self.agent_name = os.getenv("A2A_AGENT_NAME", self.agent_name)
        # ... etc
```

---

## Testing Strategy

### Unit Tests

```python
# tests/adapters/a2a/test_a2a_adapter.py

import pytest
from ciris_engine.logic.adapters.a2a import A2AAdapter

@pytest.mark.asyncio
async def test_a2a_adapter_initialization(mock_runtime):
    """Test A2A adapter initializes correctly."""
    adapter = A2AAdapter(runtime=mock_runtime)
    await adapter.start()

    assert adapter.server is not None
    assert adapter.task_manager is not None

    await adapter.stop()

@pytest.mark.asyncio
async def test_jsonrpc_message_send(a2a_client):
    """Test JSON-RPC message/send method."""
    response = await a2a_client.post("/a2a/jsonrpc", json={
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": "Hello, CIRIS!"
        },
        "id": "test-1"
    })

    assert response.status_code == 200
    data = response.json()
    assert data["jsonrpc"] == "2.0"
    assert "result" in data
    assert data["result"]["state"] == "pending"

@pytest.mark.asyncio
async def test_agent_card_generation(a2a_client):
    """Test Agent Card is generated correctly."""
    response = await a2a_client.get("/.well-known/agent-card.json")

    assert response.status_code == 200
    card = response.json()
    assert card["protocolVersion"] == "0.3.0"
    assert card["preferredTransport"] == "JSONRPC"
    assert len(card["skills"]) > 0
```

### Integration Tests

```python
# tests/integration/test_a2a_agentbeats.py

import pytest
from a2a_sdk import A2AClient  # AgentBeats SDK

@pytest.mark.integration
@pytest.mark.asyncio
async def test_agentbeats_integration():
    """Test full integration with AgentBeats SDK."""
    # Initialize A2A client
    client = A2AClient(agent_url="http://localhost:8000/a2a/jsonrpc")

    # Authenticate
    await client.authenticate(token="test-jwt-token")

    # Send message
    task = await client.send_message("What is 2+2?")
    assert task.state in ["pending", "running"]

    # Wait for completion
    result = await client.wait_for_completion(task.id, timeout=30)
    assert result.state == "completed"
    assert "4" in result.artifacts[0].content
```

### Performance Tests

```python
# tests/performance/test_a2a_load.py

import pytest
import asyncio

@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_task_handling():
    """Test handling multiple concurrent A2A tasks."""
    tasks = []
    for i in range(50):
        task = asyncio.create_task(
            send_a2a_message(f"Task {i}")
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks)

    # All tasks should complete
    assert len(results) == 50
    assert all(r.state in ["completed", "running"] for r in results)
```

---

## Deployment Guide

### Local Development

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables
export CIRIS_ADAPTER=a2a
export A2A_PUBLIC_URL=http://localhost:8000/a2a
export A2A_AGENT_NAME="CIRIS Datum (Dev)"

# 3. Start agent
python main.py --adapter a2a --port 8000 --debug

# 4. Test Agent Card
curl http://localhost:8000/.well-known/agent-card.json | jq

# 5. Test JSON-RPC
curl -X POST http://localhost:8000/a2a/jsonrpc \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "params": {"message": "Hello!"},
    "id": "1"
  }' | jq
```

### Production Deployment

```bash
# 1. Production configuration
export CIRIS_ADAPTER=a2a
export A2A_PUBLIC_URL=https://agents.ciris.ai/api/datum/a2a
export A2A_AGENT_NAME="CIRIS Datum"
export A2A_AGENT_DESCRIPTION="Ethical AI agent with WiseAuthority governance"
export A2A_MAX_CONCURRENT_TASKS=20
export A2A_ENABLE_STREAMING=true
export A2A_RATE_LIMIT_PER_MINUTE=100

# 2. Start with production settings
python main.py --adapter a2a --host 0.0.0.0 --port 8000

# 3. Configure reverse proxy (nginx)
# /etc/nginx/sites-available/ciris-a2a
server {
    listen 443 ssl;
    server_name agents.ciris.ai;

    location /api/datum/a2a/ {
        proxy_pass http://localhost:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# 4. Test from outside
curl https://agents.ciris.ai/api/datum/a2a/.well-known/agent-card.json
```

### AgentBeats Registration

```python
# agentbeats_register.py

import toml
from agentbeats import AgentRegistry

# Create agent card TOML
agent_card = {
    "name": "CIRIS Datum",
    "description": "Ethical AI agent with WiseAuthority governance",
    "agent_url": "https://agents.ciris.ai/api/datum/a2a/jsonrpc",
    "launcher_url": "https://agents.ciris.ai/api/datum/a2a/jsonrpc",
    "capabilities": ["reasoning", "ethics", "memory", "tools"],
    "protocols": ["A2A", "MCP"]
}

# Save agent card
with open("datum_agent.toml", "w") as f:
    toml.dump(agent_card, f)

# Register on AgentBeats
registry = AgentRegistry()
registry.register(
    agent_card_path="datum_agent.toml",
    auth_token="your-agentbeats-token"
)

print("Agent registered on AgentBeats!")
```

---

## Risk Assessment

### Technical Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| A2A spec changes | Medium | Medium | Monitor A2A GitHub, version pin |
| AgentBeats API changes | Low | High | Use official SDK, monitor releases |
| Performance issues | Medium | Medium | Load testing, optimization |
| Authentication complexity | Low | Medium | Use service tokens for eval |
| Task state sync errors | Medium | Medium | Comprehensive testing, audit logs |

### Security Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Unauthorized access | Low | High | Strong auth, rate limiting |
| Task injection | Low | High | Input validation, WA review |
| DDoS via tasks | Medium | Medium | Rate limiting, max concurrent tasks |
| Data leakage | Low | Critical | Audit all responses, privacy checks |

### Operational Risks

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| AgentBeats downtime | Medium | Low | Not critical, evaluation only |
| High eval costs | Medium | Medium | Mock LLM mode for testing |
| Poor leaderboard rank | High | Low | Iterative improvement, not production |

---

## Success Metrics

### Integration Success

- ✅ A2A adapter loads and runs
- ✅ Agent Card validates on AgentBeats
- ✅ Agent participates in at least 10 battles
- ✅ 80%+ test coverage for A2A code
- ✅ <100ms p95 latency for JSON-RPC calls
- ✅ Zero security incidents during evaluation

### Performance Targets

- **Throughput:** 50+ concurrent tasks
- **Latency:** <500ms for message/send
- **Availability:** 99%+ uptime during evaluation
- **Response quality:** Measured by AgentBeats scoring

### Learning Outcomes

- Understanding of multi-agent coordination
- Performance benchmarking vs other agents
- Identification of CIRIS strengths/weaknesses
- Community feedback and visibility

---

## Next Steps

### Immediate (Week 1)

1. ✅ Review this evaluation document with team
2. ⬜ Create GitHub issue for A2A adapter implementation
3. ⬜ Set up development branch: `feature/a2a-adapter`
4. ⬜ Create initial A2A adapter structure
5. ⬜ Implement Agent Card generation

### Short-term (Week 2-3)

1. ⬜ Implement JSON-RPC 2.0 server
2. ⬜ Implement task management
3. ⬜ Write comprehensive tests
4. ⬜ Local integration testing

### Medium-term (Week 4-5)

1. ⬜ Production deployment
2. ⬜ AgentBeats registration
3. ⬜ Participate in evaluation battles
4. ⬜ Iterate based on results

### Optional (Week 6+)

1. ⬜ MCP tool provider implementation
2. ⬜ Advanced A2A features (streaming, webhooks)
3. ⬜ Custom evaluation scenarios
4. ⬜ Leaderboard optimization

---

## References

### Specifications

- **A2A Protocol:** https://a2a-protocol.org/latest/specification/
- **MCP Protocol:** https://docs.anthropic.com/en/docs/agents-and-tools/mcp
- **JSON-RPC 2.0:** https://www.jsonrpc.org/specification

### SDKs

- **A2A Python SDK:** https://github.com/a2aproject/a2a-python
- **A2A JavaScript SDK:** https://github.com/a2aproject/a2a-js
- **AgentBeats SDK:** https://github.com/agentbeats/agentbeats

### CIRIS Documentation

- **Main Repository:** https://github.com/CIRISAI/CIRISAgent
- **CLAUDE.md:** /home/user/CIRISAgent/CLAUDE.md
- **Production API:** https://agents.ciris.ai/api/datum/v1/

---

## Appendix: Code Snippets

### A2A Adapter Entry Point

```python
# ciris_engine/logic/adapters/a2a/adapter.py

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import FastAPI
import uvicorn

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.enums import ServiceType

from .a2a_agent_server import create_a2a_app
from .a2a_communication import A2ACommunicationService
from .a2a_task_manager import A2ATaskManager
from .config import A2AAdapterConfig

logger = logging.getLogger(__name__)

class A2AAdapter(Service):
    """A2A protocol adapter for CIRIS agent."""

    config: A2AAdapterConfig

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize A2A adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime

        # Load configuration
        self.config = A2AAdapterConfig()
        self.config.load_env_vars()

        if "adapter_config" in kwargs:
            if isinstance(kwargs["adapter_config"], A2AAdapterConfig):
                self.config = kwargs["adapter_config"]
            elif isinstance(kwargs["adapter_config"], dict):
                self.config = A2AAdapterConfig(**kwargs["adapter_config"])

        # Create FastAPI app
        self.app: FastAPI = create_a2a_app(runtime, self.config)
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task[Any] | None = None

        # Task manager
        self.task_manager = A2ATaskManager(
            runtime=runtime,
            config=self.config
        )

        # Communication service
        self.communication = A2ACommunicationService(
            task_manager=self.task_manager,
            config=self.config
        )

        logger.info(f"A2A adapter initialized - {self.config.public_url}")

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter."""
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.communication,
                priority=Priority.NORMAL,
                capabilities=["send_message", "fetch_messages"]
            )
        ]

    async def start(self) -> None:
        """Start A2A adapter server."""
        logger.info(f"Starting A2A adapter on {self.config.host}:{self.config.port}")

        # Inject services into app
        self._inject_services()

        # Start uvicorn server
        config = uvicorn.Config(
            app=self.app,
            host=self.config.host,
            port=self.config.port,
            log_level="info"
        )
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._server.serve())

        logger.info(f"A2A adapter started - Agent Card: {self.config.public_url}/.well-known/agent-card.json")

    async def stop(self) -> None:
        """Stop A2A adapter server."""
        logger.info("Stopping A2A adapter...")

        if self._server:
            self._server.should_exit = True

        if self._server_task:
            await self._server_task

        logger.info("A2A adapter stopped")

    def _inject_services(self) -> None:
        """Inject runtime services into app state."""
        self.app.state.runtime = self.runtime
        self.app.state.task_manager = self.task_manager
        self.app.state.communication = self.communication

        # Inject core services
        if hasattr(self.runtime, "agent_processor"):
            self.app.state.agent_processor = self.runtime.agent_processor
        if hasattr(self.runtime, "service_registry"):
            self.app.state.service_registry = self.runtime.service_registry
```

### JSON-RPC Handler

```python
# ciris_engine/logic/adapters/a2a/routes/jsonrpc.py

from typing import Any, Dict
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel

from ..schemas.jsonrpc_models import (
    JSONRPCRequest,
    JSONRPCResponse,
    JSONRPCError
)
from ..a2a_task_manager import A2ATaskManager
from ..auth import verify_a2a_auth

router = APIRouter()

@router.post("/jsonrpc")
async def jsonrpc_handler(
    request: Request,
    jsonrpc_req: JSONRPCRequest,
    user: Dict[str, Any] = Depends(verify_a2a_auth)
):
    """Handle JSON-RPC 2.0 requests."""
    task_manager: A2ATaskManager = request.app.state.task_manager

    try:
        # Route to appropriate handler
        if jsonrpc_req.method == "message/send":
            result = await handle_message_send(task_manager, jsonrpc_req.params, user)
        elif jsonrpc_req.method == "tasks/get":
            result = await handle_tasks_get(task_manager, jsonrpc_req.params)
        elif jsonrpc_req.method == "tasks/list":
            result = await handle_tasks_list(task_manager, jsonrpc_req.params)
        elif jsonrpc_req.method == "tasks/cancel":
            result = await handle_tasks_cancel(task_manager, jsonrpc_req.params)
        else:
            raise ValueError(f"Unknown method: {jsonrpc_req.method}")

        return JSONRPCResponse(
            jsonrpc="2.0",
            result=result,
            id=jsonrpc_req.id
        )

    except Exception as e:
        return JSONRPCResponse(
            jsonrpc="2.0",
            error=JSONRPCError(
                code=-32603,
                message=str(e)
            ),
            id=jsonrpc_req.id
        )

async def handle_message_send(
    task_manager: A2ATaskManager,
    params: Dict[str, Any],
    user: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle message/send method."""
    message = params.get("message", "")

    # Create task
    task = await task_manager.create_task(
        message=message,
        user_id=user.get("user_id")
    )

    return task.model_dump()

async def handle_tasks_get(
    task_manager: A2ATaskManager,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    """Handle tasks/get method."""
    task_id = params.get("id")

    task = await task_manager.get_task(task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    return task.model_dump()
```

---

## Conclusion

CIRIS is **well-positioned** to integrate with AgentBeats through the **A2A protocol**. The existing adapter architecture, FastAPI infrastructure, and async processing make implementation straightforward.

**Recommended approach:**
1. **Primary:** Implement A2A adapter for agent-level evaluation
2. **Secondary:** Optionally add MCP tool provider for tool-level integration

**Timeline:** 4-5 weeks for full A2A implementation and AgentBeats registration.

**Expected benefits:**
- Standardized agent evaluation
- Performance benchmarking
- Community visibility
- Multi-agent coordination testing
- Identification of improvement areas

---

**Document prepared by:** Claude Code
**Date:** 2025-11-06
**Branch:** `claude/evaluate-agentbeats-additions-011CUsUaEy5yYpz5XXHLqb5r`
