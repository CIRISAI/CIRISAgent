# Secrets Service Telemetry

## Overview
The Secrets Service manages the detection, encryption, storage, and retrieval of sensitive information within CIRIS Agent. It provides comprehensive telemetry for security auditing, compliance monitoring, and operational health tracking. The service operates with three main components: SecretsFilter (detection), SecretsStore (encrypted storage), and SecretsService (coordination layer).

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| total_secrets | counter | in-memory calculation | on store/delete | `get_service_stats()` |
| active_filters | counter | in-memory count | on filter config | `get_service_stats()` |
| filter_matches_today | counter | filter statistics | on secret detection | `get_service_stats()` |
| last_filter_update | timestamp | filter configuration | on config update | `get_service_stats()` |
| encryption_enabled | boolean | service state | constant | `get_service_stats()` |
| secrets_stored | gauge | in-memory tracker | on store/delete | `get_status().metrics` |
| filter_enabled | boolean | service state | constant | `get_status().metrics` |
| auto_forget_enabled | boolean | service configuration | on config change | `get_status().metrics` |
| request_count | counter | base service | per operation | `get_status().metrics` |
| error_count | counter | base service | on error | `get_status().metrics` |
| error_rate | calculated | base service | continuous | `get_status().metrics` |
| uptime_seconds | gauge | base service | continuous | `get_status().metrics` |
| access_count | counter | per secret | on secret access | database query |
| last_accessed | timestamp | per secret | on secret access | database query |
| detection_patterns | list | filter configuration | on config update | `get_filter_config()` |
| sensitivity_levels | enum counts | stored secrets | on detection | database aggregation |
| encryption_operations | counter | store operations | per encrypt/decrypt | internal tracking |
| key_rotation_count | counter | encryption service | on reencrypt | internal tracking |

## Data Structures

### SecretsServiceStats
```python
{
    "total_secrets": 25,                    # Total secrets in encrypted storage
    "active_filters": 12,                   # Number of enabled detection patterns
    "filter_matches_today": 8,              # Secrets detected today
    "last_filter_update": "2025-08-14T10:30:00Z",  # Last configuration change
    "encryption_enabled": true              # Whether encryption is active
}
```

### ServiceStatus Metrics
```python
{
    "secrets_stored": 3.0,                  # Current task secrets (volatile)
    "filter_enabled": 1.0,                  # Filter component available
    "auto_forget_enabled": 1.0,             # Auto-cleanup enabled
    "uptime_seconds": 86400.0,              # Service runtime
    "request_count": 145.0,                 # Total operations performed
    "error_count": 2.0,                     # Operations that failed
    "error_rate": 0.0138                    # Failure rate percentage
}
```

### SecretReference Metadata
```python
{
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "description": "API Key for external service",
    "context_hint": "Configuration file",
    "sensitivity": "HIGH",                  # LOW, MEDIUM, HIGH, CRITICAL
    "detected_pattern": "api_key",          # Detection pattern name
    "auto_decapsulate_actions": ["tool"],   # Allowed auto-use contexts
    "created_at": "2025-08-14T13:25:00Z",
    "last_accessed": "2025-08-14T13:30:00Z"
}
```

### Detection Configuration
```python
{
    "patterns": {
        "api_key": {
            "enabled": true,
            "pattern": r"[A-Za-z0-9]{32,}",
            "sensitivity": "HIGH",
            "description": "API Key Pattern"
        },
        "password": {
            "enabled": true,
            "pattern": r"password\s*[:=]\s*[\"']?([^\"'\s]+)",
            "sensitivity": "CRITICAL",
            "description": "Password in Configuration"
        }
    },
    "sensitivity_config": {
        "CRITICAL": {
            "auto_decapsulate_actions": [],     # No automatic use
            "require_manual_access": true
        },
        "HIGH": {
            "auto_decapsulate_actions": ["tool"],
            "require_manual_access": false
        },
        "MEDIUM": {
            "auto_decapsulate_actions": ["tool", "speak"],
            "require_manual_access": false
        },
        "LOW": {
            "auto_decapsulate_actions": ["tool", "speak", "memorize"],
            "require_manual_access": false
        }
    }
}
```

