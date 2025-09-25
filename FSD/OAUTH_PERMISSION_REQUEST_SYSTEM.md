# OAuth Permission Request System - Formal Specification Document

## Abstract

This document specifies the OAuth Permission Request System for CIRIS agents, enabling OAuth-authenticated users to request communication privileges while maintaining security and preventing abuse. The system provides a streamlined workflow for users to request permissions and administrators to review requests, with built-in protections against common attack vectors.

## 1. Motivation and Rationale

### 1.1 Current State Analysis

The CIRIS platform currently implements a hard gate on communication privileges:
- OAuth users are automatically assigned the OBSERVER role upon first login
- OBSERVER role lacks the `SEND_MESSAGES` permission required for agent interaction
- Users receive a 403 error directing them to "contact an administrator"
- No in-system mechanism exists for requesting permissions
- Administrators must manually grant permissions via API calls

#### Role Hierarchy and Permissions

CIRIS uses a role-based access control system with clear separation between administrative and wisdom-based roles:

1. **OBSERVER** (default for OAuth users)
   - Read-only access to public endpoints
   - Cannot send messages to agents
   - Can request additional permissions
   - Permissions: `system.read`, `memory.read`, `telemetry.read`, `config.read`, `audit.read`

2. **ADMIN** (Administrative role)
   - All OBSERVER permissions
   - Can send messages to agents
   - Can view and manage users
   - Can grant/revoke user permissions via `manage_user_permissions`
   - Permissions: Adds `system.write`, `memory.write`, `config.write`, `audit.write`, `users.read`, `manage_user_permissions`

3. **AUTHORITY** (Wise Authority - NOT an admin)
   - All OBSERVER and basic write permissions
   - Provides moral/ethical guidance
   - Resolves deferrals
   - NOT a system administrator - cannot manage users
   - Permissions: Adds `wa.read`, `wa.write` for Wise Authority operations

4. **SYSTEM_ADMIN**
   - Full system access
   - All permissions including user management
   - Can perform emergency operations
   - Permissions: All permissions including `users.write`, `users.delete`, `wa.mint`, `emergency_shutdown`, `manage_user_permissions`

### 1.2 Problem Statement

This creates several operational challenges:
1. **User Friction**: Legitimate researchers and potential Wise Authorities cannot interact with agents without out-of-band communication
2. **Administrative Burden**: Manual permission grants require constant administrator attention
3. **Scalability Issues**: As CIRIS expands to multiple agents across different domains, manual permission management becomes untenable
4. **Security Blind Spots**: No audit trail of permission requests or systematic review process
5. **Lost Opportunities**: Potential contributors may abandon the platform when faced with unclear access procedures

### 1.3 Why Not Open Access?

CIRIS agents are designed for moral reasoning in potentially sensitive contexts:
- **Resource Protection**: Computational resources are limited; open access invites abuse
- **Quality Control**: Agent interactions should be meaningful, not spam or abuse
- **Community Safety**: Discord communities require protection from bad actors
- **Future Medical Use**: Healthcare deployments will require strict access controls
- **Ethical Considerations**: Moral reasoning systems must not be manipulated by malicious actors

### 1.4 Why Not External Auth Services?

While services like Okta, Auth0, or AWS Cognito could handle permission workflows, keeping the system internal provides:
- **Independence**: Each CIRIS agent remains fully autonomous
- **Simplicity**: No external dependencies or service integrations
- **Cost Efficiency**: No per-user licensing fees
- **Privacy**: User data remains within the agent's control
- **Offline Capability**: Aligns with CIRIS's resource-constrained deployment goals

## 2. System Design Philosophy

### 2.1 Core Principles

1. **Minimal Surface Area**: Only collect OAuth-provided data (name, email, picture)
2. **No User-Generated Content**: Prevent abuse vectors through custom fields
3. **Transparency**: Users see their request status; admins see all requests
4. **Discord-First**: Primary interaction remains through Discord communities
5. **Agent Autonomy**: Each agent manages its own permission requests independently

### 2.2 Security-First Design

