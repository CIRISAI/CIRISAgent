# CIRIS Agent Secrets Management System

## Overview

The CIRIS Agent Secrets Management System provides automated detection, secure storage, and controlled access to sensitive information while maintaining the agent's ability to reason about and use secrets safely. The system operates transparently, automatically detecting potential secrets and replacing them with UUID references.

## Core Security Principles

1. **Automatic Detection**: Secrets are automatically detected and filtered before entering the thought pipeline
2. **Zero-Knowledge Storage**: Secrets are encrypted at rest with per-secret keys
3. **Agent Self-Service**: The agent can manage its own secrets detection rules
4. **Contextual Access**: Secrets are decapsulated only when needed for specific actions
5. **Audit Trail**: All secret access is logged with full traceability
6. **Fail Secure**: Any failure defaults to keeping secrets protected
7. **Native Memory Integration**: RECALL, MEMORIZE, and FORGET work natively with secrets via graph memory
8. **Auto-Forget**: Secrets automatically FORGET after task completion unless explicitly MEMORIZEd

## Architecture

```mermaid
graph TB
    subgraph "Input Pipeline"
        MSG[Incoming Message] --> PII[PII Filter]
        PII --> SEC[Secrets Filter]
        SEC --> STOR[Secrets Store]
        SEC --> CTX[Context Builder]
    end

    subgraph "Secrets Store"
        STOR --> ENC[AES-256-GCM Encryption]
        ENC --> DB[(Encrypted Database)]
        STOR --> IDX[UUID Index]
        IDX --> META[Metadata Store]
    end

    subgraph "Agent Interface"
        CTX --> SNAP[System Snapshot]
        SNAP --> AGT[Agent Reasoning]
        AGT --> REC[RECALL Tool]
        AGT --> UPD[UPDATE_SECRETS Tool]
        REC --> STOR
        UPD --> SEC
    end

    subgraph "Action Pipeline"
        AGT --> ACT[Action Handlers]
        ACT --> DEC[Secret Decapsulation]
        DEC --> STOR
        DEC --> EXT[External Systems]
    end
```

## Secrets Detection and Storage

### Automatic Detection Patterns

The secrets filter automatically detects and protects:

```yaml
secret_patterns:
  api_keys:
    - pattern: "(?i)api[_-]?key[s]?[\\s:=]+['\"]?([a-z0-9]{20,})['\"]?"
    - description: "API Key"
    - sensitivity: HIGH

  tokens:
    - pattern: "(?i)bearer[\\s]+([a-z0-9\\-_.]{20,})"
    - description: "Bearer Token"
    - sensitivity: HIGH

  passwords:
    - pattern: "(?i)password[s]?[\\s:=]+['\"]?([^\\s'\"]{8,})['\"]?"
    - description: "Password"
    - sensitivity: CRITICAL

  urls_with_auth:
    - pattern: "https?://[^:]+:[^@]+@[^\\s]+"
    - description: "URL with Authentication"
    - sensitivity: HIGH

  private_keys:
    - pattern: "-----BEGIN [A-Z ]+PRIVATE KEY-----"
    - description: "Private Key"
    - sensitivity: CRITICAL

  credit_cards:
    - pattern: "\\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\\b"
    - description: "Credit Card Number"
    - sensitivity: CRITICAL

  social_security:
    - pattern: "\\b\\d{3}-\\d{2}-\\d{4}\\b"
    - description: "Social Security Number"
    - sensitivity: CRITICAL

  custom:
    - pattern: "{AGENT_DEFINED}"
    - description: "{AGENT_DEFINED}"
    - sensitivity: "{AGENT_DEFINED}"
```

### Storage Schema

