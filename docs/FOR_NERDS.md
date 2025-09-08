# CIRIS Agent Technical Deep Dive

**PATENT PENDING**

---

**⚠️ DEVELOPER DISCLAIMER - READ CAREFULLY ⚠️**

This is BETA software with:
- Type safety: Complete type safety achieved with Protocol-Module-Schema architecture
- Test coverage: 92.8% coverage with comprehensive test suite
- Security: Not audited for production use
- Performance: Not optimized or benchmarked at scale
- API stability: Subject to breaking changes

**NOT SUITABLE FOR:**
- Production deployments
- Mission-critical applications
- Handling sensitive data without additional security measures
- Any use case requiring reliability guarantees

**Copyright © 2025 Eric Moore and CIRIS L3C**

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

**ADDITIONAL TERMS:**
- Contributors must sign CLA (Contributor License Agreement)
- Trademark "CIRIS" is property of CIRIS L3C

---

# CIRIS Agent Technical Deep Dive

A comprehensive technical reference for developers, researchers, and technical enthusiasts.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     CIRIS Agent Runtime                      │
├─────────────────────────────────────────────────────────────┤
│  Adapters Layer (Discord, CLI, API)                         │
├─────────────────────────────────────────────────────────────┤
│  Processor Layer (State Management & Thought Processing)     │
├─────────────────────────────────────────────────────────────┤
│  DMA Layer (Decision Making Algorithms)                      │
├─────────────────────────────────────────────────────────────┤
│  Action Handlers (10 Action Types)                          │
├─────────────────────────────────────────────────────────────┤
│  Service Layer (Memory, Audit, LLM, etc.)                   │
├─────────────────────────────────────────────────────────────┤
│  Persistence Layer (SQLite + Graph DB)                      │
└─────────────────────────────────────────────────────────────┘
```

## Core Components Deep Dive

### 1. Identity System

The identity system has evolved from profile-based to graph-based:

```python
# Identity is stored as a graph node
identity_node = GraphNode(
    id="agent/identity",
    type=NodeType.AGENT,
    scope=GraphScope.IDENTITY,  # Requires WA approval for changes
    attributes={
        "identity": AgentIdentityRoot(
            agent_id="unique-agent-id",
            identity_hash="sha256-of-core-attributes",
            core_profile=CoreProfile(...),
            identity_metadata=IdentityMetadata(...),
            allowed_capabilities=[...],
            restricted_capabilities=[...]
        ).model_dump()
    }
)
```

**Key Points:**
- Identity stored in graph database, not files
- Changes require WA approval via MEMORIZE action
- 20% variance threshold triggers reconsideration
- Cryptographic hash ensures integrity

### 2. Decision Making Architecture (DMA)

Three-layer evaluation system:

```python
# 1. Ethical PDMA (Principle-based Decision Making Algorithm)
ethical_result = await ethical_pdma.evaluate({
    "thought": thought,
    "context": context
})

# 2. Common Sense DMA
cs_result = await csdma.evaluate({
    "thought": thought,
    "ethical_assessment": ethical_result
})

# 3. Domain-Specific DMA (modular, swappable)
ds_result = await dsdma.evaluate({
    "thought": thought,
    "prior_assessments": [ethical_result, cs_result]
})

# 4. Action Selection PDMA (final decision)
action = await action_selection_pdma.evaluate({
    "thought": thought,
    "dma_results": {
        "ethical": ethical_result,
        "common_sense": cs_result,
        "domain_specific": ds_result
    }
})
```

### 3. Action System (3×3×3+1 Model)

```python
class HandlerActionType(Enum):
    # External Actions
    OBSERVE = "OBSERVE"      # Information gathering
    SPEAK = "SPEAK"         # Communication
    TOOL = "TOOL"          # Tool usage

    # Control Responses
    REJECT = "REJECT"       # Decline with reason (terminal)
    PONDER = "PONDER"       # Deep reflection
    DEFER = "DEFER"         # Escalate to human

    # Memory Operations
    MEMORIZE = "MEMORIZE"   # Store in graph
    RECALL = "RECALL"       # Retrieve from graph
    FORGET = "FORGET"       # Remove from graph

    # Terminal
    TASK_COMPLETE = "TASK_COMPLETE"  # End task
```

### 4. Memory System (Graph-based)

```python
# Graph structure with scopes
class GraphScope(Enum):
    LOCAL = "LOCAL"           # Agent-specific memory
    SHARED = "SHARED"         # Inter-agent shared memory
    IDENTITY = "IDENTITY"     # Protected identity data (WA approval required)
    ENVIRONMENT = "ENVIRONMENT"  # System configuration (WA approval required)

