# CIRIS System Audit Report

## Summary

- **Total Classes**: 1204
- **Total Protocols**: 45
- **Categorized**: 1000
- **Uncategorized**: 158
- **Duplicate Groups**: 0
- **Missing Implementations**: 0
- **Incorrect Inheritance**: 0
- **Protocol Mismatches**: 101
- **Orphaned Classes**: 1110

## Critical Issues


## Component Categorization


### Services Bussed - Tool

- **CLIToolService** (ciris_engine/logic/adapters/cli/cli_tools.py)
- **APIToolService** (ciris_engine/logic/adapters/api/api_tools.py)

### Services Bussed - Secrets

- **SecretsService** (ciris_engine/logic/secrets/service.py)
- **SecretsToolService** (ciris_engine/logic/services/tools/secrets_tool_service.py)

### Services Bussed - Runtime Control

- **APIRuntimeControlService** (ciris_engine/logic/adapters/api/api_runtime_control.py)
- **RuntimeControlService** (ciris_engine/logic/services/runtime/control_service.py)

### Services Bussed - Wise Authority

- **WiseAuthorityService** (ciris_engine/logic/services/governance/wise_authority.py)

### Services Unbussed - Filter

- **AdaptiveFilterService** (ciris_engine/logic/services/governance/filter.py)

### Services Unbussed - Utility

- **BaseInfrastructureService** (ciris_engine/logic/services/base_infrastructure_service.py)
- **BaseScheduledService** (ciris_engine/logic/services/base_scheduled_service.py)
- **APICommunicationService** (ciris_engine/logic/adapters/api/api_communication.py)
- **VisibilityService** (ciris_engine/logic/services/governance/visibility.py)
- **ConsentService** (ciris_engine/logic/services/governance/consent.py)

### Adapters - Platform

- **CIRISNodeClient** (ciris_engine/logic/adapters/cirisnode_client.py)
- **CLIObserver** (ciris_engine/logic/adapters/cli/cli_observer.py)
- **CLIWiseAuthorityService** (ciris_engine/logic/adapters/cli/cli_wa_service.py)
- **CliPlatform** (ciris_engine/logic/adapters/cli/adapter.py)
- **CLIAdapter** (ciris_engine/logic/adapters/cli/cli_adapter.py)
- **CLIAdapterConfig** (ciris_engine/logic/adapters/cli/config.py)
- **ServiceMapping** (ciris_engine/logic/adapters/api/service_configuration.py)
- **ApiServiceConfiguration** (ciris_engine/logic/adapters/api/service_configuration.py)
- **AdapterService** (ciris_engine/logic/adapters/api/service_configuration.py)
- **StandardResponse** (ciris_engine/logic/adapters/api/models.py)

### Adapters - Communication

- **ToolResult** (ciris_engine/schemas/adapters/tools.py)
- **AdapterInstance** (ciris_engine/logic/runtime/adapter_manager.py)
- **AdapterManagerInterface** (ciris_engine/logic/runtime/adapter_manager.py)
- **RuntimeAdapterManager** (ciris_engine/logic/runtime/adapter_manager.py)
- **Service** (ciris_engine/logic/adapters/base.py)
- **BaseObserver** (ciris_engine/logic/adapters/base_observer.py)
- **BaseAdapter** (ciris_engine/logic/adapters/base_adapter.py)
- **MetricsEnabledAdapter** (ciris_engine/logic/services/mixins/example_usage.py)
- **ActiveAdapter** (ciris_engine/schemas/infrastructure/base.py)
- **ToolInfo** (ciris_engine/schemas/adapters/tools.py)

### Processors - Main

- **AgentProcessor** (ciris_engine/logic/processors/core/main_processor.py)
- **MainProcessorMetrics** (ciris_engine/schemas/processors/main.py)
- **AgentState** (ciris_engine/schemas/processors/states.py)
- **MaintenanceResult** (ciris_engine/schemas/processors/solitude.py)
- **AgentProcessorMetrics** (ciris_engine/protocols/processors/agent.py)
- **AgentProcessorProtocol** (ciris_engine/protocols/processors/agent.py)

### Processors - Task

- **TaskManager** (ciris_engine/logic/processors/support/task_manager.py)
- **PreloadTask** (ciris_engine/schemas/processors/main.py)
- **TaskTypePattern** (ciris_engine/schemas/processors/solitude.py)
- **TaskTypeStats** (ciris_engine/schemas/processors/solitude.py)

### Processors - Specialized

