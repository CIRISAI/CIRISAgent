# CIRIS LLM Service

**Category**: Runtime Services
**Location**: `ciris_engine/logic/services/runtime/llm_service.py` (Requires conversion to module)
**Protocol**: `ciris_engine/protocols/services/runtime/llm.py`
**Schemas**: `ciris_engine/schemas/services/llm.py`
**Version**: 1.0.0
**Status**: Production Ready

## 🎯 Mission Alignment: Supporting Meta-Goal M-1

**Meta-Goal M-1**: Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing

### How Multi-Provider LLM Abstraction Serves Meta-Goal M-1

The LLM Service implements a sophisticated multi-provider abstraction that directly serves Meta-Goal M-1 through several key mechanisms:

#### 1. **Sustainable Operation**
- **Offline Capability**: Mock LLM providers enable complete system function without external dependencies
- **Resource Efficiency**: Circuit breakers prevent cascading failures, maintaining system stability
- **Cost Management**: Comprehensive token and cost tracking across providers prevents resource exhaustion
- **Energy Awareness**: Carbon footprint tracking for environmental sustainability

#### 2. **Adaptive Coherence**
- **Provider Diversity**: Multiple LLM providers (OpenAI, local models, mock) prevent vendor lock-in
- **Failover Logic**: Automatic degradation from cloud → local → mock maintains service continuity
- **Domain-Aware Routing**: Specialized models for different domains (medical, legal, financial) enhance response quality
- **Dynamic Selection**: Latency-based and least-loaded distribution strategies optimize performance

#### 3. **Enabling Diverse Flourishing**
- **Accessibility**: 4GB RAM constraint ensures deployment in resource-limited environments
- **Offline-First**: Communities without reliable internet can still access AI assistance
- **Multi-Provider Support**: Prevents dependency on any single corporate AI provider
- **Cultural Sensitivity**: Domain routing enables culturally appropriate model selection

## 🏗️ Architecture Overview

### Core Components

```
LLM Service Architecture
├── LLMBus (Message Bus)
│   ├── Multi-Provider Routing
│   ├── Circuit Breaker Management
│   ├── Distribution Strategies
│   └── Domain-Aware Filtering
├── Provider Implementations
│   ├── OpenAICompatibleClient (Production)
│   ├── MockLLMService (Offline)
│   └── Future: Local Model Providers
└── Resource Management
    ├── Token Usage Tracking
    ├── Cost Calculation
    └── Carbon Footprint Estimation
```

### Service Hierarchy

1. **LLMBus**: Central coordinator managing multiple providers
2. **LLMService Protocol**: Standard interface all providers implement
3. **Provider Services**: Specific implementations (OpenAI, Mock, etc.)
4. **Circuit Breakers**: Per-provider failure management
5. **Telemetry Integration**: Resource usage and performance monitoring

## 🔧 Provider Implementation Details

### OpenAI Compatible Provider

**File**: `ciris_engine/logic/services/runtime/llm_service.py`

```python
class OpenAICompatibleClient(BaseService, LLMServiceProtocol):
    """Production LLM client with circuit breaker protection."""

    # Key Features:
    # - Instructor integration for structured output
    # - Circuit breaker protection (5 failures → open)
    # - Exponential backoff retry (max 3 attempts)
    # - Comprehensive cost tracking per model
    # - Resource usage telemetry
```

**Supported Models & Pricing**:
- **gpt-4o-mini**: $0.15/$0.60 per 1M tokens (input/output)
- **gpt-4o**: $2.50/$10.00 per 1M tokens
- **gpt-4-turbo**: $10.00/$30.00 per 1M tokens
- **gpt-3.5-turbo**: $0.50/$1.50 per 1M tokens
- **Llama models**: $0.10/$0.10 per 1M tokens (estimated)
- **Claude models**: $3.00/$15.00 per 1M tokens

### Mock LLM Provider

**File**: `ciris_adapters/mock_llm/service.py`

