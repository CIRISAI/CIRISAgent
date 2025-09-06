# LLMBus

## Overview

The LLMBus is CIRIS's intelligent language model coordination system that provides responsible AI access through multiple LLM providers with built-in redundancy, failover, and ethical oversight. It serves as the central hub for all language model operations in the system, ensuring sustainable and efficient utilization of AI resources while maintaining strict type safety and domain-aware routing.

## Mission Alignment

The LLMBus directly contributes to **Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"** through:

- **Sustainable Resource Management**: Tracks environmental impact (carbon emissions, energy consumption) and financial costs of LLM operations
- **Adaptive Coherence**: Provides domain-aware routing to specialized models ensuring contextually appropriate responses
- **Diverse Provider Support**: Enables multiple LLM providers (OpenAI, Anthropic, local models) to coexist and serve different needs
- **Ethical Oversight**: Integrates with WiseBus for guidance on sensitive requests and maintains strict capability boundaries
- **Resilient Architecture**: Circuit breakers and failover mechanisms ensure reliable service for critical applications

## Architecture

### Service Type Handled
- **Primary Service**: `LLMService` implementing `LLMServiceProtocol`
- **Core Capability**: `CALL_LLM_STRUCTURED` for Pydantic-based structured output generation

### Provider Routing
The LLMBus supports multiple provider types:
- **OpenAI**: GPT models for general-purpose tasks
- **Anthropic**: Claude models for reasoning and analysis
- **Local Models**: Domain-specific models (medical, legal, scientific)
- **Mock Providers**: For testing and development

### Resource Tracking Capabilities
Every LLM operation tracks comprehensive resource usage:

```python
class ResourceUsage(BaseModel):
    tokens_used: int           # Total tokens consumed
    tokens_input: int          # Input tokens
    tokens_output: int         # Output tokens
    cost_cents: float          # Financial cost in USD cents
    carbon_grams: float        # CO2 emissions in grams
    energy_kwh: float          # Energy consumption in kWh
    model_used: Optional[str]  # Model identifier
```

### Domain-Based Routing
Advanced routing system that directs requests to appropriate specialized models:
- **Medical Domain**: Routes to medical LLMs (prohibited in main repo due to liability)
- **Legal Domain**: Routes to legal-trained models
- **Financial Domain**: Routes to finance-specialized models
- **General Domain**: Default routing for general-purpose queries

## LLM Operations

### Primary Operation: `call_llm_structured`

The core method for structured LLM generation:

```python
async def call_llm_structured(
    self,
    messages: List[MessageDict],
    response_model: Type[BaseModel],
    max_tokens: int = 1024,
    temperature: float = 0.0,
    handler_name: str = "default",
    domain: Optional[str] = None,  # Domain-aware routing
) -> Tuple[BaseModel, ResourceUsage]:
```

**Parameters:**
- `messages`: List of conversation messages with 'role' and 'content'
- `response_model`: Pydantic model defining expected output structure
- `max_tokens`: Maximum tokens to generate
- `temperature`: Sampling temperature (0.0 = deterministic)
- `handler_name`: Identifier for metrics and telemetry
- `domain`: Optional domain for specialized routing

**Returns:**
- Tuple of (parsed Pydantic model, comprehensive resource usage)

### Provider Selection Strategies

Four distribution strategies for load balancing:

1. **ROUND_ROBIN**: Cycles through available providers
2. **LATENCY_BASED**: Selects provider with lowest average response time
3. **RANDOM**: Random selection for even load distribution
4. **LEAST_LOADED**: Routes to provider with fewest active requests

### Cost Tracking and Resource Management

All operations include detailed cost analysis:
- **Token-based pricing** for different model tiers
- **Environmental impact calculation** based on compute requirements
- **Real-time cost monitoring** with budget controls
- **Resource usage telemetry** for optimization insights

## Provider Support

### OpenAI Integration
```python
# Example OpenAI service registration
service_registry.register_service(
    service_type=ServiceType.LLM,
    provider=openai_service,
    priority=Priority.NORMAL,
    metadata={
        "domain": "general",
        "model": "gpt-4",
        "provider": "openai"
    }
)
```

### Anthropic Integration
```python
# Example Anthropic service registration
service_registry.register_service(
    service_type=ServiceType.LLM,
    provider=claude_service,
    priority=Priority.HIGH,
    metadata={
        "domain": "reasoning",
        "model": "claude-3-sonnet",
        "provider": "anthropic"
    }
)
```

### Local Model Support
```python
# Example domain-specific local model
service_registry.register_service(
    service_type=ServiceType.LLM,
    provider=scientific_llm,
    priority=Priority.NORMAL,
    metadata={
        "domain": "scientific",
        "model": "llama3-science-70b",
        "provider": "local",
        "offline": True
    }
)
```