### Secret Access Log
```python
{
    "secret_id": "550e8400-e29b-41d4-a716-446655440000",
    "operation": "decrypt",                 # store, retrieve, decrypt, delete
    "requester_id": "agent",                # Who accessed the secret
    "granted": true,                        # Whether access was allowed
    "reason": "auto_decapsulate_tool",      # Access justification
    "context": {
        "operation": "tool_execution",
        "channel_id": "general",
        "user_id": "user123",
        "request_id": "req_456"
    },
    "timestamp": "2025-08-14T13:30:00Z"
}
```

### Encryption Metrics
```python
{
    "encryption_algorithm": "AES-256-GCM",
    "key_derivation": "PBKDF2",
    "salt_length": 16,                      # bytes
    "nonce_length": 12,                     # bytes
    "operations_per_second": 150.5,        # encryption throughput
    "key_rotation_interval": 2592000,      # seconds (30 days)
    "last_key_rotation": "2025-07-15T00:00:00Z"
}
```

## API Access Patterns

### Current Access
- **No Direct REST API**: Secrets service accessed via service registry
- **Internal Protocol**: SecretsServiceProtocol for service-to-service communication
- **Security Boundary**: No direct external access to prevent data exposure

### Recommended Endpoints

#### Get Service Statistics
```
GET /v1/telemetry/secrets/stats
```
Returns operational statistics without exposing secret data:
```json
{
    "total_secrets": 25,
    "active_filters": 12,
    "filter_matches_today": 8,
    "last_filter_update": "2025-08-14T10:30:00Z",
    "encryption_enabled": true,
    "uptime_seconds": 86400.0,
    "operations_completed": 145,
    "error_rate": 0.0138
}
```

#### Get Detection Configuration
```
GET /v1/telemetry/secrets/config
```
Returns filter configuration (patterns sanitized):
```json
{
    "patterns_enabled": ["api_key", "password", "token"],
    "sensitivity_distribution": {
        "CRITICAL": 5,
        "HIGH": 12,
        "MEDIUM": 6,
        "LOW": 2
    },
    "auto_decapsulation_rules": {
        "tool": ["LOW", "MEDIUM", "HIGH"],
        "speak": ["LOW", "MEDIUM"],
        "memorize": ["LOW"]
    }
}
```

#### Get Access Audit Log
```
GET /v1/telemetry/secrets/audit
```
Query parameters:
- `hours`: 1|24|168 (1h, 1d, 1w)
- `operation`: store|retrieve|decrypt|delete
- `requester`: agent|user|system

Returns access log entries:
```json
{
    "period": "24h",
    "total_accesses": 45,
    "operations": {
        "store": 8,
        "retrieve": 25,
        "decrypt": 12,
        "delete": 0
    },
    "access_patterns": [
        {
            "hour": "13:00",
            "accesses": 5,
            "operations": ["retrieve", "decrypt"]
        }
    ]
}
```

#### Check Service Health
```
GET /v1/telemetry/secrets/health
```
Returns health status and component availability:
```json
{
    "healthy": true,
    "components": {
        "encryption": "operational",
        "storage": "operational",
        "filter": "operational"
    },
    "warnings": [],
    "last_error": null,
    "database_size_mb": 5.2,
    "memory_usage_mb": 12.8
}
```

## Graph Storage

### Memory Graph Integration
The Secrets Service integrates with CIRIS memory graph for telemetry persistence:

#### Metrics Nodes
- **SecretOperationMetric**: Stores operation counts and timing
- **EncryptionPerformanceMetric**: Tracks encryption/decryption performance
- **FilterEffectivenessMetric**: Pattern match rates and accuracy

#### Relationships
- `SECRET_DETECTED` → Links detection events to source content
- `ACCESS_GRANTED` → Links access events to requesting service
- `ENCRYPTION_PERFORMED` → Links encryption operations to storage events