```python
class MockLLMService(BaseService, MockLLMServiceProtocol):
    """Offline-capable mock LLM for testing and deployment."""

    # Key Features:
    # - Deterministic response generation
    # - Instructor patching for structured output
    # - Realistic token usage simulation
    # - Zero external dependencies
    # - Full protocol compatibility
```

**Mock Capabilities**:
- Structured output generation for any Pydantic model
- Realistic token usage estimation (1.3 tokens/word)
- Simulated costs based on Together.ai Llama pricing
- Energy/carbon footprint estimates for awareness

## 🚦 Circuit Breaker Protection

### Configuration
```python
CircuitBreakerConfig(
    failure_threshold=5,      # Open after 5 consecutive failures
    recovery_timeout=10.0,    # Wait 10s before testing recovery
    success_threshold=2,      # Close after 2 successful calls
    timeout_duration=30.0     # 30s API timeout
)
```

### States & Behavior
- **CLOSED**: Normal operation, all calls pass through
- **OPEN**: All calls fail fast, no API requests made
- **HALF_OPEN**: Test recovery with limited calls

### Metrics Tracked
- Consecutive failures/successes
- Success rate over time
- Last failure/success timestamps
- Total call counts

## 📊 Resource Tracking & Telemetry

### Token Usage Metrics
```python
class TokenUsageStats(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
```

### Resource Usage Tracking
```python
class ResourceUsage(BaseModel):
    tokens_used: int           # Total tokens consumed
    tokens_input: int          # Input tokens
    tokens_output: int         # Output tokens
    cost_cents: float          # API cost in cents
    carbon_grams: float        # Estimated CO2 impact
    energy_kwh: float          # Estimated energy usage
    model_used: str            # Model identifier
```

### Telemetry Metrics (v1.4.3 Compliant)
- `llm_requests_total`: Total LLM API calls
- `llm_tokens_input/output/total`: Token usage counters
- `llm_cost_cents`: Cumulative cost tracking
- `llm_errors_total`: Error count for reliability monitoring
- `llm_uptime_seconds`: Service availability tracking

## 🌐 Multi-Provider Bus Architecture

### LLMBus Distribution Strategies

1. **LATENCY_BASED** (Default): Route to fastest provider
2. **ROUND_ROBIN**: Distribute load evenly across providers
3. **RANDOM**: Random selection for load balancing
4. **LEAST_LOADED**: Route to provider with fewest active requests

### Priority-Based Selection
```python
# Provider priority levels:
CRITICAL = 0    # Highest priority
HIGH = 1        # High priority
NORMAL = 2      # Default priority
LOW = 3         # Low priority
FALLBACK = 9    # Last resort
```

### Domain-Aware Routing
```python
# Example: Medical domain routing
await llm_bus.call_llm_structured(
    messages=medical_messages,
    response_model=DiagnosisSchema,
    domain="medical"  # Routes to medical-specialized models
)
```

**Domain Support**:
- `medical`: HIPAA-compliant, offline-required models
- `legal`: Legal reasoning specialized models
- `financial`: Financial analysis models
- `general`: Default, broad-capability models

## 🔌 Protocol Interface

### Core Protocol Method
```python
@abstractmethod
async def call_llm_structured(
    self,
    messages: List[MessageDict],      # Conversation history
    response_model: Type[BaseModel],  # Expected response schema
    max_tokens: int = 1024,           # Generation limit
    temperature: float = 0.0,         # Sampling randomness
) -> Tuple[BaseModel, ResourceUsage]:
    """Generate structured output with resource tracking."""
```

### Message Format
```python
class MessageDict(TypedDict):
    role: str      # "system" | "user" | "assistant"
    content: str   # Message content
```

## 🧪 Testing & Mock Integration

### Mock LLM Activation
```python
# Environment variable
MOCK_LLM=1 python main.py

# Command line flag
python main.py --mock-llm --adapter api
```

