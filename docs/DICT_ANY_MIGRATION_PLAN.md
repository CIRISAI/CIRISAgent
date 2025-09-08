# Dict[str, Any] Migration Plan - Using Existing Schemas

## Overview

All schemas already exist in `ciris_engine/schemas/`. The task is to UPDATE code to use these schemas instead of Dict[str, Any].

## Existing Schema Mappings

### 1. Adapter Patterns → Existing Schemas

#### Channel Lists
**Current**: `List[Dict[str, Any]]`
**Use**: `ciris_engine.schemas.adapters.cli.ChannelInfo`

#### Message Data
**Current**: `List[Dict[str, Any]]` (fetch_messages)
**Use**: `ciris_engine.schemas.adapters.cli.MessageData`

#### Tool Schemas
**Current**: `Dict[str, Any]` (tool parameter schemas)
**Use**: `ciris_engine.schemas.adapters.tools.ToolParameterSchema`

#### WebSocket Clients
**Current**: `Dict[str, Any]`
**Use**: Create typed client wrapper or use connection ID strings

### 2. DMA Patterns → Existing Schemas

#### Faculty Results
**Current**: `Dict[str, Any]`
**Use**: `ciris_engine.schemas.dma.faculty.FacultyResult`

#### Triaged Inputs
**Current**: `Dict[str, Any]`
**Use**: `ciris_engine.schemas.dma.core.EnhancedDMAInputs`

#### Context Data
**Current**: `Dict[str, Any]`
**Use**: `ciris_engine.schemas.dma.core.DMAInputData`

### 3. Configuration Patterns → Existing Schemas

#### Config Sections
**Current**: `Dict[str, Any]`
**Use**: `ciris_engine.schemas.config.agent.AgentConfig` (for agent sections)
**Use**: `ciris_engine.schemas.config.essential.EssentialConfig` (for core config)

#### CLI Overrides
**Current**: `Dict[str, Any]`
**Use**: Specific override schemas or `ConfigOverride` model

### 4. Context/Snapshot Patterns → Existing Schemas

#### System Snapshot
**Current**: `Dict[str, Any]` fields
**Use**: `ciris_engine.schemas.runtime.system_context.SystemContext`

#### Agent Identity
**Current**: `Dict[str, Any]`
**Use**: `ciris_engine.schemas.runtime.core.AgentIdentityRoot`

#### Service Health
**Current**: `Dict[str, Any]`
**Use**: `ciris_engine.schemas.api.runtime.ServiceHealthDetails`

### 5. Protocol Patterns → Existing Schemas

#### Communication Fetch
**Current**: `List[Dict[str, Any]]`
**Use**: `List[ciris_engine.schemas.adapters.cli.MessageData]`

#### Faculty Analysis
**Current**: `Dict[str, Any]`
**Use**: `ciris_engine.schemas.dma.faculty.FacultyResult`

## Migration Priority

### Phase 1: High Impact, Low Risk (Week 1)
1. **Protocol Definitions** (2 files)
   - `protocols/faculties.py` → Use FacultyResult
   - `protocols/services/governance/communication.py` → Use MessageData

2. **Base Interfaces** (2 files)
   - `adapters/base_adapter.py` → Use ChannelInfo
   - `adapters/base_observer.py` → Use correlation schemas

### Phase 2: Adapter Updates (Week 2)
1. **CLI Adapter** (3 occurrences)
   - Use MessageData for fetch_messages
   - Use ChannelInfo for get_channel_list
   - Type telemetry tags properly

2. **API Adapter** (4 occurrences)
   - Use proper request/response schemas
   - Type WebSocket client registry
   - Use RuntimeStatus schema

3. **Discord Adapter** (10 occurrences)
   - Use typed thread metadata
   - Create DiscordContext schemas
   - Type tool execution results

### Phase 3: DMA Updates (Week 3)
1. **Faculty Integration** (3 files)
   - Use FacultyResult consistently
   - Type faculty evaluations
   - Use EnhancedDMAInputs

2. **Action Selection** (3 files)
   - Type tool schemas properly
   - Use proper context types
   - Remove generic dicts

### Phase 4: Core Components (Week 4)
1. **Configuration** (5 occurrences)
   - Type CLI overrides
   - Use section-specific schemas
   - Type config metadata

2. **Context Management** (8 occurrences)
   - Use proper snapshot schemas
   - Type identity data
   - Type health status

### Phase 5: Special Cases (Week 5)
1. **TSDB Consolidation** (23 occurrences)
   - Evaluate if truly dynamic
   - Consider union types
   - Document exceptions

2. **Document Justified Exceptions**
   - External API responses
   - True dynamic compression
   - User-defined plugins

## Implementation Steps

### For Each File:
1. **Identify the pattern** - What is the Dict[str, Any] representing?
2. **Find the schema** - Locate existing schema in ciris_engine/schemas/
3. **Update imports** - Add schema import
4. **Replace type** - Change Dict[str, Any] to specific schema
5. **Update usage** - Ensure code uses schema fields properly
6. **Test** - Run type checker and tests

### Example Migration:

```python
# BEFORE
async def fetch_messages(self, channel_id: str) -> List[Dict[str, Any]]:
    messages = []
    # ... fetch logic
    messages.append({
        "id": msg_id,
        "content": content,
        "author": author
    })
    return messages

# AFTER
from ciris_engine.schemas.adapters.cli import MessageData

async def fetch_messages(self, channel_id: str) -> List[MessageData]:
    messages = []
    # ... fetch logic
    messages.append(MessageData(
        message_id=msg_id,
        content=content,
        author_id=author,
        author_name=author,
        timestamp=datetime.now(timezone.utc),
        channel_id=channel_id
    ))
    return messages
```

## Success Metrics

1. **Week 1**: Protocols fully typed (0 Dict[str, Any])
2. **Week 2**: Base adapters typed (reduce by 15)
3. **Week 3**: DMAs typed (reduce by 11)
4. **Week 4**: Core components typed (reduce by 13)
5. **Week 5**: Document remaining justified cases

**Target**: Reduce from 91 to <20 Dict[str, Any] with clear justification for remainder.

## Documentation Updates

After migration:
1. Update README.md to reflect actual state
2. Add "Type Safety" section documenting:
   - Core is 100% typed
   - Boundaries have justified exceptions
   - Migration is ongoing

## Validation

1. Run mypy enhanced mode (strict=True + additional flags) after each phase
2. Ensure all tests pass
3. Document any new schemas needed
4. Track reduction in Dict[str, Any] count
