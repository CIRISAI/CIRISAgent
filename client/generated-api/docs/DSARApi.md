# DSARApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**checkDsarStatusV1DsarTicketIdGet**](DSARApi.md#checkDsarStatusV1DsarTicketIdGet) | **GET** /v1/dsar/{ticket_id} | Check Dsar Status |
| [**getDeletionStatusV1DsarTicketIdDeletionStatusGet**](DSARApi.md#getDeletionStatusV1DsarTicketIdDeletionStatusGet) | **GET** /v1/dsar/{ticket_id}/deletion-status | Get Deletion Status |
| [**listDsarRequestsV1DsarGet**](DSARApi.md#listDsarRequestsV1DsarGet) | **GET** /v1/dsar/ | List Dsar Requests |
| [**submitDsarV1DsarPost**](DSARApi.md#submitDsarV1DsarPost) | **POST** /v1/dsar/ | Submit Dsar |
| [**updateDsarStatusV1DsarTicketIdStatusPut**](DSARApi.md#updateDsarStatusV1DsarTicketIdStatusPut) | **PUT** /v1/dsar/{ticket_id}/status | Update Dsar Status |


<a id="checkDsarStatusV1DsarTicketIdGet"></a>
# **checkDsarStatusV1DsarTicketIdGet**
> StandardResponse checkDsarStatusV1DsarTicketIdGet(ticketId)

Check Dsar Status

Check the status of a DSAR request.  Anyone with the ticket ID can check status (like a tracking number).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.checkDsarStatusV1DsarTicketIdGet(ticketId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARApi#checkDsarStatusV1DsarTicketIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARApi#checkDsarStatusV1DsarTicketIdGet")
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

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getDeletionStatusV1DsarTicketIdDeletionStatusGet"></a>
# **getDeletionStatusV1DsarTicketIdDeletionStatusGet**
> StandardResponse getDeletionStatusV1DsarTicketIdDeletionStatusGet(ticketId)

Get Deletion Status

Get deletion progress for a DSAR deletion request.  This endpoint tracks the 90-day decay protocol progress for deletion requests. Anyone with the ticket ID can check status (like a tracking number).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.getDeletionStatusV1DsarTicketIdDeletionStatusGet(ticketId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARApi#getDeletionStatusV1DsarTicketIdDeletionStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARApi#getDeletionStatusV1DsarTicketIdDeletionStatusGet")
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

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listDsarRequestsV1DsarGet"></a>
# **listDsarRequestsV1DsarGet**
> StandardResponse listDsarRequestsV1DsarGet()

List Dsar Requests

List all DSAR requests (admin only).  This endpoint is for administrators to review pending requests.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARApi()
try {
    val result : StandardResponse = apiInstance.listDsarRequestsV1DsarGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARApi#listDsarRequestsV1DsarGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARApi#listDsarRequestsV1DsarGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="submitDsarV1DsarPost"></a>
# **submitDsarV1DsarPost**
> StandardResponse submitDsarV1DsarPost(dsARRequest)

Submit Dsar

Submit a Data Subject Access Request (DSAR).  This endpoint handles GDPR Article 15-22 rights: - Right of access (Article 15) - INSTANT automated response with full data - Right to rectification (Article 16) - Right to erasure / \&quot;right to be forgotten\&quot; (Article 17) - Triggers decay protocol - Right to data portability (Article 20) - INSTANT automated export  DELETE requests trigger Consensual Evolution Protocol: - Immediate identity severance - 90-day pattern decay - Safety patterns may be retained (anonymized)  ACCESS and EXPORT requests use automated DSAR service for instant responses.  Returns a ticket ID for tracking the request.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARApi()
val dsARRequest : DSARRequest =  // DSARRequest |
try {
    val result : StandardResponse = apiInstance.submitDsarV1DsarPost(dsARRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARApi#submitDsarV1DsarPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARApi#submitDsarV1DsarPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **dsARRequest** | [**DSARRequest**](DSARRequest.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="updateDsarStatusV1DsarTicketIdStatusPut"></a>
# **updateDsarStatusV1DsarTicketIdStatusPut**
> StandardResponse updateDsarStatusV1DsarTicketIdStatusPut(ticketId, newStatus, notes)

Update Dsar Status

Update the status of a DSAR request (admin only).  Status workflow: - pending_review → in_progress → completed/rejected

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = DSARApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
val newStatus : kotlin.String = newStatus_example // kotlin.String |
val notes : kotlin.String = notes_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.updateDsarStatusV1DsarTicketIdStatusPut(ticketId, newStatus, notes)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling DSARApi#updateDsarStatusV1DsarTicketIdStatusPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling DSARApi#updateDsarStatusV1DsarTicketIdStatusPut")
    e.printStackTrace()
}
```

### Parameters
| **ticketId** | **kotlin.String**|  | |
| **newStatus** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **notes** | **kotlin.String**|  | [optional] |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json
