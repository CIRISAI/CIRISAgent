# Context Management

The context module provides comprehensive situational awareness to the CIRIS agent through sophisticated context aggregation and system state monitoring. It integrates data from multiple sources to create rich, actionable context for informed decision-making across all agent operations.

## Architecture

### Core Component

#### Context Builder (`builder.py`)
Central orchestrator that aggregates information from multiple services to build comprehensive context.

## Key Features

### Multi-Source Context Aggregation

#### Data Sources Integration
- **Memory Service**: Agent identity and graph memory data
- **Secrets Service**: Secret references and security state
- **Telemetry Service**: System metrics and performance data
- **GraphQL Provider**: User profile enrichment from external sources
- **Persistence Layer**: Task and thought history
- **Configuration**: Environment and application settings

```python
class ContextBuilder:
    def __init__(
        self,
        memory_service: Optional[LocalGraphMemoryService] = None,
        graphql_provider: Optional[GraphQLContextProvider] = None,
        app_config: Optional[Any] = None,
        telemetry_service: Optional[Any] = None,
        secrets_service: Optional[SecretsService] = None,
    ):
        # Multi-service integration for comprehensive context
```

### Comprehensive System Snapshot

#### System State Monitoring
```python
class SystemSnapshot(BaseModel):
    # Current processing state
    current_task_details: Optional[TaskSummary]
    current_thought_summary: Optional[ThoughtSummary]

    # Task management
    top_pending_tasks_summary: List[TaskSummary]
    recently_completed_tasks_summary: List[TaskSummary]

    # User and community context
    user_profiles: Optional[Dict[str, UserProfile]]
    channel_id: Optional[str]

    # Security integration
    detected_secrets: List[SecretReference]
    secrets_filter_version: int
    total_secrets_stored: int

    # Performance monitoring
    telemetry: Optional[CompactTelemetry]
    resources: Optional[ResourceSnapshot]
    resource_actions_taken: Dict[str, int]

    # System health
    system_counts: Dict[str, int]  # Tasks, thoughts, pending items
```

#### Real-Time State Aggregation
- **Current Processing**: Active tasks and thoughts
- **Historical Context**: Recently completed and pending tasks
- **Security State**: Detected secrets and filter status
- **Performance Metrics**: Resource usage and system health
- **Community Health**: User interaction and engagement data

### Service Integration Patterns

#### Memory Service Integration
```python
# Identity context from graph memory
identity_context_str = self.memory_service.export_identity_context()

# Channel context resolution
channel_node = GraphNode(
    id=f"channel:{channel_id}",
    type=NodeType.CHANNEL,
    scope=GraphScope.LOCAL
)
channel_result = await self.memory_service.recall(channel_node)
```

#### Secrets Service Integration
```python
async def _build_secrets_snapshot(self) -> Dict[str, Any]:
    # Get recent secrets for context (limited to 10 for performance)
    all_secrets = await self.secrets_service.store.list_all_secrets()
    recent_secrets = sorted(all_secrets, key=lambda s: s.created_at, reverse=True)[:10]

    # Convert to context-safe references
    detected_secrets = [
        SecretReference(
            uuid=secret.secret_uuid,
            description=secret.description,
            context_hint=secret.context_hint,
            sensitivity=secret.sensitivity_level,
            auto_decapsulate_actions=secret.auto_decapsulate_for_actions,
            created_at=secret.created_at,
            last_accessed=secret.last_accessed
        )
        for secret in recent_secrets
    ]
```

#### Telemetry Integration
```python
# System metrics enrichment
if self.telemetry_service:
    await self.telemetry_service.update_system_snapshot(snapshot)

class CompactTelemetry(BaseModel):
    thoughts_active: int = 0
    thoughts_24h: int = 0
    avg_latency_ms: int = 0
    uptime_hours: float = 0
    resources: ResourceMetrics = Field(default_factory=ResourceMetrics)
    guardrail_hits: int = 0
    deferrals_24h: int = 0
    errors_24h: int = 0
    messages_processed_24h: int = 0
```

## Context Building Process

### Primary Context Building

