# WebSocket Streaming Integration Guide

This guide explains how to integrate the WebSocket streaming endpoints with the CIRIS API adapter.

## Overview

The WebSocket streaming endpoints provide real-time data streams for:
- Messages (`/v1/stream/messages`) - Agent message flow
- Telemetry (`/v1/stream/telemetry`) - System metrics
- Reasoning (`/v1/stream/reasoning`) - Agent thought process
- Logs (`/v1/stream/logs`) - System logs (admin only)
- All (`/v1/stream/all`) - Multiplexed stream

## Integration Points

### 1. Message Streaming

When the agent processes messages, broadcast them to connected clients:

```python
from ciris_engine.api.routes.stream import broadcast_message, MessageStreamData

# In your message handler
async def handle_incoming_message(msg: IncomingMessage):
    # Broadcast incoming message
    await broadcast_message(MessageStreamData(
        message_id=msg.message_id,
        channel_id=msg.channel_id,
        author_id=msg.author_id,
        content=msg.content,
        direction="incoming"
    ))

    # Process message...

    # When agent responds
    await broadcast_message(MessageStreamData(
        message_id=response_id,
        channel_id=msg.channel_id,
        author_id="agent",
        content=response_content,
        direction="outgoing"
    ))
```

### 2. Telemetry Streaming

When metrics are updated, broadcast to telemetry subscribers:

```python
from ciris_engine.api.routes.stream import broadcast_telemetry, TelemetryStreamData

# In your telemetry emitter
async def emit_metric(name: str, value: float, tags: dict):
    await broadcast_telemetry(TelemetryStreamData(
        metric_name=name,
        value=value,
        tags=tags
    ))
```

### 3. Reasoning Streaming

When the agent thinks, broadcast reasoning traces:

```python
from ciris_engine.api.routes.stream import broadcast_reasoning, ReasoningStreamData

# In your handler/processor
async def process_thought(thought: str, handler: str, depth: int):
    await broadcast_reasoning(ReasoningStreamData(
        reasoning_id=f"reason_{uuid.uuid4()}",
        step="processing",
        thought=thought,
        depth=depth,
        handler=handler
    ))
```

### 4. Log Streaming

For system logs (admin only):

```python
from ciris_engine.api.routes.stream import broadcast_log, LogStreamData

# In your logger
async def log_event(level: str, message: str, context: dict):
    await broadcast_log(LogStreamData(
        level=level,
        logger_name=__name__,
        message=message,
        context=context
    ))
```

## Client Examples

### JavaScript/TypeScript Client

```typescript
// Connect to message stream
const ws = new WebSocket('ws://localhost:8000/v1/stream/messages?token=YOUR_API_KEY');

ws.onopen = () => {
    console.log('Connected to message stream');
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);

    switch(msg.type) {
        case 'auth':
            console.log('Authenticated:', msg.data);
            break;
        case 'message':
            console.log('New message:', msg.data);
            break;
        case 'heartbeat':
            // Keep connection alive
            break;
    }
};

// Multiplexed stream with subscription
const multiWs = new WebSocket('ws://localhost:8000/v1/stream/all?token=YOUR_API_KEY');

multiWs.onopen = () => {
    // Subscribe to multiple streams
    multiWs.send(JSON.stringify({
        type: 'subscribe',
        streams: ['message', 'telemetry', 'reasoning']
    }));
};
```

### Python Client

```python
import asyncio
import websockets
import json

async def message_stream():
    uri = "ws://localhost:8000/v1/stream/messages?token=YOUR_API_KEY"

    async with websockets.connect(uri) as websocket:
        # Receive auth confirmation
        auth_msg = await websocket.recv()
        print(f"Auth: {auth_msg}")

        # Listen for messages
        async for message in websocket:
            data = json.loads(message)
            if data['type'] == 'message':
                print(f"Message: {data['data']}")

# Run client
asyncio.run(message_stream())
```

## Authentication

All WebSocket endpoints require authentication via API key:
- Pass token as query parameter: `?token=YOUR_API_KEY`
- Invalid/missing tokens result in immediate disconnect with code 1008

## Permissions

- **OBSERVER**: Can access messages, telemetry, reasoning streams
- **ADMIN**: Can also access log stream
- **AUTHORITY**: Same as ADMIN for streaming purposes
- **ROOT**: Full access to all streams

## Rate Limiting

- Maximum 10 concurrent WebSocket connections per user
- Connections idle for >5 minutes may be closed
- Heartbeat messages sent every 30 seconds

## Error Handling

WebSocket close codes:
- 1000: Normal closure
- 1008: Policy violation (auth failure)
- 1011: Internal server error

## Multiplexed Stream Protocol

The `/v1/stream/all` endpoint supports dynamic subscription management:

1. First message MUST be subscription request
2. Can add/remove subscriptions during connection
3. Permissions checked per stream type

Example flow:
```json
→ {"type": "subscribe", "streams": ["message", "telemetry"]}
← {"type": "subscribe", "data": {"subscribed": ["message", "telemetry"], "denied": []}}
← {"type": "message", "data": {...}}
← {"type": "telemetry", "data": {...}}
→ {"type": "unsubscribe", "streams": ["telemetry"]}
← {"type": "unsubscribe", "data": {"removed": ["telemetry"]}}
```
