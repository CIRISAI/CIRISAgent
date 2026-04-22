# Endpoint Inventory Auth Heuristic Summary

- Total endpoints: 256
- Endpoints with auth-like dependency: 13
- Endpoints without auth-like dependency: 243

## Methods
- DELETE: 16
- GET: 137
- PATCH: 2
- POST: 84
- PUT: 17

## Top modules by endpoint count
- ciris_engine/logic/adapters/api/routes/users.py: 16
- ciris_engine/logic/adapters/api/routes/auth.py: 15
- ciris_engine/logic/adapters/api/routes/system/adapters.py: 14
- ciris_engine/logic/adapters/api/routes/consent.py: 12
- ciris_engine/logic/adapters/api/routes/system/llm_routes.py: 11
- ciris_engine/logic/adapters/api/routes/telemetry.py: 10
- ciris_engine/logic/adapters/api/routes/system/skill_builder.py: 10
- ciris_engine/logic/adapters/api/routes/system_extensions.py: 9
- ciris_engine/logic/adapters/api/routes/memory.py: 9
- ciris_engine/logic/adapters/api/routes/tickets.py: 7

## Sample unauth endpoints (first 25)
- GET  (ciris_engine/logic/adapters/api/routes/config.py:139) deps=[]
- GET  (ciris_engine/logic/adapters/api/routes/dsar.py:459) deps=[]
- GET  (ciris_engine/logic/adapters/api/routes/tickets.py:387) deps=[]
- GET  (ciris_engine/logic/adapters/api/routes/users.py:313) deps=[]
- POST  (ciris_engine/logic/adapters/api/routes/dsar.py:285) deps=[]
- POST  (ciris_engine/logic/adapters/api/routes/dsar_multi_source.py:169) deps=[]
- POST  (ciris_engine/logic/adapters/api/routes/dsar_multi_source.py:169) deps=[]
- POST  (ciris_engine/logic/adapters/api/routes/tickets.py:272) deps=[]
- POST  (ciris_engine/logic/adapters/api/routes/users.py:369) deps=[]
- GET / (ciris_engine/logic/adapters/api/app.py:226) deps=[]
- POST /accord-invocation (ciris_engine/logic/adapters/api/routes/system_extensions.py:1038) deps=[]
- GET /accord-settings (ciris_engine/logic/adapters/api/routes/my_data.py:566) deps=[]
- PUT /accord-settings (ciris_engine/logic/adapters/api/routes/my_data.py:629) deps=[]
- GET /adapters (ciris_engine/logic/adapters/api/routes/setup/providers.py:47) deps=[]
- GET /adapters (ciris_engine/logic/adapters/api/routes/system/adapters.py:165) deps=['require_observer']
- GET /adapters/available (ciris_engine/logic/adapters/api/routes/setup/providers.py:62) deps=[]
- GET /adapters/available (ciris_engine/logic/adapters/api/routes/system/adapters.py:372) deps=['require_observer']
- GET /adapters/configurable (ciris_engine/logic/adapters/api/routes/system/adapters.py:537) deps=['require_admin']
- GET /adapters/configure/{session_id} (ciris_engine/logic/adapters/api/routes/system/adapter_config.py:332) deps=['require_setup_or_observer']
- POST /adapters/configure/{session_id}/complete (ciris_engine/logic/adapters/api/routes/system/adapter_config.py:652) deps=['require_setup_or_admin']
- GET /adapters/configure/{session_id}/oauth/callback (ciris_engine/logic/adapters/api/routes/system/adapter_config.py:483) deps=[]
- GET /adapters/configure/{session_id}/status (ciris_engine/logic/adapters/api/routes/system/adapter_config.py:429) deps=[]
- POST /adapters/configure/{session_id}/step (ciris_engine/logic/adapters/api/routes/system/adapter_config.py:384) deps=['require_setup_or_admin']
- GET /adapters/context-enrichment (ciris_engine/logic/adapters/api/routes/system/adapters.py:760) deps=['require_observer']
- POST /adapters/import-skill (ciris_engine/logic/adapters/api/routes/system/skill_import.py:612) deps=[]
