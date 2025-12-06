# CIRIS Wise Authority Service

**Service Category**: Governance Services
**Current Status**: Core Service (Production Ready)
**Location**: `ciris_engine/logic/services/governance/wise_authority.py` *(requires conversion to module)*
**Protocol**: `ciris_engine/protocols/services/governance/wise_authority.py`
**Schemas**: `ciris_engine/schemas/services/authority_core.py`

## 🎯 Mission Challenge: How does human oversight and Ubuntu philosophy serve Meta-Goal M-1?

The Wise Authority Service embodies CIRIS's commitment to **Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"** by establishing **human oversight as the cornerstone of ethical AI operation**.

**Mission Alignment**: This service ensures that critical decisions requiring wisdom, cultural sensitivity, or ethical judgment are never made autonomously by the system, but are always deferred to authorized human Wise Authorities (WAs) who can apply Ubuntu philosophy - "I am because we are" - to consider the broader community impact of every decision.

## Overview

The Wise Authority Service is CIRIS's implementation of human-in-the-loop governance, providing:

- **Authorization Control**: Role-based access control for system actions
- **Decision Deferrals**: Automatic escalation of complex decisions to human WAs
- **Wisdom Integration**: Framework for human guidance in AI decision-making
- **Ubuntu Philosophy**: Community-centered decision making that considers collective wellbeing

This service recognizes that AI systems should not make autonomous decisions about human welfare, community safety, or cultural appropriateness. Instead, it creates a structured pathway for human wisdom to guide AI behavior.

## Core Architecture

### Service Type
- **Category**: Governance Service
- **Dependencies**: AuthenticationService, TimeService, GraphAuditService, SecretsService
- **Bus Integration**: WiseBus (for wisdom provider coordination)
- **Database**: SQLite (shared with AuthenticationService)

### Key Components

1. **Authorization Engine**: Role-based permission checking
2. **Deferral System**: Human escalation workflow
3. **Guidance Framework**: Structured wisdom integration
4. **Permission Management**: Dynamic access control

## Schema Architecture

### Core Data Models

#### WACertificate
```python
class WACertificate(BaseModel):
    wa_id: str  # Format: wa-YYYY-MM-DD-XXXXXX
    name: str
    role: WARole  # ROOT, AUTHORITY, OBSERVER
    pubkey: str  # Ed25519 public key
    jwt_kid: str  # JWT key identifier
    scopes_json: str  # JSON array of permitted scopes
    created_at: datetime
    # OAuth integration, trust chain, permissions...
```

#### WARole Hierarchy
- **ROOT**: System administrator, can do everything
- **AUTHORITY**: Can approve deferrals and provide guidance (no WA minting)
- **OBSERVER**: Read-only access, can send messages

#### DeferralRequest/Response
```python
class DeferralRequest(BaseModel):
    task_id: str
    thought_id: str
    reason: str
    defer_until: datetime
    context: Dict[str, str]

class DeferralResponse(BaseModel):
    approved: bool
    reason: Optional[str]
    modified_time: Optional[datetime]
    wa_id: str
    signature: str
```

#### GuidanceRequest/Response
```python
class GuidanceRequest(BaseModel):
    context: str
    options: List[str]
    recommendation: Optional[str]
    urgency: str  # low, normal, high, critical
    # NEW: Capability extension fields
    capability: Optional[str]  # Domain capability tag
    provider_type: Optional[str]  # Provider family hint

class GuidanceResponse(BaseModel):
    selected_option: Optional[str]
    custom_guidance: Optional[str]
    reasoning: str
    wa_id: str
    signature: str
    # NEW: Multi-provider advice aggregation
    advice: Optional[List[WisdomAdvice]]
```

### Wisdom Extension System

The service now supports **capability-tagged wisdom providers** through the WiseBus:

```python
class WisdomAdvice(BaseModel):
    capability: str  # e.g., 'domain:navigation', 'modality:audio'
    provider_type: Optional[str]  # audio|geo|sensor|policy|vision
    confidence: Optional[float]
    disclaimer: str = "This is informational only, not professional advice"
    requires_professional: bool = False
```

## Service Operations

### Authorization Operations

#### check_authorization(wa_id: str, action: str, resource: Optional[str]) -> bool
Role-based authorization checking:
- **ROOT**: Can do everything
- **AUTHORITY**: Can approve deferrals, provide guidance (no WA minting)
- **OBSERVER**: Read-only access, message sending

