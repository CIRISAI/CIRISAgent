# CIRIS Round 1 Baseline

Generated (UTC): 2026-04-22T23:29:00+00:00

## Service taxonomy

- **graph** (7): memory_service, consent_service, config_service, telemetry_service, audit_service, incident_management_service, tsdb_consolidation_service
- **infrastructure** (4): authentication_service, resource_monitor, database_maintenance_service, secrets_service
- **lifecycle** (4): time_service, shutdown_service, initialization_service, task_scheduler
- **governance** (4): wa_auth_system, adaptive_filter_service, visibility_service, self_observation_service
- **runtime** (2): llm_service, runtime_control_service
- **tool** (1): secrets_tool_service
- **total**: 22

## Endpoint inventory

- Total method+path routes: **257**
- Method split: **{'DELETE': 16, 'GET': 139, 'PATCH': 2, 'POST': 83, 'PUT': 17}**
- Auth-related routes: **15**
- OAuth-related routes: **6**

## Test collection

- Collected tests: **10662**
- Collection errors: **37**
- Missing plugins observed: **['hypothesis', 'pytest_asyncio']**
- Raw summary: `10662 tests collected, 37 errors in 20.40s`
