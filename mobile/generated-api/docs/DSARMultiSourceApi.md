# DSARMultiSourceApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete**](DSARMultiSourceApi.md#cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete) | **DELETE** /v1/dsar/multi-source/{ticket_id} | Cancel Multi Source Request |
| [**getMultiSourceStatusV1DsarMultiSourceTicketIdGet**](DSARMultiSourceApi.md#getMultiSourceStatusV1DsarMultiSourceTicketIdGet) | **GET** /v1/dsar/multi-source/{ticket_id} | Get Multi Source Status |
| [**getPartialResultsV1DsarMultiSourceTicketIdPartialGet**](DSARMultiSourceApi.md#getPartialResultsV1DsarMultiSourceTicketIdPartialGet) | **GET** /v1/dsar/multi-source/{ticket_id}/partial | Get Partial Results |
| [**submitMultiSourceDsarV1DsarMultiSourcePost**](DSARMultiSourceApi.md#submitMultiSourceDsarV1DsarMultiSourcePost) | **POST** /v1/dsar/multi-source/ | Submit Multi Source Dsar |
| [**submitMultiSourceDsarV1DsarMultiSourcePost_0**](DSARMultiSourceApi.md#submitMultiSourceDsarV1DsarMultiSourcePost_0) | **POST** /v1/dsar/multi-source | Submit Multi Source Dsar |


<a id="cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete"></a>
# **cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete**
> StandardResponse cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete(ticketId)

Cancel Multi Source Request

Cancel in-progress multi-source DSAR request.  Note: Current implementation completes requests instantly, so cancellation may not be possible for most requests.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARMultiSourceApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete(ticketId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARMultiSourceApi#cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARMultiSourceApi#cancelMultiSourceRequestV1DsarMultiSourceTicketIdDelete")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **ticketId** | **kotlin.String**|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getMultiSourceStatusV1DsarMultiSourceTicketIdGet"></a>
# **getMultiSourceStatusV1DsarMultiSourceTicketIdGet**
> StandardResponse getMultiSourceStatusV1DsarMultiSourceTicketIdGet(ticketId)

Get Multi Source Status

Get real-time status of multi-source DSAR request.  Returns current progress across all data sources.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARMultiSourceApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.getMultiSourceStatusV1DsarMultiSourceTicketIdGet(ticketId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARMultiSourceApi#getMultiSourceStatusV1DsarMultiSourceTicketIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARMultiSourceApi#getMultiSourceStatusV1DsarMultiSourceTicketIdGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **ticketId** | **kotlin.String**|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getPartialResultsV1DsarMultiSourceTicketIdPartialGet"></a>
# **getPartialResultsV1DsarMultiSourceTicketIdPartialGet**
> StandardResponse getPartialResultsV1DsarMultiSourceTicketIdPartialGet(ticketId)

Get Partial Results

Get partial results as sources complete.  Returns data from completed sources while others are still processing.  Note: Current implementation completes all sources instantly, but this endpoint supports future async multi-source operations.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARMultiSourceApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.getPartialResultsV1DsarMultiSourceTicketIdPartialGet(ticketId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARMultiSourceApi#getPartialResultsV1DsarMultiSourceTicketIdPartialGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARMultiSourceApi#getPartialResultsV1DsarMultiSourceTicketIdPartialGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **ticketId** | **kotlin.String**|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="submitMultiSourceDsarV1DsarMultiSourcePost"></a>
# **submitMultiSourceDsarV1DsarMultiSourcePost**
> StandardResponse submitMultiSourceDsarV1DsarMultiSourcePost(multiSourceDSARRequest)

Submit Multi Source Dsar

Submit a multi-source Data Subject Access Request (DSAR).  Coordinates GDPR requests across CIRIS + all registered external data sources: - SQL databases - REST APIs - HL7 systems (future)  Requires authentication (admin or authorized user).  Returns aggregated results from all sources.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARMultiSourceApi()
val multiSourceDSARRequest : MultiSourceDSARRequest =  // MultiSourceDSARRequest |
try {
    val result : StandardResponse = apiInstance.submitMultiSourceDsarV1DsarMultiSourcePost(multiSourceDSARRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARMultiSourceApi#submitMultiSourceDsarV1DsarMultiSourcePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARMultiSourceApi#submitMultiSourceDsarV1DsarMultiSourcePost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **multiSourceDSARRequest** | [**MultiSourceDSARRequest**](MultiSourceDSARRequest.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="submitMultiSourceDsarV1DsarMultiSourcePost_0"></a>
# **submitMultiSourceDsarV1DsarMultiSourcePost_0**
> StandardResponse submitMultiSourceDsarV1DsarMultiSourcePost_0(multiSourceDSARRequest)

Submit Multi Source Dsar

Submit a multi-source Data Subject Access Request (DSAR).  Coordinates GDPR requests across CIRIS + all registered external data sources: - SQL databases - REST APIs - HL7 systems (future)  Requires authentication (admin or authorized user).  Returns aggregated results from all sources.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARMultiSourceApi()
val multiSourceDSARRequest : MultiSourceDSARRequest =  // MultiSourceDSARRequest |
try {
    val result : StandardResponse = apiInstance.submitMultiSourceDsarV1DsarMultiSourcePost_0(multiSourceDSARRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARMultiSourceApi#submitMultiSourceDsarV1DsarMultiSourcePost_0")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARMultiSourceApi#submitMultiSourceDsarV1DsarMultiSourcePost_0")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **multiSourceDSARRequest** | [**MultiSourceDSARRequest**](MultiSourceDSARRequest.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
