# TelemetryApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**getDetailedMetricV1TelemetryMetricsMetricNameGet**](TelemetryApi.md#getDetailedMetricV1TelemetryMetricsMetricNameGet) | **GET** /v1/telemetry/metrics/{metric_name} | Get Detailed Metric |
| [**getDetailedMetricsV1TelemetryMetricsGet**](TelemetryApi.md#getDetailedMetricsV1TelemetryMetricsGet) | **GET** /v1/telemetry/metrics | Get Detailed Metrics |
| [**getOtlpTelemetryV1TelemetryOtlpSignalGet**](TelemetryApi.md#getOtlpTelemetryV1TelemetryOtlpSignalGet) | **GET** /v1/telemetry/otlp/{signal} | Get Otlp Telemetry |
| [**getReasoningTracesV1TelemetryTracesGet**](TelemetryApi.md#getReasoningTracesV1TelemetryTracesGet) | **GET** /v1/telemetry/traces | Get Reasoning Traces |
| [**getResourceHistoryV1TelemetryResourcesHistoryGet**](TelemetryApi.md#getResourceHistoryV1TelemetryResourcesHistoryGet) | **GET** /v1/telemetry/resources/history | Get Resource History |
| [**getResourceTelemetryV1TelemetryResourcesGet**](TelemetryApi.md#getResourceTelemetryV1TelemetryResourcesGet) | **GET** /v1/telemetry/resources | Get Resource Telemetry |
| [**getSystemLogsV1TelemetryLogsGet**](TelemetryApi.md#getSystemLogsV1TelemetryLogsGet) | **GET** /v1/telemetry/logs | Get System Logs |
| [**getTelemetryOverviewV1TelemetryOverviewGet**](TelemetryApi.md#getTelemetryOverviewV1TelemetryOverviewGet) | **GET** /v1/telemetry/overview | Get Telemetry Overview |
| [**getUnifiedTelemetryV1TelemetryUnifiedGet**](TelemetryApi.md#getUnifiedTelemetryV1TelemetryUnifiedGet) | **GET** /v1/telemetry/unified | Get Unified Telemetry |
| [**queryTelemetryV1TelemetryQueryPost**](TelemetryApi.md#queryTelemetryV1TelemetryQueryPost) | **POST** /v1/telemetry/query | Query Telemetry |


<a id="getDetailedMetricV1TelemetryMetricsMetricNameGet"></a>
# **getDetailedMetricV1TelemetryMetricsMetricNameGet**
> SuccessResponseDetailedMetric getDetailedMetricV1TelemetryMetricsMetricNameGet(metricName, hours, authorization)

Get Detailed Metric

Get detailed information about a specific metric.  Returns current value, trends, and historical data for the specified metric.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val metricName : kotlin.String = metricName_example // kotlin.String |
val hours : kotlin.Int = 56 // kotlin.Int | Hours of history to include
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseDetailedMetric = apiInstance.getDetailedMetricV1TelemetryMetricsMetricNameGet(metricName, hours, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getDetailedMetricV1TelemetryMetricsMetricNameGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getDetailedMetricV1TelemetryMetricsMetricNameGet")
    e.printStackTrace()
}
```

### Parameters
| **metricName** | **kotlin.String**|  | |
| **hours** | **kotlin.Int**| Hours of history to include | [optional] [default to 24] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseDetailedMetric**](SuccessResponseDetailedMetric.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getDetailedMetricsV1TelemetryMetricsGet"></a>
# **getDetailedMetricsV1TelemetryMetricsGet**
> SuccessResponseMetricsResponse getDetailedMetricsV1TelemetryMetricsGet(authorization)

Get Detailed Metrics

Detailed metrics.  Get detailed metrics with trends and breakdowns by service.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseMetricsResponse = apiInstance.getDetailedMetricsV1TelemetryMetricsGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getDetailedMetricsV1TelemetryMetricsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getDetailedMetricsV1TelemetryMetricsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseMetricsResponse**](SuccessResponseMetricsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getOtlpTelemetryV1TelemetryOtlpSignalGet"></a>
# **getOtlpTelemetryV1TelemetryOtlpSignalGet**
> kotlin.Any getOtlpTelemetryV1TelemetryOtlpSignalGet(signal, limit, startTime, endTime, authorization)

Get Otlp Telemetry

OpenTelemetry Protocol (OTLP) JSON export.  Export telemetry data in OTLP JSON format for OpenTelemetry collectors.  Supported signals: - metrics: System and service metrics - traces: Distributed traces with spans - logs: Structured log records  Returns OTLP JSON formatted data compatible with OpenTelemetry v1.7.0 specification.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val signal : kotlin.String = signal_example // kotlin.String |
val limit : kotlin.Int = 56 // kotlin.Int | Maximum items to return
val startTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | Start of time range
val endTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | End of time range
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.Any = apiInstance.getOtlpTelemetryV1TelemetryOtlpSignalGet(signal, limit, startTime, endTime, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getOtlpTelemetryV1TelemetryOtlpSignalGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getOtlpTelemetryV1TelemetryOtlpSignalGet")
    e.printStackTrace()
}
```

### Parameters
| **signal** | **kotlin.String**|  | |
| **limit** | **kotlin.Int**| Maximum items to return | [optional] [default to 100] |
| **startTime** | **kotlin.time.Instant**| Start of time range | [optional] |
| **endTime** | **kotlin.time.Instant**| End of time range | [optional] |
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

<a id="getReasoningTracesV1TelemetryTracesGet"></a>
# **getReasoningTracesV1TelemetryTracesGet**
> SuccessResponseTracesResponse getReasoningTracesV1TelemetryTracesGet(limit, startTime, endTime, authorization)

Get Reasoning Traces

Reasoning traces.  Get reasoning traces showing agent thought processes and decision-making.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val limit : kotlin.Int = 56 // kotlin.Int | Maximum traces to return
val startTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | Start of time range
val endTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | End of time range
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseTracesResponse = apiInstance.getReasoningTracesV1TelemetryTracesGet(limit, startTime, endTime, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getReasoningTracesV1TelemetryTracesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getReasoningTracesV1TelemetryTracesGet")
    e.printStackTrace()
}
```

### Parameters
| **limit** | **kotlin.Int**| Maximum traces to return | [optional] [default to 10] |
| **startTime** | **kotlin.time.Instant**| Start of time range | [optional] |
| **endTime** | **kotlin.time.Instant**| End of time range | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseTracesResponse**](SuccessResponseTracesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getResourceHistoryV1TelemetryResourcesHistoryGet"></a>
# **getResourceHistoryV1TelemetryResourcesHistoryGet**
> SuccessResponse getResourceHistoryV1TelemetryResourcesHistoryGet(hours, authorization)

Get Resource History

Get historical resource usage data.  Returns time-series data for resource usage over the specified period.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val hours : kotlin.Int = 56 // kotlin.Int | Hours of history
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponse = apiInstance.getResourceHistoryV1TelemetryResourcesHistoryGet(hours, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getResourceHistoryV1TelemetryResourcesHistoryGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getResourceHistoryV1TelemetryResourcesHistoryGet")
    e.printStackTrace()
}
```

### Parameters
| **hours** | **kotlin.Int**| Hours of history | [optional] [default to 24] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponse**](SuccessResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getResourceTelemetryV1TelemetryResourcesGet"></a>
# **getResourceTelemetryV1TelemetryResourcesGet**
> SuccessResponseResourceTelemetryResponse getResourceTelemetryV1TelemetryResourcesGet(authorization)

Get Resource Telemetry

Get current resource usage telemetry.  Returns CPU, memory, disk, and other resource metrics.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseResourceTelemetryResponse = apiInstance.getResourceTelemetryV1TelemetryResourcesGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getResourceTelemetryV1TelemetryResourcesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getResourceTelemetryV1TelemetryResourcesGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseResourceTelemetryResponse**](SuccessResponseResourceTelemetryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getSystemLogsV1TelemetryLogsGet"></a>
# **getSystemLogsV1TelemetryLogsGet**
> SuccessResponseLogsResponse getSystemLogsV1TelemetryLogsGet(startTime, endTime, level, service, limit, authorization)

Get System Logs

System logs.  Get system logs from all services with filtering capabilities.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val startTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | Start of time range
val endTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | End of time range
val level : kotlin.String = level_example // kotlin.String | Log level filter
val service : kotlin.String = service_example // kotlin.String | Service filter
val limit : kotlin.Int = 56 // kotlin.Int | Maximum logs to return
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseLogsResponse = apiInstance.getSystemLogsV1TelemetryLogsGet(startTime, endTime, level, service, limit, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getSystemLogsV1TelemetryLogsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getSystemLogsV1TelemetryLogsGet")
    e.printStackTrace()
}
```

### Parameters
| **startTime** | **kotlin.time.Instant**| Start of time range | [optional] |
| **endTime** | **kotlin.time.Instant**| End of time range | [optional] |
| **level** | **kotlin.String**| Log level filter | [optional] |
| **service** | **kotlin.String**| Service filter | [optional] |
| **limit** | **kotlin.Int**| Maximum logs to return | [optional] [default to 100] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseLogsResponse**](SuccessResponseLogsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getTelemetryOverviewV1TelemetryOverviewGet"></a>
# **getTelemetryOverviewV1TelemetryOverviewGet**
> SuccessResponseSystemOverview getTelemetryOverviewV1TelemetryOverviewGet(authorization)

Get Telemetry Overview

System metrics summary.  Comprehensive overview combining telemetry, visibility, incidents, and resource usage.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseSystemOverview = apiInstance.getTelemetryOverviewV1TelemetryOverviewGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getTelemetryOverviewV1TelemetryOverviewGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getTelemetryOverviewV1TelemetryOverviewGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseSystemOverview**](SuccessResponseSystemOverview.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getUnifiedTelemetryV1TelemetryUnifiedGet"></a>
# **getUnifiedTelemetryV1TelemetryUnifiedGet**
> kotlin.Any getUnifiedTelemetryV1TelemetryUnifiedGet(view, category, format, live, authorization)

Get Unified Telemetry

Unified enterprise telemetry endpoint.  This single endpoint replaces 78+ individual telemetry routes by intelligently aggregating metrics from all 22 required services using parallel collection.  Features: - Parallel collection from all services (10x faster than sequential) - Smart caching with 30-second TTL - Multiple views for different stakeholders - System health and reliability scoring - Export formats for monitoring tools  Examples: - /telemetry/unified?view&#x3D;summary - Executive dashboard - /telemetry/unified?view&#x3D;health - Quick health check - /telemetry/unified?view&#x3D;operational&amp;live&#x3D;true - Live ops data - /telemetry/unified?view&#x3D;reliability - System reliability metrics - /telemetry/unified?category&#x3D;buses - Just bus metrics - /telemetry/unified?format&#x3D;prometheus - Prometheus export

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val view : kotlin.String = view_example // kotlin.String | View type: summary|health|operational|detailed|performance|reliability
val category : kotlin.String = category_example // kotlin.String | Filter by category: buses|graph|infrastructure|governance|runtime|adapters|components|all
val format : kotlin.String = format_example // kotlin.String | Output format: json|prometheus|graphite
val live : kotlin.Boolean = true // kotlin.Boolean | Force live collection (bypass cache)
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.Any = apiInstance.getUnifiedTelemetryV1TelemetryUnifiedGet(view, category, format, live, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#getUnifiedTelemetryV1TelemetryUnifiedGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#getUnifiedTelemetryV1TelemetryUnifiedGet")
    e.printStackTrace()
}
```

### Parameters
| **view** | **kotlin.String**| View type: summary|health|operational|detailed|performance|reliability | [optional] [default to &quot;summary&quot;] |
| **category** | **kotlin.String**| Filter by category: buses|graph|infrastructure|governance|runtime|adapters|components|all | [optional] |
| **format** | **kotlin.String**| Output format: json|prometheus|graphite | [optional] [default to &quot;json&quot;] |
| **live** | **kotlin.Boolean**| Force live collection (bypass cache) | [optional] [default to false] |
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

<a id="queryTelemetryV1TelemetryQueryPost"></a>
# **queryTelemetryV1TelemetryQueryPost**
> SuccessResponseQueryResponse queryTelemetryV1TelemetryQueryPost(telemetryQuery, authorization)

Query Telemetry

Custom telemetry queries.  Execute custom queries against telemetry data including metrics, traces, logs, incidents, and insights. Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TelemetryApi()
val telemetryQuery : TelemetryQuery =  // TelemetryQuery |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseQueryResponse = apiInstance.queryTelemetryV1TelemetryQueryPost(telemetryQuery, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TelemetryApi#queryTelemetryV1TelemetryQueryPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TelemetryApi#queryTelemetryV1TelemetryQueryPost")
    e.printStackTrace()
}
```

### Parameters
| **telemetryQuery** | [**TelemetryQuery**](TelemetryQuery.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseQueryResponse**](SuccessResponseQueryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