```python
class SecretRecord(BaseModel):
    """Encrypted secret storage record"""
    secret_uuid: str = Field(description="UUID identifier for the secret")
    encrypted_value: bytes = Field(description="AES-256-GCM encrypted secret value")
    encryption_key_ref: str = Field(description="Reference to encryption key in secure store")
    salt: bytes = Field(description="Cryptographic salt")
    nonce: bytes = Field(description="AES-GCM nonce")

    # Metadata (not encrypted)
    description: str = Field(description="Human-readable description")
    sensitivity_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    detected_pattern: str = Field(description="Pattern that detected this secret")
    context_hint: str = Field(description="Safe context description")

    # Audit fields
    created_at: datetime
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    source_message_id: Optional[str] = None

    # Access control
    auto_decapsulate_for_actions: List[str] = Field(default_factory=list)
    manual_access_only: bool = False

class SecretsFilter(BaseModel):
    """Agent-configurable secrets detection rules"""
    filter_id: str = Field(description="Unique identifier for this filter set")
    version: int = Field(description="Version number for updates")

    # Built-in patterns (always active)
    builtin_patterns_enabled: bool = True

    # Agent-defined custom patterns
    custom_patterns: List[SecretPattern] = Field(default_factory=list)

    # Pattern overrides
    disabled_patterns: List[str] = Field(default_factory=list)
    sensitivity_overrides: Dict[str, str] = Field(default_factory=dict)

    # Behavioral settings
    require_confirmation_for: List[str] = Field(default=["CRITICAL"])
    auto_decrypt_for_actions: List[str] = Field(default=["speak", "tool"])

class SecretPattern(BaseModel):
    """Agent-defined secret detection pattern"""
    name: str = Field(description="Pattern name")
    regex: str = Field(description="Regular expression pattern")
    description: str = Field(description="Human-readable description")
    sensitivity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    context_hint: str = Field(description="Safe description for context")
    enabled: bool = True
```

## Agent Tools

### Native Memory Operations

Secrets integrate natively with CIRIS graph memory operations:

- **RECALL**: Can recall previously stored secrets by UUID or semantic search
- **MEMORIZE**: Explicitly stores secrets in long-term memory across task boundaries
- **FORGET**: Removes secrets from storage (also happens automatically after task completion)

#### Automatic FORGET Behavior

By default, all secrets detected during a task are automatically removed from storage when the task completes, unless:

1. The agent explicitly performs a **MEMORIZE** action on the secret
2. The secret is marked with `long_term_storage: true` in its metadata
3. The secret is referenced in a **MEMORIZE** action for related information

This ensures secrets have minimal exposure time while allowing the agent to explicitly retain important secrets for future use.

```python
# Example: Agent explicitly memorizes an important secret
{
    "selected_action": "memorize",
    "action_parameters": {
        "content": "SECRET_550e8400-e29b-41d4-a716-446655440000 is the production API key for the primary service",
        "tags": ["api_key", "production", "primary_service"],
        "importance": "HIGH"
    }
}
```

### RECALL_SECRET Tool

Allows the agent to retrieve a secret for reasoning:

```python
class RecallSecretParams(BaseModel):
    """Parameters for RECALL_SECRET tool"""
    secret_uuid: str = Field(description="UUID of the secret to recall")
    purpose: str = Field(description="Why the secret is needed (for audit)")
    decrypt: bool = Field(default=False, description="Whether to decrypt the secret value")

# Usage in action selection:
{
    "selected_action": "tool",
    "action_parameters": {
        "name": "recall_secret",
        "parameters": {
            "secret_uuid": "550e8400-e29b-41d4-a716-446655440000",
            "purpose": "Need API key to make external request",
            "decrypt": true
        }
    }
}
```

### UPDATE_SECRETS_FILTER Tool

Allows the agent to modify its secrets detection rules:

