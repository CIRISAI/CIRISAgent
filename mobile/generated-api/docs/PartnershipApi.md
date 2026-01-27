# PartnershipApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**decidePartnershipV1PartnershipDecidePost**](PartnershipApi.md#decidePartnershipV1PartnershipDecidePost) | **POST** /v1/partnership/decide | Decide Partnership |
| [**getPartnershipHistoryV1PartnershipHistoryUserIdGet**](PartnershipApi.md#getPartnershipHistoryV1PartnershipHistoryUserIdGet) | **GET** /v1/partnership/history/{user_id} | Get Partnership History |
| [**getPartnershipMetricsV1PartnershipMetricsGet**](PartnershipApi.md#getPartnershipMetricsV1PartnershipMetricsGet) | **GET** /v1/partnership/metrics | Get Partnership Metrics |
| [**listPendingPartnershipsV1PartnershipPendingGet**](PartnershipApi.md#listPendingPartnershipsV1PartnershipPendingGet) | **GET** /v1/partnership/pending | List Pending Partnerships |


<a id="decidePartnershipV1PartnershipDecidePost"></a>
# **decidePartnershipV1PartnershipDecidePost**
> StandardResponse decidePartnershipV1PartnershipDecidePost(requestBody)

Decide Partnership

User decides on a partnership request (accept/reject/defer).  This endpoint handles BOTH flows with equal moral agency: 1. User responding to agent-initiated partnership request 2. Agent responding to user-initiated partnership request (via SDK)  Both parties have equal autonomy in the bilateral consent process.  Request body:     {         \&quot;task_id\&quot;: \&quot;partnership_user123_abc123\&quot;,         \&quot;decision\&quot;: \&quot;accept\&quot; | \&quot;reject\&quot; | \&quot;defer\&quot;,         \&quot;reason\&quot;: \&quot;Optional reason for decision\&quot;     }  Returns:     StandardResponse with decision confirmation and updated consent status

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = PartnershipApi()
val requestBody : kotlin.collections.Map<kotlin.String, kotlin.Any> = Object // kotlin.collections.Map<kotlin.String, kotlin.Any> |
try {
    val result : StandardResponse = apiInstance.decidePartnershipV1PartnershipDecidePost(requestBody)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling PartnershipApi#decidePartnershipV1PartnershipDecidePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling PartnershipApi#decidePartnershipV1PartnershipDecidePost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **requestBody** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="getPartnershipHistoryV1PartnershipHistoryUserIdGet"></a>
# **getPartnershipHistoryV1PartnershipHistoryUserIdGet**
> StandardResponse getPartnershipHistoryV1PartnershipHistoryUserIdGet(userId)

Get Partnership History

Get partnership history for a user (admin only).  Returns all historical partnership decisions for a specific user, including approved, rejected, deferred, and expired requests.  Requires: ADMIN or SYSTEM_ADMIN role

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = PartnershipApi()
val userId : kotlin.String = userId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.getPartnershipHistoryV1PartnershipHistoryUserIdGet(userId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling PartnershipApi#getPartnershipHistoryV1PartnershipHistoryUserIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling PartnershipApi#getPartnershipHistoryV1PartnershipHistoryUserIdGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **userId** | **kotlin.String**|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getPartnershipMetricsV1PartnershipMetricsGet"></a>
# **getPartnershipMetricsV1PartnershipMetricsGet**
> StandardResponse getPartnershipMetricsV1PartnershipMetricsGet()

Get Partnership Metrics

Get partnership system metrics (admin only).  Includes: - Total requests, approvals, rejections, deferrals - Approval/rejection/deferral rates - Average pending time - Count of critical aging requests  Requires: ADMIN or SYSTEM_ADMIN role

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = PartnershipApi()
try {
    val result : StandardResponse = apiInstance.getPartnershipMetricsV1PartnershipMetricsGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling PartnershipApi#getPartnershipMetricsV1PartnershipMetricsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling PartnershipApi#getPartnershipMetricsV1PartnershipMetricsGet")
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

<a id="listPendingPartnershipsV1PartnershipPendingGet"></a>
# **listPendingPartnershipsV1PartnershipPendingGet**
> StandardResponse listPendingPartnershipsV1PartnershipPendingGet()

List Pending Partnerships

List all pending partnership requests (admin only).  Returns list of pending requests with aging status and priority. Useful for admin dashboard to show requests requiring review.  Requires: ADMIN or SYSTEM_ADMIN role

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = PartnershipApi()
try {
    val result : StandardResponse = apiInstance.listPendingPartnershipsV1PartnershipPendingGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling PartnershipApi#listPendingPartnershipsV1PartnershipPendingGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling PartnershipApi#listPendingPartnershipsV1PartnershipPendingGet")
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
