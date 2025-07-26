# CIRIS Architecture Pattern: Intent-Driven Hybrid

## Core Principle

CIRIS uses an **Intent-Driven Hybrid Architecture** that separates:
- **Intent State** (what should exist) - Managed stateully
- **Operational State** (what does exist) - Queried statelessly

## The Three Layers

### 1. Intent Layer (Stateful)
**Purpose**: Define and persist what SHOULD exist

**Components**:
- Agent Registry (`agent_registry.py`)
- Port Manager (`port_manager.py`)
- Template definitions
- Configuration files

**Responsibilities**:
- Store agent definitions
- Allocate resources (ports)
- Define desired state
- Persist business logic

**Implementation**:
```python
# Example: Creating an agent (Intent)
agent_info = AgentInfo(
    agent_id="scout-a3b7c9",
    name="Scout",
    template="scout",
    port=8081
)
registry.register(agent_info)  # Persisted intent
```

### 2. Execution Layer (Docker)
**Purpose**: Execute the intent

**Components**:
- Docker containers
- docker-compose files
- Restart policies
- Container runtime

**Responsibilities**:
- Run containers
- Manage lifecycle
- Handle restarts
- Enforce resource limits

**Implementation**:
```yaml
# docker-compose.yml (Execution)
services:
  scout-a3b7c9:
    container_name: ciris-scout-a3b7c9
    restart: unless-stopped
    ports:
      - "8081:8080"
```

### 3. Operational Layer (Stateless)
**Purpose**: Observe and report current state

**Components**:
- DockerDiscovery (`docker_discovery.py`)
- Routing (`core/routing.py`)
- Health checks
- Metrics collection

**Responsibilities**:
- Query running containers
- Generate nginx routes
- Report health status
- Provide real-time state

**Implementation**:
```python
# Example: Querying current state (Operational)
discovery = DockerDiscovery()
running_agents = discovery.discover_agents()  # Real-time query
```

## Key Design Decisions

### 1. Stateful Intent, Stateless Operations
- **Intent** (agent should exist) → Stateful storage
- **Status** (agent is running) → Docker query

### 2. Docker as Execution Engine, Not Database
- Docker executes intent, doesn't store it
- Labels for runtime metadata only
- Configuration stays in files/registry

### 3. Clear Separation of Concerns
- Registry doesn't track container status
- Discovery doesn't make decisions
- Manager orchestrates between layers

## Anti-Patterns to Avoid

### ❌ Storing Intent in Docker Labels
```python
# BAD: Using Docker as a database
container.labels['desired_state'] = 'running'
container.labels['config'] = json.dumps(config)
```

### ❌ Tracking Operational State in Files
```python
# BAD: Files tracking runtime state
registry['container_status'] = 'running'  # Will drift!
```

### ❌ Mixing Layers
```python
# BAD: Discovery making decisions
if not container.running:
    container.start()  # Discovery should only observe!
```

## Benefits of This Architecture

1. **No State Drift**: Intent and operation clearly separated
2. **Resilience**: Can rebuild operational state from intent
3. **Scalability**: Stateless queries scale horizontally
4. **Debuggability**: Clear source of truth for each concern
5. **Flexibility**: Can change execution without changing intent

## Implementation Guidelines

### For New Features
1. Identify if it's Intent or Operational
2. Intent → Add to registry/stateful layer
3. Operational → Query Docker directly
4. Never mix the two

### For Existing Code
1. Refactor mixed concerns
2. Move intent out of Docker labels
3. Move runtime state out of files
4. Use appropriate layer for each operation

## Example: Auto-Healing Implementation

```python
class AutoHealer:
    def __init__(self, registry, docker_client):
        self.registry = registry  # Intent
        self.docker = docker_client  # Execution
        
    def heal(self):
        # Get intent
        desired_agents = self.registry.list_agents()
        
        # Get reality
        running = DockerDiscovery().discover_agents()
        running_ids = {a['agent_id'] for a in running}
        
        # Reconcile
        for agent in desired_agents:
            if agent.agent_id not in running_ids:
                self._start_agent(agent)  # Execute intent
```

## Migration Path

### Phase 1: Current State (✅ Complete)
- Hybrid implementation working
- Clear separation emerging

### Phase 2: Formalize Pattern (📍 We are here)
- Document architecture
- Align team understanding
- Fix inconsistencies

### Phase 3: Full Implementation
- Refactor remaining mixed concerns
- Implement missing operational queries
- Complete stateless routing layer

### Phase 4: Optimization
- Performance tuning
- Caching strategies
- Monitoring integration

## Conclusion

The Intent-Driven Hybrid Architecture is not a compromise—it's the correct pattern for systems that manage stateful resources with dynamic operations. By clearly separating intent from operation, we get the benefits of both approaches without their weaknesses.