#### Thought Context Construction
```python
async def build_thought_context(
    self,
    thought: Thought,
    task: Optional[Task] = None
) -> ThoughtContext:
    """Main entry point for comprehensive context building"""

    # 1. Build comprehensive system snapshot
    system_snapshot = await self.build_system_snapshot(task, thought)

    # 2. Extract user profiles from snapshot or GraphQL
    user_profiles = system_snapshot.user_profiles or {}

    # 3. Aggregate task history from recent completions
    task_history = system_snapshot.recently_completed_tasks_summary or []

    # 4. Get agent identity from memory service
    identity_context = None
    if self.memory_service:
        identity_context = self.memory_service.export_identity_context()

    # 5. Preserve initial task context
    initial_task_context = getattr(task, 'context', None) if task else None

    return ThoughtContext(
        system_snapshot=system_snapshot,
        user_profiles=user_profiles,
        task_history=task_history,
        identity_context=identity_context,
        initial_task_context=initial_task_context
    )
```

#### System Snapshot Orchestration
```python
async def build_system_snapshot(
    self,
    task: Optional[Task],
    thought: Any
) -> SystemSnapshot:
    """Comprehensive system state aggregation"""

    # Current state
    current_task_details = TaskSummary(**task.model_dump()) if task else None
    current_thought_summary = ThoughtSummary(**thought.model_dump()) if thought else None

    # System metrics from persistence
    all_tasks = persistence.get_all_tasks()
    all_thoughts = persistence.get_all_thoughts()
    system_counts = {
        "total_tasks": len(all_tasks),
        "total_thoughts": len(all_thoughts),
        "pending_tasks": len([t for t in all_tasks if t.status == TaskStatus.PENDING])
    }

    # Task management
    recent_completed = persistence.get_recent_completed_tasks(10)
    pending_tasks = persistence.get_pending_tasks(5)

    # Multi-source channel resolution
    channel_id = self._resolve_channel_id(task, thought)

    # Secrets integration
    secrets_data = await self._build_secrets_snapshot()

    # User profiles via GraphQL enrichment
    user_profiles = await self._build_user_profiles(task, thought)

    return SystemSnapshot(
        current_task_details=current_task_details,
        current_thought_summary=current_thought_summary,
        system_counts=system_counts,
        top_pending_tasks_summary=pending_tasks,
        recently_completed_tasks_summary=recent_completed,
        user_profiles=user_profiles,
        channel_id=channel_id,
        **secrets_data
    )
```

### User Profile Enrichment

#### GraphQL Integration Pattern
```python
class GraphQLContextProvider:
    async def enrich_context(self, task, thought) -> Dict[str, Any]:
        # Extract author names from task/thought context
        authors: set[str] = set()
        if task and hasattr(task, 'context'):
            if author_name := getattr(task.context, 'author_name', None):
                authors.add(author_name)

        # Query external GraphQL endpoint for user data
        if self.enable_remote_graphql and self.client and authors:
            try:
                query = """
                query GetUserProfiles($names: [String!]!) {
                    users(filter: {name: {in: $names}}) {
                        name
                        displayName
                        avatarUrl
                        bio
                        location
                    }
                }
                """
                result = await self.client.query(query, {"names": list(authors)})

                # Convert to UserProfile objects
                for user_data in result.get("data", {}).get("users", []):
                    profiles[user_data["name"]] = UserProfile(**user_data)

            except Exception as e:
                logger.error(f"GraphQL enrichment failed: {e}")

        # Fallback to memory service for missing users
        missing = authors - set(profiles.keys())
        if self.memory_service and missing:
            memory_results = await asyncio.gather(
                *(self.memory_service.recall(
                    GraphNode(id=name, type=NodeType.USER, scope=GraphScope.LOCAL)
                ) for name in missing),
                return_exceptions=True
            )
```

## Integration Patterns

### Thought Processor Integration

#### Context-Driven Processing
```python
class ThoughtProcessor:
    async def process_thought(
        self,
        thought_item: ProcessingQueueItem,
        platform_context: Optional[Dict[str, Any]] = None,
        benchmark_mode: bool = False
    ) -> Optional[ActionSelectionResult]:
        # Fetch the full Thought object
        thought = await self._fetch_thought(thought_item.thought_id)

        # Build comprehensive context - key integration point
        context = await self.context_builder.build_thought_context(thought)

        # Store context for DMA executor
        if hasattr(context, "model_dump"):
            thought_item.initial_context = context.model_dump()
        else:
            thought_item.initial_context = context

        # Context-aware DMA execution
        dma_results = await self.dma_orchestrator.run_dmas(
            thought_item, context, dsdma_context
        )
```

### Multi-Source Channel Resolution

