# CIRIS System Audit Report

## Summary

- **Total Classes**: 1653
- **Total Protocols**: 51
- **Categorized**: 1347
- **Uncategorized**: 251
- **Duplicate Groups**: 0
- **Missing Implementations**: 0
- **Incorrect Inheritance**: 0
- **Protocol Mismatches**: 137
- **Orphaned Classes**: 1545

## Critical Issues


## Component Categorization


### Services Bussed - Tool

- **CoreToolService** (ciris_engine/logic/services/tools/core_tool_service/service.py)
- **APIToolService** (ciris_engine/logic/adapters/api/api_tools.py)
- **CLIToolService** (ciris_engine/logic/adapters/cli/cli_tools.py)

### Services Bussed - Secrets

- **SecretsService** (ciris_engine/logic/secrets/service.py)

### Services Bussed - Runtime Control

- **RuntimeControlService** (ciris_engine/logic/services/runtime/control_service/service.py)
- **APIRuntimeControlService** (ciris_engine/logic/adapters/api/api_runtime_control.py)

### Services Bussed - Wise Authority

- **WiseAuthorityService** (ciris_engine/logic/services/governance/wise_authority/service.py)

### Services Unbussed - Filter

- **AdaptiveFilterService** (ciris_engine/logic/services/governance/adaptive_filter/service.py)

### Services Unbussed - Utility

- **BaseScheduledService** (ciris_engine/logic/services/base_scheduled_service.py)
- **BaseInfrastructureService** (ciris_engine/logic/services/base_infrastructure_service.py)
- **ConsentService** (ciris_engine/logic/services/governance/consent/service.py)
- **VisibilityService** (ciris_engine/logic/services/governance/visibility/service.py)
- **APICommunicationService** (ciris_engine/logic/adapters/api/api_communication.py)

### Adapters - Platform

- **AgentTemplate** (ciris_engine/logic/adapters/api/routes/setup/models.py)
- **ChannelInfo** (ciris_engine/logic/adapters/api/routes/agent.py)
- **ServicePriorityUpdateResponse** (ciris_engine/logic/adapters/api/routes/system_extensions.py)
- **CircuitBreakerResetResponse** (ciris_engine/logic/adapters/api/routes/system_extensions.py)
- **ConversationMessage** (ciris_engine/logic/adapters/api/routes/agent.py)
- **AdapterConfig** (ciris_engine/logic/adapters/api/routes/setup/models.py)
- **ResourceLimits** (ciris_engine/logic/adapters/api/routes/telemetry.py)
- **ResourceUsage** (ciris_engine/logic/adapters/api/routes/telemetry_models.py)
- **PaginatedResponse** (ciris_engine/logic/adapters/api/routes/users.py)
- **DiscordMessageData** (ciris_engine/schemas/adapters/discord.py)

### Adapters - Communication

- **ToolResult** (ciris_engine/schemas/adapters/tools.py)
- **AdaptersConfig** (ciris_engine/schemas/config/essential.py)
- **DiscordAdapterOverrides** (ciris_engine/schemas/config/agent.py)
- **APIAdapterOverrides** (ciris_engine/schemas/config/agent.py)
- **CLIAdapterOverrides** (ciris_engine/schemas/config/agent.py)
- **AdapterLoadRequest** (ciris_engine/schemas/runtime/adapter_management.py)
- **AdapterOperationResult** (ciris_engine/schemas/services/core/runtime.py)
- **AdapterMetrics** (ciris_engine/schemas/runtime/adapter_management.py)
- **RuntimeAdapterStatus** (ciris_engine/schemas/runtime/adapter_management.py)
- **AdapterListResponse** (ciris_engine/schemas/runtime/adapter_management.py)

### Processors - Main

- **AgentState** (ciris_engine/schemas/processors/states.py)
- **MainProcessorMetrics** (ciris_engine/schemas/processors/main.py)
- **MaintenanceResult** (ciris_engine/schemas/processors/solitude.py)
- **AgentProcessorMetrics** (ciris_engine/protocols/processors/agent.py)
- **AgentProcessorProtocol** (ciris_engine/protocols/processors/agent.py)
- **AgentProcessor** (ciris_engine/logic/processors/core/main_processor.py)

### Processors - Task

- **PreloadTask** (ciris_engine/schemas/processors/main.py)
- **TaskTypePattern** (ciris_engine/schemas/processors/solitude.py)
- **TaskTypeStats** (ciris_engine/schemas/processors/solitude.py)
- **TaskManager** (ciris_engine/logic/processors/support/task_manager.py)

