# CIRIS Authentication Service

**Category**: Infrastructure Services
**Location**: `ciris_engine/logic/services/infrastructure/authentication.py`
**Mission Alignment**: Meta-Goal M-1 Core Enabler

## Mission Challenge: How does identity verification serve Meta-Goal M-1 and ethical AI?

The Authentication Service embodies CIRIS's commitment to **Meta-Goal M-1: "Promote sustainable adaptive coherence enabling diverse sentient beings to pursue flourishing"** by establishing trustworthy identity verification as the foundation for ethical AI operation.

**Identity verification is not merely a security measure—it is the cornerstone of ethical accountability.** Without verifiable identity, there can be no meaningful consent, no traceable responsibility, and no sustainable trust between sentient beings and AI systems.

### Ethical AI Foundations

1. **Accountability Through Identity**: Every action in CIRIS is tied to a verified Wise Authority (WA), creating an immutable chain of responsibility
2. **Consent-Based Access**: Authentication enables informed consent by ensuring beings know exactly who they're interacting with
3. **Trust Through Transparency**: Cryptographic signatures and certificate chains provide verifiable proof of authenticity
4. **Sustainable Operations**: Role-based access control prevents abuse while enabling legitimate use across the 1000-year operational timeline

## Architecture Overview

The Authentication Service implements **Wise Authority (WA) Certificate Management** with Ed25519 cryptographic security, providing identity verification for all CIRIS entities from human users to system processes.

### Core Components

```
AuthenticationService
├── WA Certificate Management
│   ├── Creation & Storage (SQLite + encrypted keys)
│   ├── Role-based Authorization (ROOT → AUTHORITY → OBSERVER)
│   └── Trust Chain Validation (parent signatures)
├── Token Systems
│   ├── Gateway Tokens (HS256 JWT for OAuth/password)
│   ├── Authority Tokens (EdDSA for system operations)
│   └── Channel Tokens (adapter-specific long-lived)
└── Cryptographic Operations
    ├── Ed25519 Keypair Generation
    ├── Digital Signatures
    └── Password Hashing (PBKDF2)
```

## Service Protocol

### Core Authentication Methods

```python
async def authenticate(token: str) -> Optional[AuthenticationResult]:
    """Primary authentication entry point - verifies tokens and returns identity."""

async def verify_token(token: str) -> Optional[TokenVerification]:
    """Token verification with comprehensive validation."""

def verify_token_sync(token: str) -> Optional[dict]:
    """Synchronous verification for non-async contexts."""
```

### WA Certificate Lifecycle

```python
async def create_wa(name: str, email: str, scopes: List[str],
                   role: WARole = WARole.OBSERVER) -> WACertificate:
    """Create new Wise Authority identity."""

async def revoke_wa(wa_id: str, reason: str) -> bool:
    """Revoke WA certificate with audit trail."""

async def rotate_keys(wa_id: str) -> bool:
    """Cryptographic key rotation for security."""
```

### Token Management

```python
async def create_token(wa_id: str, token_type: TokenType, ttl: int = 3600) -> str:
    """Create authentication tokens of various types."""

async def create_channel_token(wa_id: str, channel_id: str, ttl: int = 3600) -> str:
    """Create adapter-specific channel tokens."""

def create_gateway_token(wa: WACertificate, expires_hours: int = 8) -> str:
    """Create OAuth/password authentication tokens."""
```

## Schema Integration

### WA Certificate Structure (`WACertificate`)

```python
class WACertificate(BaseModel):
    wa_id: str                    # Format: wa-YYYY-MM-DD-XXXXXX
    name: str                     # Human-readable identity
    role: WARole                  # ROOT, AUTHORITY, or OBSERVER

    # Cryptographic Identity
    pubkey: str                   # Base64url Ed25519 public key
    jwt_kid: str                  # JWT key identifier

    # Trust Chain
    parent_wa_id: Optional[str]   # Parent in certificate chain
    parent_signature: Optional[str] # Cryptographic parent approval

    # Permissions & Scopes
    scopes_json: str             # JSON array of permissions

    # Authentication Methods
    password_hash: Optional[str]  # PBKDF2 password hash
    oauth_provider: Optional[str] # OAuth provider name
    oauth_external_id: Optional[str] # External OAuth ID
```