## Usage Examples

### Basic Structured Generation
```python
from pydantic import BaseModel
from typing import List

class AnalysisResult(BaseModel):
    summary: str
    key_points: List[str]
    confidence: float

# Make LLM call through bus
messages = [
    {"role": "system", "content": "You are a helpful analyst."},
    {"role": "user", "content": "Analyze this data: [dataset]"}
]

result, usage = await llm_bus.call_llm_structured(
    messages=messages,
    response_model=AnalysisResult,
    handler_name="data_analyzer",
    temperature=0.2
)

print(f"Analysis: {result.summary}")
print(f"Cost: {usage.cost_cents}¢")
print(f"Carbon impact: {usage.carbon_grams}g CO2")
```

### Domain-Aware Routing
```python
class LegalAdvice(BaseModel):
    recommendation: str
    legal_basis: List[str]
    risk_level: str

# Route to legal domain LLM
result, usage = await llm_bus.call_llm_structured(
    messages=[
        {"role": "user", "content": "Review this contract clause"}
    ],
    response_model=LegalAdvice,
    handler_name="legal_analyzer",
    domain="legal",  # Routes to legal-specialized LLM
    max_tokens=2048
)
```

### Handler Integration Pattern
```python
class ExampleHandler:
    def __init__(self, llm_bus: LLMBus):
        self.llm_bus = llm_bus
    
    async def process_request(self, user_input: str) -> ProcessingResult:
        messages = [
            {"role": "system", "content": "Process user requests"},
            {"role": "user", "content": user_input}
        ]
        
        # LLM call with automatic failover and resource tracking
        result, usage = await self.llm_bus.call_llm_structured(
            messages=messages,
            response_model=ProcessingResult,
            handler_name=self.__class__.__name__,
            temperature=0.0  # Deterministic for production
        )
        
        # Telemetry automatically recorded
        return result
```

## Quality Assurance

### Type Safety Measures
- **Complete Pydantic Integration**: All inputs/outputs use typed models
- **Zero Dict[str, Any]**: Strict type validation throughout
- **Protocol-Based Design**: Clear interface contracts for all providers
- **Capability Verification**: Runtime checking of provider capabilities

### Resource Tracking
- **Comprehensive Metrics**: Tokens, cost, environmental impact per request
- **Real-time Monitoring**: Live telemetry integration with TelemetryService
- **Budget Controls**: Cost-based circuit breakers and limits
- **Historical Analysis**: Long-term resource usage patterns

### Performance Considerations
- **Circuit Breaker Pattern**: Automatic failure isolation with configurable thresholds
- **Health Monitoring**: Continuous provider health assessment
- **Latency Optimization**: Response time tracking and provider selection
- **Concurrent Safety**: Thread-safe operation with asyncio integration

### Ethical Guidelines
- **Domain Isolation**: Prevents medical/clinical code in main repository
- **Resource Awareness**: Environmental impact tracking and optimization
- **Transparent Costs**: Full financial impact visibility
- **Provider Neutrality**: No vendor lock-in, multi-provider support

## Service Provider Requirements

LLM services must implement the `LLMServiceProtocol`:

```python
class LLMServiceProtocol(ServiceProtocol, Protocol):
    @abstractmethod
    async def call_llm_structured(
        self,
        messages: List[MessageDict],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Generate structured output with comprehensive resource tracking."""
        ...
```

### Required Capabilities
- **Structured Generation**: Must support Pydantic model-based output
- **Resource Reporting**: Accurate token, cost, and environmental metrics
- **Health Monitoring**: Implement `is_healthy()` method
- **Capability Declaration**: Advertise supported operations

### Provider Metadata
```python
{
    "domain": "general|medical|legal|financial|scientific",
    "model": "model-identifier",
    "provider": "openai|anthropic|local|mock",
    "offline": bool,  # For local/offline models
    "jurisdiction": "US|EU|...",  # For legal models
    "specialization": ["reasoning", "coding", "analysis"]
}
```

### Circuit Breaker Configuration
```python
circuit_breaker_config = {
    "failure_threshold": 5,      # Failures before opening circuit
    "recovery_timeout": 60.0,    # Seconds before retry attempt
    "success_threshold": 3,      # Successes needed to close circuit
    "timeout_duration": 30.0     # Request timeout in seconds
}
```

---

The LLMBus represents CIRIS's commitment to responsible AI deployment, providing powerful language model capabilities while maintaining strict ethical boundaries, environmental consciousness, and system reliability. Through its sophisticated routing, monitoring, and failover capabilities, it ensures that AI resources are used efficiently and sustainably in service of human flourishing.