The system explicitly prevents:
- **XSS Attacks**: Profile picture URLs are domain-whitelisted and properly escaped
- **SSRF Vulnerabilities**: No server-side image fetching; browser loads directly from OAuth CDNs
- **Spam/Abuse**: No free-text fields for users to exploit
- **Data Harvesting**: Only OAuth-provided data is stored
- **Privilege Escalation**: Clear separation between request and grant operations

## 3. Technical Specification

### 3.1 Database Schema Changes

#### 3.1.1 User Model Extensions

```python
class User(Base):
    # Existing fields...

    # OAuth profile information
    oauth_name: Optional[str] = Column(String(255))  # Full name from OAuth provider
    oauth_picture: Optional[str] = Column(String(500))  # Profile picture URL

    # Permission request tracking
    permission_requested_at: Optional[datetime] = Column(DateTime(timezone=True))

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_permission_requests', 'permission_requested_at'),
        # Existing indexes...
    )
```

#### 3.1.2 Migration Strategy

```sql
-- Alembic migration
ALTER TABLE users
ADD COLUMN oauth_name VARCHAR(255),
ADD COLUMN oauth_picture VARCHAR(500),
ADD COLUMN permission_requested_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX idx_permission_requests ON users(permission_requested_at)
WHERE permission_requested_at IS NOT NULL;
```

### 3.2 OAuth Data Extraction

#### 3.2.1 Provider-Specific Mappings

**Google OAuth Response**:
```python
{
    "email": user_info.get("email"),
    "oauth_name": user_info.get("name"),  # Full name
    "oauth_picture": user_info.get("picture")  # https://lh3.googleusercontent.com/...
}
```

**Discord OAuth Response**:
```python
{
    "email": user_info.get("email"),
    "oauth_name": user_info.get("username"),  # Discord username
    "oauth_picture": f"https://cdn.discordapp.com/avatars/{user_info['id']}/{user_info['avatar']}.png"
}
```

**GitHub OAuth Response**:
```python
{
    "email": user_info.get("email"),
    "oauth_name": user_info.get("name"),  # GitHub display name
    "oauth_picture": user_info.get("avatar_url")  # https://avatars.githubusercontent.com/...
}
```

### 3.3 URL Validation and Security

#### 3.3.1 Domain Whitelist

```python
ALLOWED_AVATAR_DOMAINS = frozenset([
    'lh3.googleusercontent.com',        # Google
    'cdn.discordapp.com',               # Discord
    'avatars.githubusercontent.com',     # GitHub
    'secure.gravatar.com'               # Gravatar (fallback)
])
```

#### 3.3.2 URL Validation Function

```python
def validate_oauth_picture_url(url: Optional[str]) -> bool:
    """Validate OAuth profile picture URL for security."""
    if not url:
        return True  # Empty is safe

    try:
        parsed = urlparse(url)

        # Only allow HTTPS
        if parsed.scheme != 'https':
            return False

        # Check domain whitelist
        if parsed.netloc not in ALLOWED_AVATAR_DOMAINS:
            return False

        # Validate path doesn't contain traversal attempts
        if '..' in parsed.path or '//' in parsed.path:
            return False

        # Ensure URL length is reasonable
        if len(url) > 500:
            return False

        return True
    except Exception:
        return False
```

### 3.4 API Endpoints

#### 3.4.1 Request Permissions Endpoint

```python
@router.post("/v1/users/request-permissions")
async def request_permissions(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db)
) -> PermissionRequestResponse:
    """Request communication permissions for the current user."""

    # Check if user already has SEND_MESSAGES permission
    if auth.has_permission(Permission.SEND_MESSAGES):
        return PermissionRequestResponse(
            success=True,
            status="already_granted",
            message="You already have communication permissions."
        )

    # Check if request already pending
    user = db.query(User).filter(User.id == auth.user.id).first()
    if user.permission_requested_at:
        return PermissionRequestResponse(
            success=True,
            status="already_requested",
            message="Your permission request is pending review.",
            requested_at=user.permission_requested_at
        )

    # Set permission request timestamp
    user.permission_requested_at = datetime.utcnow()
    db.commit()

    # Log the request for audit trail
    logger.info(f"Permission request submitted by user {user.email} (ID: {user.id})")

    return PermissionRequestResponse(
        success=True,
        status="request_submitted",
        message="Your request has been submitted for review.",
        requested_at=user.permission_requested_at
    )
```