### Authorization Context (`AuthorizationContext`)

```python
class AuthorizationContext(BaseModel):
    wa_id: str                   # Verified identity
    role: WARole                 # Access level
    token_type: TokenType        # Token classification
    sub_type: JWTSubType         # JWT subject type
    scopes: List[str]           # Granted permissions
    channel_id: Optional[str]    # Channel context if applicable
```

### Token Types

- **STANDARD**: Basic authentication tokens for human users
- **CHANNEL**: Long-lived adapter tokens for automated systems
- **OAUTH**: OAuth provider authentication tokens

## Security Architecture

### Cryptographic Standards

- **Ed25519**: All WA certificates use Ed25519 public key cryptography
- **PBKDF2**: Password hashing with 100,000 iterations and 32-byte salt
- **AES-GCM**: Key encryption with machine-specific derivation
- **JWT**: Standards-compliant token format with algorithm validation

### Key Management

```python
def generate_keypair() -> Tuple[bytes, bytes]:
    """Generate cryptographically secure Ed25519 keypair."""

def _derive_encryption_key(salt: bytes) -> bytes:
    """Machine-specific key derivation for secret storage."""

def _encrypt_secret(secret: bytes) -> bytes:
    """AES-GCM encryption with random salt and nonce."""
```

### Trust Chain Validation

```python
async def verify_task_signature(task: Task) -> bool:
    """Verify cryptographic signatures on system tasks."""

def _verify_signature(data: bytes, signature: str, public_key: str) -> bool:
    """Ed25519 signature verification."""
```

## Database Schema

### WA Certificate Table (`wa_cert`)

```sql
CREATE TABLE wa_cert (
    wa_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    pubkey TEXT NOT NULL,
    jwt_kid TEXT NOT NULL UNIQUE,
    password_hash TEXT,
    api_key_hash TEXT,
    oauth_provider TEXT,
    oauth_external_id TEXT,
    auto_minted INTEGER DEFAULT 0,
    veilid_id TEXT,
    parent_wa_id TEXT,
    parent_signature TEXT,
    scopes_json TEXT NOT NULL,
    adapter_id TEXT,
    adapter_name TEXT,
    adapter_metadata_json TEXT,
    token_type TEXT DEFAULT 'standard',
    created TEXT NOT NULL,
    last_login TEXT,
    active INTEGER DEFAULT 1
);
```

## Role Hierarchy

### WARole Enumeration

```python
class WARole(str, Enum):
    ROOT = "root"           # System owner, ultimate authority
    AUTHORITY = "authority" # Can approve deferrals, system operations
    OBSERVER = "observer"   # Read access, basic operations
```

### Permission Model

- **ROOT**: Complete system access, can create AUTHORITY certificates
- **AUTHORITY**: System operations, deferral approval, task signing
- **OBSERVER**: Read access, message communication, basic interactions

## Bootstrap Process

### System Initialization

```python
async def bootstrap_if_needed() -> None:
    """Initialize root certificate and system WA if needed."""
```

1. **Root Certificate Loading**: Loads `seed/root_pub.json` if no ROOT WA exists
2. **System WA Creation**: Creates system authority as child of root certificate
3. **Key Storage**: Securely stores system WA private key for task signing

### Default Credentials (Development)

- **Username**: `admin`
- **Password**: `ciris_admin_password`
- **Role**: AUTHORITY (for API access)

## Integration Points

### Service Dependencies

- **TimeService**: Required for timestamp operations and token expiration
- **Database**: SQLite for certificate persistence
- **Filesystem**: Encrypted key storage in `~/.ciris/`

### Adapter Integration

