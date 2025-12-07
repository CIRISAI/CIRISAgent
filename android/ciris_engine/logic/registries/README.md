# Service Registry System

The registries module provides a sophisticated service discovery and fault tolerance system for the CIRIS agent architecture. It implements multi-tier priority management, configurable selection strategies (FALLBACK/ROUND_ROBIN), circuit breaker patterns, and comprehensive health monitoring to ensure robust service management across all system components.

## Service Selection Architecture

### Priority Groups & Selection Strategies
The service registry employs a two-tier priority system:

1. **Priority Groups** (0, 1, 2, etc.): Major priority tiers - lower numbers tried first
2. **Priority Levels** within groups: CRITICAL(0), HIGH(1), NORMAL(2), LOW(3), FALLBACK(9)
3. **Selection Strategies**: FALLBACK (first available) or ROUND_ROBIN (load balanced)

**Example Workflow:**
```
Priority Group 0: [OpenAI(CRITICAL), Anthropic(HIGH)] - FALLBACK strategy
Priority Group 1: [LocalLLM1(NORMAL), LocalLLM2(NORMAL)] - ROUND_ROBIN strategy
Priority Group 2: [MockLLM(FALLBACK)] - FALLBACK strategy
```

Selection tries Group 0 first (OpenAI → Anthropic), then Group 1 (round-robin between LocalLLMs), finally Group 2 (MockLLM).

## Architecture

### Core Components

#### Service Registry (`base.py`)
Central registry for all services with priority-based fallback support and comprehensive health monitoring.

#### Circuit Breaker (`circuit_breaker.py`)
Fault tolerance implementation that monitors service failures and temporarily disables failing services.

## Key Features

### Priority-Based Service Selection

#### **Priority Levels**
```python
class Priority(Enum):
    CRITICAL = 0    # Mission-critical services
    HIGH = 1        # High-priority services (Discord adapter)
    NORMAL = 2      # Standard services (CLI adapter)
    LOW = 3         # Background services
    FALLBACK = 9    # Last resort services
```

#### **Selection Strategies**
```python
class SelectionStrategy(Enum):
    FALLBACK = "fallback"      # First available in priority order - for redundancy
    ROUND_ROBIN = "round_robin"  # Rotate through providers - for load balancing
```

**Strategy Behaviors:**
- **FALLBACK**: Always tries services in the same priority order until one succeeds. Ideal for primary/backup configurations.
- **ROUND_ROBIN**: Cycles through available services to distribute load evenly. Perfect for load-balanced service pools.

### Service Provider Management

#### **Service Provider Structure**
```python
@dataclass
class ServiceProvider:
    name: str                           # Unique provider identifier
    priority: Priority                  # Service priority level
    instance: Any                       # Service instance
    capabilities: List[str]             # Service capabilities
    circuit_breaker: Optional[CircuitBreaker]  # Fault tolerance
    metadata: Optional[Dict[str, Any]]  # Additional metadata
    priority_group: int = 0             # Priority grouping
    strategy: SelectionStrategy         # Selection strategy
```

#### **Service Registration**
```python
class ServiceRegistry:
    def register(
        self,
        handler: str,                   # Handler that will use this service
        service_type: str,              # Service type (llm, memory, audit, etc.)
        provider: Any,                  # Service instance
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """Register a service provider for a specific handler"""
```

### Global vs Handler-Specific Services

#### **Handler-Specific Registration**
Services registered for specific handlers with targeted capabilities:
```python
# Register LLM service specifically for ActionSelectionPDMA
registry.register(
    handler="ActionSelectionPDMA",
    service_type="llm",
    provider=openai_client,
    priority=Priority.HIGH,
    capabilities=["structured_output", "function_calling"]
)
```

#### **Global Service Registration**
Services available to all handlers as fallbacks:
```python
# Register global LLM service for system-wide use
registry.register_service(
    service_type="llm",
    provider=fallback_llm,
    priority=Priority.NORMAL,
    capabilities=["basic_completion"]
)
```

### Circuit Breaker Implementation

#### **Circuit Breaker States**
```python
class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation, requests pass through
    OPEN = "open"           # Service disabled, requests fail fast
    HALF_OPEN = "half_open" # Testing recovery, limited requests allowed
```

#### **Fault Tolerance Configuration**
```python
@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5      # Failures before opening circuit
    recovery_timeout: float = 60.0  # Seconds before attempting recovery
    success_threshold: int = 3      # Successes needed to close circuit
    timeout_duration: float = 30.0  # Request timeout duration
```

#### **Automatic State Transitions**
```python
class CircuitBreaker:
    def record_failure(self) -> None:
        """Record failed operation and possibly open circuit"""
        self.failure_count += 1
        if self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()

    def record_success(self) -> None:
        """Record successful operation and possibly close circuit"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()
```