### Processors - Specialized

- **CircuitBreakerStatus** (ciris_engine/schemas/processors/dma.py)
- **ErrorSeverity** (ciris_engine/schemas/processors/error.py)
- **StateTransitionResult** (ciris_engine/schemas/processors/main.py)
- **ProcessorSpecificMetrics** (ciris_engine/schemas/processors/base.py)
- **ProcessorMetrics** (ciris_engine/schemas/processors/base.py)
- **ProcessorServices** (ciris_engine/schemas/processors/main.py)
- **ProcessorContext** (ciris_engine/schemas/processors/context.py)
- **MetricsUpdate** (ciris_engine/schemas/processors/base.py)
- **WakeupState** (ciris_engine/schemas/processors/cognitive.py)
- **WorkState** (ciris_engine/schemas/processors/cognitive.py)

### Handlers - External Actions

- **ConnectedNodeInfo** (ciris_engine/schemas/handlers/memory_schemas.py)
- **HandlerActionType** (ciris_engine/schemas/runtime/enums.py)
- **HandlerInfo** (ciris_engine/schemas/registries/base.py)
- **HandlerContext** (ciris_engine/schemas/handlers/schemas.py)
- **HandlerResult** (ciris_engine/schemas/handlers/schemas.py)
- **HandlerDecapsulatedParams** (ciris_engine/schemas/handlers/schemas.py)
- **BaseActionContext** (ciris_engine/schemas/handlers/contexts.py)
- **SpeakContext** (ciris_engine/schemas/handlers/contexts.py)
- **ToolContext** (ciris_engine/schemas/handlers/contexts.py)
- **ObserveContext** (ciris_engine/schemas/handlers/contexts.py)

### Handlers - Control Actions

- **DeferralPackage** (ciris_engine/schemas/handlers/core.py)
- **RejectContext** (ciris_engine/schemas/handlers/contexts.py)
- **PonderContext** (ciris_engine/schemas/handlers/contexts.py)
- **DeferContext** (ciris_engine/schemas/handlers/contexts.py)
- **DeferralReason** (ciris_engine/schemas/handlers/core.py)
- **DeferralReport** (ciris_engine/schemas/handlers/core.py)
- **PonderHandler** (ciris_engine/logic/handlers/control/ponder_handler.py)
- **RejectHandler** (ciris_engine/logic/handlers/control/reject_handler.py)
- **DeferHandler** (ciris_engine/logic/handlers/control/defer_handler.py)

### Handlers - Memory Actions

- **MemorizeContext** (ciris_engine/schemas/handlers/contexts.py)
- **RecallContext** (ciris_engine/schemas/handlers/contexts.py)
- **ForgetContext** (ciris_engine/schemas/handlers/contexts.py)
- **RecalledNodeInfo** (ciris_engine/schemas/handlers/memory_schemas.py)
- **RecallResult** (ciris_engine/schemas/handlers/memory_schemas.py)
- **ForgetHandler** (ciris_engine/logic/handlers/memory/forget_handler.py)
- **DreamMemorizeHandler** (ciris_engine/logic/handlers/memory/dream_memorize_handler.py)
- **MemorizeHandler** (ciris_engine/logic/handlers/memory/memorize_handler.py)
- **RecallHandler** (ciris_engine/logic/handlers/memory/recall_handler.py)

### Handlers - Terminal Actions

- **TaskCompleteContext** (ciris_engine/schemas/handlers/contexts.py)
- **TaskCompleteHandler** (ciris_engine/logic/handlers/terminal/task_complete_handler.py)

### Dmas - Ethical

- **PDMAOverrides** (ciris_engine/schemas/config/agent.py)
- **StepResultPerformDMAs** (ciris_engine/schemas/services/runtime_control.py)
- **StepResultPerformASPDMA** (ciris_engine/schemas/services/runtime_control.py)
- **StepResultRecursiveASPDMA** (ciris_engine/schemas/services/runtime_control.py)
- **PerformDMAsStepData** (ciris_engine/schemas/services/runtime_control.py)
- **PerformASPDMAStepData** (ciris_engine/schemas/services/runtime_control.py)
- **RecursiveASPDMAStepData** (ciris_engine/schemas/services/runtime_control.py)
- **DMAResultsEvent** (ciris_engine/schemas/services/runtime_control.py)
- **IDMAResultEvent** (ciris_engine/schemas/services/runtime_control.py)
- **ASPDMAResultEvent** (ciris_engine/schemas/services/runtime_control.py)