- **ShutdownRequest** (ciris_engine/schemas/processors/main.py)
- **BaseProcessor** (ciris_engine/logic/processors/core/base_processor.py)
- **ThoughtProcessor** (ciris_engine/logic/processors/core/thought_processor.py)
- **ThoughtManager** (ciris_engine/logic/processors/support/thought_manager.py)
- **ThoughtContent** (ciris_engine/logic/processors/support/processing_queue.py)
- **DMAOrchestrator** (ciris_engine/logic/processors/support/dma_orchestrator.py)
- **StateTransition** (ciris_engine/logic/processors/support/state_manager.py)
- **StateManager** (ciris_engine/logic/processors/support/state_manager.py)
- **WakeupProcessor** (ciris_engine/logic/processors/states/wakeup_processor.py)
- **PlayProcessor** (ciris_engine/logic/processors/states/play_processor.py)

### Handlers - External Actions

- **IncidentCaptureHandler** (ciris_engine/logic/utils/incident_capture_handler.py)
- **TSDBLogHandler** (ciris_engine/logic/telemetry/log_collector.py)
- **PartnershipRequestHandler** (ciris_engine/logic/utils/consent/partnership_utils.py)
- **ActionDispatcher** (ciris_engine/logic/infrastructure/handlers/action_dispatcher.py)
- **ActionHandlerDependencies** (ciris_engine/logic/infrastructure/handlers/base_handler.py)
- **BaseActionHandler** (ciris_engine/logic/infrastructure/handlers/base_handler.py)
- **FollowUpCreationError** (ciris_engine/logic/infrastructure/handlers/exceptions.py)
- **OAuthCallbackHandler** (ciris_engine/logic/infrastructure/sub_services/wa_cli_oauth.py)
- **ObserveHandler** (ciris_engine/logic/handlers/external/observe_handler.py)
- **SpeakHandler** (ciris_engine/logic/handlers/external/speak_handler.py)

### Handlers - Control Actions

- **PonderHandler** (ciris_engine/logic/handlers/control/ponder_handler.py)
- **DeferHandler** (ciris_engine/logic/handlers/control/defer_handler.py)
- **RejectHandler** (ciris_engine/logic/handlers/control/reject_handler.py)
- **DeferralPackage** (ciris_engine/schemas/handlers/core.py)
- **DeferralReason** (ciris_engine/schemas/handlers/core.py)
- **DeferralReport** (ciris_engine/schemas/handlers/core.py)
- **RejectContext** (ciris_engine/schemas/handlers/contexts.py)
- **PonderContext** (ciris_engine/schemas/handlers/contexts.py)
- **DeferContext** (ciris_engine/schemas/handlers/contexts.py)

### Handlers - Memory Actions

- **RecallHandler** (ciris_engine/logic/handlers/memory/recall_handler.py)
- **ForgetHandler** (ciris_engine/logic/handlers/memory/forget_handler.py)
- **MemorizeHandler** (ciris_engine/logic/handlers/memory/memorize_handler.py)
- **MemorizeContext** (ciris_engine/schemas/handlers/contexts.py)
- **RecallContext** (ciris_engine/schemas/handlers/contexts.py)
- **ForgetContext** (ciris_engine/schemas/handlers/contexts.py)
- **RecalledNodeInfo** (ciris_engine/schemas/handlers/memory_schemas.py)
- **RecallResult** (ciris_engine/schemas/handlers/memory_schemas.py)

### Handlers - Terminal Actions

- **TaskCompleteHandler** (ciris_engine/logic/handlers/terminal/task_complete_handler.py)
- **TaskCompleteContext** (ciris_engine/schemas/handlers/contexts.py)

### Dmas - Ethical

- **DMAPromptLoader** (ciris_engine/logic/dma/prompt_loader.py)
- **ActionSelectionPDMAEvaluator** (ciris_engine/logic/dma/action_selection_pdma.py)
- **EthicalPDMAEvaluator** (ciris_engine/logic/dma/pdma.py)
- **BaseDMA** (ciris_engine/logic/dma/base_dma.py)
- **DMAFailure** (ciris_engine/logic/dma/exceptions.py)
- **FacultyIntegration** (ciris_engine/logic/dma/action_selection/faculty_integration.py)
- **ActionInstructionGenerator** (ciris_engine/logic/dma/action_selection/action_instruction_generator.py)
- **DMAInputData** (ciris_engine/schemas/dma/core.py)
- **DMAContext** (ciris_engine/schemas/dma/core.py)
- **DMADecision** (ciris_engine/schemas/dma/core.py)

### Dmas - Common Sense