## Service Discovery & Health Monitoring

### Intelligent Service Resolution

#### **Multi-Tier Service Selection**
```python
async def get_service(
    self,
    handler: str,
    service_type: str,
    required_capabilities: Optional[List[str]] = None,
    fallback_to_global: bool = True
) -> Optional[Any]:
    """Get the best available service with fallback support"""

    # 1. Try handler-specific services first
    handler_providers = self._providers.get(handler, {}).get(service_type, [])
    service = await self._get_service_from_providers(
        handler_providers, required_capabilities
    )

    # 2. Fallback to global services if needed
    if service is None and fallback_to_global:
        global_providers = self._global_services.get(service_type, [])
        service = await self._get_service_from_providers(
            global_providers, required_capabilities
        )

    return service
```

#### **Health Check Integration**
```python
class HealthCheckProtocol(Protocol):
    async def is_healthy(self) -> bool:
        """Check if the service is healthy and ready to handle requests"""

async def _validate_provider(
    self,
    provider: ServiceProvider,
    required_capabilities: Optional[List[str]] = None,
) -> Optional[Any]:
    """Validate provider availability with health checking"""

    # 1. Check capability requirements
    if required_capabilities:
        if not all(cap in provider.capabilities for cap in required_capabilities):
            return None

    # 2. Check circuit breaker status
    if provider.circuit_breaker and not provider.circuit_breaker.is_available():
        return None

    # 3. Perform health check if supported
    if hasattr(provider.instance, "is_healthy"):
        if not await provider.instance.is_healthy():
            provider.circuit_breaker.record_failure()
            return None

    provider.circuit_breaker.record_success()
    return provider.instance
```

### Comprehensive Service Monitoring

#### **Priority Group Management**
```python
async def _get_service_from_providers(
    self,
    providers: List[ServiceProvider],
    required_capabilities: Optional[List[str]] = None
) -> Optional[Any]:
    """Get service with priority group and strategy support"""

    # Group providers by priority group
    grouped: Dict[int, List[ServiceProvider]] = {}
    for p in providers:
        grouped.setdefault(p.priority_group, []).append(p)

    # Process groups in priority order
    for group in sorted(grouped.keys()):
        group_providers = sorted(grouped[group], key=lambda x: x.priority.value)
        strategy = group_providers[0].strategy

        if strategy == SelectionStrategy.ROUND_ROBIN:
            # Rotate through providers for load balancing
            for provider in self._round_robin_selection(group_providers):
                service = await self._validate_provider(provider, required_capabilities)
                if service is not None:
                    return service
        else:  # FALLBACK strategy
            # Use first available provider
            for provider in group_providers:
                service = await self._validate_provider(provider, required_capabilities)
                if service is not None:
                    return service

    return None
```

#### **Service Registry Information**
```python
def get_provider_info(
    self,
    handler: Optional[str] = None,
    service_type: Optional[str] = None
) -> Dict[str, Any]:
    """Get comprehensive information about registered providers"""
    return {
        "handlers": {
            # Handler-specific service mappings
        },
        "global_services": {
            # Global service providers
        },
        "circuit_breaker_stats": {
            # Circuit breaker health metrics
        }
    }
```

## Integration Patterns

### Runtime Integration

#### **Service Registry Initialization**
```python
class CIRISRuntime:
    def __init__(self):
        self.service_registry = ServiceRegistry(
            required_services=["communication", "memory", "audit", "llm"]
        )

    async def start(self):
        # Register runtime-specific services
        await self._register_services()

        # Wait for all required services
        ready = await self.service_registry.wait_ready(timeout=30.0)
        if not ready:
            logger.error("Failed to start: missing required services")
            return False
```

#### **Adapter Service Registration**
```python
class DiscordRuntime:
    async def _register_services(self):
        # High-priority Discord services
        self.service_registry.register(
            handler="*",
            service_type="communication",
            provider=self.discord_adapter,
            priority=Priority.HIGH,
            capabilities=["async_messaging", "file_upload", "rich_embeds"]
        )

        self.service_registry.register(
            handler="*",
            service_type="observer",
            provider=self.discord_observer,
            priority=Priority.HIGH,
            capabilities=["message_filtering", "user_tracking"]
        )

class CLIRuntime:
    async def _register_services(self):
        # Normal priority CLI services as fallbacks
        self.service_registry.register(
            handler="*",
            service_type="communication",
            provider=self.cli_adapter,
            priority=Priority.NORMAL,
            capabilities=["text_input", "console_output"]
        )
```

### Handler Service Resolution