#### 3.4.2 List Permission Requests Endpoint

```python
@router.get("/v1/users/permission-requests")
async def get_permission_requests(
    auth: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
    include_granted: bool = False
) -> List[PermissionRequestUser]:
    """Get list of users who have requested permissions."""

    # Require ADMIN role or higher (AUTHORITY cannot manage users)
    if auth.user.role not in [APIRole.ADMIN, APIRole.SYSTEM_ADMIN]:
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    query = db.query(User).filter(User.permission_requested_at.isnot(None))

    if not include_granted:
        # Only show users who don't already have SEND_MESSAGES permission
        query = query.filter(
            ~User.custom_permissions.contains([Permission.SEND_MESSAGES.value])
        )

    users = query.order_by(User.permission_requested_at.desc()).all()

    return [
        PermissionRequestUser(
            id=user.id,
            email=user.email,
            oauth_name=user.oauth_name,
            oauth_picture=user.oauth_picture,
            role=user.role,
            permission_requested_at=user.permission_requested_at,
            has_send_messages=Permission.SEND_MESSAGES.value in (user.custom_permissions or [])
        )
        for user in users
    ]
```

### 3.5 Updated Error Response

#### 3.5.1 Enhanced 403 Error for Interact Endpoint

```python
# In agent.py interact endpoint
if not auth.has_permission(Permission.SEND_MESSAGES):
    # Check if user has already requested permissions
    user = db.query(User).filter(User.id == auth.user.id).first()

    error_detail = {
        "error": "insufficient_permissions",
        "message": "You do not have permission to send messages to this agent.",
        "discord_invite": "https://discord.gg/YOUR_INVITE_CODE",  # From config
        "can_request_permissions": user.permission_requested_at is None,
        "permission_requested": user.permission_requested_at is not None,
        "requested_at": user.permission_requested_at.isoformat() if user.permission_requested_at else None
    }

    raise HTTPException(
        status_code=403,
        detail=error_detail
    )
```

### 3.6 GUI Implementation

#### 3.6.1 Permission Request Component

```typescript
// components/PermissionRequest.tsx
export function PermissionRequest() {
  const { user } = useAuth();
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');

  const handleRequest = async () => {
    setStatus('loading');
    try {
      const response = await sdk.users.requestPermissions();
      setStatus('success');
    } catch (error) {
      setStatus('error');
    }
  };

  if (user?.hasPermission('SEND_MESSAGES')) {
    return null; // User already has permissions
  }

  return (
    <Card className="p-6">
      <CardHeader>
        <CardTitle>Request Communication Access</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="mb-4">
          To interact with CIRIS agents, you need communication permissions.
        </p>

        {user?.permissionRequestedAt ? (
          <Alert>
            <AlertDescription>
              Your request was submitted on {formatDate(user.permissionRequestedAt)}.
              An administrator will review it soon.
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <p className="mb-4">
              For immediate access, join our Discord community:
            </p>
            <div className="flex gap-4">
              <Button
                variant="primary"
                onClick={() => window.open('https://discord.gg/YOUR_INVITE', '_blank')}
              >
                <DiscordIcon className="mr-2" />
                Join Discord
              </Button>

              <Button
                variant="secondary"
                onClick={handleRequest}
                disabled={status === 'loading' || status === 'success'}
              >
                Request Research Access
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
```

#### 3.6.2 Admin Review Interface