#### Robust Channel Context
```python
def _resolve_channel_id(self, task: Optional[Task], thought: Any) -> Optional[str]:
    """Multi-source channel ID resolution with fallbacks"""
    channel_id = None

    # Priority 1: Task context
    if task and task.context:
        channel_id = getattr(task.context, 'channel_id', None)

    # Priority 2: Thought context
    if not channel_id and thought.context:
        channel_id = getattr(thought.context, 'channel_id', None)

    # Priority 3: Environment variable
    if not channel_id:
        channel_id = get_env_var("DISCORD_CHANNEL_ID")

    # Priority 4: Application configuration
    if not channel_id and self.app_config:
        channel_id = getattr(self.app_config, 'discord_channel_id', None)

    return channel_id
```

## Performance and Scalability

### Efficient Data Access

#### Optimization Strategies
- **Database Connection Pooling**: Uses `get_db_connection()` for efficient access
- **Parallel Operations**: GraphQL user lookups use `asyncio.gather()`
- **Memory Service Caching**: Cached identity context export
- **Lazy Service Loading**: Optional services only called when available
- **Limited Data Sets**: Recent tasks limited to 10 items for performance

#### Memory Management
```python
# Compact telemetry designed for <4KB footprint
class CompactTelemetry(BaseModel):
    # Essential metrics only
    thoughts_active: int = 0
    thoughts_24h: int = 0
    avg_latency_ms: int = 0
    uptime_hours: float = 0

    # Resource monitoring (minimal footprint)
    resources: ResourceMetrics = Field(default_factory=ResourceMetrics)

    # Key operational metrics
    guardrail_hits: int = 0
    deferrals_24h: int = 0
    errors_24h: int = 0
    messages_processed_24h: int = 0
```

### Error Handling and Resilience

#### Comprehensive Error Management
```python
async def _build_secrets_snapshot(self) -> Dict[str, Any]:
    """Build secrets context with robust error handling"""
    try:
        if not self.secrets_service:
            return self._empty_secrets_snapshot()

        # Get secrets information for the snapshot
        all_secrets = await self.secrets_service.store.list_all_secrets()

        # Process and limit data
        recent_secrets = sorted(all_secrets, key=lambda s: s.created_at, reverse=True)[:10]

        return {
            "detected_secrets": [SecretReference(...) for secret in recent_secrets],
            "secrets_filter_version": filter_version,
            "total_secrets_stored": len(all_secrets)
        }

    except Exception as e:
        logger.error(f"Error building secrets snapshot: {e}")
        return self._empty_secrets_snapshot()

def _empty_secrets_snapshot(self) -> Dict[str, Any]:
    """Fallback empty secrets snapshot"""
    return {
        "detected_secrets": [],
        "secrets_filter_version": 0,
        "total_secrets_stored": 0
    }
```

## Usage Examples

### Basic Context Building
```python
from ciris_engine.context import ContextBuilder

# Initialize with available services
context_builder = ContextBuilder(
    memory_service=memory_service,
    graphql_provider=graphql_provider,
    telemetry_service=telemetry_service,
    secrets_service=secrets_service
)

# Build comprehensive context
context = await context_builder.build_thought_context(thought, task)

# Access rich context data
system_state = context.system_snapshot
user_info = context.user_profiles
agent_identity = context.identity_context
task_history = context.task_history
```

### System Snapshot Access
```python
# Rich system state information
snapshot = context.system_snapshot

# Current processing state
current_task = snapshot.current_task_details
current_thought = snapshot.current_thought_summary

# Task management
pending_tasks = snapshot.top_pending_tasks_summary
recent_completions = snapshot.recently_completed_tasks_summary

# Security context
detected_secrets = snapshot.detected_secrets
secrets_filter_version = snapshot.secrets_filter_version

# Performance metrics
if snapshot.telemetry:
    active_thoughts = snapshot.telemetry.thoughts_active
    avg_latency = snapshot.telemetry.avg_latency_ms
    system_health = snapshot.telemetry.errors_24h
```

### User Profile Integration
```python
# Access enriched user profiles
for user_id, profile in context.user_profiles.items():
    display_name = profile.displayName
    avatar_url = profile.avatarUrl
    user_bio = profile.bio
    location = profile.location
```

## Testing and Validation

### Comprehensive Test Coverage
- **Unit Tests**: Individual component functionality
- **Integration Tests**: Multi-service context building
- **Performance Tests**: Context building latency and memory usage
- **Error Condition Tests**: Service unavailability and fallback behavior
- **Data Consistency Tests**: Context accuracy across multiple builds

---

The context module provides comprehensive situational awareness enabling informed decision-making across all CIRIS agent operations while maintaining high performance, reliability, and security through robust error handling and efficient data access patterns.
