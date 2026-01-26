# TransparencyApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**getCoherenceTracesV1TransparencyTracesGet**](TransparencyApi.md#getCoherenceTracesV1TransparencyTracesGet) | **GET** /v1/transparency/traces | Get Coherence Traces |
| [**getLatestTraceV1TransparencyTracesLatestGet**](TransparencyApi.md#getLatestTraceV1TransparencyTracesLatestGet) | **GET** /v1/transparency/traces/latest | Get Latest Trace |
| [**getSystemStatusV1TransparencyStatusGet**](TransparencyApi.md#getSystemStatusV1TransparencyStatusGet) | **GET** /v1/transparency/status | Get System Status |
| [**getTransparencyFeedV1TransparencyFeedGet**](TransparencyApi.md#getTransparencyFeedV1TransparencyFeedGet) | **GET** /v1/transparency/feed | Get Transparency Feed |
| [**getTransparencyPolicyV1TransparencyPolicyGet**](TransparencyApi.md#getTransparencyPolicyV1TransparencyPolicyGet) | **GET** /v1/transparency/policy | Get Transparency Policy |


<a id="getCoherenceTracesV1TransparencyTracesGet"></a>
# **getCoherenceTracesV1TransparencyTracesGet**
> TracesListResponse getCoherenceTracesV1TransparencyTracesGet(limit)

Get Coherence Traces

Get captured reasoning traces for Coherence Ratchet corpus.  Returns complete 6-component traces from opted-in agents. Traces include: Observation, Context, Rationale, Conscience, Action, Outcome.  Requires metrics consent to be enabled.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TransparencyApi()
val limit : kotlin.Int = 56 // kotlin.Int |
try {
    val result : TracesListResponse = apiInstance.getCoherenceTracesV1TransparencyTracesGet(limit)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TransparencyApi#getCoherenceTracesV1TransparencyTracesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TransparencyApi#getCoherenceTracesV1TransparencyTracesGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **limit** | **kotlin.Int**|  | [optional] [default to 10] |

### Return type

[**TracesListResponse**](TracesListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getLatestTraceV1TransparencyTracesLatestGet"></a>
# **getLatestTraceV1TransparencyTracesLatestGet**
> CompleteTraceResponse getLatestTraceV1TransparencyTracesLatestGet()

Get Latest Trace

Get the most recently captured reasoning trace.  Returns the latest complete trace with all 6 components.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TransparencyApi()
try {
    val result : CompleteTraceResponse = apiInstance.getLatestTraceV1TransparencyTracesLatestGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TransparencyApi#getLatestTraceV1TransparencyTracesLatestGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TransparencyApi#getLatestTraceV1TransparencyTracesLatestGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**CompleteTraceResponse**](CompleteTraceResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getSystemStatusV1TransparencyStatusGet"></a>
# **getSystemStatusV1TransparencyStatusGet**
> kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt; getSystemStatusV1TransparencyStatusGet()

Get System Status

Get current system status.  This endpoint can be updated quickly if we need to pause.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TransparencyApi()
try {
    val result : kotlin.collections.Map<kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue> = apiInstance.getSystemStatusV1TransparencyStatusGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TransparencyApi#getSystemStatusV1TransparencyStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TransparencyApi#getSystemStatusV1TransparencyStatusGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getTransparencyFeedV1TransparencyFeedGet"></a>
# **getTransparencyFeedV1TransparencyFeedGet**
> TransparencyStats getTransparencyFeedV1TransparencyFeedGet(hours)

Get Transparency Feed

Get public transparency statistics.  No authentication required - this is public information. Returns anonymized, aggregated statistics only.  Args:     hours: Number of hours to report (default 24, max 168/7 days)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TransparencyApi()
val hours : kotlin.Int = 56 // kotlin.Int |
try {
    val result : TransparencyStats = apiInstance.getTransparencyFeedV1TransparencyFeedGet(hours)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TransparencyApi#getTransparencyFeedV1TransparencyFeedGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TransparencyApi#getTransparencyFeedV1TransparencyFeedGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **hours** | **kotlin.Int**|  | [optional] [default to 24] |

### Return type

[**TransparencyStats**](TransparencyStats.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getTransparencyPolicyV1TransparencyPolicyGet"></a>
# **getTransparencyPolicyV1TransparencyPolicyGet**
> TransparencyPolicy getTransparencyPolicyV1TransparencyPolicyGet()

Get Transparency Policy

Get transparency policy information.  Public endpoint describing our transparency commitments.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TransparencyApi()
try {
    val result : TransparencyPolicy = apiInstance.getTransparencyPolicyV1TransparencyPolicyGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TransparencyApi#getTransparencyPolicyV1TransparencyPolicyGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TransparencyApi#getTransparencyPolicyV1TransparencyPolicyGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**TransparencyPolicy**](TransparencyPolicy.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json
