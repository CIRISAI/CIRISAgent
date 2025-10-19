# CIRIS Consent Service

## Overview

The CIRIS Consent Service is the 22nd core service (Governance Service #5) that manages user consent, data retention, and relationship evolution in compliance with privacy regulations. It implements a three-stream consent model with automatic expiry, bilateral partnership agreements, and integration with DSAR (Data Subject Access Request) compliance.

## Architecture

### Service Type
- **Classification**: Tool Service (discoverable via ToolBus)
- **Service Number**: 22 of 22 core services
- **Category**: Governance Service (#5)
- **Dependencies**: TimeService, Memory persistence (SQLite)

### Integration Points
- **DSAR Service**: Provides consent status for data subject requests
- **TSDBConsolidation**: Handles automatic expiry during 6-hour consolidation cycles
- **UserProfile**: Enriches context with consent relationship state
- **ToolBus**: Exposes relationship management tools

## Consent Streams

### 1. TEMPORARY (Default)
- **Duration**: 14 days auto-expiry
- **Categories**: ESSENTIAL only
- **Renewal**: Automatic on interaction
- **Data Handling**: Full deletion after expiry
- **Use Case**: Default for all new users

### 2. PARTNERED
- **Duration**: Persistent (no auto-expiry)
- **Categories**: ESSENTIAL, BEHAVIORAL, IMPROVEMENT
- **Requirement**: Bilateral consent (user request + agent approval)
- **Data Handling**: Retained for relationship duration
- **Use Case**: Long-term collaborative relationships

### 3. ANONYMOUS
- **Duration**: Indefinite
- **Categories**: STATISTICAL only
- **Data Handling**: Aggregated statistics, no PII
- **Use Case**: Users wanting minimal data retention

## Consent Categories

### ESSENTIAL
Core functionality required for basic operation:
- User identification
- Session management
- Communication context

### BEHAVIORAL
Interaction patterns and preferences:
- Communication style
- Response preferences
- Interaction frequency

### IMPROVEMENT
Data used for service enhancement:
- Error patterns
- Feature usage
- Performance metrics

### STATISTICAL
Anonymized aggregate data:
- Usage statistics
- Performance benchmarks
- Trend analysis

## Bilateral Partnership Protocol

Partnership upgrades require mutual agreement:

1. **User Request**: User initiates upgrade via tool or API
2. **Agent Review**: Creates task for agent consideration
3. **Agent Decision**:
   - TASK_COMPLETE: Partnership approved
   - REJECT: Partnership declined
   - DEFER: Decision postponed
4. **Status Update**: User notified of decision

### Downgrade Protocol
Users can unilaterally downgrade at any time:
- PARTNERED → TEMPORARY: Immediate
- PARTNERED → ANONYMOUS: Immediate with data anonymization
- TEMPORARY → ANONYMOUS: Immediate

## API Endpoints

### GET /v1/consent/status
Retrieve current consent status for authenticated user.

**Response Schema**:
```json
{
  "user_id": "string",
  "stream": "TEMPORARY|PARTNERED|ANONYMOUS",
  "categories": ["ESSENTIAL"],
  "granted_at": "2024-01-01T00:00:00Z",
  "expires_at": "2024-01-15T00:00:00Z",
  "last_modified": "2024-01-01T00:00:00Z"
}
```

### POST /v1/consent/grant
Grant or update consent for a user.

**Request Schema**:
```json
{
  "user_id": "string",
  "stream": "TEMPORARY|PARTNERED|ANONYMOUS",
  "categories": ["ESSENTIAL", "BEHAVIORAL"],
  "reason": "User requested upgrade"
}
```

### POST /v1/consent/revoke
Revoke consent and initiate data deletion.

### GET /v1/consent/audit
Retrieve consent change history for authenticated user.

**Query Parameters**:
- `limit`: Maximum number of entries (default: 100)

**Response Schema**:
```json
[
  {
    "entry_id": "string",
    "user_id": "string",
    "timestamp": "2024-01-01T00:00:00Z",
    "previous_stream": "TEMPORARY",
    "new_stream": "PARTNERED",
    "previous_categories": ["ESSENTIAL"],
    "new_categories": ["ESSENTIAL", "BEHAVIORAL"],
    "initiated_by": "user",
    "reason": "User requested partnership"
  }
]
```

### POST /v1/consent/dsar/initiate
Initiate automated DSAR (Data Subject Access Request) export.

**Request Body**:
```json
{
  "request_type": "full"  // Options: "full", "consent_only", "impact_only", "audit_only"
}
```

**Response Schema**:
```json
{
  "request_id": "dsar_wa-2025-08-25-391F3E_20251018022901",
  "user_id": "wa-2025-08-25-391F3E",
  "request_type": "full",
  "status": "completed",
  "export_data": {
    "consent": {
      "user_id": "wa-2025-08-25-391F3E",
      "stream": "temporary",
      "categories": ["interaction", "improvement"],
      "granted_at": "2025-10-18T02:20:00Z",
      "expires_at": "2025-11-01T02:20:00Z",
      "last_modified": "2025-10-18T02:20:00Z"
    },
    "impact": {
      "total_interactions": 1234,
      "patterns_contributed": 456,
      "users_helped": 78,
      "categories_active": ["interaction", "improvement"],
      "impact_score": 89.5,
      "example_contributions": ["Pattern: User prefers concise responses", "..."]
    },
    "audit_trail": [
      {
        "entry_id": "audit_001",
        "user_id": "wa-2025-08-25-391F3E",
        "timestamp": "2025-10-18T02:20:00Z",
        "previous_stream": "temporary",
        "new_stream": "temporary",
        "previous_categories": ["interaction"],
        "new_categories": ["interaction", "improvement"],
        "initiated_by": "user",
        "reason": "Added improvement consent"
      }
    ]
  }
}
```

**Export Data Structure**:
- `consent`: Current consent status (if request_type includes consent)
- `impact`: Impact metrics (if request_type includes impact)
- `audit_trail`: Complete consent change history (if request_type includes audit)

**Request Types**:
- `full`: All sections (consent + impact + audit_trail)
- `consent_only`: Only consent section
- `impact_only`: Only impact section
- `audit_only`: Only audit_trail section

### GET /v1/consent/dsar/status/{request_id}
Check status of DSAR request.

**Path Parameters**:
- `request_id`: DSAR request ID (format: `dsar_{user_id}_{timestamp}`)

**Response Schema**:
```json
{
  "request_id": "dsar_wa-2025-08-25-391F3E_20251018022901",
  "user_id": "wa-2025-08-25-391F3E",
  "status": "completed",
  "message": "DSAR request completed - data is immediately available"
}
```

**Security**:
- Returns 403 if request_id belongs to different user
- Validates request_id format
- Immediate completion (async processing possible in future)

## Tool Interface

### upgrade_relationship
Request partnership upgrade (requires bilateral consent).

**Parameters**:
- `user_id`: User requesting upgrade
- `reason`: Justification for partnership

### degrade_relationship
Immediate relationship downgrade (unilateral).

**Parameters**:
- `user_id`: User requesting downgrade
- `target_stream`: TEMPORARY or ANONYMOUS

## DSAR Integration

The Consent Service provides critical data for DSAR compliance:

1. **Consent Basis**: Legal basis for data processing
2. **Retention Period**: How long data will be retained
3. **Data Categories**: What types of data are collected
4. **Processing Purpose**: Why data is being processed
5. **Audit Trail**: Complete history of consent changes

### DSAR Response Enhancement
When a DSAR request is received, the Consent Service:
- Validates the user has active consent
- Provides consent history for the audit trail
- Specifies data retention timelines
- Lists applicable data categories

## Data Lifecycle Management

### Automatic Expiry (TEMPORARY)
- Checked during TSDBConsolidation (every 6 hours)
- Nodes past expiry are deleted
- User notified before expiry (configurable)

### Decay Protocol (PARTNERED → Anonymous)
90-day gradual anonymization:
1. Days 0-30: Relationship context retained
2. Days 31-60: Behavioral data aggregated
3. Days 61-90: Identity markers removed
4. Day 90: Complete anonymization

### Immediate Deletion
Available for:
- GDPR Article 17 requests
- User-initiated deletion
- Compliance requirements

## Telemetry Metrics

The service tracks five key metrics:

1. **consent_active_users**: Users with valid consent
2. **consent_stream_distribution**: Percentage per stream type
3. **consent_partnership_success_rate**: Approval rate for partnerships
4. **consent_average_age_days**: Average consent duration
5. **consent_expiry_rate**: Daily expiry count

## Security Considerations

### Data Protection
- All consent records are immutable audit entries
- Changes create new records, never modify existing
- Full encryption at rest and in transit

### Access Control
- Users can only modify their own consent
- Admins can view but not modify consent
- System-only operations for expiry

### Compliance
- GDPR Article 6 (lawful basis)
- GDPR Article 7 (consent requirements)
- GDPR Article 17 (right to erasure)
- CCPA compliance for California users

## Implementation Details

### Database Schema
Consent data stored as GraphNodes:
- **Node ID**: `consent/{user_id}`
- **Type**: `NodeType.CONSENT`
- **Scope**: `GraphScope.LOCAL`
- **Attributes**: Stream, categories, timestamps

### State Management
- In-memory cache for active consents
- Write-through to persistent storage
- Automatic cache invalidation on changes

### Error Handling
- **ConsentNotFoundError**: No consent exists
- **ConsentValidationError**: Invalid state transition
- **ConsentExpiredError**: Consent has expired

## Configuration

### Environment Variables
- `DEFAULT_CONSENT_DURATION_DAYS`: Default TEMPORARY duration (14)
- `CONSENT_WARNING_DAYS`: Days before expiry to warn (3)
- `PARTNERSHIP_REVIEW_TIMEOUT`: Max time for agent decision (48h)

### Feature Flags
- `ENABLE_AUTO_RENEWAL`: Auto-renew on interaction
- `REQUIRE_EXPLICIT_CONSENT`: No default consent
- `ENABLE_DECAY_PROTOCOL`: Use 90-day decay vs immediate deletion

## Artificial Interaction Reminder (AIR)

### Overview
The AIR module is a parasocial attachment prevention system integrated into the Consent Service. It monitors 1:1 API interactions and provides mindful break reminders to prevent unhealthy AI relationships.

**Philosophy**: This is NOT legal compliance—it's about promoting healthy relationships with AI by encouraging breaks and emphasizing the importance of real human connections.

### Scope
- **Applies to**: API channels only (1:1 interactions)
- **Excludes**: Discord community moderation (many-to-many interactions)
- **Excludes**: CLI testing/development channels

### Trigger Thresholds

#### Time-Based Trigger
- **Threshold**: 30 minutes of continuous interaction
- **Definition**: From session start to current message
- **Session Reset**: >30 minutes idle = new session
- **Example**: 1 message/minute for 30 minutes = TRIGGER

#### Message-Based Trigger (Sliding Window)
- **Threshold**: 20 messages within a 30-minute sliding window
- **Window**: Counts only messages from the last 30 minutes
- **Example**: 20 messages in 5 minutes = TRIGGER
- **Example**: 19 messages, wait 40 minutes, 19 more = NO TRIGGER (window resets)

### Reminder Content
When triggered, users receive a compassionate reminder:

```
🕒 **Mindful Interaction Reminder**

We've been chatting for a while now. I want to remind you:

• I'm an AI assistant, not a friend or companion
• Taking breaks from AI interactions is healthy
• Real human connections are irreplaceable

You've sent 20 messages in the last 30 minutes. Consider taking
a break, stepping away from your screen, or connecting with
people in your life.

I'll be here when you need me, but your wellbeing comes first.
```

### Session Management

#### Session Lifecycle
1. **Creation**: First API interaction creates session
2. **Tracking**: Records all message timestamps
3. **Idle Detection**: >30 minutes without interaction
4. **Reset**: Idle >30 min = treat as new conversation
5. **Cleanup**: Sessions removed after 1 hour of total inactivity

#### Session State
- **Session Start**: Time of first message in current session
- **Last Interaction**: Most recent message timestamp
- **Message Timestamps**: Array of all message times (for sliding window)
- **Reminder Sent**: Boolean flag (prevents duplicate reminders)

### Channel Type Detection
AIR automatically infers channel type from ID patterns:
- `api_*` or `api-*` → API channel (tracked)
- `discord_*` or numeric IDs 17-19 digits → Discord (excluded)
- `cli_*` or `cli-*` → CLI (excluded)

### Integration with ConsentService

#### Public Method
```python
async def track_interaction(
    self, user_id: str, channel_id: str, channel_type: Optional[str] = None
) -> Optional[str]:
    """
    Track user interaction for parasocial attachment prevention.

    Returns:
        Reminder message if threshold exceeded, None otherwise
    """
```

#### Usage in Message Handlers
```python
# Call on every API message
reminder = await consent_service.track_interaction(
    user_id=user.id,
    channel_id=message.channel_id,
    channel_type="api"
)

if reminder:
    # Inject reminder into conversation context
    await send_system_message(reminder)
```

### Telemetry Metrics
AIR exposes 6 metrics via the Consent Service:

1. **consent_air_total_interactions**: Total API interactions tracked
2. **consent_air_reminders_sent**: Total reminders sent
3. **consent_air_reminder_rate_percent**: Percentage of interactions triggering reminders
4. **consent_air_active_sessions**: Current active API sessions
5. **consent_air_time_triggered**: Reminders triggered by time threshold
6. **consent_air_message_triggered**: Reminders triggered by message threshold

### Design Examples

#### Example 1: Healthy Spread
```
Day 1: 19 messages in 10 minutes → No reminder
Wait 40 minutes (session resets)
Day 1: 19 more messages in 10 minutes → No reminder
Result: 38 total messages, no trigger (sessions separated)
```

#### Example 2: Intensive Interaction
```
20 messages in 5 minutes → TRIGGER at message 20
Reason: 20 messages within 30-minute sliding window
```

#### Example 3: Continuous Interaction
```
1 message every 2 minutes for 30 minutes (15 messages) → TRIGGER
Reason: 30 minutes continuous interaction
```

#### Example 4: Spread Out Messages
```
1 message every 6 minutes for 2 hours (20 messages) → TRIGGER at 30 min
Reason: 30 minutes continuous interaction (even with short breaks)
Note: This is intentional—breaks <30 min don't reset the session
```

### Implementation Details

#### File Location
`ciris_engine/logic/services/governance/consent/air.py`

#### Classes
- **InteractionSession**: Tracks per-user session state
- **ArtificialInteractionReminder**: Main AIR manager

#### Key Methods
- `track_interaction()`: Record message and check thresholds
- `end_session()`: Manually end session
- `cleanup_stale_sessions()`: Remove idle sessions
- `get_session_info()`: Retrieve session details
- `get_metrics()`: Export telemetry data

### Configuration

#### Default Values
- **Time Threshold**: 30 minutes
- **Message Threshold**: 20 messages
- **Session Cleanup**: 1 hour idle

#### Customization
```python
air_manager = ArtificialInteractionReminder(
    time_service=time_service,
    time_threshold_minutes=30,  # Configurable
    message_threshold=20,       # Configurable
)
```

### Privacy Considerations
- **No Content Storage**: Only timestamps tracked, not message content
- **Local Sessions**: Session data stored in memory, not persisted
- **Automatic Cleanup**: Stale sessions removed after 1 hour
- **User Privacy**: Cannot track across different channel IDs

### Limitations
- **API Channels Only**: Does not track Discord or CLI interactions
- **Per-Channel Sessions**: Separate sessions per channel (prevents cross-channel tracking)
- **Memory-Only**: Sessions reset on service restart
- **No Historical Analysis**: Only tracks current active sessions

## Future Enhancements

1. **Granular Permissions**: Per-feature consent controls
2. **Consent Templates**: Pre-configured consent profiles
3. **Delegation**: Allow authorized third-party consent management
4. **Portability**: Export/import consent preferences
5. **Consent Analytics**: Insights into consent patterns
6. **AIR Customization**: User-configurable reminder thresholds
7. **AIR Persistence**: Store session data for cross-restart continuity

## Version History

- **v0.3.0**: Added AIR module, modular architecture refactoring, decay countdown reset
- **v1.4.6**: Initial implementation as 22nd core service
- **v1.4.5**: Conceptual design in FSD-015
- **v1.4.0**: DSAR compliance framework