#### **Action Handler Integration**
```python
class BaseHandler:
    def __init__(self, dependencies: ActionHandlerDependencies):
        self.service_registry = dependencies.service_registry

    async def _get_communication_service(self):
        """Get communication service with capability requirements"""
        return await self.service_registry.get_service(
            handler=self.__class__.__name__,
            service_type="communication",
            required_capabilities=["async_messaging"]
        )

    async def _get_memory_service(self):
        """Get memory service for data persistence"""
        return await self.service_registry.get_service(
            handler=self.__class__.__name__,
            service_type="memory",
            required_capabilities=["graph_storage"]
        )
```

#### **DMA Service Usage**
```python
class ActionSelectionPDMA:
    async def run(self, context, dma_results):
        # Get specialized LLM service for action selection
        llm_service = await self.service_registry.get_service(
            handler="ActionSelectionPDMA",
            service_type="llm",
            required_capabilities=["structured_output", "function_calling"]
        )

        if not llm_service:
            logger.error("No suitable LLM service available for action selection")
            raise DMAFailure("LLM service unavailable")
```

## Error Handling & Resilience

### Comprehensive Fault Tolerance

#### **Circuit Breaker Error Handling**
```python
class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""

def check_and_raise(self) -> None:
    """Check availability and raise exception if service unavailable"""
    if not self.is_available():
        raise CircuitBreakerError(
            f"Circuit breaker '{self.name}' is {self.state.value}, service unavailable"
        )
```

#### **Graceful Degradation**
```python
async def get_service_with_fallback(self, handler: str, service_type: str):
    """Get service with comprehensive fallback strategy"""
    try:
        # 1. Try primary service
        service = await self.get_service(handler, service_type)
        if service:
            return service

        # 2. Try global fallback
        service = await self.get_service(handler, service_type, fallback_to_global=True)
        if service:
            return service

        # 3. Use mock service for testing/degraded mode
        if self.config.allow_mock_services:
            return self._get_mock_service(service_type)

        return None

    except CircuitBreakerError:
        logger.warning(f"Circuit breaker open for {service_type} service")
        return None
```

#### **Service Recovery Management**
```python
def reset_circuit_breakers(self) -> None:
    """Reset all circuit breakers to closed state"""
    for cb in self._circuit_breakers.values():
        cb.reset()
    logger.info("Reset all circuit breakers")

async def health_check_all(self) -> Dict[str, bool]:
    """Perform health checks on all registered services"""
    results = {}
    for handler, services in self._providers.items():
        for service_type, providers in services.items():
            for provider in providers:
                if hasattr(provider.instance, 'is_healthy'):
                    try:
                        healthy = await provider.instance.is_healthy()
                        results[f"{handler}.{service_type}.{provider.name}"] = healthy
                    except Exception as e:
                        logger.warning(f"Health check failed for {provider.name}: {e}")
                        results[f"{handler}.{service_type}.{provider.name}"] = False
    return results
```

## Usage Examples

### Basic Service Registration

```python
from ciris_engine.registries import ServiceRegistry, Priority

# Initialize registry
registry = ServiceRegistry()

# Register high-priority Discord communication service
discord_provider = registry.register(
    handler="SpeakHandler",
    service_type="communication",
    provider=discord_adapter,
    priority=Priority.HIGH,
    capabilities=["async_messaging", "rich_embeds", "file_upload"]
)

# Register fallback CLI communication service
cli_provider = registry.register(
    handler="SpeakHandler",
    service_type="communication",
    provider=cli_adapter,
    priority=Priority.NORMAL,
    capabilities=["text_output"]
)

# Get best available communication service
comm_service = await registry.get_service(
    handler="SpeakHandler",
    service_type="communication",
    required_capabilities=["async_messaging"]
)
```

### Advanced Service Configuration

```python
from ciris_engine.registries import CircuitBreakerConfig, SelectionStrategy

# Configure circuit breaker for sensitive services
sensitive_cb_config = CircuitBreakerConfig(
    failure_threshold=3,      # Open after 3 failures
    recovery_timeout=120.0,   # Wait 2 minutes before retry
    success_threshold=5,      # Need 5 successes to close
    timeout_duration=10.0     # 10 second request timeout
)

# Register LLM service with custom circuit breaker
registry.register(
    handler="ActionSelectionPDMA",
    service_type="llm",
    provider=openai_client,
    priority=Priority.HIGH,
    capabilities=["structured_output", "function_calling"],
    circuit_breaker_config=sensitive_cb_config,
    metadata={"model": "gpt-4", "max_tokens": 4000}
)

# Register load-balanced LLM pool
for i, llm in enumerate(llm_pool):
    registry.register(
        handler="EthicalPDMA",
        service_type="llm",
        provider=llm,
        priority=Priority.NORMAL,
        priority_group=1,  # Group for round-robin
        strategy=SelectionStrategy.ROUND_ROBIN,
        capabilities=["ethical_reasoning"]
    )
```

### Service Monitoring and Management