```python
async def _create_adapter_observer(adapter_id: str, name: str) -> WACertificate:
    """Create observer certificates for adapters (CLI, API, Discord)."""

async def _create_channel_token_for_adapter(adapter_type: str,
                                           adapter_info: dict) -> str:
    """Generate long-lived tokens for adapter authentication."""
```

### Message Bus Participation

The Authentication Service operates as a **direct call service** (not bussed) because:
- Identity verification must be consistent and authoritative
- No benefit from multiple authentication providers
- Security requires centralized certificate management

## Security Considerations

### Algorithm Confusion Prevention

```python
async def _verify_jwt_and_get_context(token: str) -> Optional[Tuple[AuthorizationContext, Optional[datetime]]]:
    """
    Implements algorithm confusion attack prevention:
    - AUTHORITY tokens MUST be verified with Ed25519
    - Gateway tokens MUST be verified with HMAC-SHA256
    """
```

### Token Security

- **Gateway Secret**: 32-byte cryptographically random secret for JWT signing
- **Encrypted Storage**: All secrets encrypted with machine-specific keys
- **Token Caching**: Memory cache for performance with automatic cleanup

### Audit Integration

```python
async def revoke_wa(wa_id: str, reason: str) -> bool:
    """WA revocation includes automatic audit trail generation."""
```

## Metrics and Monitoring

### Authentication Metrics

```python
def _collect_custom_metrics() -> Dict[str, float]:
    """Comprehensive authentication metrics collection."""
```

- **Auth Success Rate**: `auth_successes / auth_attempts`
- **Active Sessions**: Current authenticated sessions
- **Certificate Counts**: By role and status
- **Token Cache Performance**: Hit rates and memory usage

### Health Checks

```python
async def is_healthy() -> bool:
    """Database connectivity and service status verification."""
```

## Production Considerations

### OAuth Integration

- **Callback URL Format**: `https://agents.ciris.ai/v1/auth/oauth/{agent_id}/{provider}/callback`
- **Supported Providers**: Google, GitHub, Discord (via adapter configuration)
- **Auto-Minting**: Automatic WA creation for OAuth users

### Performance Optimizations

- **Token Caching**: In-memory cache for frequent verifications
- **Database Indexing**: Optimized queries on `wa_id`, `jwt_kid`, `oauth_provider`
- **Key Derivation**: Cached machine-specific encryption keys

### Security Hardening

- **Rate Limiting**: Should be implemented at adapter level
- **Secret Rotation**: Gateway secret supports hot rotation
- **Key Storage**: Encrypted at rest with machine-specific derivation

## Migration Path: .py to Module Structure

**Current Status**: Single file implementation (`authentication.py`)
**Recommended Structure**:

```
authentication/
├── __init__.py              # Service export
├── service.py              # Main AuthenticationService class
├── models.py               # WA certificate operations
├── tokens.py               # Token generation and verification
├── crypto.py               # Cryptographic operations
└── bootstrap.py            # System initialization
```

**Benefits of Modularization**:
- Clearer separation of concerns
- Easier testing and maintenance
- Better IDE navigation
- Reduced file size for individual components

## Future Enhancements

### Veilid Integration

The service includes placeholder support for Veilid distributed identity:

```python
veilid_id: Optional[str] = None  # Future decentralized identity
```

### Advanced Permission Systems

- **Custom Permissions**: `custom_permissions_json` field ready for extension
- **Resource-Specific Access**: Permission metadata supports fine-grained control
- **Time-Based Permissions**: Expiration support in permission model

### Multi-Tenant Support

- **Adapter Isolation**: Channel tokens provide tenant-specific authentication
- **Namespace Support**: WA IDs designed for tenant prefixing
- **Role Inheritance**: Trust chain supports organizational hierarchies

---

**The Authentication Service stands as the ethical foundation of CIRIS, ensuring that every interaction is grounded in verified identity, transparent permissions, and cryptographic accountability—essential requirements for AI systems designed to serve diverse sentient beings across millennial timescales.**
