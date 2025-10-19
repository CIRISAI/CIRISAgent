# Registry Type Safety Migration Guide

## Overview

This document provides a complete migration path for converting all ServiceRegistry usage to use the new typed registries. The work is partially complete and this guide will help future developers (or Claude) finish the migration.

## Current Status

### ✅ Completed (Phases 1-3)

1. **Created Specialized Typed Registries** (`ciris_engine/logic/registries/typed_registries.py`)
   - `MemoryRegistry` - Type-safe memory service registry
   - `LLMRegistry` - Type-safe LLM service registry
   - `CommunicationRegistry` - Type-safe communication service registry
   - `ToolRegistry` - Type-safe tool service registry
   - `RuntimeControlRegistry` - Type-safe runtime control service registry
   - `WiseRegistry` - Type-safe wise authority service registry

2. **Comprehensive Test Coverage** (`tests/ciris_engine/logic/registries/test_typed_registries.py`)
   - 8 tests covering all 6 specialized registries
   - Tests verify type-safe registration and lookup
   - Tests verify capabilities filtering
   - Tests verify get_all() returns properly typed lists

### 🔄 Remaining Work (Phases 4-7)

The following phases still need to be completed:

## Phase 4: Update ServiceInitializer with Typed Registries

**File**: `ciris_engine/logic/runtime/service_initializer.py`

**Current Pattern** (lines 298-320):
```python
from ciris_engine.logic.registries.base import Priority, get_global_registry
from ciris_engine.schemas.runtime.enums import ServiceType

registry = get_global_registry()
registry.register_service(
    service_type=ServiceType.CONFIG,
    provider=self.config_service,
    priority=Priority.HIGH,
    capabilities=["get_config", "set_config", "list_configs"],
    metadata={"backend": "graph", "type": "essential"},
)
```

**New Pattern**:
```python
from ciris_engine.logic.registries import MemoryRegistry, LLMRegistry, WiseRegistry
from ciris_engine.logic.registries.base import Priority

class ServiceInitializer:
    def __init__(self, essential_config: Optional[EssentialConfig] = None):
        # Replace single registry with typed registries
        self.memory_registry = MemoryRegistry()
        self.llm_registry = LLMRegistry()
        self.communication_registry = CommunicationRegistry()
        self.tool_registry = ToolRegistry()
        self.runtime_control_registry = RuntimeControlRegistry()
        self.wise_registry = WiseRegistry()

    async def initialize_memory_service(self, config: Any) -> None:
        # ... create memory service ...

        # Register with type safety
        self.memory_registry.register(
            name="memory",
            provider=self.memory_service,
            priority=Priority.HIGH,
            capabilities=["memorize", "recall", "forget", ...]
        )
```

**Search and Replace Patterns**:
1. Find all `self.service_registry.register_service(service_type=ServiceType.MEMORY, ...)`
   Replace with `self.memory_registry.register(...)`

2. Find all `self.service_registry.register_service(service_type=ServiceType.LLM, ...)`
   Replace with `self.llm_registry.register(...)`

3. Find all `self.service_registry.register_service(service_type=ServiceType.WISE_AUTHORITY, ...)`
   Replace with `self.wise_registry.register(...)`

4. Find all `self.service_registry.register_service(service_type=ServiceType.TOOL, ...)`
   Replace with `self.tool_registry.register(...)`

**Files to Update**:
- `ciris_engine/logic/runtime/service_initializer.py` (main file)
- Any location that registers services during initialization

**Expected Outcome**:
- Zero `cast()` calls needed in ServiceInitializer
- All service registrations use typed registries
- Type safety enforced at compile time

## Phase 5: Update BusManager with Typed Registries

**File**: `ciris_engine/logic/buses/bus_manager.py`

**Current Pattern**:
```python
class BusManager:
    def __init__(self, service_registry: ServiceRegistry, ...):
        self.service_registry = service_registry
        self.memory = MemoryBus(service_registry, ...)
        self.llm = LLMBus(service_registry, ...)
```

**New Pattern**:
```python
class BusManager:
    def __init__(
        self,
        memory_registry: MemoryRegistry,
        llm_registry: LLMRegistry,
        communication_registry: CommunicationRegistry,
        tool_registry: ToolRegistry,
        runtime_control_registry: RuntimeControlRegistry,
        wise_registry: WiseRegistry,
        ...
    ):
        # Store typed registries
        self.memory_registry = memory_registry
        self.llm_registry = llm_registry
        self.communication_registry = communication_registry
        self.tool_registry = tool_registry
        self.runtime_control_registry = runtime_control_registry
        self.wise_registry = wise_registry

        # Create buses with typed registries
        self.memory = MemoryBus(memory_registry, ...)
        self.llm = LLMBus(llm_registry, ...)
        self.communication = CommunicationBus(communication_registry, ...)
        self.tool = ToolBus(tool_registry, ...)
        self.runtime_control = RuntimeControlBus(runtime_control_registry, ...)
        self.wise = WiseBus(wise_registry, ...)
```