```python
class UpdateSecretsFilterParams(BaseModel):
    """Parameters for UPDATE_SECRETS_FILTER tool"""
    operation: Literal["add_pattern", "remove_pattern", "update_pattern", "get_current"]

    # For add_pattern/update_pattern
    pattern: Optional[SecretPattern] = None

    # For remove_pattern
    pattern_name: Optional[str] = None

    # For configuration changes
    config_updates: Optional[Dict[str, Any]] = None

# Examples:

# Add a new pattern
{
    "selected_action": "tool",
    "action_parameters": {
        "name": "update_secrets_filter",
        "parameters": {
            "operation": "add_pattern",
            "pattern": {
                "name": "slack_webhook",
                "regex": "https://hooks\\.slack\\.com/services/[A-Z0-9]{9}/[A-Z0-9]{11}/[a-zA-Z0-9]{24}",
                "description": "Slack Webhook URL",
                "sensitivity": "HIGH",
                "context_hint": "Slack integration webhook"
            }
        }
    }
}

# Get current filter configuration
{
    "selected_action": "tool",
    "action_parameters": {
        "name": "update_secrets_filter",
        "parameters": {
            "operation": "get_current"
        }
    }
}

# Update sensitivity levels
{
    "selected_action": "tool",
    "action_parameters": {
        "name": "update_secrets_filter",
        "parameters": {
            "operation": "update_config",
            "config_updates": {
                "auto_decrypt_for_actions": ["speak", "tool", "memorize"],
                "sensitivity_overrides": {
                    "api_keys": "CRITICAL"
                }
            }
        }
    }
}
```

## Context Integration

### Secret References in Context

When secrets are detected, they're replaced with references in the context:

```python
# Original message:
"Please use API key sk-abc123def456 to call the OpenAI API"

# After secrets filtering:
"Please use API key SECRET_550e8400-e29b-41d4-a716-446655440000 (API Key) to call the OpenAI API"

# In SystemSnapshot:
{
    "detected_secrets": [
        {
            "uuid": "550e8400-e29b-41d4-a716-446655440000",
            "description": "API Key",
            "context_hint": "OpenAI API authentication",
            "sensitivity": "HIGH",
            "auto_decapsulate": ["speak", "tool"]
        }
    ]
}
```

### Automatic Decapsulation

During action execution, secrets are automatically decapsulated if configured:

```python
# Agent action:
{
    "selected_action": "tool",
    "action_parameters": {
        "name": "http_request",
        "parameters": {
            "url": "https://api.openai.com/v1/models",
            "headers": {
                "Authorization": "Bearer SECRET_550e8400-e29b-41d4-a716-446655440000"
            }
        }
    }
}

# Before execution, automatically becomes:
{
    "url": "https://api.openai.com/v1/models",
    "headers": {
        "Authorization": "Bearer sk-abc123def456"
    }
}
```

## Security Controls

### Encryption at Rest

```python
class SecretsEncryption:
    """Handles encryption/decryption of secrets"""

    def encrypt_secret(self, value: str) -> Tuple[bytes, bytes, bytes]:
        """
        Returns: (encrypted_value, salt, nonce)
        Uses AES-256-GCM with per-secret keys derived from master key + salt
        """

    def decrypt_secret(self, encrypted_value: bytes, salt: bytes, nonce: bytes) -> str:
        """
        Decrypts secret value using master key + salt
        """

    def rotate_master_key(self) -> None:
        """
        Rotates master encryption key and re-encrypts all secrets
        """
```

### Access Audit

```python
class SecretAccessLog(BaseModel):
    """Audit log for secret access"""
    access_id: str = Field(description="Unique access identifier")
    secret_uuid: str = Field(description="Secret that was accessed")
    access_type: Literal["VIEW", "DECRYPT", "UPDATE", "DELETE"]
    accessor: str = Field(description="Who/what accessed the secret")
    purpose: str = Field(description="Stated purpose for access")
    timestamp: datetime
    source_ip: Optional[str] = None
    user_agent: Optional[str] = None
    action_context: Optional[str] = None
    success: bool = True
    failure_reason: Optional[str] = None
```

### Rate Limiting