- **CSDMAEvaluator** (ciris_engine/logic/dma/csdma.py)
- **CSDMAOverrides** (ciris_engine/schemas/config/agent.py)
- **CSDMADecision** (ciris_engine/schemas/dma/decisions.py)
- **CSDMAResult** (ciris_engine/schemas/dma/results.py)
- **CSDMAProtocol** (ciris_engine/protocols/dma/base.py)

### Dmas - Domain Specific

- **BaseDSDMA** (ciris_engine/logic/dma/dsdma_base.py)
- **LLMOutputForDSDMA** (ciris_engine/logic/dma/dsdma_base.py)
- **DSDMAConfiguration** (ciris_engine/schemas/config/agent.py)
- **DSDMADecision** (ciris_engine/schemas/dma/decisions.py)
- **DSDMAResult** (ciris_engine/schemas/dma/results.py)
- **DSDMAProtocol** (ciris_engine/protocols/dma/base.py)

### Dmas - Action Selection

- **ActionSelectionContextBuilder** (ciris_engine/logic/dma/action_selection/context_builder.py)
- **ActionSelectionSpecialCases** (ciris_engine/logic/dma/action_selection/special_cases.py)
- **ActionSelectionDecision** (ciris_engine/schemas/dma/decisions.py)
- **ActionSelectionDMAResult** (ciris_engine/schemas/dma/results.py)
- **ActionSelectionDMAProtocol** (ciris_engine/protocols/dma/base.py)

### Faculties - Cognitive

- **EpistemicFaculty** (ciris_engine/protocols/faculties.py)

### Guardrails - Process

- **ThoughtDepthGuardrail** (ciris_engine/logic/conscience/thought_depth_guardrail.py)

### Runtime - Core

- **CIRISRuntime** (ciris_engine/logic/runtime/ciris_runtime.py)
- **RuntimeInterface** (ciris_engine/logic/runtime/runtime_interface.py)
- **RuntimeEvent** (ciris_engine/schemas/services/core/runtime.py)
- **RuntimeStatusResponse** (ciris_engine/schemas/services/core/runtime.py)
- **RuntimeStateSnapshot** (ciris_engine/schemas/services/core/runtime.py)
- **RuntimeConfig** (ciris_engine/schemas/services/core/runtime_config.py)

### Runtime - Initialization

- **ServiceInitializer** (ciris_engine/logic/runtime/service_initializer.py)

### Runtime - Management

- **ModularServiceLoader** (ciris_engine/logic/runtime/modular_service_loader.py)
- **ModuleLoader** (ciris_engine/logic/runtime/module_loader.py)
- **ComponentBuilder** (ciris_engine/logic/runtime/component_builder.py)
- **IdentityManager** (ciris_engine/logic/runtime/identity_manager.py)
- **OperationPriority** (ciris_engine/logic/buses/runtime_control_bus.py)
- **RuntimeControlBus** (ciris_engine/logic/buses/runtime_control_bus.py)
- **ResourceUsage** (ciris_engine/schemas/runtime/resources.py)
- **ServicePriorityUpdateResponse** (ciris_engine/schemas/services/runtime_control.py)
- **CircuitBreakerResetResponse** (ciris_engine/schemas/services/runtime_control.py)
- **ResourceLimits** (ciris_engine/schemas/runtime/protocols_core.py)

### Infrastructure - Buses

- **BusManager** (ciris_engine/logic/buses/bus_manager.py)
- **WiseBus** (ciris_engine/logic/buses/wise_bus.py)
- **ProhibitionSeverity** (ciris_engine/logic/buses/prohibitions.py)
- **SendMessageRequest** (ciris_engine/logic/buses/communication_bus.py)
- **FetchMessagesRequest** (ciris_engine/logic/buses/communication_bus.py)
- **CommunicationBus** (ciris_engine/logic/buses/communication_bus.py)
- **DistributionStrategy** (ciris_engine/logic/buses/llm_bus.py)
- **LLMBusMessage** (ciris_engine/logic/buses/llm_bus.py)
- **LLMBus** (ciris_engine/logic/buses/llm_bus.py)
- **BusMessage** (ciris_engine/logic/buses/base_bus.py)

### Infrastructure - Registry

- **conscienceEntry** (ciris_engine/logic/conscience/registry.py)
- **conscienceRegistry** (ciris_engine/logic/conscience/registry.py)
- **ServiceRegistry** (ciris_engine/logic/registries/base.py)
- **ServiceRegistrySnapshot** (ciris_engine/schemas/infrastructure/base.py)
- **CrisisResourceRegistry** (ciris_engine/schemas/resources/crisis.py)
- **RegistryInfo** (ciris_engine/schemas/registries/base.py)
- **NodeTypeRegistry** (ciris_engine/schemas/services/graph_typed_nodes.py)
- **ServiceRegistryProtocol** (ciris_engine/protocols/infrastructure/base.py)