**Files to Update**:
- `ciris_engine/logic/buses/bus_manager.py`
- `ciris_engine/logic/buses/memory_bus.py`
- `ciris_engine/logic/buses/llm_bus.py`
- `ciris_engine/logic/buses/communication_bus.py`
- `ciris_engine/logic/buses/tool_bus.py`
- `ciris_engine/logic/buses/runtime_control_bus.py`
- `ciris_engine/logic/buses/wise_bus.py`

**Bus Constructor Updates**:
Each bus needs to accept and use its specialized typed registry:

```python
# Before
class MemoryBus:
    def __init__(self, service_registry: ServiceRegistry, ...):
        self._registry = service_registry

# After
class MemoryBus:
    def __init__(self, memory_registry: MemoryRegistry, ...):
        self._registry = memory_registry
```

## Phase 6: Update All Service Registration Call Sites

**Locations to Update**:

1. **Adapter Registration** (Multiple adapters):
   ```bash
   grep -r "register_service.*COMMUNICATION" ciris_engine/logic/adapters/
   grep -r "register_service.*TOOL" ciris_engine/logic/adapters/
   grep -r "register_service.*RUNTIME_CONTROL" ciris_engine/logic/adapters/
   ```

2. **Module Loader** (`ciris_engine/logic/runtime/module_loader.py`):
   - Updates module registration to use typed registries
   - Needs access to all typed registries

3. **Runtime Helpers** (`ciris_engine/logic/runtime/ciris_runtime_helpers.py`):
   - Update any service lookups to use typed registries

**Pattern for Each Location**:
```python
# Before
await registry.get_service("handler", ServiceType.MEMORY, ["read"])

# After
await memory_registry.get("handler", ["read"])  # Returns Optional[MemoryServiceProtocol]
```

## Phase 7: Update Conscience Registry

**File**: `ciris_engine/logic/conscience/registry.py`

**Current Implementation**: Unknown (needs examination)

**Expected Pattern**:
Create a `ConscienceRegistry` that follows the same pattern as other typed registries.

```python
from ciris_engine.logic.registries import TypedServiceRegistry
from ciris_engine.protocols.conscience import ConscienceProtocol  # If exists

class ConscienceRegistry(TypedServiceRegistry):
    """Type-safe registry for conscience services."""

    _service_type = ServiceType.CONSCIENCE  # If exists

    def register(
        self,
        name: str,
        provider: "ConscienceProtocol",
        priority: Priority = Priority.NORMAL,
        ...
    ) -> str:
        return super().register(name, provider, priority, ...)

    async def get(
        self,
        handler: str = "default",
        required_capabilities: Optional[List[str]] = None
    ) -> Optional["ConscienceProtocol"]:
        result = await super().get(handler, required_capabilities)
        return result  # type: ignore[return-value]
```

## Phase 8: Run Full Test Suite and Mypy Validation

**Commands to Run**:

```bash
# 1. Run all registry tests
pytest tests/ciris_engine/logic/registries/ -v

# 2. Run bus tests
pytest tests/ciris_engine/logic/buses/ -v

# 3. Run service initializer tests
pytest tests/ciris_engine/logic/runtime/test_service_initializer.py -v

# 4. Run full test suite
pytest -n 16 tests/ --timeout=300

# 5. Check mypy on affected files
mypy ciris_engine/logic/registries/
mypy ciris_engine/logic/buses/
mypy ciris_engine/logic/runtime/service_initializer.py
mypy ciris_engine/logic/runtime/bus_manager.py

# 6. Check for remaining cast() usage
grep -r "cast.*ServiceProtocol\|cast.*Service" ciris_engine/ --include="*.py" | grep -v __pycache__
```

**Success Criteria**:
- ✅ Zero mypy errors in registry-related code
- ✅ Zero `cast()` calls for service lookups
- ✅ All tests passing
- ✅ Type hints properly inferred by IDE/language server

## Benefits After Migration

1. **Type Safety**: All service lookups return properly typed instances
2. **No Cast Required**: IDE auto-completion works correctly
3. **Compile-Time Checks**: Mypy catches type errors before runtime
4. **Clear Separation**: Each service type has its own registry
5. **Better Documentation**: Type hints serve as inline documentation

## Migration Checklist

Use this checklist to track progress:

- [x] Phase 1: Create specialized typed registries module
- [x] Phase 2: Create comprehensive typed registry tests
- [ ] Phase 3: Update ServiceInitializer with typed registries
  - [ ] Replace `service_registry` field with typed registries
  - [ ] Update `initialize_memory_service()` registration
  - [ ] Update `_initialize_llm_services()` registration
  - [ ] Update `initialize_security_services()` WA registration
  - [ ] Update `register_core_services()` tool registration
  - [ ] Remove all `cast()` calls in service_initializer.py
- [ ] Phase 4: Update BusManager with typed registries
  - [ ] Update constructor to accept typed registries
  - [ ] Update all bus constructors
  - [ ] Update bus registration methods
  - [ ] Remove all `cast()` calls in bus_manager.py
- [ ] Phase 5: Update all service registration call sites
  - [ ] Update API adapter registration
  - [ ] Update CLI adapter registration
  - [ ] Update Discord adapter registration
  - [ ] Update module loader registration
  - [ ] Update runtime helpers
