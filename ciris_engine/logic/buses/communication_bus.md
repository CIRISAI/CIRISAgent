# CommunicationBus

## Overview

The CommunicationBus is a central message routing system in CIRIS that provides a unified interface for all communication operations across multiple adapter types. It abstracts communication complexities and enables seamless message flow between Discord, API, CLI, and other communication channels while maintaining strict type safety and reliability.

## Mission Alignment

The CommunicationBus directly supports Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing" by:

- **Enabling Universal Access**: Providing communication capabilities across multiple platforms (Discord, API, CLI) to ensure diverse beings can interact with CIRIS regardless of their preferred communication medium
- **Adaptive Channel Routing**: Intelligently routing messages to appropriate adapters based on channel prefixes, enabling seamless cross-platform communication
- **Sustainable Message Processing**: Implementing queue-based processing with proper error handling and metrics tracking to ensure reliable, long-term operation
- **Coherent Message Flow**: Standardizing message formats through typed schemas (`SendMessageRequest`, `FetchMessagesRequest`, `FetchedMessage`) to maintain consistent communication patterns

## Architecture

- **Service Type Handled**: `ServiceType.COMMUNICATION`
- **Message Types Supported**:
  - `SendMessageRequest`: Async message sending with channel routing
  - `FetchMessagesRequest`: Synchronous message retrieval (queue-processed but not recommended)
- **Key Capabilities**:
  - Multi-adapter communication routing
  - Priority-based default channel resolution
  - Synchronous and asynchronous message operations
  - Cross-platform channel identification via prefixes
  - Comprehensive metrics and telemetry

### Channel ID Format Standards

The bus uses prefixed channel IDs for intelligent routing:

- **Discord**: `discord_{channel_id}` or `discord_{guild_id}_{channel_id}`
- **API**: `api_{identifier}` or `ws:{websocket_id}`  
- **CLI**: `cli_{user}@{host}`

## Message Processing

### SendMessageRequest Handling

**Asynchronous Path** (`send_message`):
```python
# Queues message for background processing
message = SendMessageRequest(
    id=str(uuid.uuid4()),
    handler_name=handler_name,
    timestamp=time_service.now(),
    metadata=metadata or {},
    channel_id=channel_id,
    content=content,
)
success = await bus._enqueue(message)
```

**Synchronous Path** (`send_message_sync`):
```python
# Immediate processing with intelligent routing
service = None
if channel_id.startswith("discord_"):
    service = find_discord_service()
elif channel_id.startswith("api_") or channel_id.startswith("ws:"):
    service = find_api_service()
elif channel_id.startswith("cli_"):
    service = find_cli_service()

result = await service.send_message(channel_id, content)
```

### FetchMessagesRequest Handling

All message fetching is **synchronous only** as handlers require immediate results:

```python
async def fetch_messages(self, channel_id: str, limit: int, handler_name: str) -> List[FetchedMessage]:
    service = await self.get_service(handler_name, ["fetch_messages"])
    messages = await service.fetch_messages(channel_id, limit=limit)
    
    # Convert all message formats to standardized FetchedMessage objects
    return [FetchedMessage(**msg) if isinstance(msg, dict) else msg 
            for msg in messages]
```

### Error Handling Approach

- **Queue Overflow**: Messages dropped with error logging when queue exceeds 1000 items
- **Service Unavailable**: Graceful fallback with detailed error messages
- **Message Conversion**: Robust handling of different message object types with fallback conversion
- **Network Failures**: Proper exception catching with detailed error context
- **Missing Channels**: Default channel resolution from highest priority adapter

## Adapter Integration

### Default Channel Resolution

The bus implements priority-based channel resolution when no specific channel is provided:

```python
async def get_default_channel(self) -> Optional[str]:
    # Get all communication services sorted by priority
    all_services = self.service_registry.get_services_by_type(ServiceType.COMMUNICATION)
    
    # Sort by registry-defined priority (HIGHEST, HIGH, NORMAL, LOW, LOWEST)
    providers_with_priority = self._sort_by_priority(all_services)
    
    # Return home channel from highest priority adapter
    for _, service in providers_with_priority:
        if hasattr(service, "get_home_channel_id"):
            home_channel = service.get_home_channel_id()
            if home_channel:
                return home_channel
    return None
```

### Adapter Requirements

Communication adapters must implement `CommunicationServiceProtocol`:

```python
class YourCommunicationAdapter(CommunicationService):
    async def send_message(self, channel_id: str, content: str) -> bool:
        # Implement platform-specific message sending
        pass
    
    async def fetch_messages(self, channel_id: str, *, limit: int = 50, 
                           before: Optional[datetime] = None) -> List[FetchedMessage]:
        # Implement platform-specific message fetching
        pass
    
    def get_home_channel_id(self) -> Optional[str]:
        # Return formatted channel ID or None
        # Format: "{platform}_{identifier}"
        pass
```

### Integration Examples

