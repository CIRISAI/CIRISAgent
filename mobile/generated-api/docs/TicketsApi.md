# TicketsApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**cancelTicketV1TicketsTicketIdDelete**](TicketsApi.md#cancelTicketV1TicketsTicketIdDelete) | **DELETE** /v1/tickets/{ticket_id} | Cancel Ticket |
| [**createNewTicketV1TicketsPost**](TicketsApi.md#createNewTicketV1TicketsPost) | **POST** /v1/tickets/ | Create New Ticket |
| [**getSopMetadataV1TicketsSopsSopGet**](TicketsApi.md#getSopMetadataV1TicketsSopsSopGet) | **GET** /v1/tickets/sops/{sop} | Get Sop Metadata |
| [**getTicketByIdV1TicketsTicketIdGet**](TicketsApi.md#getTicketByIdV1TicketsTicketIdGet) | **GET** /v1/tickets/{ticket_id} | Get Ticket By Id |
| [**listAllTicketsV1TicketsGet**](TicketsApi.md#listAllTicketsV1TicketsGet) | **GET** /v1/tickets/ | List All Tickets |
| [**listSupportedSopsV1TicketsSopsGet**](TicketsApi.md#listSupportedSopsV1TicketsSopsGet) | **GET** /v1/tickets/sops | List Supported Sops |
| [**updateExistingTicketV1TicketsTicketIdPatch**](TicketsApi.md#updateExistingTicketV1TicketsTicketIdPatch) | **PATCH** /v1/tickets/{ticket_id} | Update Existing Ticket |


<a id="cancelTicketV1TicketsTicketIdDelete"></a>
# **cancelTicketV1TicketsTicketIdDelete**
> StandardResponse cancelTicketV1TicketsTicketIdDelete(ticketId)

Cancel Ticket

Cancel/delete a ticket.  Returns:     Success confirmation  Raises:     404: Ticket not found     500: Deletion failed

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TicketsApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.cancelTicketV1TicketsTicketIdDelete(ticketId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TicketsApi#cancelTicketV1TicketsTicketIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TicketsApi#cancelTicketV1TicketsTicketIdDelete")
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

<a id="createNewTicketV1TicketsPost"></a>
# **createNewTicketV1TicketsPost**
> TicketResponse createNewTicketV1TicketsPost(createTicketRequest)

Create New Ticket

Create a new ticket.  Validates that the SOP is supported by this agent (organic enforcement). Automatically calculates deadline based on SOP configuration. Initializes metadata with stage structure.  Returns:     Created ticket data  Raises:     501: SOP not supported by this agent     500: Ticket creation failed

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TicketsApi()
val createTicketRequest : CreateTicketRequest =  // CreateTicketRequest |
try {
    val result : TicketResponse = apiInstance.createNewTicketV1TicketsPost(createTicketRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TicketsApi#createNewTicketV1TicketsPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TicketsApi#createNewTicketV1TicketsPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **createTicketRequest** | [**CreateTicketRequest**](CreateTicketRequest.md)|  | |

### Return type

[**TicketResponse**](TicketResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="getSopMetadataV1TicketsSopsSopGet"></a>
# **getSopMetadataV1TicketsSopsSopGet**
> SOPMetadataResponse getSopMetadataV1TicketsSopsSopGet(sop)

Get Sop Metadata

Get metadata about a specific Standard Operating Procedure.  Returns:     SOP configuration including stages, required fields, deadline, etc.  Raises:     404: SOP not found/supported

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TicketsApi()
val sop : kotlin.String = sop_example // kotlin.String |
try {
    val result : SOPMetadataResponse = apiInstance.getSopMetadataV1TicketsSopsSopGet(sop)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TicketsApi#getSopMetadataV1TicketsSopsSopGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TicketsApi#getSopMetadataV1TicketsSopsSopGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **sop** | **kotlin.String**|  | |

### Return type

[**SOPMetadataResponse**](SOPMetadataResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getTicketByIdV1TicketsTicketIdGet"></a>
# **getTicketByIdV1TicketsTicketIdGet**
> TicketResponse getTicketByIdV1TicketsTicketIdGet(ticketId)

Get Ticket By Id

Get a specific ticket by ID.  Returns:     Ticket data  Raises:     404: Ticket not found

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TicketsApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
try {
    val result : TicketResponse = apiInstance.getTicketByIdV1TicketsTicketIdGet(ticketId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TicketsApi#getTicketByIdV1TicketsTicketIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TicketsApi#getTicketByIdV1TicketsTicketIdGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **ticketId** | **kotlin.String**|  | |

### Return type

[**TicketResponse**](TicketResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listAllTicketsV1TicketsGet"></a>
# **listAllTicketsV1TicketsGet**
> kotlin.collections.List&lt;TicketResponse&gt; listAllTicketsV1TicketsGet(sop, ticketType, statusFilter, email, limit)

List All Tickets

List tickets with optional filters.  Args:     sop: Filter by SOP (e.g., \&quot;DSAR_ACCESS\&quot;)     ticket_type: Filter by type (e.g., \&quot;dsar\&quot;)     status_filter: Filter by status (pending|in_progress|completed|cancelled|failed)     email: Filter by email     limit: Maximum number of results  Returns:     List of matching tickets (sorted by submission date, newest first)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TicketsApi()
val sop : kotlin.String = sop_example // kotlin.String |
val ticketType : kotlin.String = ticketType_example // kotlin.String |
val statusFilter : kotlin.String = statusFilter_example // kotlin.String |
val email : kotlin.String = email_example // kotlin.String |
val limit : kotlin.Int = 56 // kotlin.Int |
try {
    val result : kotlin.collections.List<TicketResponse> = apiInstance.listAllTicketsV1TicketsGet(sop, ticketType, statusFilter, email, limit)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TicketsApi#listAllTicketsV1TicketsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TicketsApi#listAllTicketsV1TicketsGet")
    e.printStackTrace()
}
```

### Parameters
| **sop** | **kotlin.String**|  | [optional] |
| **ticketType** | **kotlin.String**|  | [optional] |
| **statusFilter** | **kotlin.String**|  | [optional] |
| **email** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **limit** | **kotlin.Int**|  | [optional] |

### Return type

[**kotlin.collections.List&lt;TicketResponse&gt;**](TicketResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listSupportedSopsV1TicketsSopsGet"></a>
# **listSupportedSopsV1TicketsSopsGet**
> kotlin.collections.List&lt;kotlin.String?&gt; listSupportedSopsV1TicketsSopsGet()

List Supported Sops

List all supported Standard Operating Procedures for this agent.  DSAR SOPs are always present (GDPR compliance). Additional SOPs defined in graph config (seeded from template on first run).  Returns:     List of SOP identifiers (e.g., [\&quot;DSAR_ACCESS\&quot;, \&quot;DSAR_DELETE\&quot;, ...])

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TicketsApi()
try {
    val result : kotlin.collections.List<kotlin.String?> = apiInstance.listSupportedSopsV1TicketsSopsGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TicketsApi#listSupportedSopsV1TicketsSopsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TicketsApi#listSupportedSopsV1TicketsSopsGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

**kotlin.collections.List&lt;kotlin.String?&gt;**

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="updateExistingTicketV1TicketsTicketIdPatch"></a>
# **updateExistingTicketV1TicketsTicketIdPatch**
> TicketResponse updateExistingTicketV1TicketsTicketIdPatch(ticketId, updateTicketRequest)

Update Existing Ticket

Update ticket status, metadata, or notes.  Returns:     Updated ticket data  Raises:     404: Ticket not found     500: Update failed

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = TicketsApi()
val ticketId : kotlin.String = ticketId_example // kotlin.String |
val updateTicketRequest : UpdateTicketRequest =  // UpdateTicketRequest |
try {
    val result : TicketResponse = apiInstance.updateExistingTicketV1TicketsTicketIdPatch(ticketId, updateTicketRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling TicketsApi#updateExistingTicketV1TicketsTicketIdPatch")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling TicketsApi#updateExistingTicketV1TicketsTicketIdPatch")
    e.printStackTrace()
}
```

### Parameters
| **ticketId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **updateTicketRequest** | [**UpdateTicketRequest**](UpdateTicketRequest.md)|  | |

### Return type

[**TicketResponse**](TicketResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