#### Graph Queries
```cypher
// Recent secret detections by pattern
MATCH (m:SecretOperationMetric)-[:DETECTED_BY]->(p:Pattern)
WHERE m.timestamp > datetime() - duration('PT1H')
RETURN p.name, count(m) as detections

// High-sensitivity secret access patterns
MATCH (s:Secret {sensitivity: 'CRITICAL'})-[:ACCESSED_BY]->(a:AccessEvent)
WHERE a.timestamp > datetime() - duration('P1D')
RETURN a.requester, count(a) as access_count
```

## Example Usage

### Get Current Service Statistics
```python
secrets_service = get_service(ServiceType.SECRETS)
stats = await secrets_service.get_service_stats()

print(f"Total secrets stored: {stats.total_secrets}")
print(f"Active detection filters: {stats.active_filters}")
print(f"Encryption enabled: {stats.encryption_enabled}")
```

### Monitor Detection Activity
```python
# Check service status for runtime metrics
status = secrets_service.get_status()
print(f"Recent operations: {status.metrics['request_count']}")
print(f"Error rate: {status.metrics['error_rate']:.2%}")
```

### Track Secret Lifecycle
```python
# Process text and monitor detections
filtered_text, secret_refs = await secrets_service.process_incoming_text(
    text="API key: sk_test_abc123xyz789",
    source_message_id="msg_001"
)

for ref in secret_refs:
    print(f"Detected {ref.sensitivity} secret: {ref.description}")
    print(f"Pattern: {ref.detected_pattern}")
    print(f"Auto-decapsulate for: {ref.auto_decapsulate_actions}")
```

### Audit Secret Access
```python
# Recall secret with audit trail
result = await secrets_service.recall_secret(
    secret_uuid="550e8400-e29b-41d4-a716-446655440000",
    purpose="tool_execution",
    accessor="agent",
    decrypt=True
)

if result and result.found:
    print(f"Secret retrieved successfully")
    # Access logged automatically in audit trail
```

### Monitor Encryption Performance
```python
# Direct encryption operations
encrypted = await secrets_service.encrypt("sensitive_data")
decrypted = await secrets_service.decrypt(encrypted)

# Performance tracked in internal metrics
# Access via custom telemetry endpoint
```

## Testing

### Test Files
- `tests/logic/secrets/test_service.py`
- `tests/logic/secrets/test_store.py`
- `tests/logic/secrets/test_filter.py`
- `tests/integration/test_secrets_workflow.py`

### Validation Steps
1. Start secrets service and verify component initialization
2. Test secret detection and storage workflow
3. Verify encryption/decryption operations
4. Test access controls and audit logging
5. Check telemetry data collection accuracy
6. Validate service statistics calculation

```python
async def test_secrets_telemetry():
    service = SecretsService(
        time_service=time_service,
        db_path=":memory:",
        detection_config=test_config
    )

    await service.start()

    # Test secret detection telemetry
    initial_stats = await service.get_service_stats()
    assert initial_stats.total_secrets == 0

    # Process text with secrets
    filtered_text, refs = await service.process_incoming_text(
        "Password: secret123",
        "test_message"
    )

    # Verify telemetry updated
    updated_stats = await service.get_service_stats()
    assert updated_stats.total_secrets == 1
    assert len(refs) == 1

    # Test access telemetry
    result = await service.recall_secret(
        refs[0].uuid,
        purpose="testing",
        decrypt=True
    )
    assert result.found is True

    # Verify status metrics
    status = service.get_status()
    assert status.metrics["request_count"] >= 2.0
    assert status.metrics["secrets_stored"] == 1.0
```

## Configuration

### Detection Patterns
- **Default Patterns**: API keys, passwords, tokens, connection strings
- **Custom Patterns**: User-defined regex patterns via configuration
- **Sensitivity Mapping**: Pattern → sensitivity level assignment
- **Update Frequency**: Configuration changes applied immediately

### Encryption Settings
- **Algorithm**: AES-256-GCM (fixed for security)
- **Key Derivation**: PBKDF2 with configurable iterations
- **Salt/Nonce**: Randomly generated per secret
- **Master Key**: Configurable, auto-generated if not provided

### Storage Configuration
```python
SecretsStore:
    db_path: str = "secrets.db"              # SQLite database location
    master_key: Optional[bytes] = None       # Encryption master key
    max_accesses_per_minute: int = 10        # Rate limiting
    max_accesses_per_hour: int = 100         # Hourly access limit
```