- [ ] Phase 6: Update conscience registry
  - [ ] Examine current implementation
  - [ ] Create ConscienceRegistry if needed
  - [ ] Update all usage sites
- [ ] Phase 7: Run full test suite and mypy validation
  - [ ] All tests passing
  - [ ] Zero mypy errors
  - [ ] Zero cast() calls remaining
  - [ ] Documentation updated

## Key Architectural Decisions

### Why Specialized Registries Instead of Generic?

**Option 1: Single Generic Registry (Current)**
```python
registry = ServiceRegistry()
service = cast(MemoryServiceProtocol, await registry.get_service("handler", ServiceType.MEMORY))
```
- ❌ Requires cast() at every usage site
- ❌ No type safety at compile time
- ❌ IDE can't infer return types

**Option 2: Specialized Typed Registries (New)**
```python
memory_registry = MemoryRegistry()
service = await memory_registry.get("handler")  # Returns Optional[MemoryServiceProtocol]
```
- ✅ No cast() needed
- ✅ Type safety enforced by mypy
- ✅ IDE auto-completion works
- ✅ Clear separation of concerns

### Why Not Use Union Types?

Some might suggest:
```python
async def get(self, service_type: ServiceType) -> Union[MemoryServiceProtocol, LLMServiceProtocol, ...]:
```

This doesn't work because:
- Can't narrow type based on runtime value (service_type)
- Would require `cast()` at usage sites anyway
- Defeats the purpose of type safety

### Why TYPE_CHECKING and Forward References?

To avoid circular imports:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol

class MemoryRegistry:
    async def get(self) -> Optional["MemoryServiceProtocol"]:  # Forward reference
        ...
```

This pattern:
- ✅ Avoids circular imports at runtime
- ✅ Provides full type checking at development time
- ✅ Mypy understands forward references

## Common Pitfalls to Avoid

1. **Don't Keep Both Patterns**
   ```python
   # ❌ Bad - mixing patterns
   self.service_registry = get_global_registry()  # Old
   self.memory_registry = MemoryRegistry()  # New
   ```
   Choose ONE approach and stick with it.

2. **Don't Forget Bus Updates**
   Buses ALSO need to accept typed registries, not just ServiceInitializer.

3. **Don't Skip Tests**
   Every changed file needs test coverage to verify type safety.

4. **Don't Ignore Mypy Warnings**
   If mypy complains, fix the types - don't add `# type: ignore`

## Questions and Answers

**Q: Do we still need ServiceRegistry at all?**
A: Yes, it's the base class for TypedServiceRegistry. The generic registry is still used internally, we just add type-safe wrappers.

**Q: What about backwards compatibility?**
A: This is an internal API change. External users (SDK) are not affected. Internal code needs to be updated systematically.

**Q: Should we delete get_global_registry()?**
A: Not immediately. It might be used in places we haven't updated yet. Mark it deprecated first, then remove after full migration.

**Q: How do we handle edge cases like dynamic service types?**
A: Those rare cases can still use the base `ServiceRegistry` with explicit type annotations. The typed registries are for the 99% common case.

## Estimated Effort

Based on grep results:
- ~90 files use ServiceRegistry
- ~15-20 hours for complete migration
- Can be done incrementally (bus by bus, service by service)

## Incremental Migration Strategy

You can migrate one bus at a time:

1. **Week 1**: MemoryBus + MemoryRegistry
2. **Week 2**: LLMBus + LLMRegistry
3. **Week 3**: CommunicationBus + CommunicationRegistry
4. **Week 4**: ToolBus + ToolRegistry
5. **Week 5**: RuntimeControlBus + RuntimeControlRegistry
6. **Week 6**: WiseBus + WiseRegistry
7. **Week 7**: Final cleanup, remove old patterns

Each week includes:
- Update bus to use typed registry
- Update all call sites for that bus
- Update tests
- Run mypy + full test suite

## Example Pull Request Structure

For each phase, create a focused PR:

**PR 1: "refactor: Add typed registries infrastructure"**
- Add typed_registries.py
- Add comprehensive tests
- No behavior changes

**PR 2: "refactor: Migrate MemoryBus to MemoryRegistry"**
- Update MemoryBus to use MemoryRegistry
- Update all memory service registration sites
- Remove cast() calls for memory services
- Update tests

**PR 3: "refactor: Migrate LLMBus to LLMRegistry"**
- Update LLMBus to use LLMRegistry
- Update all LLM service registration sites
- Remove cast() calls for LLM services
- Update tests

... and so on for each bus.

## Contact and Support

For questions about this migration:
1. Check this document first
2. Review the test file for examples
3. Ask in #engineering channel
4. Tag @claude-code for AI assistance

## References

- **Typed Registries Implementation**: `ciris_engine/logic/registries/typed_registries.py`
- **Test Examples**: `tests/ciris_engine/logic/registries/test_typed_registries.py`
- **Base Registry**: `ciris_engine/logic/registries/base.py`
- **Service Protocols**: `ciris_engine/protocols/services/`
