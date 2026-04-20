# WiseAuthorityApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**getDeferralsV1WaDeferralsGet**](WiseAuthorityApi.md#getDeferralsV1WaDeferralsGet) | **GET** /v1/wa/deferrals | Get Deferrals |
| [**getPermissionsV1WaPermissionsGet**](WiseAuthorityApi.md#getPermissionsV1WaPermissionsGet) | **GET** /v1/wa/permissions | Get Permissions |
| [**getWaStatusV1WaStatusGet**](WiseAuthorityApi.md#getWaStatusV1WaStatusGet) | **GET** /v1/wa/status | Get Wa Status |
| [**requestGuidanceV1WaGuidancePost**](WiseAuthorityApi.md#requestGuidanceV1WaGuidancePost) | **POST** /v1/wa/guidance | Request Guidance |
| [**resolveDeferralV1WaDeferralsDeferralIdResolvePost**](WiseAuthorityApi.md#resolveDeferralV1WaDeferralsDeferralIdResolvePost) | **POST** /v1/wa/deferrals/{deferral_id}/resolve | Resolve Deferral |


<a id="getDeferralsV1WaDeferralsGet"></a>
# **getDeferralsV1WaDeferralsGet**
> SuccessResponseDeferralListResponse getDeferralsV1WaDeferralsGet(waId, authorization)

Get Deferrals

Get list of pending deferrals.  Returns all pending deferrals that need WA review. Can optionally filter by WA ID to see deferrals assigned to a specific authority.  Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = WiseAuthorityApi()
val waId : kotlin.String = waId_example // kotlin.String | Filter by WA ID
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseDeferralListResponse = apiInstance.getDeferralsV1WaDeferralsGet(waId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling WiseAuthorityApi#getDeferralsV1WaDeferralsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling WiseAuthorityApi#getDeferralsV1WaDeferralsGet")
    e.printStackTrace()
}
```

### Parameters
| **waId** | **kotlin.String**| Filter by WA ID | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseDeferralListResponse**](SuccessResponseDeferralListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getPermissionsV1WaPermissionsGet"></a>
# **getPermissionsV1WaPermissionsGet**
> SuccessResponsePermissionsListResponse getPermissionsV1WaPermissionsGet(waId, authorization)

Get Permissions

Get WA permission status.  Returns permission status for a specific WA. If no WA ID is provided, returns permissions for the authenticated user. This simplified endpoint focuses on viewing permissions only.  Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = WiseAuthorityApi()
val waId : kotlin.String = waId_example // kotlin.String | WA ID to get permissions for (defaults to current user)
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponsePermissionsListResponse = apiInstance.getPermissionsV1WaPermissionsGet(waId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling WiseAuthorityApi#getPermissionsV1WaPermissionsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling WiseAuthorityApi#getPermissionsV1WaPermissionsGet")
    e.printStackTrace()
}
```

### Parameters
| **waId** | **kotlin.String**| WA ID to get permissions for (defaults to current user) | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponsePermissionsListResponse**](SuccessResponsePermissionsListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getWaStatusV1WaStatusGet"></a>
# **getWaStatusV1WaStatusGet**
> SuccessResponseWAStatusResponse getWaStatusV1WaStatusGet(authorization)

Get Wa Status

Get current WA service status.  Returns information about the WA service including: - Number of active WAs - Number of pending deferrals - Service health status  Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = WiseAuthorityApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseWAStatusResponse = apiInstance.getWaStatusV1WaStatusGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling WiseAuthorityApi#getWaStatusV1WaStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling WiseAuthorityApi#getWaStatusV1WaStatusGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseWAStatusResponse**](SuccessResponseWAStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="requestGuidanceV1WaGuidancePost"></a>
# **requestGuidanceV1WaGuidancePost**
> SuccessResponseWAGuidanceResponse requestGuidanceV1WaGuidancePost(waGuidanceRequest, authorization)

Request Guidance

Request guidance from WA on a specific topic.  This endpoint allows requesting wisdom guidance without creating a formal deferral. Useful for proactive wisdom integration.  Requires OBSERVER role or higher.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = WiseAuthorityApi()
val waGuidanceRequest : WAGuidanceRequest =  // WAGuidanceRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseWAGuidanceResponse = apiInstance.requestGuidanceV1WaGuidancePost(waGuidanceRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling WiseAuthorityApi#requestGuidanceV1WaGuidancePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling WiseAuthorityApi#requestGuidanceV1WaGuidancePost")
    e.printStackTrace()
}
```

### Parameters
| **waGuidanceRequest** | [**WAGuidanceRequest**](WAGuidanceRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseWAGuidanceResponse**](SuccessResponseWAGuidanceResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="resolveDeferralV1WaDeferralsDeferralIdResolvePost"></a>
# **resolveDeferralV1WaDeferralsDeferralIdResolvePost**
> SuccessResponseResolveDeferralResponse resolveDeferralV1WaDeferralsDeferralIdResolvePost(deferralId, resolveDeferralRequest, authorization)

Resolve Deferral

Resolve a pending deferral with guidance.  Allows a WA with AUTHORITY role to approve, reject, or modify a deferred decision. The resolution includes wisdom guidance integrated into the decision.  Requires AUTHORITY role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = WiseAuthorityApi()
val deferralId : kotlin.String = deferralId_example // kotlin.String |
val resolveDeferralRequest : ResolveDeferralRequest =  // ResolveDeferralRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseResolveDeferralResponse = apiInstance.resolveDeferralV1WaDeferralsDeferralIdResolvePost(deferralId, resolveDeferralRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling WiseAuthorityApi#resolveDeferralV1WaDeferralsDeferralIdResolvePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling WiseAuthorityApi#resolveDeferralV1WaDeferralsDeferralIdResolvePost")
    e.printStackTrace()
}
```

### Parameters
| **deferralId** | **kotlin.String**|  | |
| **resolveDeferralRequest** | [**ResolveDeferralRequest**](ResolveDeferralRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseResolveDeferralResponse**](SuccessResponseResolveDeferralResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
