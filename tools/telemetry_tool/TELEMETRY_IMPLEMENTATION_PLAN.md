# Telemetry Implementation Plan - v1.4.3

## Goal: 250 Metrics via get_telemetry()

### Current State (165 metrics)
- **4/21 services** have `get_telemetry()` → 42 metrics
- **All 21 services** inherit BaseService → 105 base metrics
- **TSDB historical** → 18 metrics
- **Total**: ~165 metrics

### Target State (250+ metrics)
- **21/21 services** have `get_telemetry()` → ~250 metrics
- **TSDB unchanged** → 18 metrics (historical only)
- **Total**: ~268 metrics

## Implementation Priority & Metrics Per Service

### Phase 1: High-Value Services (Core Functionality)
| Service | Priority | Metrics | Status | Owner |
|---------|----------|---------|--------|-------|
| telemetry | HIGH | 12 | ❌ TODO | |
| audit | HIGH | 12 | ❌ TODO | |
| llm | HIGH | 12 | ❌ TODO | |
| wise_authority | HIGH | 12 | ❌ TODO | |
| runtime_control | HIGH | 12 | ❌ TODO | |

**Phase 1 Total**: 60 new metrics → Running total: 225

### Phase 2: Infrastructure Services
| Service | Priority | Metrics | Status | Owner |
|---------|----------|---------|--------|-------|
| authentication | MED | 10 | ❌ TODO | |
| resource_monitor | MED | 12 | ❌ TODO | |
| database_maintenance | MED | 10 | ❌ TODO | |
| time | MED | 8 | ❌ TODO | |
| secrets | MED | 10 | ❌ TODO | |

**Phase 2 Total**: 50 new metrics → Running total: 275

### Phase 3: Governance & Support Services
| Service | Priority | Metrics | Status | Owner |
|---------|----------|---------|--------|-------|
| adaptive_filter | LOW | 10 | ❌ TODO | |
| visibility | LOW | 10 | ❌ TODO | |
| self_observation | LOW | 12 | ❌ TODO | |
| task_scheduler | LOW | 10 | ❌ TODO | |
| shutdown | LOW | 8 | ❌ TODO | |
| initialization | LOW | 10 | ❌ TODO | |
| tsdb_consolidation | LOW | 8 | ❌ TODO | |

**Phase 3 Total**: 68 new metrics → Running total: 333

### Already Complete ✅
| Service | Metrics | Status |
|---------|---------|--------|
| memory | 13 | ✅ DONE |
| config | 14 | ✅ DONE |
| incident_management | 8 | ✅ DONE |
| secrets_tool | 7 | ✅ DONE |

## Metric Guidelines Per Service Type

### Graph Services (12-15 metrics each)
```python
async def get_telemetry(self) -> Dict[str, any]:
    return {
        "service_name": "service",
        "healthy": self._started,
        "uptime_seconds": uptime,
        # Operations
        "operations_total": count,
        "operations_failed": count,
        "operations_rate": rate,
        # Storage
        "nodes_total": count,
        "edges_total": count,
        "storage_size_mb": size,
        # Performance
        "query_latency_ms": latency,
        "cache_hit_rate": rate,
        # Custom
        "service_specific_1": value,
        "service_specific_2": value,
    }
```

### Infrastructure Services (8-10 metrics each)
```python
async def get_telemetry(self) -> Dict[str, any]:
    return {
        "service_name": "service",
        "healthy": self._started,
        "uptime_seconds": uptime,
        # Core functionality
        "primary_operation_count": count,
        "primary_operation_rate": rate,
        "error_rate": rate,
        # Resource usage
        "resource_usage": value,
        # Service specific
        "custom_metric_1": value,
        "custom_metric_2": value,
    }
```

### Governance Services (10-12 metrics each)
```python
async def get_telemetry(self) -> Dict[str, any]:
    return {
        "service_name": "service",
        "healthy": self._started,
        "uptime_seconds": uptime,
        # Decisions/Actions
        "decisions_made": count,
        "actions_taken": count,
        "deferrals": count,
        # Effectiveness
        "success_rate": rate,
        "impact_score": score,
        # Governance specific
        "violations_prevented": count,
        "compliance_score": score,
    }
```

## Implementation Template

```python
async def get_telemetry(self) -> Dict[str, any]:
    """
    Get telemetry data for the {service_name} service.

    Returns metrics including:
    - {metric_1}: Description
    - {metric_2}: Description
    - ...
    """
    try:
        # Calculate uptime
        current_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        uptime_seconds = int((current_time - self._start_time).total_seconds()) if self._start_time else 0

        # Get base metrics from _collect_metrics() if available
        base_metrics = self._collect_metrics() if hasattr(self, '_collect_metrics') else {}

        # Service-specific metrics
        specific_metrics = {
            "service_name": "{service_name}",
            "healthy": self._started if hasattr(self, '_started') else False,
            "uptime_seconds": uptime_seconds,
            # Add 8-12 service-specific metrics here
        }

        # Merge base and specific
        specific_metrics.update(base_metrics)
        return specific_metrics

    except Exception as e:
        logger.warning(f"Failed to get telemetry for {service_name}: {e}")
        return {
            "service_name": "{service_name}",
            "healthy": False,
            "error": str(e)
        }
```

## Success Criteria

1. **Coverage**: 21/21 services have `get_telemetry()`
2. **Metric Count**: 250+ total metrics available
3. **Consistency**: All follow the same pattern
4. **Performance**: < 100ms to collect all metrics
5. **No Breaking Changes**: Existing metrics unchanged

## Timeline

- **Phase 1**: 2 days (5 services × 12 metrics)
- **Phase 2**: 2 days (5 services × 10 metrics)
- **Phase 3**: 2 days (7 services × 10 metrics)
- **Testing**: 1 day
- **Total**: 1 week

## Notes

- Keep metrics PULL-based (no TSDB storage unless needed for history)
- Use existing `_collect_metrics()` where available
- Follow naming conventions: `snake_case`, descriptive, no abbreviations
- Include units in metric names: `_ms`, `_seconds`, `_mb`, `_count`, `_rate`
- Return `Dict[str, any]` not `Dict[str, float]` for flexibility