### Dmas - Common Sense

- **CSDMAOverrides** (ciris_engine/schemas/config/agent.py)
- **CSDMAResult** (ciris_engine/schemas/dma/results.py)
- **CSDMAProtocol** (ciris_engine/protocols/dma/base.py)
- **CSDMAEvaluator** (ciris_engine/logic/dma/csdma.py)

### Dmas - Domain Specific

- **DSDMAConfiguration** (ciris_engine/schemas/config/agent.py)
- **DSDMAResult** (ciris_engine/schemas/dma/results.py)
- **DSDMAProtocol** (ciris_engine/protocols/dma/base.py)
- **BaseDSDMA** (ciris_engine/logic/dma/dsdma_base.py)
- **LLMOutputForDSDMA** (ciris_engine/logic/dma/dsdma_base.py)

### Dmas - Action Selection

- **ActionSelectionDMAResult** (ciris_engine/schemas/dma/results.py)
- **ActionSelectionDMAProtocol** (ciris_engine/protocols/dma/base.py)
- **ActionSelectionContextBuilder** (ciris_engine/logic/dma/action_selection/context_builder.py)
- **ActionSelectionSpecialCases** (ciris_engine/logic/dma/action_selection/special_cases.py)

### Faculties - Cognitive

- **EpistemicFaculty** (ciris_engine/protocols/faculties.py)

### Guardrails - Process

- **ThoughtDepthGuardrail** (ciris_engine/logic/conscience/thought_depth_guardrail.py)

### Runtime - Core

- **RuntimeBootstrapConfig** (ciris_engine/schemas/runtime/bootstrap.py)
- **RuntimeEvent** (ciris_engine/schemas/services/core/runtime.py)
- **RuntimeStatusResponse** (ciris_engine/schemas/services/core/runtime.py)
- **RuntimeStateSnapshot** (ciris_engine/schemas/services/core/runtime.py)
- **CIRISRuntime** (ciris_engine/logic/runtime/ciris_runtime.py)
- **RuntimeInterface** (ciris_engine/logic/runtime/runtime_interface.py)

### Runtime - Initialization

- **ServiceInitializer** (ciris_engine/logic/runtime/service_initializer.py)

### Runtime - Management

- **ThoughtProcessingResult** (ciris_engine/schemas/services/runtime_control.py)
- **ConfigDictMixin** (ciris_engine/schemas/services/runtime_control.py)
- **PropagatedCoherenceEntropyMixin** (ciris_engine/schemas/services/runtime_control.py)
- **StepPoint** (ciris_engine/schemas/services/runtime_control.py)
- **ReasoningEvent** (ciris_engine/schemas/services/runtime_control.py)
- **StepDuration** (ciris_engine/schemas/services/runtime_control.py)
- **SpanAttribute** (ciris_engine/schemas/services/runtime_control.py)
- **ConfigValueMap** (ciris_engine/schemas/services/runtime_control.py)
- **TaskSelectionCriteria** (ciris_engine/schemas/services/runtime_control.py)
- **ServiceProviderUpdate** (ciris_engine/schemas/services/runtime_control.py)

### Infrastructure - Buses

- **ServiceMetrics** (ciris_engine/logic/buses/llm_bus.py)
- **BusMetrics** (ciris_engine/schemas/infrastructure/base.py)
- **BusManagerProtocol** (ciris_engine/protocols/infrastructure/base.py)
- **BusManager** (ciris_engine/logic/buses/bus_manager.py)
- **SendMessageRequest** (ciris_engine/logic/buses/communication_bus.py)
- **FetchMessagesRequest** (ciris_engine/logic/buses/communication_bus.py)
- **CommunicationBus** (ciris_engine/logic/buses/communication_bus.py)
- **ProhibitionSeverity** (ciris_engine/logic/buses/prohibitions.py)
- **MemorizeBusMessage** (ciris_engine/logic/buses/memory_bus.py)
- **RecallBusMessage** (ciris_engine/logic/buses/memory_bus.py)

### Infrastructure - Registry

- **CrisisResourceRegistry** (ciris_engine/schemas/resources/crisis.py)
- **NodeTypeRegistry** (ciris_engine/schemas/services/graph_typed_nodes.py)
- **RegistryInfo** (ciris_engine/schemas/registries/base.py)
- **ServiceRegistrySnapshot** (ciris_engine/schemas/infrastructure/base.py)
- **ServiceRegistryProtocol** (ciris_engine/protocols/infrastructure/base.py)
- **RegistryAwareServiceProtocol** (ciris_engine/protocols/infrastructure/base.py)
- **ServiceRegistry** (ciris_engine/logic/registries/base.py)
- **TypedServiceRegistry** (ciris_engine/logic/registries/typed_registries.py)
- **MemoryRegistry** (ciris_engine/logic/registries/typed_registries.py)
- **LLMRegistry** (ciris_engine/logic/registries/typed_registries.py)