### Test Response Generation
The mock service generates contextually appropriate responses:
- Analyzes message content for keywords
- Matches response to expected schema structure
- Provides realistic token usage simulation
- Maintains conversation context

### Instructor Integration
```python
# Mock instructor.patch() override
instructor.patch = MockLLMClient._mock_instructor_patch

# Ensures compatibility with structured output patterns
response_model = create_response(
    response_model=MySchema,
    messages=conversation_history
)
```

## 🚧 Required Service Migration

### Current State: Single File
- **Location**: `ciris_engine/logic/services/runtime/llm_service.py`
- **Status**: Monolithic implementation

### Target State: Modular Directory

```
ciris_engine/logic/services/runtime/llm_service/
├── __init__.py              # Module entry point
├── openai_client.py         # OpenAI compatible implementation
├── circuit_breaker.py       # Circuit breaker logic
├── resource_tracker.py      # Usage and cost tracking
├── README.md               # Service documentation
└── tests/                  # Service-specific tests
    ├── test_openai_client.py
    ├── test_circuit_breaker.py
    └── test_resource_tracking.py
```

### Migration Benefits
1. **Separation of Concerns**: Each provider in separate file
2. **Enhanced Testability**: Isolated unit tests per component
3. **Future Extensibility**: Easy addition of new providers
4. **Maintenance**: Clearer code organization

## 📈 Performance Characteristics

### Latency Profiles
- **OpenAI GPT-4o-mini**: ~500-2000ms typical
- **OpenAI GPT-4o**: ~1000-4000ms typical
- **Local Models**: ~100-1000ms (hardware dependent)
- **Mock Service**: <10ms (instant response)

### Resource Consumption
- **Memory**: ~50-100MB per provider instance
- **CPU**: Minimal (I/O bound operations)
- **Network**: Varies by provider and token usage
- **Storage**: Circuit breaker state (~1KB per provider)

### Scalability Limits
- **Concurrent Requests**: Limited by provider API rate limits
- **Provider Count**: No architectural limit
- **Circuit Breakers**: One per provider, minimal overhead

## 🛡️ Reliability & Error Handling

### Error Classification
```python
# Retryable Errors
retryable_exceptions = (
    APIConnectionError,    # Network issues
    RateLimitError,       # Rate limit exceeded
    InternalServerError   # Server-side errors
)

# Non-Retryable Errors
non_retryable_exceptions = (
    APIStatusError,       # Authentication, invalid requests
)
```

### Retry Strategy
- **Exponential Backoff**: 1s, 2s, 4s delays
- **Maximum Attempts**: 3 retries per request
- **Circuit Breaker Integration**: Fast-fail when provider unhealthy

### Failover Sequence
1. Primary provider (highest priority)
2. Secondary provider (next priority level)
3. Fallback provider (mock/local)
4. Error propagation if all fail

## 🔧 Configuration Management

### OpenAI Configuration
```python
class OpenAIConfig(BaseModel):
    api_key: str = ""                    # Required for production
    model_name: str = "gpt-4o-mini"     # Default model
    base_url: Optional[str] = None       # Custom API endpoint
    instructor_mode: str = "JSON"        # Structured output mode
    max_retries: int = 3                 # Retry attempts
    timeout_seconds: int = 30            # Request timeout
```

### Environment Variables
- `OPENAI_API_KEY`: Primary OpenAI API key
- `MOCK_LLM`: Enable mock mode for offline operation
- `LLM_DEFAULT_MODEL`: Override default model selection

## 🌱 Future Enhancements

### Planned Provider Additions
1. **Anthropic Claude**: Direct API integration
2. **Local Llama**: Ollama/llama.cpp integration
3. **Hugging Face**: Transformers library integration
4. **Together.ai**: Hosted open model access

### Advanced Features
- **Model Caching**: Local response caching for efficiency
- **Streaming Responses**: Real-time token streaming
- **Function Calling**: Tool use integration
- **Multi-Modal**: Image/vision model support
- **Fine-Tuning**: Custom model training integration

