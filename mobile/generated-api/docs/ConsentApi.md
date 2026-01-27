# ConsentApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**checkPartnershipStatusV1ConsentPartnershipStatusGet**](ConsentApi.md#checkPartnershipStatusV1ConsentPartnershipStatusGet) | **GET** /v1/consent/partnership/status | Check Partnership Status |
| [**cleanupExpiredV1ConsentCleanupPost**](ConsentApi.md#cleanupExpiredV1ConsentCleanupPost) | **POST** /v1/consent/cleanup | Cleanup Expired |
| [**getAuditTrailV1ConsentAuditGet**](ConsentApi.md#getAuditTrailV1ConsentAuditGet) | **GET** /v1/consent/audit | Get Audit Trail |
| [**getConsentCategoriesV1ConsentCategoriesGet**](ConsentApi.md#getConsentCategoriesV1ConsentCategoriesGet) | **GET** /v1/consent/categories | Get Consent Categories |
| [**getConsentStatusV1ConsentStatusGet**](ConsentApi.md#getConsentStatusV1ConsentStatusGet) | **GET** /v1/consent/status | Get Consent Status |
| [**getConsentStreamsV1ConsentStreamsGet**](ConsentApi.md#getConsentStreamsV1ConsentStreamsGet) | **GET** /v1/consent/streams | Get Consent Streams |
| [**getDsarStatusV1ConsentDsarStatusRequestIdGet**](ConsentApi.md#getDsarStatusV1ConsentDsarStatusRequestIdGet) | **GET** /v1/consent/dsar/status/{request_id} | Get Dsar Status |
| [**getImpactReportV1ConsentImpactGet**](ConsentApi.md#getImpactReportV1ConsentImpactGet) | **GET** /v1/consent/impact | Get Impact Report |
| [**grantConsentV1ConsentGrantPost**](ConsentApi.md#grantConsentV1ConsentGrantPost) | **POST** /v1/consent/grant | Grant Consent |
| [**initiateDsarV1ConsentDsarInitiatePost**](ConsentApi.md#initiateDsarV1ConsentDsarInitiatePost) | **POST** /v1/consent/dsar/initiate | Initiate Dsar |
| [**queryConsentsV1ConsentQueryGet**](ConsentApi.md#queryConsentsV1ConsentQueryGet) | **GET** /v1/consent/query | Query Consents |
| [**revokeConsentV1ConsentRevokePost**](ConsentApi.md#revokeConsentV1ConsentRevokePost) | **POST** /v1/consent/revoke | Revoke Consent |


<a id="checkPartnershipStatusV1ConsentPartnershipStatusGet"></a>
# **checkPartnershipStatusV1ConsentPartnershipStatusGet**
> PartnershipStatusResponse checkPartnershipStatusV1ConsentPartnershipStatusGet(authorization)

Check Partnership Status

Check status of pending partnership request.  Returns current status and any pending partnership request outcome.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : PartnershipStatusResponse = apiInstance.checkPartnershipStatusV1ConsentPartnershipStatusGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#checkPartnershipStatusV1ConsentPartnershipStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#checkPartnershipStatusV1ConsentPartnershipStatusGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**PartnershipStatusResponse**](PartnershipStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="cleanupExpiredV1ConsentCleanupPost"></a>
# **cleanupExpiredV1ConsentCleanupPost**
> ConsentCleanupResponse cleanupExpiredV1ConsentCleanupPost(authorization)

Cleanup Expired

Clean up expired TEMPORARY consents (admin only).  HARD DELETE after 14 days - NO GRACE PERIOD.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ConsentCleanupResponse = apiInstance.cleanupExpiredV1ConsentCleanupPost(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#cleanupExpiredV1ConsentCleanupPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#cleanupExpiredV1ConsentCleanupPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ConsentCleanupResponse**](ConsentCleanupResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getAuditTrailV1ConsentAuditGet"></a>
# **getAuditTrailV1ConsentAuditGet**
> kotlin.collections.List&lt;ConsentAuditEntry&gt; getAuditTrailV1ConsentAuditGet(limit, authorization)

Get Audit Trail

Get consent change history - IMMUTABLE AUDIT TRAIL.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val limit : kotlin.Int = 56 // kotlin.Int |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.collections.List<ConsentAuditEntry> = apiInstance.getAuditTrailV1ConsentAuditGet(limit, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#getAuditTrailV1ConsentAuditGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#getAuditTrailV1ConsentAuditGet")
    e.printStackTrace()
}
```

### Parameters
| **limit** | **kotlin.Int**|  | [optional] [default to 100] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**kotlin.collections.List&lt;ConsentAuditEntry&gt;**](ConsentAuditEntry.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getConsentCategoriesV1ConsentCategoriesGet"></a>
# **getConsentCategoriesV1ConsentCategoriesGet**
> ConsentCategoriesResponse getConsentCategoriesV1ConsentCategoriesGet()

Get Consent Categories

Get available consent categories for PARTNERED stream.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
try {
    val result : ConsentCategoriesResponse = apiInstance.getConsentCategoriesV1ConsentCategoriesGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#getConsentCategoriesV1ConsentCategoriesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#getConsentCategoriesV1ConsentCategoriesGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**ConsentCategoriesResponse**](ConsentCategoriesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getConsentStatusV1ConsentStatusGet"></a>
# **getConsentStatusV1ConsentStatusGet**
> ConsentStatusResponse getConsentStatusV1ConsentStatusGet(authorization)

Get Consent Status

Get current consent status for authenticated user.  Returns None if no consent exists (user has not interacted yet).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ConsentStatusResponse = apiInstance.getConsentStatusV1ConsentStatusGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#getConsentStatusV1ConsentStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#getConsentStatusV1ConsentStatusGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ConsentStatusResponse**](ConsentStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getConsentStreamsV1ConsentStreamsGet"></a>
# **getConsentStreamsV1ConsentStreamsGet**
> ConsentStreamsResponse getConsentStreamsV1ConsentStreamsGet()

Get Consent Streams

Get available consent streams and their descriptions.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
try {
    val result : ConsentStreamsResponse = apiInstance.getConsentStreamsV1ConsentStreamsGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#getConsentStreamsV1ConsentStreamsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#getConsentStreamsV1ConsentStreamsGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**ConsentStreamsResponse**](ConsentStreamsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getDsarStatusV1ConsentDsarStatusRequestIdGet"></a>
# **getDsarStatusV1ConsentDsarStatusRequestIdGet**
> DSARStatusResponse getDsarStatusV1ConsentDsarStatusRequestIdGet(requestId, authorization)

Get Dsar Status

Get status of a DSAR request.  Since DSAR requests are processed immediately, this always returns \&quot;completed\&quot;. In a production system with async processing, this would track actual status.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val requestId : kotlin.String = requestId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : DSARStatusResponse = apiInstance.getDsarStatusV1ConsentDsarStatusRequestIdGet(requestId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#getDsarStatusV1ConsentDsarStatusRequestIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#getDsarStatusV1ConsentDsarStatusRequestIdGet")
    e.printStackTrace()
}
```

### Parameters
| **requestId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**DSARStatusResponse**](DSARStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getImpactReportV1ConsentImpactGet"></a>
# **getImpactReportV1ConsentImpactGet**
> ConsentImpactReport getImpactReportV1ConsentImpactGet(authorization)

Get Impact Report

Get impact report showing contribution to collective learning.  Shows: - Patterns contributed - Users helped - Impact score - Example contributions (anonymized)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ConsentImpactReport = apiInstance.getImpactReportV1ConsentImpactGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#getImpactReportV1ConsentImpactGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#getImpactReportV1ConsentImpactGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ConsentImpactReport**](ConsentImpactReport.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="grantConsentV1ConsentGrantPost"></a>
# **grantConsentV1ConsentGrantPost**
> ConsentStatus grantConsentV1ConsentGrantPost(consentRequest, authorization)

Grant Consent

Grant or update consent.  Streams: - TEMPORARY: 14-day auto-forget (default) - PARTNERED: Explicit consent for mutual growth - ANONYMOUS: Statistics only, no identity

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val consentRequest : ConsentRequest =  // ConsentRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ConsentStatus = apiInstance.grantConsentV1ConsentGrantPost(consentRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#grantConsentV1ConsentGrantPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#grantConsentV1ConsentGrantPost")
    e.printStackTrace()
}
```

### Parameters
| **consentRequest** | [**ConsentRequest**](ConsentRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ConsentStatus**](ConsentStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="initiateDsarV1ConsentDsarInitiatePost"></a>
# **initiateDsarV1ConsentDsarInitiatePost**
> DSARInitiateResponse initiateDsarV1ConsentDsarInitiatePost(requestType, authorization)

Initiate Dsar

Initiate automated DSAR (Data Subject Access Request).  Args:     request_type: Type of DSAR - \&quot;full\&quot;, \&quot;consent_only\&quot;, \&quot;impact_only\&quot;, or \&quot;audit_only\&quot;  Returns:     Export data matching the request type

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val requestType : kotlin.String = requestType_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : DSARInitiateResponse = apiInstance.initiateDsarV1ConsentDsarInitiatePost(requestType, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#initiateDsarV1ConsentDsarInitiatePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#initiateDsarV1ConsentDsarInitiatePost")
    e.printStackTrace()
}
```

### Parameters
| **requestType** | **kotlin.String**|  | [optional] [default to &quot;full&quot;] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**DSARInitiateResponse**](DSARInitiateResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="queryConsentsV1ConsentQueryGet"></a>
# **queryConsentsV1ConsentQueryGet**
> ConsentQueryResponse queryConsentsV1ConsentQueryGet(status, userId, authorization)

Query Consents

Query consent records with optional filters.  Args:     status: Filter by status (ACTIVE, REVOKED, EXPIRED)     user_id: Filter by user ID (admin only)  Returns:     Dictionary with consents list and total count

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val status : kotlin.String = status_example // kotlin.String |
val userId : kotlin.String = userId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ConsentQueryResponse = apiInstance.queryConsentsV1ConsentQueryGet(status, userId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#queryConsentsV1ConsentQueryGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#queryConsentsV1ConsentQueryGet")
    e.printStackTrace()
}
```

### Parameters
| **status** | **kotlin.String**|  | [optional] |
| **userId** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ConsentQueryResponse**](ConsentQueryResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="revokeConsentV1ConsentRevokePost"></a>
# **revokeConsentV1ConsentRevokePost**
> ConsentDecayStatus revokeConsentV1ConsentRevokePost(reason, authorization)

Revoke Consent

Revoke consent and start decay protocol.  - Immediate identity severance - 90-day pattern decay - Safety patterns may be retained (anonymized)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConsentApi()
val reason : kotlin.String = reason_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ConsentDecayStatus = apiInstance.revokeConsentV1ConsentRevokePost(reason, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConsentApi#revokeConsentV1ConsentRevokePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConsentApi#revokeConsentV1ConsentRevokePost")
    e.printStackTrace()
}
```

### Parameters
| **reason** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ConsentDecayStatus**](ConsentDecayStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json