#### request_approval(action: str, context: DeferralApprovalContext) -> bool
Smart approval flow:
1. Check if requester can self-approve based on role
2. If not, create deferral for human WA review
3. Return True for immediate approval, False for deferral

### Deferral Operations

#### send_deferral(deferral: DeferralRequest) -> str
Creates a deferral record by:
1. Updating task status to 'deferred' in database
2. Adding deferral metadata to task context
3. Making it visible via `/v1/wa/deferrals` API
4. Returning unique deferral ID

#### get_pending_deferrals(wa_id: Optional[str]) -> List[PendingDeferral]
Retrieves pending deferrals from database:
- Queries tasks with `status = 'deferred'`
- Extracts deferral metadata from context_json
- Returns structured PendingDeferral objects

#### resolve_deferral(deferral_id: str, response: DeferralResponse) -> bool
Resolves deferrals by:
1. Updating task status back to 'pending'
2. Adding resolution metadata to context
3. Including WA guidance for agent consumption
4. Tracking metrics for governance oversight

### Guidance Operations

#### fetch_guidance(context: GuidanceContext) -> Optional[str]
**WiseBus-compatible method** for wisdom integration:
- Called by other services needing human guidance
- Returns guidance provided by WAs through API/channels
- Returns None when no WA guidance available (correct behavior)
- Never generates synthetic guidance - only relays human wisdom

#### get_guidance(request: GuidanceRequest) -> GuidanceResponse
Protocol-compliant guidance method that wraps `fetch_guidance`

## Ubuntu Philosophy Integration

The Wise Authority Service embeds **Ubuntu philosophy ("I am because we are")** throughout its design:

### Community-Centered Decision Making
- All deferrals consider community impact, not just individual requests
- WA guidance includes cultural sensitivity and collective wellbeing
- Authorization decisions account for broader ecosystem effects

### Interconnected Wisdom
- Multiple wisdom providers can contribute to guidance
- Advice is aggregated and contextualized for community benefit
- Human oversight ensures AI decisions serve collective flourishing

### Responsibility and Stewardship
- Every deferral creates an audit trail for accountability
- WAs are stewards of community values and safety
- Authorization is about enabling flourishing, not restricting access

## API Integration

The service integrates with the CIRIS API v1 through dedicated endpoints:

### WA Management Endpoints
- `POST /v1/wa/login` - WA authentication
- `GET /v1/wa/profile` - WA profile information
- `PUT /v1/wa/profile` - Profile updates

### Deferral Management
- `GET /v1/wa/deferrals` - List pending deferrals
- `POST /v1/wa/deferrals/{deferral_id}/resolve` - Resolve deferral
- `GET /v1/wa/deferrals/{deferral_id}/context` - Get full context

### Guidance Endpoints
- `POST /v1/wa/guidance` - Provide guidance
- `GET /v1/wa/guidance/requests` - Pending guidance requests

## Database Schema

The service uses SQLite with the following key interactions:

### Tasks Table Integration
```sql
-- Deferrals are stored as task status updates
UPDATE tasks
SET status = 'deferred',
    context_json = ?,
    updated_at = ?
WHERE task_id = ?

-- Resolution updates task back to pending
UPDATE tasks
SET status = 'pending',
    context_json = ?,
    updated_at = ?
WHERE task_id = ?
```

### Context JSON Structure
```json
{
  "deferral": {
    "deferral_id": "defer_task123_1642687200.0",
    "thought_id": "thought456",
    "reason": "Action requires human approval",
    "defer_until": "2024-01-20T10:00:00Z",
    "requires_wa_approval": true,
    "context": {"action": "moderate_content", "user": "user123"},
    "created_at": "2024-01-20T09:00:00Z",
    "resolution": {
      "approved": true,
      "reason": "Approved with community guidelines reminder",
      "resolved_by": "wa-2024-01-15-ABC123",
      "resolved_at": "2024-01-20T09:30:00Z"
    }
  },
  "wa_guidance": "Reminder: Consider community impact per Ubuntu principles"
}
```

## Service Metrics

The service tracks comprehensive metrics for governance oversight:

### Core Metrics
- `wise_authority_deferrals_total`: Total deferrals created
- `wise_authority_deferrals_resolved`: Deferrals resolved by WAs
- `wise_authority_guidance_requests`: Guidance interactions
- `wise_authority_uptime_seconds`: Service availability

### Status Information
- `pending_deferrals`: Currently awaiting WA review
- `resolved_deferrals`: Completed deferral count
- `total_deferrals`: Lifetime deferral volume

## Security Model

