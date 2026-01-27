# AuditApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**exportAuditDataV1AuditExportPost**](AuditApi.md#exportAuditDataV1AuditExportPost) | **POST** /v1/audit/export | Export Audit Data |
| [**getAuditEntryV1AuditEntriesEntryIdGet**](AuditApi.md#getAuditEntryV1AuditEntriesEntryIdGet) | **GET** /v1/audit/entries/{entry_id} | Get Audit Entry |
| [**queryAuditEntriesV1AuditEntriesGet**](AuditApi.md#queryAuditEntriesV1AuditEntriesGet) | **GET** /v1/audit/entries | Query Audit Entries |
| [**searchAuditTrailsV1AuditSearchPost**](AuditApi.md#searchAuditTrailsV1AuditSearchPost) | **POST** /v1/audit/search | Search Audit Trails |
| [**verifyAuditEntryV1AuditVerifyEntryIdPost**](AuditApi.md#verifyAuditEntryV1AuditVerifyEntryIdPost) | **POST** /v1/audit/verify/{entry_id} | Verify Audit Entry |


<a id="exportAuditDataV1AuditExportPost"></a>
# **exportAuditDataV1AuditExportPost**
> SuccessResponseAuditExportResponse exportAuditDataV1AuditExportPost(startDate, endDate, format, includeVerification, authorization)

Export Audit Data

Export audit data for compliance and analysis.  Exports audit entries in the specified format. For small datasets (&lt; 1000 entries), data is returned inline. For larger datasets, a download URL is provided.  Formats: - **jsonl**: JSON Lines format (one entry per line) - **json**: Standard JSON array - **csv**: CSV format with standard audit fields  Requires ADMIN role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuditApi()
val startDate : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | Export start date
val endDate : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | Export end date
val format : kotlin.String = format_example // kotlin.String | Export format
val includeVerification : kotlin.Boolean = true // kotlin.Boolean | Include verification data in export
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAuditExportResponse = apiInstance.exportAuditDataV1AuditExportPost(startDate, endDate, format, includeVerification, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuditApi#exportAuditDataV1AuditExportPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuditApi#exportAuditDataV1AuditExportPost")
    e.printStackTrace()
}
```

### Parameters
| **startDate** | **kotlin.time.Instant**| Export start date | [optional] |
| **endDate** | **kotlin.time.Instant**| Export end date | [optional] |
| **format** | **kotlin.String**| Export format | [optional] [default to &quot;jsonl&quot;] |
| **includeVerification** | **kotlin.Boolean**| Include verification data in export | [optional] [default to false] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAuditExportResponse**](SuccessResponseAuditExportResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getAuditEntryV1AuditEntriesEntryIdGet"></a>
# **getAuditEntryV1AuditEntriesEntryIdGet**
> SuccessResponseAuditEntryDetailResponse getAuditEntryV1AuditEntriesEntryIdGet(entryId, verify, authorization)

Get Audit Entry

Get specific audit entry by ID with optional verification.  Returns the audit entry and optionally includes: - Verification status of the entry&#39;s signature and hash - Position in the audit chain - Links to previous and next entries  Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuditApi()
val entryId : kotlin.String = entryId_example // kotlin.String | Audit entry ID
val verify : kotlin.Boolean = true // kotlin.Boolean | Include verification information
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAuditEntryDetailResponse = apiInstance.getAuditEntryV1AuditEntriesEntryIdGet(entryId, verify, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuditApi#getAuditEntryV1AuditEntriesEntryIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuditApi#getAuditEntryV1AuditEntriesEntryIdGet")
    e.printStackTrace()
}
```

### Parameters
| **entryId** | **kotlin.String**| Audit entry ID | |
| **verify** | **kotlin.Boolean**| Include verification information | [optional] [default to false] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAuditEntryDetailResponse**](SuccessResponseAuditEntryDetailResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="queryAuditEntriesV1AuditEntriesGet"></a>
# **queryAuditEntriesV1AuditEntriesGet**
> SuccessResponseAuditEntriesResponse queryAuditEntriesV1AuditEntriesGet(startTime, endTime, actor, eventType, entityId, search, severity, outcome, limit, offset, authorization)

Query Audit Entries

Query audit entries with flexible filtering.  Combines time-based queries, entity filtering, and text search into a single endpoint. Returns paginated results sorted by timestamp (newest first).  Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuditApi()
val startTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | Start of time range
val endTime : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | End of time range
val actor : kotlin.String = actor_example // kotlin.String | Filter by actor
val eventType : kotlin.String = eventType_example // kotlin.String | Filter by event type
val entityId : kotlin.String = entityId_example // kotlin.String | Filter by entity ID
val search : kotlin.String = search_example // kotlin.String | Search in audit details
val severity : kotlin.String = severity_example // kotlin.String | Filter by severity (info, warning, error)
val outcome : kotlin.String = outcome_example // kotlin.String | Filter by outcome (success, failure)
val limit : kotlin.Int = 56 // kotlin.Int | Maximum results
val offset : kotlin.Int = 56 // kotlin.Int | Results offset
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAuditEntriesResponse = apiInstance.queryAuditEntriesV1AuditEntriesGet(startTime, endTime, actor, eventType, entityId, search, severity, outcome, limit, offset, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuditApi#queryAuditEntriesV1AuditEntriesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuditApi#queryAuditEntriesV1AuditEntriesGet")
    e.printStackTrace()
}
```

### Parameters
| **startTime** | **kotlin.time.Instant**| Start of time range | [optional] |
| **endTime** | **kotlin.time.Instant**| End of time range | [optional] |
| **actor** | **kotlin.String**| Filter by actor | [optional] |
| **eventType** | **kotlin.String**| Filter by event type | [optional] |
| **entityId** | **kotlin.String**| Filter by entity ID | [optional] |
| **search** | **kotlin.String**| Search in audit details | [optional] |
| **severity** | **kotlin.String**| Filter by severity (info, warning, error) | [optional] |
| **outcome** | **kotlin.String**| Filter by outcome (success, failure) | [optional] |
| **limit** | **kotlin.Int**| Maximum results | [optional] [default to 100] |
| **offset** | **kotlin.Int**| Results offset | [optional] [default to 0] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAuditEntriesResponse**](SuccessResponseAuditEntriesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="searchAuditTrailsV1AuditSearchPost"></a>
# **searchAuditTrailsV1AuditSearchPost**
> SuccessResponseAuditEntriesResponse searchAuditTrailsV1AuditSearchPost(searchText, entityId, severity, outcome, limit, offset, authorization)

Search Audit Trails

Search audit trails with text search and filters.  This is a convenience endpoint that focuses on search functionality. For more complex queries, use the /entries endpoint.  Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuditApi()
val searchText : kotlin.String = searchText_example // kotlin.String | Text to search for
val entityId : kotlin.String = entityId_example // kotlin.String | Filter by entity ID
val severity : kotlin.String = severity_example // kotlin.String | Filter by severity
val outcome : kotlin.String = outcome_example // kotlin.String | Filter by outcome
val limit : kotlin.Int = 56 // kotlin.Int | Maximum results
val offset : kotlin.Int = 56 // kotlin.Int | Results offset
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAuditEntriesResponse = apiInstance.searchAuditTrailsV1AuditSearchPost(searchText, entityId, severity, outcome, limit, offset, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuditApi#searchAuditTrailsV1AuditSearchPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuditApi#searchAuditTrailsV1AuditSearchPost")
    e.printStackTrace()
}
```

### Parameters
| **searchText** | **kotlin.String**| Text to search for | [optional] |
| **entityId** | **kotlin.String**| Filter by entity ID | [optional] |
| **severity** | **kotlin.String**| Filter by severity | [optional] |
| **outcome** | **kotlin.String**| Filter by outcome | [optional] |
| **limit** | **kotlin.Int**| Maximum results | [optional] [default to 100] |
| **offset** | **kotlin.Int**| Results offset | [optional] [default to 0] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAuditEntriesResponse**](SuccessResponseAuditEntriesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="verifyAuditEntryV1AuditVerifyEntryIdPost"></a>
# **verifyAuditEntryV1AuditVerifyEntryIdPost**
> SuccessResponseVerificationReport verifyAuditEntryV1AuditVerifyEntryIdPost(entryId, authorization)

Verify Audit Entry

Verify the integrity of a specific audit entry.  Returns detailed verification information including signature validation and hash chain integrity.  Requires ADMIN role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuditApi()
val entryId : kotlin.String = entryId_example // kotlin.String | Audit entry ID to verify
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseVerificationReport = apiInstance.verifyAuditEntryV1AuditVerifyEntryIdPost(entryId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuditApi#verifyAuditEntryV1AuditVerifyEntryIdPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuditApi#verifyAuditEntryV1AuditVerifyEntryIdPost")
    e.printStackTrace()
}
```

### Parameters
| **entryId** | **kotlin.String**| Audit entry ID to verify | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseVerificationReport**](SuccessResponseVerificationReport.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json