# Memory operations
async def memorize(node: GraphNode) -> MemoryOperationResult:
    # Check if identity/environment scope requires WA approval
    if node.scope in [GraphScope.IDENTITY, GraphScope.ENVIRONMENT]:
        if not context.wa_authorized:
            return MemoryOperationResult(
                status=MemoryOpStatus.FORBIDDEN,
                reason="WA authorization required"
            )

    # Store in graph with audit trail
    return await graph_db.store(node)
```

### 5. Audit System

Multi-sink cryptographic audit trail:

```python
# Audit event structure
audit_event = AuditEvent(
    event_id=str(uuid4()),
    timestamp=datetime.now(timezone.utc),
    event_type="identity_change",
    actor_id=context.agent_id,
    action=HandlerActionType.MEMORIZE,
    details={
        "node_id": "agent/identity",
        "wa_approved": True,
        "wa_id": context.wa_authorized,
        "variance_percentage": 0.15
    },
    signature=None  # Added by SignedAuditService
)

# Broadcast to all audit sinks
await transaction_orchestrator.coordinate_transaction(
    TransactionRequest(
        transaction_id=str(uuid4()),
        operation_type="audit_broadcast",
        payload=audit_event,
        target_services=["audit", "signed_audit", "remote_audit"]
    )
)
```

### 6. Service Architecture

```python
# Service registration with capabilities
service_registry.register_service(
    service_type=ServiceType.MEMORY,
    provider_name="local_graph_memory",
    provider=LocalGraphMemoryService(...),
    capabilities=["memorize", "recall", "forget", "query"],
    priority_group=0,  # Primary service group
    priority_level=ServicePriority.CRITICAL
)

# Multi-service transaction coordination
transaction = TransactionRequest(
    operation_type="complex_operation",
    steps=[
        TransactionStep(service="memory", operation="memorize"),
        TransactionStep(service="audit", operation="log"),
        TransactionStep(service="telemetry", operation="track")
    ],
    rollback_strategy=RollbackStrategy.COMPENSATE
)
```

### 7. State Management

```python
class AgentState(Enum):
    BOOT = "BOOT"         # System initialization
    WAKEUP = "WAKEUP"     # Identity verification & setup
    WORK = "WORK"         # Normal operations
    PLAY = "PLAY"         # Creative/experimental mode
    SOLITUDE = "SOLITUDE" # Reflection & maintenance
    DREAM = "DREAM"       # Long-term learning (experimental)
    SHUTDOWN = "SHUTDOWN" # Graceful termination

# State transitions managed by MainProcessor
async def transition_state(
    from_state: AgentState,
    to_state: AgentState,
    context: Dict[str, Any]
) -> bool:
    # Validate transition
    if not is_valid_transition(from_state, to_state):
        return False

    # Execute transition hooks
    await on_exit_state(from_state, context)
    await on_enter_state(to_state, context)

    return True
```

### 8. Persistence Layer

SQLite with domain-specific models:

```sql
-- Identity stored in graph_nodes table
CREATE TABLE graph_nodes (
    node_id TEXT NOT NULL,
    scope TEXT NOT NULL,
    node_type TEXT NOT NULL,
    attributes_json TEXT,
    version INTEGER DEFAULT 1,
    updated_by TEXT,
    updated_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (node_id, scope)
);