**Discord Adapter Integration**:
```python
class DiscordAdapter(Service, CommunicationService, WiseAuthorityService):
    def get_home_channel_id(self) -> Optional[str]:
        if self.discord_config.home_channel_id:
            return f"discord_{self.discord_config.home_channel_id}"
        return None
```

**API Adapter Integration**:  
```python
class APICommunicationService(CommunicationService):
    def get_home_channel_id(self) -> Optional[str]:
        return f"api_{self.host}_{self.port}"
```

## Usage Examples

### Basic Message Sending

```python
# Async message sending (queued)
await communication_bus.send_message(
    channel_id="discord_123456789",
    content="Hello from CIRIS!",
    handler_name="agent_handler"
)

# Sync message sending (immediate)
success = await communication_bus.send_message_sync(
    channel_id="api_websocket_abc123",
    content="Status update",
    handler_name="system_handler"
)
```

### Cross-Platform Communication

```python
# Send to Discord channel
await bus.send_message_sync("discord_123456", "Discord message", "handler")

# Send to API WebSocket  
await bus.send_message_sync("ws:abc123", "API message", "handler")

# Send to CLI session
await bus.send_message_sync("cli_user@hostname", "CLI message", "handler")

# Send to default channel (highest priority adapter)
await bus.send_message_sync(None, "Broadcast message", "handler")
```

### Message Fetching

```python
# Fetch recent messages from Discord
messages = await communication_bus.fetch_messages(
    channel_id="discord_987654321",
    limit=20,
    handler_name="history_handler"
)

for message in messages:
    print(f"{message.author_name}: {message.content}")
```

### Integration with Handlers

```python
class AgentHandler:
    def __init__(self, communication_bus: CommunicationBus):
        self.comm_bus = communication_bus
    
    async def send_response(self, channel_id: str, response: str):
        # Always use sync for handler responses to ensure delivery
        success = await self.comm_bus.send_message_sync(
            channel_id=channel_id,
            content=response,
            handler_name=self.__class__.__name__
        )
        if not success:
            logger.error(f"Failed to send response to {channel_id}")
```

## Quality Assurance

### Type Safety Measures

- **Pydantic Schema Validation**: All messages use typed schemas (`SendMessageRequest`, `FetchedMessage`)
- **Protocol Enforcement**: Adapters must implement `CommunicationServiceProtocol`
- **Generic Type Safety**: `BaseBus[CommunicationService]` ensures type consistency
- **No Dict[str, Any]**: Complete elimination of untyped dictionaries per CIRIS philosophy

### Reliability Features

- **Queue Management**: 1000-item queue with overflow protection
- **Circuit Breaker Pattern**: Service registry provides health checking
- **Graceful Degradation**: Fallback routing when primary services unavailable
- **Comprehensive Logging**: Debug, warning, and error logging at all levels
- **Metrics Tracking**: Real-time metrics for messages sent, received, broadcasts, and errors

### Performance Considerations

- **Async Queue Processing**: Background message processing doesn't block handlers
- **Intelligent Routing**: Direct service lookup based on channel prefixes
- **Connection Pooling**: Leverages adapter-specific connection management
- **Memory Efficiency**: Bounded queues prevent memory exhaustion
- **Telemetry Integration**: Lightweight metrics collection with minimal overhead

### Metrics Available

```python
{
    "communication_messages_sent": 1250,
    "communication_messages_received": 890,
    "communication_broadcasts": 45,
    "communication_errors": 3,
    "communication_uptime_seconds": 86400.0,
    "communication_bus_connections": 3  # Active adapters
}
```

## Service Provider Requirements

Communication service providers must:

### 1. Implement Required Protocol Methods

```python
async def send_message(self, channel_id: str, content: str) -> bool
async def fetch_messages(self, channel_id: str, *, limit: int = 50, before: Optional[datetime] = None) -> List[FetchedMessage]
def get_home_channel_id(self) -> Optional[str]
```

### 2. Follow Channel ID Conventions

- Use consistent prefixing: `{platform}_{identifier}`
- Handle both prefixed and unprefixed IDs gracefully
- Document supported channel ID formats

### 3. Provide Proper Error Handling

```python
async def send_message(self, channel_id: str, content: str) -> bool:
    try:
        # Platform-specific sending logic
        return True
    except PlatformSpecificException as e:
        logger.error(f"Failed to send message: {e}")
        return False
```

### 4. Register with Service Registry

```python
# In adapter initialization
self.service_registry.register_service(
    service_type=ServiceType.COMMUNICATION,
    service=self,
    priority=Priority.HIGH,  # Set appropriate priority
    capabilities=["send_message", "fetch_messages"]
)
```

### 5. Support Home Channel Configuration

```python
def get_home_channel_id(self) -> Optional[str]:
    # Return configured home channel or None
    if self.config.home_channel:
        return f"{self.platform_prefix}_{self.config.home_channel}"
    return None
```

---

**Note**: The CommunicationBus is **NOT** one of the 22 core CIRIS services. It is a message bus that coordinates adapter-provided communication services, enabling the multi-adapter architecture that allows CIRIS to operate across Discord, API, CLI, and other communication platforms simultaneously.