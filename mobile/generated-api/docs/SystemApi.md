# SystemApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost**](SystemApi.md#completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost) | **POST** /v1/system/adapters/configure/{session_id}/complete | Complete Configuration |
| [**controlRuntimeV1SystemRuntimeActionPost**](SystemApi.md#controlRuntimeV1SystemRuntimeActionPost) | **POST** /v1/system/runtime/{action} | Control Runtime |
| [**executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost**](SystemApi.md#executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost) | **POST** /v1/system/adapters/configure/{session_id}/step | Execute Configuration Step |
| [**getAdapterStatusV1SystemAdaptersAdapterIdGet**](SystemApi.md#getAdapterStatusV1SystemAdaptersAdapterIdGet) | **GET** /v1/system/adapters/{adapter_id} | Get Adapter Status |
| [**getAvailableToolsV1SystemToolsGet**](SystemApi.md#getAvailableToolsV1SystemToolsGet) | **GET** /v1/system/tools | Get Available Tools |
| [**getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet**](SystemApi.md#getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet) | **GET** /v1/system/adapters/configure/{session_id} | Get Configuration Status |
| [**getResourceUsageV1SystemResourcesGet**](SystemApi.md#getResourceUsageV1SystemResourcesGet) | **GET** /v1/system/resources | Get Resource Usage |
| [**getServicesStatusV1SystemServicesGet**](SystemApi.md#getServicesStatusV1SystemServicesGet) | **GET** /v1/system/services | Get Services Status |
| [**getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet**](SystemApi.md#getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet) | **GET** /v1/system/adapters/configure/{session_id}/status | Get Session Status |
| [**getSystemHealthV1SystemHealthGet**](SystemApi.md#getSystemHealthV1SystemHealthGet) | **GET** /v1/system/health | Get System Health |
| [**getSystemTimeV1SystemTimeGet**](SystemApi.md#getSystemTimeV1SystemTimeGet) | **GET** /v1/system/time | Get System Time |
| [**listAdaptersV1SystemAdaptersGet**](SystemApi.md#listAdaptersV1SystemAdaptersGet) | **GET** /v1/system/adapters | List Adapters |
| [**listConfigurableAdaptersV1SystemAdaptersConfigurableGet**](SystemApi.md#listConfigurableAdaptersV1SystemAdaptersConfigurableGet) | **GET** /v1/system/adapters/configurable | List Configurable Adapters |
| [**listModuleTypesV1SystemAdaptersTypesGet**](SystemApi.md#listModuleTypesV1SystemAdaptersTypesGet) | **GET** /v1/system/adapters/types | List Module Types |
| [**listPersistedConfigurationsV1SystemAdaptersPersistedGet**](SystemApi.md#listPersistedConfigurationsV1SystemAdaptersPersistedGet) | **GET** /v1/system/adapters/persisted | List Persisted Configurations |
| [**loadAdapterV1SystemAdaptersAdapterTypePost**](SystemApi.md#loadAdapterV1SystemAdaptersAdapterTypePost) | **POST** /v1/system/adapters/{adapter_type} | Load Adapter |
| [**localShutdownV1SystemLocalShutdownPost**](SystemApi.md#localShutdownV1SystemLocalShutdownPost) | **POST** /v1/system/local-shutdown | Local Shutdown |
| [**oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet**](SystemApi.md#oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet) | **GET** /v1/system/adapters/configure/{session_id}/oauth/callback | Oauth Callback |
| [**oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet**](SystemApi.md#oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet) | **GET** /v1/system/adapters/oauth/callback | Oauth Deeplink Callback |
| [**reloadAdapterV1SystemAdaptersAdapterIdReloadPut**](SystemApi.md#reloadAdapterV1SystemAdaptersAdapterIdReloadPut) | **PUT** /v1/system/adapters/{adapter_id}/reload | Reload Adapter |
| [**removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete**](SystemApi.md#removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete) | **DELETE** /v1/system/adapters/{adapter_type}/persisted | Remove Persisted Configuration |
| [**shutdownSystemV1SystemShutdownPost**](SystemApi.md#shutdownSystemV1SystemShutdownPost) | **POST** /v1/system/shutdown | Shutdown System |
| [**startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost**](SystemApi.md#startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost) | **POST** /v1/system/adapters/{adapter_type}/configure/start | Start Adapter Configuration |
| [**transitionCognitiveStateV1SystemStateTransitionPost**](SystemApi.md#transitionCognitiveStateV1SystemStateTransitionPost) | **POST** /v1/system/state/transition | Transition Cognitive State |
| [**unloadAdapterV1SystemAdaptersAdapterIdDelete**](SystemApi.md#unloadAdapterV1SystemAdaptersAdapterIdDelete) | **DELETE** /v1/system/adapters/{adapter_id} | Unload Adapter |


<a id="completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost"></a>
# **completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost**
> SuccessResponseConfigurationCompleteResponse completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost(sessionId, authorization, configurationCompleteRequest)

Complete Configuration

Finalize and apply the configuration.  Validates the collected configuration and applies it to the adapter. Once completed, the adapter should be ready to use with the new configuration.  If &#x60;persist&#x60; is True, the configuration will be saved for automatic loading on startup, allowing the adapter to be automatically configured when the system restarts.  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val sessionId : kotlin.String = sessionId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
val configurationCompleteRequest : ConfigurationCompleteRequest =  // ConfigurationCompleteRequest |
try {
    val result : SuccessResponseConfigurationCompleteResponse = apiInstance.completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost(sessionId, authorization, configurationCompleteRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#completeConfigurationV1SystemAdaptersConfigureSessionIdCompletePost")
    e.printStackTrace()
}
```

### Parameters
| **sessionId** | **kotlin.String**|  | |
| **authorization** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **configurationCompleteRequest** | [**ConfigurationCompleteRequest**](ConfigurationCompleteRequest.md)|  | [optional] |

### Return type

[**SuccessResponseConfigurationCompleteResponse**](SuccessResponseConfigurationCompleteResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="controlRuntimeV1SystemRuntimeActionPost"></a>
# **controlRuntimeV1SystemRuntimeActionPost**
> SuccessResponseRuntimeControlResponse controlRuntimeV1SystemRuntimeActionPost(action, runtimeAction, authorization)

Control Runtime

Runtime control actions.  Control agent runtime behavior. Valid actions: - pause: Pause message processing - resume: Resume message processing - state: Get current runtime state  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val action : kotlin.String = action_example // kotlin.String |
val runtimeAction : RuntimeAction =  // RuntimeAction |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseRuntimeControlResponse = apiInstance.controlRuntimeV1SystemRuntimeActionPost(action, runtimeAction, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#controlRuntimeV1SystemRuntimeActionPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#controlRuntimeV1SystemRuntimeActionPost")
    e.printStackTrace()
}
```

### Parameters
| **action** | **kotlin.String**|  | |
| **runtimeAction** | [**RuntimeAction**](RuntimeAction.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseRuntimeControlResponse**](SuccessResponseRuntimeControlResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost"></a>
# **executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost**
> SuccessResponseStepExecutionResponse executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost(sessionId, stepExecutionRequest, authorization)

Execute Configuration Step

Execute the current configuration step.  The body contains step-specific data such as user selections, input values, or OAuth callback data. The step type determines what data is expected.  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val sessionId : kotlin.String = sessionId_example // kotlin.String |
val stepExecutionRequest : StepExecutionRequest =  // StepExecutionRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseStepExecutionResponse = apiInstance.executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost(sessionId, stepExecutionRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#executeConfigurationStepV1SystemAdaptersConfigureSessionIdStepPost")
    e.printStackTrace()
}
```

### Parameters
| **sessionId** | **kotlin.String**|  | |
| **stepExecutionRequest** | [**StepExecutionRequest**](StepExecutionRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseStepExecutionResponse**](SuccessResponseStepExecutionResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="getAdapterStatusV1SystemAdaptersAdapterIdGet"></a>
# **getAdapterStatusV1SystemAdaptersAdapterIdGet**
> SuccessResponseRuntimeAdapterStatus getAdapterStatusV1SystemAdaptersAdapterIdGet(adapterId, authorization)

Get Adapter Status

Get detailed status of a specific adapter.  Returns comprehensive information about an adapter instance including configuration, metrics, and service registrations.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val adapterId : kotlin.String = adapterId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseRuntimeAdapterStatus = apiInstance.getAdapterStatusV1SystemAdaptersAdapterIdGet(adapterId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getAdapterStatusV1SystemAdaptersAdapterIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getAdapterStatusV1SystemAdaptersAdapterIdGet")
    e.printStackTrace()
}
```

### Parameters
| **adapterId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseRuntimeAdapterStatus**](SuccessResponseRuntimeAdapterStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getAvailableToolsV1SystemToolsGet"></a>
# **getAvailableToolsV1SystemToolsGet**
> kotlin.collections.Map&lt;kotlin.String, ResponseGetAvailableToolsV1SystemToolsGetValue&gt; getAvailableToolsV1SystemToolsGet(authorization)

Get Available Tools

Get list of all available tools from all tool providers.  Returns tools from: - Core tool services (secrets, self_help) - Adapter tool services (API, Discord, etc.)  Requires OBSERVER role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.collections.Map<kotlin.String, ResponseGetAvailableToolsV1SystemToolsGetValue> = apiInstance.getAvailableToolsV1SystemToolsGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getAvailableToolsV1SystemToolsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getAvailableToolsV1SystemToolsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**kotlin.collections.Map&lt;kotlin.String, ResponseGetAvailableToolsV1SystemToolsGetValue&gt;**](ResponseGetAvailableToolsV1SystemToolsGetValue.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet"></a>
# **getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet**
> SuccessResponseConfigurationStatusResponse getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet(sessionId, authorization)

Get Configuration Status

Get current status of a configuration session.  Returns complete session state including current step, collected configuration, and session status.  Requires OBSERVER role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val sessionId : kotlin.String = sessionId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseConfigurationStatusResponse = apiInstance.getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet(sessionId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getConfigurationStatusV1SystemAdaptersConfigureSessionIdGet")
    e.printStackTrace()
}
```

### Parameters
| **sessionId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseConfigurationStatusResponse**](SuccessResponseConfigurationStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getResourceUsageV1SystemResourcesGet"></a>
# **getResourceUsageV1SystemResourcesGet**
> SuccessResponseResourceUsageResponse getResourceUsageV1SystemResourcesGet(authorization)

Get Resource Usage

Resource usage and limits.  Returns current resource consumption, configured limits, and health status.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseResourceUsageResponse = apiInstance.getResourceUsageV1SystemResourcesGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getResourceUsageV1SystemResourcesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getResourceUsageV1SystemResourcesGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseResourceUsageResponse**](SuccessResponseResourceUsageResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getServicesStatusV1SystemServicesGet"></a>
# **getServicesStatusV1SystemServicesGet**
> SuccessResponseServicesStatusResponse getServicesStatusV1SystemServicesGet(authorization)

Get Services Status

Service status.  Returns status of all system services including health, availability, and basic metrics.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseServicesStatusResponse = apiInstance.getServicesStatusV1SystemServicesGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getServicesStatusV1SystemServicesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getServicesStatusV1SystemServicesGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseServicesStatusResponse**](SuccessResponseServicesStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet"></a>
# **getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet**
> SuccessResponseConfigurationSessionResponse getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet(sessionId)

Get Session Status

Get the current status of a configuration session.  Useful for polling after OAuth callback to check if authentication completed.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val sessionId : kotlin.String = sessionId_example // kotlin.String |
try {
    val result : SuccessResponseConfigurationSessionResponse = apiInstance.getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet(sessionId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getSessionStatusV1SystemAdaptersConfigureSessionIdStatusGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **sessionId** | **kotlin.String**|  | |

### Return type

[**SuccessResponseConfigurationSessionResponse**](SuccessResponseConfigurationSessionResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getSystemHealthV1SystemHealthGet"></a>
# **getSystemHealthV1SystemHealthGet**
> SuccessResponseSystemHealthResponse getSystemHealthV1SystemHealthGet()

Get System Health

Overall system health.  Returns comprehensive system health including service status, initialization state, and current cognitive state.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
try {
    val result : SuccessResponseSystemHealthResponse = apiInstance.getSystemHealthV1SystemHealthGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getSystemHealthV1SystemHealthGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getSystemHealthV1SystemHealthGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseSystemHealthResponse**](SuccessResponseSystemHealthResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getSystemTimeV1SystemTimeGet"></a>
# **getSystemTimeV1SystemTimeGet**
> SuccessResponseSystemTimeResponse getSystemTimeV1SystemTimeGet(authorization)

Get System Time

System time information.  Returns both system time (host OS) and agent time (TimeService), along with synchronization status.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseSystemTimeResponse = apiInstance.getSystemTimeV1SystemTimeGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#getSystemTimeV1SystemTimeGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#getSystemTimeV1SystemTimeGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseSystemTimeResponse**](SuccessResponseSystemTimeResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listAdaptersV1SystemAdaptersGet"></a>
# **listAdaptersV1SystemAdaptersGet**
> SuccessResponseAdapterListResponse listAdaptersV1SystemAdaptersGet(authorization)

List Adapters

List all loaded adapters.  Returns information about all currently loaded adapter instances including their type, status, and basic metrics.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAdapterListResponse = apiInstance.listAdaptersV1SystemAdaptersGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#listAdaptersV1SystemAdaptersGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#listAdaptersV1SystemAdaptersGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAdapterListResponse**](SuccessResponseAdapterListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listConfigurableAdaptersV1SystemAdaptersConfigurableGet"></a>
# **listConfigurableAdaptersV1SystemAdaptersConfigurableGet**
> SuccessResponseConfigurableAdaptersResponse listConfigurableAdaptersV1SystemAdaptersConfigurableGet(authorization)

List Configurable Adapters

List adapters that support interactive configuration.  Returns information about all adapters that have defined interactive configuration workflows, including their workflow types and step counts.  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseConfigurableAdaptersResponse = apiInstance.listConfigurableAdaptersV1SystemAdaptersConfigurableGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#listConfigurableAdaptersV1SystemAdaptersConfigurableGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#listConfigurableAdaptersV1SystemAdaptersConfigurableGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseConfigurableAdaptersResponse**](SuccessResponseConfigurableAdaptersResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listModuleTypesV1SystemAdaptersTypesGet"></a>
# **listModuleTypesV1SystemAdaptersTypesGet**
> SuccessResponseModuleTypesResponse listModuleTypesV1SystemAdaptersTypesGet(authorization)

List Module Types

List all available module/adapter types.  Returns both core adapters (api, cli, discord) and modular services (mcp_client, mcp_server, reddit, etc.) with their typed configuration schemas.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseModuleTypesResponse = apiInstance.listModuleTypesV1SystemAdaptersTypesGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#listModuleTypesV1SystemAdaptersTypesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#listModuleTypesV1SystemAdaptersTypesGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseModuleTypesResponse**](SuccessResponseModuleTypesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listPersistedConfigurationsV1SystemAdaptersPersistedGet"></a>
# **listPersistedConfigurationsV1SystemAdaptersPersistedGet**
> SuccessResponsePersistedConfigsResponse listPersistedConfigurationsV1SystemAdaptersPersistedGet(authorization)

List Persisted Configurations

List all persisted adapter configurations.  Returns configurations that are set to load on startup.  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponsePersistedConfigsResponse = apiInstance.listPersistedConfigurationsV1SystemAdaptersPersistedGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#listPersistedConfigurationsV1SystemAdaptersPersistedGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#listPersistedConfigurationsV1SystemAdaptersPersistedGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponsePersistedConfigsResponse**](SuccessResponsePersistedConfigsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="loadAdapterV1SystemAdaptersAdapterTypePost"></a>
# **loadAdapterV1SystemAdaptersAdapterTypePost**
> SuccessResponseAdapterOperationResult loadAdapterV1SystemAdaptersAdapterTypePost(adapterType, adapterActionRequest, adapterId, authorization)

Load Adapter

Load a new adapter instance.  Dynamically loads and starts a new adapter of the specified type. Requires ADMIN role.  Adapter types: cli, api, discord, mcp, mcp_server

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val adapterType : kotlin.String = adapterType_example // kotlin.String |
val adapterActionRequest : AdapterActionRequest =  // AdapterActionRequest |
val adapterId : kotlin.String = adapterId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAdapterOperationResult = apiInstance.loadAdapterV1SystemAdaptersAdapterTypePost(adapterType, adapterActionRequest, adapterId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#loadAdapterV1SystemAdaptersAdapterTypePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#loadAdapterV1SystemAdaptersAdapterTypePost")
    e.printStackTrace()
}
```

### Parameters
| **adapterType** | **kotlin.String**|  | |
| **adapterActionRequest** | [**AdapterActionRequest**](AdapterActionRequest.md)|  | |
| **adapterId** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAdapterOperationResult**](SuccessResponseAdapterOperationResult.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="localShutdownV1SystemLocalShutdownPost"></a>
# **localShutdownV1SystemLocalShutdownPost**
> SuccessResponseShutdownResponse localShutdownV1SystemLocalShutdownPost()

Local Shutdown

Localhost-only shutdown endpoint (no authentication required).  This endpoint is designed for Android/mobile apps where: - App data may be cleared (losing auth tokens) - Previous Python process may still be running - Need to gracefully shut down before starting new instance  Security: Only accepts requests from localhost (127.0.0.1, ::1). This is safe because only processes on the same device can call it.  Response codes for SmartStartup negotiation: - 200: Shutdown initiated successfully - 202: Shutdown already in progress - 403: Not localhost (security rejection) - 409: Resume in progress, retry later (with retry_after_ms) - 503: Server not ready

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
try {
    val result : SuccessResponseShutdownResponse = apiInstance.localShutdownV1SystemLocalShutdownPost()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#localShutdownV1SystemLocalShutdownPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#localShutdownV1SystemLocalShutdownPost")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseShutdownResponse**](SuccessResponseShutdownResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet"></a>
# **oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet**
> kotlin.Any oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet(sessionId, code, state)

Oauth Callback

Handle OAuth callback from external service.  This endpoint is called by OAuth providers after user authorization. It processes the authorization code and advances the configuration workflow. Returns HTML that redirects back to the app or shows success message.  No authentication required (OAuth state validation provides security).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val sessionId : kotlin.String = sessionId_example // kotlin.String |
val code : kotlin.String = code_example // kotlin.String |
val state : kotlin.String = state_example // kotlin.String |
try {
    val result : kotlin.Any = apiInstance.oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet(sessionId, code, state)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#oauthCallbackV1SystemAdaptersConfigureSessionIdOauthCallbackGet")
    e.printStackTrace()
}
```

### Parameters
| **sessionId** | **kotlin.String**|  | |
| **code** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **state** | **kotlin.String**|  | |

### Return type

[**kotlin.Any**](kotlin.Any.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet"></a>
# **oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet**
> SuccessResponseDictStrAny oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet(code, state, provider, source)

Oauth Deeplink Callback

Handle OAuth callback forwarded from Android deep link (ciris://oauth/callback).  This endpoint receives OAuth callbacks that were forwarded from OAuthCallbackActivity on Android. The Android app uses a deep link (ciris://oauth/callback) to receive the OAuth redirect from the system browser, then forwards to this endpoint.  This is a generic endpoint that works for any OAuth2 provider (Home Assistant, Discord, Google, Microsoft, Reddit, etc.) - the state parameter contains the session_id which identifies the configuration session.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val code : kotlin.String = code_example // kotlin.String |
val state : kotlin.String = state_example // kotlin.String |
val provider : kotlin.String = provider_example // kotlin.String |
val source : kotlin.String = source_example // kotlin.String |
try {
    val result : SuccessResponseDictStrAny = apiInstance.oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet(code, state, provider, source)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#oauthDeeplinkCallbackV1SystemAdaptersOauthCallbackGet")
    e.printStackTrace()
}
```

### Parameters
| **code** | **kotlin.String**|  | |
| **state** | **kotlin.String**|  | |
| **provider** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **source** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseDictStrAny**](SuccessResponseDictStrAny.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="reloadAdapterV1SystemAdaptersAdapterIdReloadPut"></a>
# **reloadAdapterV1SystemAdaptersAdapterIdReloadPut**
> SuccessResponseAdapterOperationResult reloadAdapterV1SystemAdaptersAdapterIdReloadPut(adapterId, adapterActionRequest, authorization)

Reload Adapter

Reload an adapter with new configuration.  Stops the adapter and restarts it with new configuration. Useful for applying configuration changes without full restart. Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val adapterId : kotlin.String = adapterId_example // kotlin.String |
val adapterActionRequest : AdapterActionRequest =  // AdapterActionRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAdapterOperationResult = apiInstance.reloadAdapterV1SystemAdaptersAdapterIdReloadPut(adapterId, adapterActionRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#reloadAdapterV1SystemAdaptersAdapterIdReloadPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#reloadAdapterV1SystemAdaptersAdapterIdReloadPut")
    e.printStackTrace()
}
```

### Parameters
| **adapterId** | **kotlin.String**|  | |
| **adapterActionRequest** | [**AdapterActionRequest**](AdapterActionRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAdapterOperationResult**](SuccessResponseAdapterOperationResult.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete"></a>
# **removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete**
> SuccessResponseRemovePersistedResponse removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete(adapterType, authorization)

Remove Persisted Configuration

Remove a persisted adapter configuration.  This prevents the adapter from being automatically loaded on startup.  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val adapterType : kotlin.String = adapterType_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseRemovePersistedResponse = apiInstance.removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete(adapterType, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#removePersistedConfigurationV1SystemAdaptersAdapterTypePersistedDelete")
    e.printStackTrace()
}
```

### Parameters
| **adapterType** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseRemovePersistedResponse**](SuccessResponseRemovePersistedResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="shutdownSystemV1SystemShutdownPost"></a>
# **shutdownSystemV1SystemShutdownPost**
> SuccessResponseShutdownResponse shutdownSystemV1SystemShutdownPost(shutdownRequest, authorization)

Shutdown System

Graceful shutdown.  Initiates graceful system shutdown. Requires confirmation flag to prevent accidental shutdowns.  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val shutdownRequest : ShutdownRequest =  // ShutdownRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseShutdownResponse = apiInstance.shutdownSystemV1SystemShutdownPost(shutdownRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#shutdownSystemV1SystemShutdownPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#shutdownSystemV1SystemShutdownPost")
    e.printStackTrace()
}
```

### Parameters
| **shutdownRequest** | [**ShutdownRequest**](ShutdownRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseShutdownResponse**](SuccessResponseShutdownResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost"></a>
# **startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost**
> SuccessResponseConfigurationSessionResponse startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost(adapterType, authorization)

Start Adapter Configuration

Start interactive configuration session for an adapter.  Creates a new configuration session and returns the session ID along with information about the first step in the workflow.  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val adapterType : kotlin.String = adapterType_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseConfigurationSessionResponse = apiInstance.startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost(adapterType, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#startAdapterConfigurationV1SystemAdaptersAdapterTypeConfigureStartPost")
    e.printStackTrace()
}
```

### Parameters
| **adapterType** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseConfigurationSessionResponse**](SuccessResponseConfigurationSessionResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="transitionCognitiveStateV1SystemStateTransitionPost"></a>
# **transitionCognitiveStateV1SystemStateTransitionPost**
> SuccessResponseStateTransitionResponse transitionCognitiveStateV1SystemStateTransitionPost(stateTransitionRequest, authorization)

Transition Cognitive State

Request a cognitive state transition.  Transitions the agent to a different cognitive state (WORK, DREAM, PLAY, SOLITUDE). Valid transitions depend on the current state: - From WORK: Can transition to DREAM, PLAY, or SOLITUDE - From PLAY: Can transition to WORK or SOLITUDE - From SOLITUDE: Can transition to WORK - From DREAM: Typically transitions back to WORK when complete  Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val stateTransitionRequest : StateTransitionRequest =  // StateTransitionRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseStateTransitionResponse = apiInstance.transitionCognitiveStateV1SystemStateTransitionPost(stateTransitionRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#transitionCognitiveStateV1SystemStateTransitionPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#transitionCognitiveStateV1SystemStateTransitionPost")
    e.printStackTrace()
}
```

### Parameters
| **stateTransitionRequest** | [**StateTransitionRequest**](StateTransitionRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseStateTransitionResponse**](SuccessResponseStateTransitionResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="unloadAdapterV1SystemAdaptersAdapterIdDelete"></a>
# **unloadAdapterV1SystemAdaptersAdapterIdDelete**
> SuccessResponseAdapterOperationResult unloadAdapterV1SystemAdaptersAdapterIdDelete(adapterId, authorization)

Unload Adapter

Unload an adapter instance.  Stops and removes an adapter from the runtime. Will fail if it&#39;s the last communication-capable adapter. Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemApi()
val adapterId : kotlin.String = adapterId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAdapterOperationResult = apiInstance.unloadAdapterV1SystemAdaptersAdapterIdDelete(adapterId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemApi#unloadAdapterV1SystemAdaptersAdapterIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemApi#unloadAdapterV1SystemAdaptersAdapterIdDelete")
    e.printStackTrace()
}
```

### Parameters
| **adapterId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAdapterOperationResult**](SuccessResponseAdapterOperationResult.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json
