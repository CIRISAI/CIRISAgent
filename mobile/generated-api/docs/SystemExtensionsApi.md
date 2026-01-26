# SystemExtensionsApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**getProcessingQueueStatusV1SystemRuntimeQueueGet**](SystemExtensionsApi.md#getProcessingQueueStatusV1SystemRuntimeQueueGet) | **GET** /v1/system/runtime/queue | Get Processing Queue Status |
| [**getProcessorStatesV1SystemProcessorsGet**](SystemExtensionsApi.md#getProcessorStatesV1SystemProcessorsGet) | **GET** /v1/system/processors | Get Processor States |
| [**getServiceHealthDetailsV1SystemServicesHealthGet**](SystemExtensionsApi.md#getServiceHealthDetailsV1SystemServicesHealthGet) | **GET** /v1/system/services/health | Get Service Health Details |
| [**getServiceSelectionExplanationV1SystemServicesSelectionLogicGet**](SystemExtensionsApi.md#getServiceSelectionExplanationV1SystemServicesSelectionLogicGet) | **GET** /v1/system/services/selection-logic | Get Service Selection Explanation |
| [**reasoningStreamV1SystemRuntimeReasoningStreamGet**](SystemExtensionsApi.md#reasoningStreamV1SystemRuntimeReasoningStreamGet) | **GET** /v1/system/runtime/reasoning-stream | Reasoning Stream |
| [**resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost**](SystemExtensionsApi.md#resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost) | **POST** /v1/system/services/circuit-breakers/reset | Reset Service Circuit Breakers |
| [**singleStepProcessorV1SystemRuntimeStepPost**](SystemExtensionsApi.md#singleStepProcessorV1SystemRuntimeStepPost) | **POST** /v1/system/runtime/step | Single Step Processor |
| [**updateServicePriorityV1SystemServicesProviderNamePriorityPut**](SystemExtensionsApi.md#updateServicePriorityV1SystemServicesProviderNamePriorityPut) | **PUT** /v1/system/services/{provider_name}/priority | Update Service Priority |


<a id="getProcessingQueueStatusV1SystemRuntimeQueueGet"></a>
# **getProcessingQueueStatusV1SystemRuntimeQueueGet**
> SuccessResponseProcessorQueueStatus getProcessingQueueStatusV1SystemRuntimeQueueGet(authorization)

Get Processing Queue Status

Get processing queue status.  Returns information about pending thoughts, tasks, and processing metrics.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseProcessorQueueStatus = apiInstance.getProcessingQueueStatusV1SystemRuntimeQueueGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#getProcessingQueueStatusV1SystemRuntimeQueueGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#getProcessingQueueStatusV1SystemRuntimeQueueGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseProcessorQueueStatus**](SuccessResponseProcessorQueueStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getProcessorStatesV1SystemProcessorsGet"></a>
# **getProcessorStatesV1SystemProcessorsGet**
> SuccessResponseListProcessorStateInfo getProcessorStatesV1SystemProcessorsGet(authorization)

Get Processor States

Get information about all processor states.  Returns the list of available processor states (WAKEUP, WORK, DREAM, PLAY, SOLITUDE, SHUTDOWN) and which one is currently active.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseListProcessorStateInfo = apiInstance.getProcessorStatesV1SystemProcessorsGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#getProcessorStatesV1SystemProcessorsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#getProcessorStatesV1SystemProcessorsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseListProcessorStateInfo**](SuccessResponseListProcessorStateInfo.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getServiceHealthDetailsV1SystemServicesHealthGet"></a>
# **getServiceHealthDetailsV1SystemServicesHealthGet**
> SuccessResponseServiceHealthStatus getServiceHealthDetailsV1SystemServicesHealthGet(authorization)

Get Service Health Details

Get detailed service health status.  Returns comprehensive health information including circuit breaker states, error rates, and recommendations.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseServiceHealthStatus = apiInstance.getServiceHealthDetailsV1SystemServicesHealthGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#getServiceHealthDetailsV1SystemServicesHealthGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#getServiceHealthDetailsV1SystemServicesHealthGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseServiceHealthStatus**](SuccessResponseServiceHealthStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getServiceSelectionExplanationV1SystemServicesSelectionLogicGet"></a>
# **getServiceSelectionExplanationV1SystemServicesSelectionLogicGet**
> SuccessResponseServiceSelectionExplanation getServiceSelectionExplanationV1SystemServicesSelectionLogicGet(authorization)

Get Service Selection Explanation

Get service selection logic explanation.  Returns detailed explanation of how services are selected, including priority groups, priorities, strategies, and circuit breaker behavior.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseServiceSelectionExplanation = apiInstance.getServiceSelectionExplanationV1SystemServicesSelectionLogicGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#getServiceSelectionExplanationV1SystemServicesSelectionLogicGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#getServiceSelectionExplanationV1SystemServicesSelectionLogicGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseServiceSelectionExplanation**](SuccessResponseServiceSelectionExplanation.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="reasoningStreamV1SystemRuntimeReasoningStreamGet"></a>
# **reasoningStreamV1SystemRuntimeReasoningStreamGet**
> kotlin.Any reasoningStreamV1SystemRuntimeReasoningStreamGet(authorization)

Reasoning Stream

Stream live H3ERE reasoning steps as they occur.  Provides real-time streaming of step-by-step reasoning for live UI generation. Returns Server-Sent Events (SSE) with step data as processing happens. Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.Any = apiInstance.reasoningStreamV1SystemRuntimeReasoningStreamGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#reasoningStreamV1SystemRuntimeReasoningStreamGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#reasoningStreamV1SystemRuntimeReasoningStreamGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**kotlin.Any**](kotlin.Any.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost"></a>
# **resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost**
> SuccessResponseCircuitBreakerResetResponse resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost(circuitBreakerResetRequest, authorization)

Reset Service Circuit Breakers

Reset circuit breakers.  Resets circuit breakers for specified service type or all services. Useful for recovering from transient failures. Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val circuitBreakerResetRequest : CircuitBreakerResetRequest =  // CircuitBreakerResetRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseCircuitBreakerResetResponse = apiInstance.resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost(circuitBreakerResetRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#resetServiceCircuitBreakersV1SystemServicesCircuitBreakersResetPost")
    e.printStackTrace()
}
```

### Parameters
| **circuitBreakerResetRequest** | [**CircuitBreakerResetRequest**](CircuitBreakerResetRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseCircuitBreakerResetResponse**](SuccessResponseCircuitBreakerResetResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="singleStepProcessorV1SystemRuntimeStepPost"></a>
# **singleStepProcessorV1SystemRuntimeStepPost**
> SuccessResponseSingleStepResponse singleStepProcessorV1SystemRuntimeStepPost(authorization, requestBody)

Single Step Processor

Execute a single processing step.  Useful for debugging and demonstrations. Processes one item from the queue. Always returns detailed H3ERE step data for transparency. Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
val requestBody : kotlin.collections.Map<kotlin.String, BodyValue> = Object // kotlin.collections.Map<kotlin.String, BodyValue> |
try {
    val result : SuccessResponseSingleStepResponse = apiInstance.singleStepProcessorV1SystemRuntimeStepPost(authorization, requestBody)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#singleStepProcessorV1SystemRuntimeStepPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#singleStepProcessorV1SystemRuntimeStepPost")
    e.printStackTrace()
}
```

### Parameters
| **authorization** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **requestBody** | [**kotlin.collections.Map&lt;kotlin.String, BodyValue&gt;**](BodyValue.md)|  | [optional] |

### Return type

[**SuccessResponseSingleStepResponse**](SuccessResponseSingleStepResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="updateServicePriorityV1SystemServicesProviderNamePriorityPut"></a>
# **updateServicePriorityV1SystemServicesProviderNamePriorityPut**
> SuccessResponseServicePriorityUpdateResponse updateServicePriorityV1SystemServicesProviderNamePriorityPut(providerName, servicePriorityUpdateRequest, authorization)

Update Service Priority

Update service provider priority.  Changes the priority, priority group, and/or selection strategy for a service provider. Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SystemExtensionsApi()
val providerName : kotlin.String = providerName_example // kotlin.String |
val servicePriorityUpdateRequest : ServicePriorityUpdateRequest =  // ServicePriorityUpdateRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseServicePriorityUpdateResponse = apiInstance.updateServicePriorityV1SystemServicesProviderNamePriorityPut(providerName, servicePriorityUpdateRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SystemExtensionsApi#updateServicePriorityV1SystemServicesProviderNamePriorityPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SystemExtensionsApi#updateServicePriorityV1SystemServicesProviderNamePriorityPut")
    e.printStackTrace()
}
```

### Parameters
| **providerName** | **kotlin.String**|  | |
| **servicePriorityUpdateRequest** | [**ServicePriorityUpdateRequest**](ServicePriorityUpdateRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseServicePriorityUpdateResponse**](SuccessResponseServicePriorityUpdateResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
