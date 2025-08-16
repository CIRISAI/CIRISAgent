# Authentication Service Telemetry

## Overview
The Authentication Service provides WA (Wise Authority) certificate management, JWT token creation/verification, and cryptographic operations. It tracks authentication events, certificate lifecycle, token usage, and security metrics. The service maintains comprehensive telemetry for security auditing, performance monitoring, and operational insights.

## Telemetry Data Collected

| Metric Name | Type | Storage | Update Frequency | Access Method |
|------------|------|---------|------------------|---------------|
| active_certificates | counter | in-memory calculation | on request | `get_status().custom_metrics` |
| revoked_certificates | counter | in-memory calculation | on request | `get_status().custom_metrics` |
| observer_certificates | counter | in-memory calculation | on request | `get_status().custom_metrics` |
| user_certificates | counter | in-memory calculation | on request | `get_status().custom_metrics` |
| admin_certificates | counter | in-memory calculation | on request | `get_status().custom_metrics` |
| authority_certificates | counter | in-memory calculation | on request | `get_status().custom_metrics` |
| root_certificates | counter | in-memory calculation | on request | `get_status().custom_metrics` |
| auth_contexts_cached | gauge | in-memory cache | on request | `get_status().custom_metrics` |
| channel_tokens_cached | gauge | in-memory cache | on request | `get_status().custom_metrics` |
| total_tokens_cached | gauge | in-memory cache | on request | `get_status().custom_metrics` |
| uptime_seconds | gauge | calculated | on request | `get_status().uptime_seconds` |
| request_count | counter | BaseService tracking | per operation | `get_status().metrics` |
| error_count | counter | BaseService tracking | per operation | `get_status().metrics` |
| error_rate | gauge | calculated | on request | `get_status().metrics` |
| healthy | boolean | calculated | on request | `get_status().metrics` |
| availability | gauge | calculated | on request | BaseInfrastructureService |

## Data Structures

### ServiceStatus (Authentication Service)
```python
{
    "service_name": "AuthenticationService",
    "service_type": "infrastructure_service",
    "is_healthy": true,
    "uptime_seconds": 86400.5,
    "last_error": null,
    "metrics": {
        "certificate_count": 15,
        "cached_tokens": 3,
        "active_sessions": 0,
        "uptime_seconds": 86400.5,
        "request_count": 234,
        "error_count": 2,
        "error_rate": 0.0085,
        "healthy": 1.0
    },
    "custom_metrics": {
        "active_certificates": 15,
        "revoked_certificates": 2,
        "observer_certificates": 8,
        "user_certificates": 4,
        "admin_certificates": 2,
        "authority_certificates": 1,
        "root_certificates": 1,
        "auth_contexts_cached": 5,
        "channel_tokens_cached": 3,
        "total_tokens_cached": 8
    },
    "last_health_check": "2025-08-14T15:30:00Z"
}
```

### WA Certificate Statistics
```python
{
    "total_certificates": 15,
    "by_role": {
        "OBSERVER": 8,    # Adapter-linked observers
        "USER": 4,        # Human users
        "ADMIN": 2,       # System administrators
        "AUTHORITY": 1,   # System authority
        "ROOT": 1         # Root certificate
    },
    "by_status": {
        "active": 15,
        "revoked": 2
    },
    "by_auth_method": {
        "password": 3,
        "oauth": 5,
        "certificate": 7
    }
}
```

### Token Cache Statistics
```python
{
    "auth_contexts": {
        "cached_count": 5,
        "cache_size_estimate_mb": 0.05,
        "average_token_length": 256
    },
    "channel_tokens": {
        "cached_count": 3,
        "by_adapter": {
            "discord_default": 1,
            "api_default": 1,
            "cli_default": 1
        }
    },
    "total_cached": 8
}
```

### Authentication Events (Logged)
```python
{
    "event_type": "authentication_success|authentication_failure|token_created|wa_created|wa_revoked|key_rotation",
    "timestamp": "2025-08-14T15:30:00Z",
    "wa_id": "wa-2025-08-14-A3F2B1",
    "token_type": "channel|standard|oauth",
    "ip_address": "192.168.1.100",  # If available
    "user_agent": "CIRIS-API/1.0",  # If available
    "result": "success|failure|error",
    "error_reason": null,           # If failed
    "metadata": {}
}
```

## API Access Patterns

### Current Access
- **Internal Service Status**: Available via `get_status()` method
- **No Direct REST API**: Authentication metrics not exposed via REST endpoints
- **Service Registry**: Capabilities available via service discovery

### Recommended Endpoints

#### Get Authentication Status
```
GET /v1/telemetry/authentication/status
```
Returns complete service status with all metrics:
```json
{
    "service": {
        "name": "AuthenticationService",
        "healthy": true,
        "uptime_seconds": 86400.5,
        "last_error": null
    },
    "certificates": {
        "total_active": 15,
        "total_revoked": 2,
        "by_role": {
            "OBSERVER": 8,
            "USER": 4,
            "ADMIN": 2,
            "AUTHORITY": 1,
            "ROOT": 1
        }
    },
    "tokens": {
        "auth_contexts_cached": 5,
        "channel_tokens_cached": 3,
        "total_cached": 8
    },
    "performance": {
        "request_count": 234,
        "error_count": 2,
        "error_rate": 0.0085,
        "availability": 0.998
    }
}
```

