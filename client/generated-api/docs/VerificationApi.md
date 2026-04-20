# VerificationApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**downloadPublicKeyV1VerificationKeysKeyIdPubGet**](VerificationApi.md#downloadPublicKeyV1VerificationKeysKeyIdPubGet) | **GET** /v1/verification/keys/{key_id}.pub | Download Public Key |
| [**getCurrentPublicKeyInfoV1VerificationKeysCurrentGet**](VerificationApi.md#getCurrentPublicKeyInfoV1VerificationKeysCurrentGet) | **GET** /v1/verification/keys/current | Get Current Public Key Info |
| [**manualSignatureVerificationV1VerificationVerifySignaturePost**](VerificationApi.md#manualSignatureVerificationV1VerificationVerifySignaturePost) | **POST** /v1/verification/verify-signature | Manual Signature Verification |
| [**publicVerificationPageV1VerificationPublicDeletionIdGet**](VerificationApi.md#publicVerificationPageV1VerificationPublicDeletionIdGet) | **GET** /v1/verification/public/{deletion_id} | Public Verification Page |
| [**verifyDeletionProofV1VerificationDeletionPost**](VerificationApi.md#verifyDeletionProofV1VerificationDeletionPost) | **POST** /v1/verification/deletion | Verify Deletion Proof |


<a id="downloadPublicKeyV1VerificationKeysKeyIdPubGet"></a>
# **downloadPublicKeyV1VerificationKeysKeyIdPubGet**
> kotlin.String downloadPublicKeyV1VerificationKeysKeyIdPubGet(keyId)

Download Public Key

Download RSA public key.  NO AUTHENTICATION REQUIRED - Public keys are public by design.  Users can download the public key to manually verify deletion signatures.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = VerificationApi()
val keyId : kotlin.String = keyId_example // kotlin.String |
try {
    val result : kotlin.String = apiInstance.downloadPublicKeyV1VerificationKeysKeyIdPubGet(keyId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling VerificationApi#downloadPublicKeyV1VerificationKeysKeyIdPubGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling VerificationApi#downloadPublicKeyV1VerificationKeysKeyIdPubGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **keyId** | **kotlin.String**|  | |

### Return type

**kotlin.String**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: text/plain, application/json

<a id="getCurrentPublicKeyInfoV1VerificationKeysCurrentGet"></a>
# **getCurrentPublicKeyInfoV1VerificationKeysCurrentGet**
> StandardResponse getCurrentPublicKeyInfoV1VerificationKeysCurrentGet()

Get Current Public Key Info

Get current public key information.  NO AUTHENTICATION REQUIRED - Public key metadata is public.  Returns the current public key ID and download URL.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = VerificationApi()
try {
    val result : StandardResponse = apiInstance.getCurrentPublicKeyInfoV1VerificationKeysCurrentGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling VerificationApi#getCurrentPublicKeyInfoV1VerificationKeysCurrentGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling VerificationApi#getCurrentPublicKeyInfoV1VerificationKeysCurrentGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="manualSignatureVerificationV1VerificationVerifySignaturePost"></a>
# **manualSignatureVerificationV1VerificationVerifySignaturePost**
> StandardResponse manualSignatureVerificationV1VerificationVerifySignaturePost(manualSignatureVerificationRequest)

Manual Signature Verification

Manual signature verification endpoint.  NO AUTHENTICATION REQUIRED - For manual verification using external tools.  Users can verify signatures manually by: 1. Computing hash of deletion data 2. Verifying RSA-PSS signature using public key 3. Comparing with this endpoint&#39;s result  This endpoint helps users who want to verify independently.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = VerificationApi()
val manualSignatureVerificationRequest : ManualSignatureVerificationRequest =  // ManualSignatureVerificationRequest |
try {
    val result : StandardResponse = apiInstance.manualSignatureVerificationV1VerificationVerifySignaturePost(manualSignatureVerificationRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling VerificationApi#manualSignatureVerificationV1VerificationVerifySignaturePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling VerificationApi#manualSignatureVerificationV1VerificationVerifySignaturePost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **manualSignatureVerificationRequest** | [**ManualSignatureVerificationRequest**](ManualSignatureVerificationRequest.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="publicVerificationPageV1VerificationPublicDeletionIdGet"></a>
# **publicVerificationPageV1VerificationPublicDeletionIdGet**
> kotlin.String publicVerificationPageV1VerificationPublicDeletionIdGet(deletionId)

Public Verification Page

Public verification page (HTML).  NO AUTHENTICATION REQUIRED - Anyone can view.  Provides a human-readable page showing deletion proof verification.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = VerificationApi()
val deletionId : kotlin.String = deletionId_example // kotlin.String |
try {
    val result : kotlin.String = apiInstance.publicVerificationPageV1VerificationPublicDeletionIdGet(deletionId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling VerificationApi#publicVerificationPageV1VerificationPublicDeletionIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling VerificationApi#publicVerificationPageV1VerificationPublicDeletionIdGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **deletionId** | **kotlin.String**|  | |

### Return type

**kotlin.String**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: text/html, application/json

<a id="verifyDeletionProofV1VerificationDeletionPost"></a>
# **verifyDeletionProofV1VerificationDeletionPost**
> StandardResponse verifyDeletionProofV1VerificationDeletionPost(verifyDeletionRequest)

Verify Deletion Proof

Verify cryptographic deletion proof.  NO AUTHENTICATION REQUIRED - Public verification endpoint.  Users can verify that their data was actually deleted by checking the RSA-PSS signature on the deletion proof.  Returns verification result with signature validity.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = VerificationApi()
val verifyDeletionRequest : VerifyDeletionRequest =  // VerifyDeletionRequest |
try {
    val result : StandardResponse = apiInstance.verifyDeletionProofV1VerificationDeletionPost(verifyDeletionRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling VerificationApi#verifyDeletionProofV1VerificationDeletionPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling VerificationApi#verifyDeletionProofV1VerificationDeletionPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **verifyDeletionRequest** | [**VerifyDeletionRequest**](VerifyDeletionRequest.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