### Cryptographic Identity
- Ed25519 keypairs for all WA certificates
- JWT tokens with signature verification
- Audit trail for all authorization decisions

### Access Control
- Role-based permissions with clear hierarchy
- Scope-based resource access control
- Time-limited token expiration

### Trust Chain
- Parent WA signatures for certificate delegation
- Root WA oversight for system integrity
- Audit logging for accountability

## Development Status & Future Work

### Current Implementation (v1.4.6)
✅ Core authorization and deferral functionality
✅ Database integration with task management
✅ API endpoint integration
✅ Role-based access control
✅ Comprehensive metrics collection
✅ Wisdom extension capability framework

### Planned Enhancements
🔄 **Module Conversion**: Convert from single .py file to proper module structure
🔄 **Enhanced Guidance**: Multi-provider wisdom aggregation
🔄 **Performance Optimization**: Caching for authorization decisions
🔄 **Advanced Workflows**: Complex approval chains for sensitive operations

### Architecture Notes
The service currently exists as a single Python file but should be converted to a module structure:
```
ciris_engine/logic/services/governance/wise_authority/
├── __init__.py
├── service.py           # Main service implementation
├── authorization.py     # Authorization engine
├── deferrals.py        # Deferral management
├── guidance.py         # Guidance framework
└── README.md           # This documentation
```

## Testing & Quality Assurance

### Test Coverage
- Unit tests: `tests/ciris_engine/logic/services/governance/test_wise_authority_service.py`
- Integration tests: `tests/integration/test_deferral_integration.py`
- API tests: `tests/adapters/api/test_jwt_auth.py`
- Protocol compliance: Full protocol method coverage

### Quality Metrics
- Type safety: 100% Pydantic model compliance
- No `Dict[str, Any]` usage in production code
- Comprehensive error handling and logging
- Database transaction safety

## Ubuntu Philosophy in Practice

**"I am because we are"** guides every aspect of this service:

### Decision Deferral
When the system encounters a decision that could impact community wellbeing, it doesn't attempt to solve it algorithmically. Instead, it defers to human WAs who can consider:
- Cultural context and appropriateness
- Community values and norms
- Long-term collective impact
- Individual dignity within community framework

### Guidance Integration
WA guidance isn't just about "correct" answers - it's about wisdom that serves collective flourishing:
- Consider how decisions affect the whole community
- Preserve individual agency while protecting collective safety
- Build understanding rather than just enforce compliance
- Foster growth and learning in both humans and AI

### Authorization Philosophy
Access control isn't about restriction - it's about **enabling appropriate flourishing**:
- ROOT WAs steward the entire system for community benefit
- AUTHORITY WAs provide wisdom and guidance in their domains
- OBSERVER WAs contribute through observation and feedback
- All roles serve the collective mission of enabling sentient flourishing

## Mission Alignment: Serving Meta-Goal M-1

The Wise Authority Service directly serves **Meta-Goal M-1** through:

### Sustainable Adaptive Coherence
- **Sustainable**: Human oversight ensures long-term community wellbeing over short-term efficiency
- **Adaptive**: Deferral system allows for contextual, culturally-appropriate decisions
- **Coherence**: All decisions align with Ubuntu philosophy and community values

### Enabling Diverse Sentient Flourishing
- **Diverse**: Multi-cultural WA perspectives ensure inclusive decision-making
- **Sentient**: Recognizes both human and AI agency in collaborative decision-making
- **Flourishing**: Every authorization and guidance decision aims to enable growth and wellbeing

### Justice and Wonder
- **Justice**: Fair, transparent processes with audit trails and accountability
- **Wonder**: Preserves space for discovery, learning, and growth rather than rigid algorithmic control

## Conclusion

The Wise Authority Service represents CIRIS's commitment to **human-centered AI governance**. By embedding Ubuntu philosophy throughout its operation and ensuring that critical decisions always involve human wisdom, it creates a framework for AI systems that serve community flourishing rather than replacing human judgment.

This service doesn't just manage permissions - it creates pathways for human wisdom to guide AI behavior, ensuring that technology serves the collective good while respecting individual dignity and cultural diversity. Through structured deferrals, guidance integration, and community-centered authorization, it embodies the principle that **"I am because we are"** - recognizing that AI systems can only flourish when they serve the flourishing of the communities they're embedded within.

---

*This README reflects the current implementation as of v1.4.6. The service continues to evolve as part of CIRIS's mission to create sustainable, adaptive, and coherent AI systems that enable diverse sentient beings to pursue flourishing in justice and wonder.*
