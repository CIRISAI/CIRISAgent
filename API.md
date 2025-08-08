# CIRIS API Documentation

**Base URL**: `https://agents.ciris.ai/api/{agent_id}/v1`
**Authentication**: Bearer token (JWT)
**Content-Type**: `application/json`

## Table of Contents

1. [Authentication](#authentication)
2. [Core Endpoints](#core-endpoints)
3. [Privacy & Transparency](#privacy--transparency)
4. [Error Handling](#error-handling)
5. [Rate Limiting](#rate-limiting)
6. [WebSocket Support](#websocket-support)

## Authentication

### Login
```http
POST /v1/auth/login
```

**Request:**
```json
{
  "username": "admin",
  "password": "password"
}
```

**Response:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

### Using the Token
Include in Authorization header:
```
Authorization: Bearer eyJ...
```

### Roles
- `OBSERVER` - Read-only access
- `ADMIN` - Standard administrative access
- `AUTHORITY` - Wise Authority operations
- `SYSTEM_ADMIN` - Full system control

## Core Endpoints

### Agent Operations

#### Interact with Agent
```http
POST /v1/agent/interact
```
Send a message to the agent for processing.

**Request:**
```json
{
  "message": "Hello, how can you help?",
  "channel_id": "api_session_123",
  "author": "user@example.com"
}
```

**Response:**
```json
{
  "message_id": "msg_abc123",
  "response": "Hello! I can help with...",
  "state": "WORK",
  "processing_time_ms": 250
}
```

#### Get Agent Status
```http
GET /v1/agent/status
```
Returns current agent state and health.

#### Get Agent Identity
```http
GET /v1/agent/identity
```
Returns agent's identity information.

#### Get Conversation History
```http
GET /v1/agent/history?channel_id={channel_id}&limit=50
```
Retrieve conversation history for a channel.

### System Management

#### System Health
```http
GET /v1/system/health
```
Returns overall system health and service status.

#### Resource Usage
```http
GET /v1/system/resources
```
Returns CPU, memory, and disk usage statistics.

#### Service Health Details
```http
GET /v1/system/services/health
```
Detailed health status for each service.

#### Runtime Control
```http
POST /v1/system/pause
POST /v1/system/resume
GET /v1/system/state
POST /v1/system/single-step
GET /v1/system/queue
```
Control the agent's processing state.

### Memory & Graph

#### Store Memory
```http
POST /v1/memory/store
```
Store data in the graph memory.

**Request:**
```json
{
  "node_type": "observation",
  "data": {
    "content": "User prefers formal language",
    "confidence": 0.85
  }
}
```

#### Query Memory
```http
POST /v1/memory/query
```
Query the graph database.

**Request:**
```json
{
  "cypher": "MATCH (n:Observation) RETURN n LIMIT 10"
}
```

#### Recall Memories
```http
GET /v1/memory/recall?topic={topic}&limit=10
```
Recall memories related to a topic.

### Configuration

#### Get Configuration
```http
GET /v1/config
GET /v1/config/{key}
```
Retrieve system configuration.

#### Update Configuration
```http
PUT /v1/config/{key}
```
Update configuration (requires ADMIN role).

**Request:**
```json
{
  "value": "new_value"
}
```

### Telemetry

#### Get Metrics
```http
GET /v1/telemetry/metrics?window=1h
```
Returns system metrics.

#### Get Logs
```http
GET /v1/telemetry/logs?level=INFO&limit=100
```
Returns recent log entries.

#### Get Traces
```http
GET /v1/telemetry/traces?limit=50
```
Returns request traces for debugging.

### Audit Trail

#### Get Audit Log
```http
GET /v1/audit?start={timestamp}&end={timestamp}
```
Returns audit trail entries.

#### Search Audit Log
```http
POST /v1/audit/search
```
Search audit entries with filters.

**Request:**
```json
{
  "action": "agent.interact",
  "user": "admin",
  "start_time": "2025-08-01T00:00:00Z",
  "end_time": "2025-08-07T23:59:59Z"
}
```

### Wise Authority

#### Request Guidance
```http
POST /v1/wa/guidance
```
Request Wise Authority guidance.

**Request:**
```json
{
  "context": "User requesting potentially harmful action",
  "proposed_action": "REJECT",
  "confidence": 0.3
}
```

#### Get Deferrals
```http
GET /v1/wa/deferrals?status=pending
```
Returns deferred decisions awaiting WA review.

## Privacy & Transparency

### Data Subject Access Requests (DSAR)

#### Submit DSAR
```http
POST /v1/dsr
```
Submit a data access request (GDPR Articles 15-22).

**Request:**
```json
{
  "request_type": "access",
  "email": "user@example.com",
  "user_identifier": "discord_user_123",
  "details": "Please provide all data you have about me",
  "urgent": false
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "ticket_id": "DSAR-20250807-A1B2C3D4",
    "status": "pending_review",
    "estimated_completion": "2025-08-21",
    "contact_email": "user@example.com",
    "message": "Your access request has been received..."
  }
}
```

#### Check DSAR Status
```http
GET /v1/dsr/{ticket_id}
```
Check status of a DSAR request.

#### List DSARs (Admin)
```http
GET /v1/dsr
```
List all pending DSAR requests (requires ADMIN role).

#### Update DSAR Status (Admin)
```http
PUT /v1/dsr/{ticket_id}/status
```
Update DSAR status (requires ADMIN role).

### Transparency Feed

#### Get Public Statistics
```http
GET /v1/transparency/feed?hours=24
```
**No authentication required** - Returns anonymized statistics.

**Response:**
```json
{
  "period_start": "2025-08-06T20:00:00Z",
  "period_end": "2025-08-07T20:00:00Z",
  "total_interactions": 1523,
  "actions_taken": [
    {"action": "SPEAK", "count": 1200, "percentage": 78.8},
    {"action": "DEFER", "count": 250, "percentage": 16.4},
    {"action": "REJECT", "count": 73, "percentage": 4.8}
  ],
  "deferrals_to_human": 180,
  "deferrals_uncertainty": 50,
  "deferrals_ethical": 20,
  "harmful_requests_blocked": 73,
  "rate_limit_triggers": 12,
  "emergency_shutdowns": 0,
  "uptime_percentage": 99.95,
  "average_response_ms": 287.3,
  "active_agents": 3,
  "data_requests_received": 2,
  "data_requests_completed": 1
}
```

#### Get Transparency Policy
```http
GET /v1/transparency/policy
```
Returns privacy policy and commitments.

## Emergency Endpoints

### Emergency Shutdown
```http
POST /emergency/shutdown
```
**No authentication required** - Requires Ed25519 signature.

**Request:**
```json
{
  "reason": "Emergency shutdown requested",
  "signature": "base64_ed25519_signature",
  "public_key": "base64_public_key"
}
```

## Error Handling

All endpoints return consistent error responses:

```json
{
  "success": false,
  "error": "Error message",
  "detail": "Detailed error information",
  "status_code": 400
}
```

### Common Status Codes
- `200` - Success
- `400` - Bad Request
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `429` - Rate Limited
- `500` - Internal Server Error

## Rate Limiting

Default limits:
- **General**: 100 requests/minute
- **Agent Interact**: 30 requests/minute
- **Memory Queries**: 20 requests/minute

Rate limit headers:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1691442000
```

## WebSocket Support

### Connect
```
wss://agents.ciris.ai/api/{agent_id}/v1/ws
```

### Authentication
Send token after connection:
```json
{
  "type": "auth",
  "token": "Bearer eyJ..."
}
```

### Message Types
- `agent.message` - Agent responses
- `system.status` - System status updates
- `telemetry.metric` - Real-time metrics
- `error` - Error messages

### Example WebSocket Flow
```javascript
const ws = new WebSocket('wss://agents.ciris.ai/api/datum/v1/ws');

ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'auth',
    token: 'Bearer eyJ...'
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};

// Send message
ws.send(JSON.stringify({
  type: 'agent.interact',
  message: 'Hello',
  channel_id: 'ws_session_123'
}));
```

## SDK Examples

### Python
```python
import requests

class CIRISClient:
    def __init__(self, base_url, agent_id):
        self.base_url = f"{base_url}/api/{agent_id}/v1"
        self.token = None

    def login(self, username, password):
        response = requests.post(
            f"{self.base_url}/auth/login",
            json={"username": username, "password": password}
        )
        self.token = response.json()["access_token"]

    def interact(self, message):
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.post(
            f"{self.base_url}/agent/interact",
            headers=headers,
            json={"message": message, "channel_id": "python_client"}
        )
        return response.json()

# Usage
client = CIRISClient("https://agents.ciris.ai", "datum")
client.login("admin", "password")
response = client.interact("Hello!")
print(response["response"])
```

### TypeScript
```typescript
class CIRISClient {
  private token: string | null = null;

  constructor(
    private baseURL: string,
    private agentId: string
  ) {}

  async login(username: string, password: string): Promise<void> {
    const response = await fetch(
      `${this.baseURL}/api/${this.agentId}/v1/auth/login`,
      {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username, password})
      }
    );
    const data = await response.json();
    this.token = data.access_token;
  }

  async interact(message: string): Promise<any> {
    const response = await fetch(
      `${this.baseURL}/api/${this.agentId}/v1/agent/interact`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          message,
          channel_id: 'ts_client'
        })
      }
    );
    return response.json();
  }
}
```

### cURL
```bash
# Login
TOKEN=$(curl -s -X POST https://agents.ciris.ai/api/datum/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password"}' \
  | jq -r '.access_token')

# Interact
curl -X POST https://agents.ciris.ai/api/datum/v1/agent/interact \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello!","channel_id":"curl_session"}'

# Get transparency feed (no auth needed)
curl https://agents.ciris.ai/api/datum/v1/transparency/feed?hours=24
```

## Privacy & Data Retention

### Current Pilot Phase Policy
- **Message Content**: 14 days
- **Moderation Logs**: 14 days, then hashed
- **Audit Trail**: 90 days
- **System Metrics**: Aggregated indefinitely (no personal data)
- **TSDB Consolidation**: Every 6 hours

### Key Commitments
- We do NOT train on your content
- We provide DSAR compliance within 14 days
- We maintain public transparency feeds
- We defer to human judgment when uncertain

### Stop Conditions
**Red Lines (Immediate Shutdown):**
- Verified request to target, surveil, or doxx individuals
- Compelled use for harassment
- Evidence of weaponization
- Loss of human oversight

**Yellow Lines (WA Review):**
- Pattern of false positives
- Extremist self-labeling detected
- Adversarial manipulation attempts
- Deferral rate exceeds 30%

---

*For the full OpenAPI specification, visit: `https://agents.ciris.ai/api/{agent_id}/openapi.json`*