```python
class SecretAccessControl:
    """Controls access to secrets with rate limiting"""

    max_accesses_per_minute: int = 10
    max_accesses_per_hour: int = 100
    max_decryptions_per_hour: int = 20

    critical_secrets_require_confirmation: bool = True
    auto_decrypt_enabled: bool = True
```

## Integration Points

### 1. Message Processing Pipeline

```python
# In message handler:
async def process_incoming_message(self, message: IncomingMessage) -> IncomingMessage:
    # Apply PII filter first
    filtered_message = await self.pii_filter.filter(message)

    # Apply secrets filter
    secrets_result = await self.secrets_filter.filter(filtered_message)

    # Store detected secrets
    for secret in secrets_result.detected_secrets:
        await self.secrets_store.store_secret(secret)

    # Return message with secret references
    return secrets_result.filtered_message
```

### 2. SystemSnapshot Integration

```python
class SystemSnapshot(BaseModel):
    # Existing fields...

    # New secrets information
    detected_secrets: List[SecretReference] = Field(default_factory=list)
    secrets_filter_version: int = 0
    total_secrets_stored: int = 0

class SecretReference(BaseModel):
    """Non-sensitive reference to a stored secret"""
    uuid: str
    description: str
    context_hint: str
    sensitivity: str
    auto_decapsulate_actions: List[str]
    created_at: datetime
    last_accessed: Optional[datetime]
```

### 3. Action Handler Integration

```python
# In base action handler:
async def handle(self, result: ActionSelectionResult, thought: Thought, context: Dict[str, Any]):
    # Automatically decapsulate secrets in action parameters
    decapsulated_params = await self.secrets_service.decapsulate_secrets(
        result.action_parameters,
        action_type=result.selected_action,
        context=context
    )

    # Continue with normal handler logic using decapsulated parameters
    await self._execute_action(decapsulated_params, thought, context)
```

## Configuration

```yaml
# config/secrets.yaml
secrets:
  enabled: true

  storage:
    database_path: "${SECRETS_DB_PATH:/var/lib/ciris/secrets.db}"
    encryption_key: "${SECRETS_MASTER_KEY}"
    key_rotation_days: 90

  detection:
    builtin_patterns: true
    custom_patterns_enabled: true
    sensitivity_threshold: "MEDIUM"

  access_control:
    max_accesses_per_minute: 10
    max_accesses_per_hour: 100
    max_decryptions_per_hour: 20
    require_confirmation_for: ["CRITICAL"]

  audit:
    log_all_access: true
    log_path: "${SECRETS_AUDIT_LOG:/var/log/ciris/secrets.log}"
    retention_days: 365

  auto_decapsulation:
    enabled: true
    allowed_actions: ["speak", "tool", "memorize"]
    require_purpose: true
```

## Security Guarantees

1. **Encryption**: All secrets encrypted with AES-256-GCM
2. **Key Management**: Master keys rotated every 90 days
3. **Access Control**: Rate limiting and confirmation requirements
4. **Audit Trail**: Complete logging of all secret access
5. **Zero Trust**: Secrets never stored or transmitted in plaintext
6. **Agent Control**: Agent can manage its own detection rules
7. **Fail Secure**: Any error defaults to protecting secrets
8. **Forward Secrecy**: Old secrets remain protected after key rotation

## Testing Requirements

- [ ] All secret patterns correctly detect test secrets
- [ ] Encryption/decryption works correctly
- [ ] Rate limiting prevents abuse
- [ ] Audit logging captures all access
- [ ] Agent tools work correctly
- [ ] Integration with existing pipeline works
- [ ] Performance impact is minimal (<1% overhead)
- [ ] Security review passes all tests

This secrets management system ensures that CIRIS can safely handle sensitive information while maintaining full transparency with the agent about what secrets it has access to and how they can be used.

---

*Copyright © 2025 Eric Moore and CIRIS L3C - AGPL-3.0 License*