### Auto-Decapsulation Rules
```python
# Based on sensitivity level
CRITICAL: []                                 # Manual access only
HIGH: ["tool"]                              # Tool actions only
MEDIUM: ["tool", "speak"]                   # Tool and communication
LOW: ["tool", "speak", "memorize"]          # Most actions allowed
```

## Known Limitations

1. **No Cross-Instance Sharing**: Secrets not shared between service instances
2. **Database-Only Persistence**: No distributed storage or clustering
3. **Rate Limiting Per Instance**: Access limits not coordinated across instances
4. **Pattern Performance**: Complex regex patterns may impact detection speed
5. **Memory Leakage**: Task secrets held in memory until auto-forget triggered
6. **No Backup Encryption**: Database backups contain encrypted but recoverable data
7. **Limited Audit Retention**: Access logs stored in same database as secrets

## Future Enhancements

1. **Distributed Secret Store**: Multi-instance secret sharing with consensus
2. **Advanced Analytics**: ML-based secret detection and anomaly detection
3. **Key Management Service**: External key management and rotation
4. **Compliance Reporting**: Automated compliance report generation
5. **Performance Optimization**: Async encryption and bulk operations
6. **Audit Log Separation**: Dedicated audit database with longer retention
7. **Real-Time Monitoring**: WebSocket-based telemetry streaming
8. **Secret Expiration**: Automatic secret lifecycle management

## Integration Points

- **TimeService**: Provides consistent timestamps for all operations
- **Memory Graph**: Stores telemetry metrics and audit events
- **All Services**: Can detect secrets in their input/output via service protocol
- **Communication Bus**: Filters outgoing messages for secret leakage
- **Action Pipeline**: Automatic secret decapsulation during action execution
- **Configuration Service**: Stores detection patterns and sensitivity rules

## Monitoring Recommendations

1. **Security Alerts**: Monitor for unauthorized secret access attempts
2. **Detection Effectiveness**: Track pattern match rates and false positives
3. **Performance Monitoring**: Watch encryption operation timing and throughput
4. **Storage Growth**: Alert on rapid secret accumulation indicating leakage
5. **Error Rate Tracking**: Monitor encryption/decryption failure rates
6. **Access Pattern Analysis**: Identify unusual secret access patterns
7. **Configuration Drift**: Alert on unexpected filter configuration changes

## Performance Considerations

1. **Database Operations**: SQLite operations are synchronous and may block
2. **Encryption Overhead**: AES-GCM encryption adds ~100μs per operation
3. **Pattern Matching**: Complex regex patterns can cause processing delays
4. **Memory Usage**: Each secret reference consumes ~200 bytes in memory
5. **Access Rate Limits**: Built-in throttling prevents DoS but may delay operations
6. **Transaction Isolation**: Database locks may serialize concurrent operations

## Security Considerations

1. **Master Key Protection**: Master key stored in memory, vulnerable to memory dumps
2. **Database File Security**: SQLite file contains encrypted data but metadata is plain
3. **Access Log Privacy**: Audit logs may contain sensitive context information
4. **Memory Cleanup**: Plaintext secrets temporarily held in memory during processing
5. **Error Message Leakage**: Error logs must not contain decrypted secret values
6. **Side Channel Attacks**: Timing attacks possible on encryption operations

## Compliance Integration

The Secrets Service supports various compliance frameworks:

- **GDPR**: Right to erasure via `forget_secret()` method
- **SOX**: Complete audit trail of all secret access events
- **HIPAA**: Encryption at rest and access controls for sensitive data
- **PCI DSS**: Secure storage and handling of payment card data
- **SOC 2**: Comprehensive logging and monitoring capabilities

## System Integration

The Secrets Service acts as a critical security component:
- Prevents accidental secret exposure in logs and communications
- Enables secure parameter passing between services
- Provides centralized secret management and audit capabilities
- Supports compliance requirements through comprehensive telemetry
- Maintains operational security through encryption and access controls

It serves as the "security membrane" of CIRIS, ensuring sensitive information is properly protected while remaining accessible for legitimate operational needs.