### Operational Improvements
- **Health Monitoring**: Advanced provider health checks
- **Load Balancing**: Sophisticated request distribution
- **Rate Limiting**: Per-provider rate limit management
- **Metrics Dashboard**: Real-time performance visualization

## 🔍 Debugging & Troubleshooting

### Common Issues

#### Circuit Breaker Stuck Open
```python
# Check circuit breaker status
cb_stats = service.circuit_breaker.get_stats()
print(f"State: {cb_stats['state']}")

# Manual reset (testing only)
service.circuit_breaker.reset()
```

#### Mock LLM Not Working
```bash
# Verify environment
echo $MOCK_LLM

# Check initialization
docker logs container_name | grep "MockLLMService"
```

#### Provider Selection Issues
```python
# Debug LLM bus routing
stats = llm_bus.get_service_stats()
for service, metrics in stats.items():
    print(f"{service}: {metrics['circuit_breaker_state']}")
```

### Health Check Endpoints
```bash
# Check LLM service health
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/system/health

# LLM-specific metrics
curl -H "Authorization: Bearer $TOKEN" \
     http://localhost:8000/v1/telemetry/unified
```

## 📝 Integration Examples

### Basic Structured Call
```python
from ciris_engine.schemas.services.llm import LLMResponse

response, usage = await llm_service.call_llm_structured(
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
    response_model=LLMResponse,
    max_tokens=100,
    temperature=0.0
)

print(f"Response: {response.content}")
print(f"Cost: {usage.cost_cents:.4f} cents")
```

### Domain-Specific Routing
```python
# Medical domain (routes to HIPAA-compliant providers)
medical_response, usage = await llm_bus.call_llm_structured(
    messages=patient_messages,
    response_model=DiagnosisSchema,
    domain="medical",
    handler_name="diagnosis_handler"
)
```

### Custom Provider Registration
```python
# Register new provider
service_registry.register_service(
    service_type=ServiceType.LLM,
    service=CustomLLMProvider(),
    priority="HIGH",
    metadata={"domain": "legal", "offline": False}
)
```

## 🎓 Educational Resources

### Key Concepts to Understand
1. **Circuit Breaker Pattern**: Prevents cascade failures
2. **Instructor Library**: Structured output generation
3. **Provider Abstraction**: Uniform interface across LLM APIs
4. **Resource Tracking**: Cost and usage monitoring
5. **Domain Routing**: Specialized model selection

### Recommended Reading
- [Instructor Documentation](https://jxnl.github.io/instructor/)
- [Circuit Breaker Pattern](https://martinfowler.com/bliki/CircuitBreaker.html)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [Pydantic Model Validation](https://docs.pydantic.dev/)

## 🎯 Mission Challenge Resolution

**Question**: How does multi-provider LLM abstraction serve Meta-Goal M-1 and offline operation?

**Answer**: The CIRIS LLM Service architecture directly enables Meta-Goal M-1's vision of "sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing" through:

1. **Sustainable**: Circuit breakers prevent system exhaustion, cost tracking prevents resource depletion, and offline capabilities ensure operation in resource-constrained environments

2. **Adaptive**: Multi-provider support with automatic failover, domain-aware routing for specialized use cases, and dynamic provider selection based on performance

3. **Coherent**: Uniform protocol interface across all providers, consistent resource tracking, and standardized error handling patterns

4. **Enabling Diverse Flourishing**: 4GB RAM constraint for accessibility, offline-first design for underserved communities, and provider diversity preventing vendor lock-in

The service embodies CIRIS's commitment to bringing ethical AI to resource-limited environments while maintaining production-grade reliability and performance. By abstracting LLM complexity behind a clean protocol interface, it enables the broader system to focus on mission-critical functionality while ensuring sustainable, adaptive operation across diverse deployment scenarios.

---

**Next Steps**: Convert `llm_service.py` to modular directory structure following the architecture outlined above.