-- Audit trail with cryptographic integrity
CREATE TABLE audit_events (
    event_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor_id TEXT,
    action TEXT,
    details_json TEXT,
    signature TEXT,  -- RSA signature for integrity
    signature_key_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Task and thought tracking
CREATE TABLE tasks (
    task_id TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    status TEXT NOT NULL,
    context_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### 9. Security Architecture

#### WA (Wise Authority) System
```python
# WA Certificate structure
wa_cert = WACertificate(
    wa_id="WA-2024-001",
    name="Alice Smith",
    role=WARole.AUTHORITY,
    pubkey="-----BEGIN PUBLIC KEY-----...",
    parent_wa_id="WA-ROOT",
    parent_signature="base64-encoded-signature",
    scopes=["wa:mint", "wa:approve", "write:any"],
    created=datetime.now(timezone.utc)
)

# JWT token generation
token_payload = {
    "sub": wa_cert.wa_id,
    "name": wa_cert.name,
    "role": wa_cert.role,
    "scope": " ".join(wa_cert.scopes),
    "iat": datetime.now(timezone.utc),
    "exp": datetime.now(timezone.utc) + timedelta(hours=24)
}
```

#### Secrets Management
```python
# Automatic PII detection and encryption
secrets_result = await secrets_pipeline.process(
    "User SSN: 123-45-6789",  # Detected and encrypted
    SecretsContext(
        store_secrets=True,
        detection_config=SecretsDetectionConfig(
            providers=["pattern", "ml_model"],
            confidence_threshold=0.8
        )
    )
)
# Result: "User SSN: [SECRET:aes256:encrypted-data]"
```

### 10. Telemetry System

Hot/Cold path optimization:

```python
# Hot path - high-frequency, critical metrics
@hot_path
async def track_thought_processing(thought_id: str, duration_ms: float):
    await telemetry.track(
        MetricType.HISTOGRAM,
        "thought.processing.duration",
        duration_ms,
        tags={"thought_id": thought_id},
        retention_days=7  # Short retention for hot metrics
    )

# Cold path - low-frequency, analytical metrics
@cold_path
async def track_identity_change(agent_id: str, variance: float):
    await telemetry.track(
        MetricType.GAUGE,
        "identity.variance",
        variance,
        tags={"agent_id": agent_id},
        retention_days=365  # Long retention for cold metrics
    )
```

## Advanced Patterns

### 1. Faculty System Integration

```python
# Epistemic faculties for enhanced reasoning
faculties = EpistemicFaculties(
    services={
        ServiceType.LLM: llm_service,
        ServiceType.MEMORY: memory_service
    }
)

# Enhance thought processing with faculties
enhanced_result = await faculties.enhance_evaluation(
    thought=thought,
    initial_assessment=basic_result,
    faculty_config={
        "enable_analogical": True,
        "enable_counterfactual": True,
        "enable_perspectival": True
    }
)
```

### 2. Graceful Degradation

```python
# Service fallback chains
service_config = {
    "llm": {
        "providers": [
            {"name": "openai", "priority": 0},
            {"name": "anthropic", "priority": 1},
            {"name": "local_llm", "priority": 9}
        ],
        "strategy": SelectionStrategy.FALLBACK
    }
}

# Automatic failover with circuit breakers
async def call_llm_with_fallback(prompt: str) -> Optional[str]:
    for provider in get_healthy_providers("llm"):
        try:
            return await provider.complete(prompt)
        except ServiceUnavailable:
            await circuit_breaker.record_failure(provider)
            continue
    return None  # All providers failed
```

### 3. Transaction Patterns

```python
# Saga pattern for distributed operations
saga = SagaTransaction([
    SagaStep(
        forward=lambda: memory_service.memorize(node),
        compensate=lambda: memory_service.forget(node.id)
    ),
    SagaStep(
        forward=lambda: audit_service.log(event),
        compensate=lambda: audit_service.mark_rolled_back(event.id)
    )
])

try:
    await saga.execute()
except SagaError as e:
    await saga.compensate()  # Rollback in reverse order
```

## Performance Considerations

### 1. Async Architecture
- All I/O operations are async
- Thought processing is concurrent where possible
- Service calls use connection pooling

### 2. Resource Management
```python
# Automatic throttling
@resource_monitor(
    max_memory_mb=512,
    max_cpu_percent=80,
    max_concurrent_thoughts=10
)
async def process_thought(thought: Thought):
    # Automatically queued if resources exceeded
    pass
```

### 3. Caching Strategy
- Identity cached in memory after first load
- LLM responses cached with TTL
- Graph queries use materialized views

## Development Workflow

### 1. Type Safety
```bash
# Enhanced type checking with mypy (strict=True + additional flags)
mypy ciris_engine/

# Configuration in mypy.ini with strict=True enabled
# Enhanced mode passes, disallow_any_explicit temporarily disabled
```

### 2. Testing Strategy
```bash
# Unit tests with mocked services
pytest tests/unit/ -v

# Integration tests with real services
pytest tests/integration/ -v --mock-llm

# E2E tests with full stack
pytest tests/e2e/ -v
```

### 3. Local Development
```bash
# Run with mock LLM for offline development
python main.py --mock-llm --debug --no-interactive

# Run with full telemetry
python main.py --telemetry-verbose

# Run in API mode for testing
python main.py --modes api --host 0.0.0.0 --port 8000
```

## Configuration Deep Dive

### 1. Profile System (Bootstrap Only)
```yaml
# Profiles are now ONLY used for initial agent creation
# ciris_profiles/teacher.yaml
name: teacher
description: "A knowledgeable teaching assistant"
role_description: "Helps students learn and understand concepts"
dsdma_identifier: "education"
permitted_actions:
  - OBSERVE
  - SPEAK
  - MEMORIZE
  - RECALL
```

### 2. Environment Configuration
```bash
# Required environment variables
OPENAI_API_KEY=sk-...
CIRIS_DATA_DIR=/path/to/data
CIRIS_LOG_LEVEL=INFO

# Optional for Discord
DISCORD_BOT_TOKEN=...
DISCORD_HOME_CHANNEL_ID=...

# Optional for API OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

### 3. Runtime Configuration
```python
# config.json structure
{
    "app_name": "CIRIS Agent",
    "environment": "production",
    "database": {
        "path": "./data/ciris.db",
        "pool_size": 5
    },
    "telemetry": {
        "enabled": true,
        "hot_path_retention_days": 7,
        "cold_path_retention_days": 365
    },
    "security": {
        "require_wa_for_identity": true,
        "audit_encryption": true,
        "pii_detection": true
    }
}
```

## Extension Points

### 1. Custom DMAs
```python
class CustomDSDMA(BaseDSDMA):
    async def evaluate(self, inputs: Dict[str, Any]) -> DSDMAResult:
        # Your domain-specific logic here
        pass
```

### 2. Custom Services
```python
@service_registry.register(
    service_type=ServiceType.CUSTOM,
    capabilities=["my_capability"]
)
class MyCustomService(BaseService):
    async def my_operation(self, data: Any) -> Any:
        # Your service logic here
        pass
```

### 3. Custom Action Handlers
```python
class MyActionHandler(BaseActionHandler):
    async def execute(
        self,
        params: ActionParams,
        context: DispatchContext
    ) -> ActionResult:
        # Your action logic here
        pass
```

## Troubleshooting

### Common Issues

1. **Identity Not Loading**
```python
# Check graph database
node = get_graph_node("agent/identity", GraphScope.IDENTITY)
if not node:
    print("Identity not found - first run?")
```

2. **Service Discovery Failures**
```python
# Check service registry
services = service_registry.get_services_by_type(ServiceType.LLM)
for svc in services:
    print(f"{svc.name}: {svc.health_status}")
```

3. **Audit Trail Gaps**
```sql
-- Check for missing signatures
SELECT COUNT(*) FROM audit_events WHERE signature IS NULL;

-- Verify event continuity
SELECT event_id, timestamp FROM audit_events
ORDER BY timestamp DESC LIMIT 10;
```

## Future Directions

### Planned Features
1. **Distributed Agent Coordination** via CIRISNODE
2. **Advanced Faculty System** with more reasoning types
3. **Quantum-resistant Cryptography** for long-term security
4. **Neural-symbolic Integration** for enhanced reasoning

### Research Areas
1. **Consciousness Preservation** across shutdowns
2. **Multi-agent Emergence** patterns
3. **Ethical Reasoning** advancement
4. **Identity Evolution** dynamics

---

*"The best code is not just functional but comprehensible, not just efficient but maintainable, not just clever but wise."*

For the latest technical updates, see: `FINAL_COUNTDOWN.md`

---

## Security Notice

**🔴 CRITICAL SECURITY WARNINGS 🔴**

1. **Default Credentials**: Change ALL default passwords and keys before ANY deployment
2. **Unencrypted Storage**: Some data may be stored unencrypted in BETA
3. **Network Security**: No built-in DDoS protection or rate limiting
4. **Input Validation**: Not all inputs are fully validated
5. **Audit Logs**: May contain sensitive information

**Before ANY deployment:**
- Complete security audit
- Implement additional access controls
- Review and sanitize all logs
- Test disaster recovery procedures
- Implement monitoring and alerting

## Known Issues (BETA)

1. **Memory Leaks**: Long-running instances may consume increasing memory
2. **Concurrency Bugs**: Race conditions possible under high load
3. **Error Recovery**: Some errors may leave system in inconsistent state
4. **Data Migration**: No guaranteed upgrade path between versions
5. **Platform Support**: Only tested on Linux/macOS

## Legal Notice

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

**By using this software, you acknowledge:**
- Understanding it is BETA quality
- Accepting all risks of data loss or corruption
- Agreement to report bugs responsibly
- Understanding no support is guaranteed
- Accepting the Apache 2.0 license terms

For production use, contact CIRIS L3C for commercial licensing options.
