# CIRIS Schema Architecture

This directory contains the organized, typed schema definitions that replace all `Dict[str, Any]` usage in CIRIS. Every data structure is now properly typed with Pydantic models.

## Schema Categories (24 directories)

### Core Schema Directories

#### 📋 [Actions](./actions/) - Action Parameters
- **parameters.py**: Typed parameters for all 10 action types

#### 🧮 [DMA](./dma/) - Decision Making Algorithms
- **core.py**: Base DMA schemas
- **decisions.py**: DMA evaluation results
- **faculty.py**: Faculty integration schemas
- **prompts.py**: DMA prompt templates
- **results.py**: Action selection results

#### 🎯 [Handlers](./handlers/) - Handler Operations
- **context.py**: Handler execution context
- **core.py**: Base handler schemas
- **memory_schemas.py**: Memory operation schemas
- **schemas.py**: Handler-specific schemas

#### 🏢 [Services](./services/) - Service Schemas
- **graph/**: Graph service schemas (memory, telemetry, audit, etc.)
- **authority/**: Wise Authority schemas
- **core/**: Core service schemas (runtime, secrets)
- **infrastructure/**: Infrastructure service schemas
- **lifecycle/**: Lifecycle service schemas
- **special/**: Special service schemas (self_observation)
- **graph_core.py**: Graph node and edge schemas
- **operations.py**: Service operation schemas

#### 🧠 [Processors](./processors/) - Cognitive Processing
- **cognitive.py**: Cognitive state definitions
- **state.py**: State transition schemas
- **main.py**: Main processor schemas
- **dma.py**: DMA processor integration

### Infrastructure Schema Directories

#### 🔌 [Adapters](./adapters/) - External Interfaces
- **cli.py**: CLI adapter schemas
- **discord.py**: Discord adapter schemas
- **registration.py**: Adapter registration schemas
- **tools.py**: Tool execution schemas

#### 🔐 [API](./api/) - API Request/Response
- **agent.py**: Agent endpoints
- **auth.py**: Authentication schemas
- **runtime.py**: Runtime control schemas
- **telemetry.py**: Telemetry endpoints
- **wa.py**: Wise Authority endpoints

#### 📊 [Telemetry](./telemetry/) - Monitoring
- **core.py**: Telemetry data schemas
- **collector.py**: Metric collection schemas

#### 🔒 [Secrets](./secrets/) - Security
- **core.py**: Secret management schemas
- **service.py**: Secrets service schemas

### Supporting Schema Directories

#### 🎭 [Conscience](./conscience/) - Ethical Reasoning
- **core.py**: Conscience evaluation schemas
- **results.py**: Ethical assessment results

#### ⚙️ [Config](./config/) - Configuration
- **agent.py**: Agent configuration schemas
- **essential.py**: Essential config schemas

#### 📝 [Audit](./audit/) - Audit Trail
- **core.py**: Audit entry schemas
- **verification.py**: Audit verification schemas

#### 🏗️ [Infrastructure](./infrastructure/) - System Infrastructure
- **identity_variance.py**: Identity monitoring schemas
- **behavioral_patterns.py**: Pattern analysis schemas
- **oauth.py**: OAuth authentication schemas

#### 💾 [Persistence](./persistence/) - Database
- **core.py**: Database operation schemas
- **tables.py**: Table definition schemas

#### 🚌 [Buses](./buses/) - Message Bus Schemas

#### 🌐 [Context](./context/) - Context Management

#### 📦 [Data](./data/) - Data Structures

#### 📋 [Formatters](./formatters/) - Output Formatting

#### 📚 [Registries](./registries/) - Service Registries

#### 🏃 [Runtime](./runtime/) - Runtime System
- **core.py**: Core runtime schemas
- **enums.py**: System enumerations
- **memory.py**: Memory operation schemas
- **system_context.py**: System context schemas

#### 🛠️ [Utils](./utils/) - Utilities
- **config_validator.py**: Configuration validation

#### 🔧 [tools.py](./tools.py) - Tool Schemas

## Key Schema Replacements

### Before (Dict[str, Any])
```python
# BAD - untyped
metadata: Dict[str, Any] = {
    "service": "memory",
    "method": "recall",
    "correlation_id": str(uuid4())
}
```

### After (Typed Schema)
```python
# GOOD - typed
from ciris_engine.schemas.services import ServiceMetadata

metadata = ServiceMetadata(
    service_name="memory",
    method_name="recall",
    correlation_id=uuid4()
)
```

## Schema Principles

1. **No Dict[str, Any]**: Every dict is now a typed Pydantic model
2. **Validation**: All inputs are validated at the boundary
3. **Serialization**: All schemas support JSON serialization
4. **Evolution**: Schemas support backward-compatible evolution
5. **Documentation**: Every field has a description

## Common Patterns

### Optional Fields
```python
class MySchema(BaseModel):
    required_field: str
    optional_field: Optional[str] = None
    with_default: str = "default_value"
```

### Nested Schemas
```python
class ParentSchema(BaseModel):
    child: ChildSchema
    children: List[ChildSchema]
```

### Discriminated Unions
```python
class ActionContext(BaseModel):
    action_type: HandlerActionType
    # Fields vary by action_type
```

## Migration Guide

To migrate from Dict[str, Any]:

1. Identify the dict usage
2. Find or create appropriate schema in the relevant directory
3. Replace dict creation with schema instantiation
4. Update type hints throughout call chain
5. Run mypy to verify

## Adding New Schemas

1. Determine correct category
2. Add schema to appropriate file
3. Update category's __init__.py
4. Add to this README
5. Write schema tests