```python
# Get comprehensive service information
info = registry.get_provider_info()
print(f"Registered handlers: {list(info['handlers'].keys())}")
print(f"Global services: {list(info['global_services'].keys())}")

# Monitor circuit breaker health
for name, stats in info['circuit_breaker_stats'].items():
    if stats['state'] != 'closed':
        logger.warning(f"Circuit breaker {name} is {stats['state']}")

# Wait for required services during startup
ready = await registry.wait_ready(
    timeout=30.0,
    service_types=["communication", "memory", "llm", "audit"]
)

if not ready:
    logger.error("System startup failed: missing required services")
    return False

# Health check all services
health_results = await registry.health_check_all()
unhealthy = [name for name, healthy in health_results.items() if not healthy]
if unhealthy:
    logger.warning(f"Unhealthy services detected: {unhealthy}")
```

### Custom Service Implementation

```python
from ciris_engine.registries.base import HealthCheckProtocol

class CustomLLMService(HealthCheckProtocol):
    async def is_healthy(self) -> bool:
        """Custom health check implementation"""
        try:
            # Test basic functionality
            response = await self.simple_completion("test")
            return response is not None
        except Exception:
            return False

    async def generate_response(self, prompt: str) -> str:
        """Main service functionality"""
        # Implementation here
        pass

# Register custom service with health checking
custom_llm = CustomLLMService()
registry.register(
    handler="TestHandler",
    service_type="llm",
    provider=custom_llm,
    priority=Priority.NORMAL,
    capabilities=["custom_reasoning"]
)
```

## Performance & Monitoring

### Optimization Features

#### **Efficient Service Lookup**
- **Priority-based sorting**: Services sorted by priority for fast selection
- **Capability matching**: Early filtering based on required capabilities
- **Circuit breaker caching**: Avoid repeated health checks for failed services
- **Round-robin state**: Efficient load balancing across service pools

#### **Memory Management**
- **Weak references**: Prevent memory leaks from service registration
- **Lazy initialization**: Services created only when needed
- **Registry cleanup**: Clear services and circuit breakers on shutdown

### Monitoring Integration

#### **Circuit Breaker Statistics**
```python
def get_stats(self) -> dict:
    return {
        "name": self.name,
        "state": self.state.value,
        "failure_count": self.failure_count,
        "success_count": self.success_count,
        "last_failure_time": self.last_failure_time
    }
```

#### **Service Registry Metrics**
- **Provider counts**: Number of registered providers per service type
- **Health status**: Current health of all registered services
- **Circuit breaker states**: Real-time fault tolerance status
- **Service resolution latency**: Time taken for service discovery

## Runtime Service Management

### Service Priority Configuration
Services can be reconfigured at runtime through the API:

```bash
# Update service priority and strategy
curl -X PUT http://localhost:8080/v1/runtime/services/OpenAIProvider_123/priority \
  -H "Content-Type: application/json" \
  -d '{
    "priority": "CRITICAL",
    "priority_group": 0,
    "strategy": "FALLBACK"
  }'

# Get service health and configuration
curl http://localhost:8080/v1/runtime/services/health

# Reset circuit breakers for failed services
curl -X POST http://localhost:8080/v1/runtime/services/circuit-breakers/reset
```

### Service Selection Analytics
The registry provides detailed insights into service selection behavior:

```python
# Get comprehensive service analytics
analytics = await runtime_control.get_service_selection_explanation()

# Monitor service health in real-time
health = await runtime_control.get_service_health_status()
print(f"Overall health: {health['overall_health']}")
print(f"Services: {health['total_services']} total, {health['healthy_services']} healthy")
```

### Load Balancing Examples

**High-Availability LLM Configuration:**
```python
# Primary production service (Group 0)
registry.register(
    service_type="llm",
    provider=openai_primary,
    priority=Priority.CRITICAL,
    priority_group=0,
    strategy=SelectionStrategy.FALLBACK
)

# Load-balanced backup pool (Group 1)
for i, llm in enumerate(backup_llm_pool):
    registry.register(
        service_type="llm",
        provider=llm,
        priority=Priority.NORMAL,
        priority_group=1,
        strategy=SelectionStrategy.ROUND_ROBIN
    )

# Emergency fallback (Group 2)
registry.register(
    service_type="llm",
    provider=local_llm,
    priority=Priority.FALLBACK,
    priority_group=2,
    strategy=SelectionStrategy.FALLBACK
)
```

This configuration ensures:
1. Primary service gets all requests when healthy
2. Backup pool shares load when primary fails
3. Local LLM provides emergency coverage

---

The registries module provides robust service management capabilities that enable CIRIS to maintain high availability and fault tolerance through intelligent service discovery, priority-based selection strategies, automatic failover, and comprehensive health monitoring while supporting complex multi-runtime architectures with real-time configuration management.
