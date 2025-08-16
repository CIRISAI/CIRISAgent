# get_telemetry() Implementation Guide for v1.4.3

## Overview
Goal: Implement `get_telemetry()` method for all 21 core services to expose ~250-300 metrics via API.

## Current State (v1.4.2)
- **2/21 services** have get_telemetry(): incident_management, secrets_tool
- **72 total accessible metrics**
- Most metrics NOT stored in TSDB (that's fine - step 2 later)

## Target State (v1.4.3)
- **21/21 services** have get_telemetry()
- **~250-300 total accessible metrics**
- Metrics available via API telemetry aggregator
- TSDB storage remains optional for later

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
        # Calculate metrics
        current_time = self._time_service.now() if self._time_service else datetime.now()
        uptime_seconds = int((current_time - self._start_time).total_seconds()) if self._start_time else 0

        return {
            "service_name": "{service_name}",
            "healthy": self._started,
            "uptime_seconds": uptime_seconds,
            # Service-specific metrics
            "{metric_1}": value_1,
            "{metric_2}": value_2,
            # ... 10-15 metrics total
        }
    except Exception as e:
        logger.warning(f"Failed to get telemetry for {service_name}: {e}")
        return {
            "service_name": "{service_name}",
            "healthy": False,
            "error": str(e)
        }
```

## Services Needing Implementation (19)

### Graph Services (4)
1. **memory** - Needs get_telemetry()
   - graph_operations_total
   - nodes_created
   - edges_created
   - query_count
   - query_latency_ms
   - cache_hits
   - cache_misses
   - memory_usage_mb
   - largest_subgraph_size
   - total_nodes

2. **config** - Needs get_telemetry()
   - configs_loaded
   - configs_updated
   - validation_errors
   - cache_size
   - reload_count
   - last_reload_timestamp
   - active_overrides
   - deprecated_keys_used
   - missing_keys_requested
   - config_version

3. **telemetry** - Needs get_telemetry()
   - metrics_recorded
   - metrics_queried
   - tsdb_nodes_created
   - aggregations_performed
   - export_count
   - failed_exports
   - buffer_size
   - oldest_metric_age_seconds
   - compression_ratio
   - storage_size_mb

4. **audit** - Needs get_telemetry()
   - events_logged
   - events_by_severity
   - events_by_type
   - retention_policy_executions
   - query_count
   - export_count
   - compliance_checks_passed
   - compliance_checks_failed
   - storage_size_mb
   - oldest_event_age_days

5. **tsdb_consolidation** - Needs get_telemetry()
   - consolidations_performed
   - nodes_consolidated
   - space_saved_mb
   - oldest_unconsolidated_seconds
   - consolidation_errors
   - last_consolidation_timestamp
   - average_compression_ratio
   - pending_consolidations
   - consolidation_latency_ms
   - retention_violations

### Infrastructure Services (7)
6. **time** - Needs get_telemetry()
   - current_timestamp
   - timezone
   - ntp_sync_status
   - drift_ms
   - adjustments_made
   - time_queries
   - scheduled_tasks
   - missed_schedules
   - clock_skew_detected
   - uptime_seconds

7. **shutdown** - Needs get_telemetry()
   - shutdown_requests
   - emergency_shutdowns
   - graceful_shutdowns
   - shutdown_hooks_registered
   - shutdown_hooks_executed
   - average_shutdown_time_ms
   - pending_operations
   - force_shutdown_count
   - shutdown_errors
   - last_shutdown_reason

8. **initialization** - Needs get_telemetry()
   - services_initialized
   - initialization_time_ms
   - initialization_errors
   - dependency_resolution_time_ms
   - circular_dependencies_detected
   - retry_count
   - failed_services
   - initialization_order
   - config_load_time_ms
   - total_startup_time_ms

9. **authentication** - Needs get_telemetry()
   - auth_attempts
   - successful_auths
   - failed_auths
   - token_validations
   - token_refreshes
   - expired_tokens
   - revoked_tokens
   - active_sessions
   - unique_users
   - auth_latency_ms

10. **resource_monitor** - Needs get_telemetry()
    - cpu_percent
    - memory_mb
    - disk_usage_gb
    - network_bytes_sent
    - network_bytes_received
    - open_file_descriptors
    - thread_count
    - gc_collections
    - resource_limit_warnings
    - oom_risk_score

11. **database_maintenance** - Needs get_telemetry()
    - vacuum_operations
    - index_rebuilds
    - backup_count
    - backup_size_gb
    - last_backup_timestamp
    - integrity_checks
    - corruption_detected
    - auto_repairs
    - connection_pool_size
    - slow_queries

12. **secrets** - Needs get_telemetry()
    - secrets_accessed
    - secrets_rotated
    - encryption_operations
    - decryption_operations
    - key_generations
    - vault_connections
    - vault_errors
    - secret_age_days
    - rotation_failures
    - compliance_violations

### Governance Services (4)
13. **wise_authority** - Needs get_telemetry()
    - guidance_requests
    - deferrals_made
    - guidance_provided
    - consensus_reached
    - consensus_failed
    - average_decision_time_ms
    - ethical_violations_prevented
    - override_requests
    - override_approvals
    - wisdom_score

14. **adaptive_filter** - Needs get_telemetry()
    - messages_filtered
    - messages_passed
    - filter_updates
    - rules_active
    - rules_triggered
    - false_positives
    - false_negatives
    - adaptation_cycles
    - learning_rate
    - filter_effectiveness

15. **visibility** - Needs get_telemetry()
    - visibility_level
    - transparency_reports_generated
    - data_classifications
    - redactions_applied
    - visibility_requests
    - visibility_changes
    - audit_trail_entries
    - compliance_score
    - data_exposure_incidents
    - privacy_violations

16. **self_observation** - Needs get_telemetry()
    - observations_made
    - patterns_detected
    - anomalies_found
    - self_corrections
    - performance_analyses
    - introspection_depth
    - metacognitive_cycles
    - improvement_suggestions
    - behavior_adjustments
    - coherence_score

### Runtime Services (3)
17. **llm** - Needs get_telemetry()
    - requests_total
    - tokens_used
    - average_latency_ms
    - model_switches
    - context_overflows
    - rate_limit_hits
    - retry_count
    - success_rate
    - cost_estimate_cents
    - active_models

18. **runtime_control** - Needs get_telemetry()
    - control_commands_received
    - state_changes
    - pause_count
    - resume_count
    - speed_adjustments
    - priority_changes
    - queue_modifications
    - debug_sessions
    - breakpoints_hit
    - control_latency_ms

19. **task_scheduler** - Needs get_telemetry()
    - tasks_scheduled
    - tasks_completed
    - tasks_failed
    - tasks_cancelled
    - tasks_pending
    - average_execution_time_ms
    - queue_depth
    - worker_utilization
    - deadline_misses
    - priority_inversions

## Implementation Priority
1. **High Priority** (Core functionality): llm, memory, wise_authority, runtime_control
2. **Medium Priority** (Observability): audit, telemetry, resource_monitor, self_observation
3. **Low Priority** (Support): time, shutdown, initialization, etc.

## Testing Checklist
- [ ] Each service returns valid Dict[str, any]
- [ ] All metrics have appropriate data types
- [ ] Error handling doesn't crash service
- [ ] Metrics are meaningful (not all zeros)
- [ ] Service name is included in response
- [ ] Healthy flag reflects actual state
- [ ] Uptime calculation is correct

## Verification
After implementation, verify with:
```python
# Check via SDK
client = CIRISClient(base_url='https://agents.ciris.ai/api/datum')
telemetry = await client.telemetry.get_unified_telemetry()

# Should show ~250-300 metrics from 21 services
```