#### Get Certificate Metrics
```
GET /v1/telemetry/authentication/certificates
```
Query parameters:
- `role`: Filter by WARole (OBSERVER|USER|ADMIN|AUTHORITY|ROOT)
- `active`: Filter by active status (true|false)
- `created_since`: ISO timestamp for recent certificates

Returns certificate statistics:
```json
{
    "total_certificates": 15,
    "active_certificates": 15,
    "revoked_certificates": 2,
    "certificates_by_role": {
        "OBSERVER": 8,
        "USER": 4,
        "ADMIN": 2,
        "AUTHORITY": 1,
        "ROOT": 1
    },
    "recent_activity": {
        "created_last_24h": 2,
        "revoked_last_24h": 0,
        "last_rotation": "2025-08-14T10:15:00Z"
    }
}
```

#### Get Authentication Events
```
GET /v1/telemetry/authentication/events
```
Query parameters:
- `event_type`: Filter by event type
- `wa_id`: Filter by specific WA
- `since`: ISO timestamp
- `limit`: Max results (default 100)

Returns authentication event log:
```json
{
    "events": [
        {
            "timestamp": "2025-08-14T15:30:00Z",
            "event_type": "authentication_success",
            "wa_id": "wa-2025-08-14-A3F2B1",
            "token_type": "channel",
            "metadata": {}
        }
    ],
    "total_count": 156,
    "filtered_count": 25
}
```

## Graph Storage

### Memory Graph Integration
The Authentication Service does not directly write to the memory graph but could benefit from telemetry integration:

#### Potential Graph Nodes
```python
# AuthenticationMetrics node type
{
    "node_type": "AuthenticationMetrics",
    "timestamp": "2025-08-14T15:30:00Z",
    "data": {
        "active_certificates": 15,
        "authentication_events_last_hour": 25,
        "failed_authentications_last_hour": 2,
        "token_verifications_last_hour": 150,
        "cache_hit_rate": 0.85
    },
    "tags": {
        "service": "authentication",
        "metric_type": "security"
    }
}

# SecurityEvent node type
{
    "node_type": "SecurityEvent",
    "timestamp": "2025-08-14T15:30:00Z",
    "data": {
        "event_type": "authentication_failure",
        "wa_id": "wa-2025-08-14-B4G3C2",
        "failure_reason": "invalid_token",
        "source_ip": "192.168.1.100",
        "risk_score": 0.3
    },
    "tags": {
        "service": "authentication",
        "event_type": "security_alert",
        "severity": "medium"
    }
}
```

### Consolidation Strategy
- **Hourly rollups**: Aggregate authentication events, token verifications, failures
- **Daily summaries**: Certificate lifecycle events, security alerts
- **Weekly reports**: Trend analysis, capacity planning metrics

## Example Usage

### Get Current Authentication Status
```python
auth_service = get_service(ServiceType.WISE_AUTHORITY)
status = auth_service.get_status()

print(f"Active certificates: {status.custom_metrics['active_certificates']}")
print(f"Cached tokens: {status.custom_metrics['total_tokens_cached']}")
print(f"Error rate: {status.metrics['error_rate']:.2%}")
print(f"Service uptime: {status.uptime_seconds / 3600:.1f} hours")
```

### Monitor Certificate Health
```python
status = auth_service.get_status()
custom = status.custom_metrics

# Check certificate distribution
if custom['root_certificates'] != 1:
    logger.error("Root certificate missing or duplicated")

if custom['authority_certificates'] == 0:
    logger.warning("No system authority certificate")

# Monitor growth
total_certs = custom['active_certificates']
if total_certs > 1000:
    logger.warning(f"High certificate count: {total_certs}")
```

### Track Authentication Performance
```python
status = auth_service.get_status()
metrics = status.metrics

# Performance monitoring
if metrics['error_rate'] > 0.05:  # 5% threshold
    logger.alert(f"High authentication error rate: {metrics['error_rate']:.2%}")

# Cache efficiency
cache_hit_ratio = metrics.get('cached_tokens', 0) / max(metrics.get('request_count', 1), 1)
if cache_hit_ratio < 0.7:  # 70% threshold
    logger.info(f"Low token cache efficiency: {cache_hit_ratio:.2%}")
```

### Security Monitoring
```python
# Check for security anomalies
status = auth_service.get_status()

# Unusual certificate patterns
if status.custom_metrics['revoked_certificates'] > status.custom_metrics['active_certificates']:
    logger.critical("More revoked than active certificates - possible security incident")

# Token cache analysis
if status.custom_metrics['total_tokens_cached'] == 0:
    logger.info("No cached tokens - cold start or cache cleared")
```

## Testing

### Test Files
- `tests/logic/services/infrastructure/test_authentication.py`
- `tests/integration/test_authentication_telemetry.py` (recommended)
- `tests/api/test_auth_metrics_endpoints.py` (recommended)