### Infrastructure - Persistence

- **CorrelationRequestData** (ciris_engine/schemas/persistence/correlations.py)
- **CorrelationResponseData** (ciris_engine/schemas/persistence/correlations.py)
- **ConversationSummaryData** (ciris_engine/schemas/persistence/correlations.py)
- **DeferralReportContext** (ciris_engine/schemas/persistence/core.py)
- **CorrelationUpdateRequest** (ciris_engine/schemas/persistence/core.py)
- **MetricsQuery** (ciris_engine/schemas/persistence/core.py)
- **IdentityContext** (ciris_engine/schemas/persistence/core.py)
- **TaskSummaryInfo** (ciris_engine/schemas/persistence/core.py)
- **QueryTimeRange** (ciris_engine/schemas/persistence/core.py)
- **PersistenceHealth** (ciris_engine/schemas/persistence/core.py)

### Infrastructure - Schemas

- **UserIdentifier** (ciris_engine/schemas/identity.py)
- **UserIdentityNode** (ciris_engine/schemas/identity.py)
- **IdentityMappingEvidence** (ciris_engine/schemas/identity.py)
- **IdentityConflict** (ciris_engine/schemas/identity.py)
- **IdentityConfidence** (ciris_engine/schemas/identity.py)
- **IdentityGraphVisualization** (ciris_engine/schemas/identity.py)
- **IdentityResolutionRequest** (ciris_engine/schemas/identity.py)
- **IdentityResolutionResult** (ciris_engine/schemas/identity.py)
- **IdentityMergeRequest** (ciris_engine/schemas/identity.py)
- **IdentityMergeResult** (ciris_engine/schemas/identity.py)

### Infrastructure - Utilities

- **DirectorySetupError** (ciris_engine/logic/utils/directory_setup.py)
- **PermissionError** (ciris_engine/logic/utils/directory_setup.py)
- **DiskSpaceError** (ciris_engine/logic/utils/directory_setup.py)
- **DirectoryCreationError** (ciris_engine/logic/utils/directory_setup.py)
- **OwnershipError** (ciris_engine/logic/utils/directory_setup.py)
- **WriteTestError** (ciris_engine/logic/utils/directory_setup.py)
- **DatabaseAccessError** (ciris_engine/logic/utils/directory_setup.py)
- **InitializationError** (ciris_engine/logic/utils/initialization_manager.py)
- **ShutdownManagerWrapper** (ciris_engine/logic/utils/shutdown_manager.py)
- **UserLocation** (ciris_engine/logic/utils/location_utils.py)

### ❓ Uncategorized Components

- **ModelCapabilities** (ciris_engine/config/model_capabilities.py)
- **ModelInfo** (ciris_engine/config/model_capabilities.py)
- **ProviderModels** (ciris_engine/config/model_capabilities.py)
- **RejectedModel** (ciris_engine/config/model_capabilities.py)
- **TierInfo** (ciris_engine/config/model_capabilities.py)
- **CirisRequirements** (ciris_engine/config/model_capabilities.py)
- **CapabilitiesMetadata** (ciris_engine/config/model_capabilities.py)
- **ModelCapabilitiesConfig** (ciris_engine/config/model_capabilities.py)
- **ServiceEndpoint** (ciris_engine/config/ciris_services.py)
- **ModelConfig** (ciris_engine/config/pricing_models.py)
- **RateLimits** (ciris_engine/config/pricing_models.py)
- **ProviderConfig** (ciris_engine/config/pricing_models.py)
- **EnergyEstimates** (ciris_engine/config/pricing_models.py)
- **CarbonIntensity** (ciris_engine/config/pricing_models.py)
- **EnvironmentalFactors** (ciris_engine/config/pricing_models.py)
- **FallbackPricing** (ciris_engine/config/pricing_models.py)
- **PricingMetadata** (ciris_engine/config/pricing_models.py)
- **PricingConfig** (ciris_engine/config/pricing_models.py)
- **ParameterType** (ciris_engine/schemas/tools.py)
- **ToolStatus** (ciris_engine/schemas/tools.py)
