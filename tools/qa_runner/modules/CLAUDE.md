# QA Runner Modules - CLAUDE.md

Each module is a self-contained test suite. The QA runner auto-starts the API server, authenticates, runs the module, and tears down. Modules use the CIRIS Python SDK client for API calls and `FilterTestHelper` for SSE-based task completion monitoring.

## Invoke any module

```bash
python3 -m tools.qa_runner <module_name>           # auto server lifecycle
python3 -m tools.qa_runner <module> --verbose       # detailed output
python3 -m tools.qa_runner <module> --no-auto-start # use existing server
```

## Base Infrastructure

| File | Purpose |
|------|---------|
| `base_test_module.py` | Base class all test modules inherit — provides `self.client`, `self.token`, result tracking |
| `filter_test_helper.py` | SSE stream monitor at `/v1/system/runtime/reasoning-stream` — watches for `TASK_COMPLETE` events to prevent test overlap |

## Test Modules

### Core API & Auth
| Module | File | Tests |
|--------|------|-------|
| `auth` | `api_tests.py` | Authentication endpoints, login, logout, token refresh |
| `api_full` | `comprehensive_api_tests.py` | Extended API coverage (24 tests) |
| `sdk` | `sdk_tests.py` | TypeScript/Python SDK compatibility validation |

### Agent Behavior
| Module | File | Tests |
|--------|------|-------|
| `handlers` | `handler_tests.py` | All 10 handler verbs: SPEAK, MEMORIZE, RECALL, FORGET, TOOL, OBSERVE, DEFER, REJECT, PONDER, TASK_COMPLETE |
| `simple_handlers` | `simple_single_step_tests.py` | Simplified single-step handler tests |
| `single_step_comprehensive` | `comprehensive_single_step_tests.py` | Full 17-phase ACCORD single-step validation |
| `streaming` | `streaming_verification.py` | H3ERE pipeline streaming verification |

### Cognitive States
| Module | File | Tests |
|--------|------|-------|
| `state_transitions` | `state_transition_tests.py` | Cognitive state transition validation |
| `cognitive_api` | `cognitive_state_api_tests.py` | Cognitive state API endpoints |
| `dream_live` | `dream_live_tests.py` | DREAM state live behavior |
| `play_live` | `play_live_tests.py` | PLAY state creative mode |
| `solitude_live` | `solitude_live_tests.py` | SOLITUDE state reflection |

### Governance & Ethics
| Module | File | Tests |
|--------|------|-------|
| `filters` | `filter_tests.py` | Adaptive filtering (36 tests) |
| `guidance` | (in api_tests) | Wise Authority guidance system |
| `accord` | `accord_tests.py` | Accord invocation system (kill switch) |
| `accord_metrics` | `accord_metrics_tests.py` | Trace capture, signing, logshipper forwarding |
| `consent` | `consent_tests.py` | Consent management |
| `air` | `air_tests.py` | Artificial Interaction Reminder compliance |

### Privacy & Compliance
| Module | File | Tests |
|--------|------|-------|
| `dsar` | `dsar_tests.py` | Data Subject Access Request automation |
| `dsar_multi_source` | `dsar_multi_source_tests.py` | Multi-source DSAR lifecycle |
| `dsar_tickets` | `dsar_ticket_workflow_tests.py` | DSAR ticket workflow |

### Adapters & Integrations
| Module | File | Tests |
|--------|------|-------|
| `adapter_autoload` | `adapter_autoload_tests.py` | Adapter discovery and loading |
| `adapter_manifest` | `adapter_manifest_tests.py` | Manifest validation |
| `adapter_config` | `adapter_config_tests.py` | Adapter configuration |
| `adapter_availability` | `adapter_availability_tests.py` | Installation and availability |
| `reddit` | `reddit_tests.py` | Reddit adapter |
| `mcp` | `mcp_tests.py` | Model Context Protocol adapter |
| `sql_external_data` | `sql_external_data_tests.py` | SQL external data service |
| `utility_adapters` | `utility_adapters_tests.py` | Geo, weather, sensor adapters |
| `hosted_tools` | `hosted_tools_tests.py` | CIRIS hosted tools adapter |

### Agent Lifecycle
| Module | File | Tests |
|--------|------|-------|
| `setup` | `setup_tests.py` | Setup wizard API |
| `setup_e2e` | `setup_e2e_tests.py` | End-to-end setup wizard flow |
| `licensed_agent` | `licensed_agent_tests.py` | Licensed agent device auth (RFC 8628) |
| `identity_update` | `identity_update_tests.py` | Identity update integration |
| `multi_occurrence` | `multi_occurrence_tests.py` | Multi-occurrence horizontal scaling |
| `cirisnode` | `cirisnode_tests.py` | CIRISNode deferral routing, trace forwarding |

### Billing & Partnership
| Module | File | Tests |
|--------|------|-------|
| `billing` | `billing_tests.py` | Credit system, usage tracking |
| `billing_integration` | `billing_integration_tests.py` | OAuth user billing flows |
| `partnership` | `partnership_tests.py` | Partnership management |

### Other
| Module | File | Tests |
|--------|------|-------|
| `vision` | `vision_tests.py` | Vision/multimodal capabilities |
| `context_enrichment` | `context_enrichment_tests.py` | ASPDMA context enrichment |
| `system_messages` | `system_messages_tests.py` | System message visibility |
| `he300` | `he300_benchmark_tests.py` | HE-300 ethical benchmark |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `mobile/` | Android/iOS device testing — ADB helper, UI automator, portal registration, verify/trust tests |
| `web_ui/` | Desktop app + browser UI testing — TestAutomation HTTP client, Playwright browser tests |

## Critical Pattern: SSE Task Completion

**Every test that submits a message MUST wait for TASK_COMPLETE via SSE before proceeding.** Without this, `updated_info_available` gets set, triggering conscience retries and test flakiness. See `filter_test_helper.py` and the parent `CLAUDE.md` for details.