```typescript
// app/dashboard/users/PermissionRequests.tsx
export function PermissionRequests() {
  const { data: requests, refetch } = useQuery({
    queryKey: ['permission-requests'],
    queryFn: () => sdk.users.getPermissionRequests()
  });

  const grantPermission = async (userId: string) => {
    await sdk.users.updatePermissions(userId, {
      grant_permissions: ['SEND_MESSAGES']
    });
    refetch();
  };

  return (
    <div className="space-y-4">
      <h2 className="text-2xl font-bold">Permission Requests</h2>

      <div className="grid gap-4">
        {requests?.map(user => (
          <Card key={user.id} className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                {user.oauthPicture && (
                  <img
                    src={user.oauthPicture}
                    alt={user.oauthName || 'Profile'}
                    className="w-12 h-12 rounded-full"
                    referrerPolicy="no-referrer"
                    crossOrigin="anonymous"
                    onError={(e) => {
                      e.currentTarget.src = '/default-avatar.png';
                    }}
                  />
                )}

                <div>
                  <p className="font-medium">{user.oauthName || 'Unknown'}</p>
                  <p className="text-sm text-muted-foreground">{user.email}</p>
                  <p className="text-xs text-muted-foreground">
                    Requested {formatRelativeTime(user.permissionRequestedAt)}
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="default"
                  onClick={() => grantPermission(user.id)}
                  disabled={user.hasSendMessages}
                >
                  {user.hasSendMessages ? 'Granted' : 'Grant Access'}
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
```

## 4. Security Analysis

### 4.1 Attack Vectors Mitigated

1. **XSS via Profile Pictures**
   - Domain whitelist prevents arbitrary URLs
   - Proper HTML escaping on output
   - Content Security Policy headers restrict image sources

2. **SSRF Attacks**
   - No server-side image fetching
   - URLs are validated but never fetched by the server
   - Browser loads images directly from OAuth provider CDNs

3. **Spam/Abuse**
   - No free-text fields for users to abuse
   - Rate limiting on permission request endpoint
   - One request per user limitation

4. **Information Disclosure**
   - Only admins can view permission requests
   - No user can see other users' requests
   - Minimal data exposure (only OAuth-provided info)

### 4.2 Privacy Considerations

1. **Data Minimization**
   - Only store data provided by OAuth providers
   - No additional user profiling or tracking
   - Clear data retention policies

2. **User Control**
   - Users can see their request status
   - Future: ability to withdraw permission requests
   - Transparent about what data is collected

## 5. Implementation Phases

### Phase 1: Core Functionality (Week 1)
1. Database schema changes and migration
2. OAuth callback updates to store profile data
3. Permission request API endpoints
4. Basic security validations

### Phase 2: GUI Integration (Week 2)
1. Permission request component
2. Admin review interface
3. Updated chat interface with proper messaging
4. SDK updates for new endpoints

### Phase 3: Enhancement (Week 3)
1. Email notifications for admins (optional)
2. Audit logging for all permission changes
3. Metrics on request/grant rates
4. Auto-cleanup of old pending requests

## 6. Testing Strategy

### 6.1 Security Testing
- Attempt XSS via manipulated OAuth responses
- Verify SSRF prevention with malicious URLs
- Test rate limiting and abuse prevention
- Validate domain whitelist enforcement

### 6.2 Functional Testing
- OAuth flow with all providers (Google, Discord, GitHub)
- Permission request workflow end-to-end
- Admin grant/review interface
- Error handling and edge cases

### 6.3 Performance Testing
- Query performance with many permission requests
- GUI responsiveness with large user lists
- API endpoint response times

## 7. Future Considerations

### 7.1 Potential Enhancements
1. **Automated Approval Rules**: Auto-approve users from certain email domains
2. **Expiring Requests**: Auto-cleanup requests older than 30 days
3. **Request Categories**: Different types of access (research, testing, production)
4. **Delegation**: Allow Authority users to handle permission requests

### 7.2 Multi-Agent Scaling
As CIRIS expands to multiple specialized agents:
- Each agent maintains its own permission request queue
- No cross-agent permission sharing (security boundary)
- Potential for agent-specific approval criteria
- Dashboard for managing permissions across multiple agents

## 8. Conclusion

The OAuth Permission Request System provides a secure, scalable solution for managing access to CIRIS agents while maintaining the platform's security posture and commitment to meaningful interactions. By leveraging OAuth provider data and implementing strict validation, the system prevents common attack vectors while providing a smooth user experience for legitimate researchers and community members.

The design prioritizes simplicity and security over features, aligning with CIRIS's philosophy of "No Untyped Dicts, No Bypass Patterns, No Exceptions" - using typed, validated data throughout the system with no special cases or bypass mechanisms.
