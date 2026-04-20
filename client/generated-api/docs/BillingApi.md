# BillingApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**getCreditsV1ApiBillingCreditsGet**](BillingApi.md#getCreditsV1ApiBillingCreditsGet) | **GET** /v1/api/billing/credits | Get Credits |
| [**getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet**](BillingApi.md#getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet) | **GET** /v1/api/billing/purchase/status/{payment_id} | Get Purchase Status |
| [**getTransactionsV1ApiBillingTransactionsGet**](BillingApi.md#getTransactionsV1ApiBillingTransactionsGet) | **GET** /v1/api/billing/transactions | Get Transactions |
| [**initiatePurchaseV1ApiBillingPurchaseInitiatePost**](BillingApi.md#initiatePurchaseV1ApiBillingPurchaseInitiatePost) | **POST** /v1/api/billing/purchase/initiate | Initiate Purchase |
| [**verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost**](BillingApi.md#verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost) | **POST** /v1/api/billing/google-play/verify | Verify Google Play Purchase |


<a id="getCreditsV1ApiBillingCreditsGet"></a>
# **getCreditsV1ApiBillingCreditsGet**
> CreditStatusResponse getCreditsV1ApiBillingCreditsGet(authorization)

Get Credits

Get user&#39;s credit balance and status.  Works with both: - SimpleCreditProvider (1 free credit per OAuth user, no billing backend needed) - CIRISBillingProvider (full billing backend with paid credits)  The frontend calls this to display credit status.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = BillingApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : CreditStatusResponse = apiInstance.getCreditsV1ApiBillingCreditsGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling BillingApi#getCreditsV1ApiBillingCreditsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling BillingApi#getCreditsV1ApiBillingCreditsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**CreditStatusResponse**](CreditStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet"></a>
# **getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet**
> PurchaseStatusResponse getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet(paymentId, authorization)

Get Purchase Status

Check payment status (optional - for polling after payment).  Frontend can poll this after initiating payment to confirm credits were added. Only works when CIRIS_BILLING_ENABLED&#x3D;true (CIRISBillingProvider).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = BillingApi()
val paymentId : kotlin.String = paymentId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : PurchaseStatusResponse = apiInstance.getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet(paymentId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling BillingApi#getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling BillingApi#getPurchaseStatusV1ApiBillingPurchaseStatusPaymentIdGet")
    e.printStackTrace()
}
```

### Parameters
| **paymentId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**PurchaseStatusResponse**](PurchaseStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getTransactionsV1ApiBillingTransactionsGet"></a>
# **getTransactionsV1ApiBillingTransactionsGet**
> TransactionListResponse getTransactionsV1ApiBillingTransactionsGet(limit, offset, authorization)

Get Transactions

Get transaction history for the current user.  Returns a paginated list of all transactions (charges and credits) in reverse chronological order.  Only works when CIRIS_BILLING_ENABLED&#x3D;true (CIRISBillingProvider). Returns empty list when SimpleCreditProvider is active (billing disabled).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = BillingApi()
val limit : kotlin.Int = 56 // kotlin.Int |
val offset : kotlin.Int = 56 // kotlin.Int |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : TransactionListResponse = apiInstance.getTransactionsV1ApiBillingTransactionsGet(limit, offset, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling BillingApi#getTransactionsV1ApiBillingTransactionsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling BillingApi#getTransactionsV1ApiBillingTransactionsGet")
    e.printStackTrace()
}
```

### Parameters
| **limit** | **kotlin.Int**|  | [optional] [default to 50] |
| **offset** | **kotlin.Int**|  | [optional] [default to 0] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**TransactionListResponse**](TransactionListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="initiatePurchaseV1ApiBillingPurchaseInitiatePost"></a>
# **initiatePurchaseV1ApiBillingPurchaseInitiatePost**
> PurchaseInitiateResponse initiatePurchaseV1ApiBillingPurchaseInitiatePost(purchaseInitiateRequest, authorization)

Initiate Purchase

Initiate credit purchase (creates Stripe payment intent).  Only works when CIRIS_BILLING_ENABLED&#x3D;true (CIRISBillingProvider). Returns error when SimpleCreditProvider is active (billing disabled).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = BillingApi()
val purchaseInitiateRequest : PurchaseInitiateRequest =  // PurchaseInitiateRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : PurchaseInitiateResponse = apiInstance.initiatePurchaseV1ApiBillingPurchaseInitiatePost(purchaseInitiateRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling BillingApi#initiatePurchaseV1ApiBillingPurchaseInitiatePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling BillingApi#initiatePurchaseV1ApiBillingPurchaseInitiatePost")
    e.printStackTrace()
}
```

### Parameters
| **purchaseInitiateRequest** | [**PurchaseInitiateRequest**](PurchaseInitiateRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**PurchaseInitiateResponse**](PurchaseInitiateResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost"></a>
# **verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost**
> GooglePlayVerifyResponse verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost(googlePlayVerifyRequest, authorization)

Verify Google Play Purchase

Verify a Google Play purchase and add credits.  This endpoint proxies the verification request to the billing backend, which validates the purchase token with Google Play and adds credits.  Supports two authentication modes: 1. Server mode: Uses CIRIS_BILLING_API_KEY (agents.ciris.ai) 2. JWT pass-through: Uses Bearer token from request (Android/native)  Only works when CIRISBillingProvider is configured.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = BillingApi()
val googlePlayVerifyRequest : GooglePlayVerifyRequest =  // GooglePlayVerifyRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : GooglePlayVerifyResponse = apiInstance.verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost(googlePlayVerifyRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling BillingApi#verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling BillingApi#verifyGooglePlayPurchaseV1ApiBillingGooglePlayVerifyPost")
    e.printStackTrace()
}
```

### Parameters
| **googlePlayVerifyRequest** | [**GooglePlayVerifyRequest**](GooglePlayVerifyRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**GooglePlayVerifyResponse**](GooglePlayVerifyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
