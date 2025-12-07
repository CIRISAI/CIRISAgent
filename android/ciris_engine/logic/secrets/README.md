# CIRIS Engine - Secrets Management Module

## Overview

The Secrets Management module provides comprehensive protection for sensitive information within the CIRIS agent system. It automatically detects, encrypts, and manages secrets across all agent operations, ensuring that sensitive data is never exposed in logs, persistence, or external communications.

## Architecture

### Core Components

1. **SecretsFilter** (`filter.py`)
   - Pattern-based detection engine
   - Built-in patterns for common secrets (API keys, passwords, tokens)
   - Custom pattern support with agent-configurable rules
   - Context-aware filtering based on security levels

2. **SecretsEncryption** (`encryption.py`)
   - AES-256-GCM encryption for all stored secrets
   - Per-secret encryption keys with secure key derivation
   - Cryptographically secure random initialization vectors

3. **SecretsStore** (`store.py`)
   - SQLite-based encrypted storage backend
   - Atomic operations with transaction support
   - Rate limiting and access control
   - Comprehensive audit logging

4. **SecretsService** (`service.py`)
   - Unified interface for secrets operations
   - Automatic detection and encryption pipeline
   - Context-aware decapsulation
   - Integration with message processing

5. **SecretTools** (`tools.py`)
   - Agent-accessible tools for secret management
   - RECALL_SECRET: Retrieve stored secrets with audit
   - UPDATE_SECRETS_FILTER: Configure detection patterns
   - LIST_SECRETS: Inventory management

## Key Features

### Automatic Detection
- Real-time scanning of all incoming messages
- Pattern matching for 12+ built-in secret types
- False positive reduction through context analysis
- Configurable sensitivity levels

### Secure Storage
- Military-grade AES-256-GCM encryption
- Per-secret encryption keys
- Secure key derivation using PBKDF2
- Protected metadata storage

### Seamless Integration
- Transparent operation with existing workflows
- Automatic encryption during MEMORIZE operations
- Automatic decryption during RECALL operations
- Natural language processing preservation

### Comprehensive Audit Trail
- All secret access logged with timestamps
- Operation tracking (store, retrieve, update)
- Success/failure status recording
- Integration with signed audit system

## Usage

### Message Pipeline Integration

The secrets system automatically processes all incoming messages:

```python
# In observers (Discord, CLI, API)
filtered_content, secret_refs = secrets_service.filter_message(
    content=message.content,
    context_id=str(message.id)
)
```

### Graph Memory Integration

Secrets are naturally handled through memory operations:

```python
# During MEMORIZE - automatic encryption
result = memory_service.memorize(
    content="API key: sk-1234...",  # Automatically detected and encrypted
    metadata={"type": "credentials"}
)

# During RECALL - automatic decryption
memories = memory_service.recall(
    query="API credentials",
    action_type="TOOL"  # Decrypts if action requires it
)
```

### Direct Service Usage

```python
# Initialize service
secrets_service = SecretsService(
    store=secrets_store,
    llm_service=llm_service,
    audit_service=audit_service
)

# Filter content
filtered, refs = secrets_service.filter_message(content, context_id)

# Retrieve secret
secret_value = await secrets_service.retrieve_secret(
    secret_id=ref.secret_id,
    context=context
)
```

## Security Considerations

1. **Encryption Keys**: Never stored in plaintext, derived using PBKDF2
2. **Access Control**: All retrievals require valid context and are audited
3. **Pattern Updates**: Only WA-approved updates to detection patterns
4. **Cleanup**: Automatic cleanup of orphaned secrets
5. **Memory Safety**: Secrets never held in memory longer than necessary

## Configuration

Secrets behavior is configured through the agent's configuration:

```yaml
secrets:
  encryption:
    algorithm: "AES-256-GCM"
    key_derivation: "PBKDF2"
    iterations: 100000
  detection:
    sensitivity: "medium"  # low, medium, high
    custom_patterns: []
  storage:
    cleanup_days: 30
    max_secrets: 10000
```

## Testing

The module includes comprehensive test coverage:

- Unit tests for each component
- Integration tests for pipeline flows
- Security tests for encryption/decryption
- Performance tests for pattern matching

Run tests:
```bash
pytest tests/ciris_engine/secrets/
```

## Future Enhancements

1. **Pattern Learning**: ML-based pattern discovery
2. **Format Preservation**: Maintain secret formats for specific use cases
3. **Key Rotation**: Automated re-encryption with new keys
4. **External Vaults**: Integration with HashiCorp Vault, AWS Secrets Manager
5. **Homomorphic Operations**: Compute on encrypted secrets

## Dependencies

- `cryptography`: Encryption operations
- `sqlite3`: Storage backend
- `pydantic`: Data models
- `asyncio`: Async operations

## Related Modules

- **Audit**: Provides audit trail for secret operations
- **Graph Memory**: Integrates with memory storage
- **Action Handlers**: Consume decrypted secrets
- **Telemetry**: Monitors secret operation metrics