### Validation Steps
1. Start authentication service
2. Create test WA certificates
3. Generate tokens and verify caching
4. Trigger authentication events
5. Check status metrics
6. Verify certificate counts
7. Test error tracking

```python
async def test_authentication_telemetry():
    auth_service = AuthenticationService(
        db_path=":memory:",
        time_service=time_service
    )

    await auth_service.start()

    # Create test certificates
    wa = await auth_service.create_wa(
        name="Test User",
        email="test@example.com",
        scopes=["read:any"],
        role=WARole.USER
    )

    # Generate token to populate cache
    token = await auth_service.create_channel_token(wa.wa_id, "test_channel")

    # Verify token to trigger caching
    result = await auth_service.verify_token(token)
    assert result.valid

    # Check status metrics
    status = auth_service.get_status()
    assert status.custom_metrics['active_certificates'] == 1
    assert status.custom_metrics['user_certificates'] == 1
    assert status.custom_metrics['total_tokens_cached'] >= 1

    # Test revocation tracking
    await auth_service.revoke_wa(wa.wa_id, "test_revocation")

    status = auth_service.get_status()
    assert status.custom_metrics['revoked_certificates'] == 1
```

## Configuration

### Service Configuration
- **Database Path**: SQLite database for certificate storage
- **Key Directory**: Directory for cryptographic key storage (default: ~/.ciris/)
- **Cache Sizes**: Token and context cache limits (no configured limits currently)

### Telemetry Configuration
- **Status Update Frequency**: On-demand (no background updates)
- **Metric Collection**: Real-time calculation from database
- **Cache Monitoring**: Live cache size tracking

### Security Settings
```python
{
    "gateway_secret_encryption": True,     # AES-GCM encryption
    "key_derivation_iterations": 100000,   # PBKDF2 iterations
    "token_cache_enabled": True,           # Enable token caching
    "audit_authentication_events": True,  # Log auth events
    "certificate_auto_cleanup": False     # Manual certificate management
}
```

## Known Limitations

1. **No Persistent Metrics**: Status metrics calculated on-demand from database
2. **No Event History**: Authentication events only logged, not stored for telemetry
3. **Limited Cache Metrics**: Basic cache size tracking only
4. **No Performance Timing**: No latency or response time tracking
5. **No Graph Integration**: Metrics not automatically written to memory graph
6. **No Alerting**: No built-in threshold-based alerting
7. **No Token Analytics**: Limited visibility into token usage patterns
8. **Database Lock Contention**: SQLite may block during status queries

## Future Enhancements

1. **Event Store Integration**: Persistent authentication event storage
2. **Performance Metrics**: Add latency tracking for token operations
3. **Advanced Cache Analytics**: Hit rates, eviction patterns, size trends
4. **Security Analytics**: Anomaly detection, risk scoring, threat intelligence
5. **Graph Integration**: Automatic telemetry node creation
6. **Real-time Streaming**: WebSocket streaming of authentication events
7. **Certificate Analytics**: Lifecycle tracking, usage patterns, expiry monitoring
8. **Token Analytics**: Usage frequency, lifetime analysis, security insights

## Integration Points

- **TimeService**: Provides consistent timestamps for metrics
- **Database**: SQLite storage for certificate data and metrics calculation
- **BaseService**: Inherits standard service metrics (uptime, request/error tracking)
- **BaseInfrastructureService**: Adds availability and infrastructure-specific metrics
- **ServiceRegistry**: Service discovery and capability advertisement
- **Audit Service**: Potential integration for security event logging
- **Telemetry Service**: Future integration for graph storage and consolidation

## Monitoring Recommendations

1. **Certificate Health**: Monitor certificate counts by role and status
2. **Authentication Success Rate**: Track error_rate metric for authentication failures
3. **Token Cache Performance**: Monitor cache efficiency and size growth
4. **Security Events**: Watch for unusual authentication patterns
5. **Service Availability**: Track uptime and health status
6. **Database Performance**: Monitor SQLite query performance during status checks
7. **Key Rotation**: Track key rotation frequency and success
8. **Memory Usage**: Monitor service memory consumption and cache sizes

## Performance Considerations

1. **Database Queries**: Status metrics require database queries on each request
2. **Cache Memory**: Token caches consume memory proportional to active tokens
3. **Cryptographic Operations**: Key operations and token verification are CPU-intensive
4. **SQLite Locking**: Concurrent access may cause temporary blocking
5. **Status Calculation**: Real-time metric calculation adds latency
6. **Certificate Queries**: Large certificate sets slow down status queries

## System Integration

The Authentication Service is critical for CIRIS security:
- Provides identity and access management for all system components
- Enables secure adapter communication via channel tokens
- Supports OAuth integration for external user authentication
- Maintains cryptographic integrity through Ed25519 signatures
- Provides foundation for audit trails and security monitoring

The telemetry from this service is essential for:
- Security incident detection and response
- Capacity planning for authentication infrastructure
- Performance optimization of token validation
- Compliance reporting and audit support
- Operational monitoring of critical security functions