### Infrastructure - Persistence

- **DatabaseMaintenanceService** (ciris_engine/logic/persistence/maintenance.py)
- **ChannelInfo** (ciris_engine/schemas/persistence/correlations.py)
- **DateTimeEncoder** (ciris_engine/logic/persistence/models/graph.py)
- **RetryConnection** (ciris_engine/logic/persistence/db/core.py)
- **CorrelationRequestData** (ciris_engine/schemas/persistence/correlations.py)
- **CorrelationResponseData** (ciris_engine/schemas/persistence/correlations.py)
- **ConversationSummaryData** (ciris_engine/schemas/persistence/correlations.py)
- **DeferralReportContext** (ciris_engine/schemas/persistence/core.py)
- **CorrelationUpdateRequest** (ciris_engine/schemas/persistence/core.py)
- **MetricsQuery** (ciris_engine/schemas/persistence/core.py)

### Infrastructure - Schemas

- **ToolParameter** (ciris_engine/schemas/tools.py)
- **Tool** (ciris_engine/schemas/tools.py)
- **ServiceMetrics** (ciris_engine/schemas/api/telemetry.py)
- **MetricData** (ciris_engine/schemas/telemetry/core.py)
- **ConfigListResponse** (ciris_engine/schemas/api/config_security.py)
- **ConfigUpdate** (ciris_engine/schemas/services/core/secrets.py)
- **APIKeyInfo** (ciris_engine/schemas/api/auth.py)
- **OAuthProviderInfo** (ciris_engine/schemas/infrastructure/oauth.py)
- **ConfigData** (ciris_engine/schemas/utils/config_validator.py)
- **LLMConfig** (ciris_engine/schemas/utils/config_validator.py)

### Infrastructure - Utilities

- **GraphQLClient** (ciris_engine/logic/utils/graphql_context_provider.py)
- **GraphQLContextProvider** (ciris_engine/logic/utils/graphql_context_provider.py)
- **ShutdownManagerWrapper** (ciris_engine/logic/utils/shutdown_manager.py)
- **InitializationError** (ciris_engine/logic/utils/initialization_manager.py)
- **DirectorySetupError** (ciris_engine/logic/utils/directory_setup.py)
- **PermissionError** (ciris_engine/logic/utils/directory_setup.py)
- **DiskSpaceError** (ciris_engine/logic/utils/directory_setup.py)
- **DirectoryCreationError** (ciris_engine/logic/utils/directory_setup.py)
- **OwnershipError** (ciris_engine/logic/utils/directory_setup.py)
- **WriteTestError** (ciris_engine/logic/utils/directory_setup.py)

### ❓ Uncategorized Components

- **ParameterType** (ciris_engine/schemas/tools.py)
- **ToolStatus** (ciris_engine/schemas/tools.py)
- **PipelineController** (ciris_engine/protocols/pipeline_control.py)
- **ContextBuilder** (ciris_engine/logic/context/builder.py)
- **BatchContextData** (ciris_engine/logic/context/batch_context.py)
- **BasicTelemetryCollector** (ciris_engine/logic/telemetry/core.py)
- **PathConfig** (ciris_engine/logic/telemetry/hot_cold_config.py)
- **ModulePathConfig** (ciris_engine/logic/telemetry/hot_cold_config.py)
- **LogCorrelationCollector** (ciris_engine/logic/telemetry/log_collector.py)
- **SecurityFilter** (ciris_engine/logic/telemetry/security.py)
- **ConscienceConfig** (ciris_engine/logic/conscience/core.py)
- **EntropyResult** (ciris_engine/logic/conscience/core.py)
- **CoherenceResult** (ciris_engine/logic/conscience/core.py)
- **EntropyConscience** (ciris_engine/logic/conscience/core.py)
- **CoherenceConscience** (ciris_engine/logic/conscience/core.py)
- **OptimizationVetoConscience** (ciris_engine/logic/conscience/core.py)
- **EpistemicHumilityConscience** (ciris_engine/logic/conscience/core.py)
- **AuditHashChain** (ciris_engine/logic/audit/hash_chain.py)
- **AuditVerifier** (ciris_engine/logic/audit/verifier.py)
- **AuditSignatureManager** (ciris_engine/logic/audit/signature_manager.py)
