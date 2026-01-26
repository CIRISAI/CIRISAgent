# ToolsApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**checkToolCreditV1ApiToolsCheckToolNameGet**](ToolsApi.md#checkToolCreditV1ApiToolsCheckToolNameGet) | **GET** /v1/api/tools/check/{tool_name} | Check Tool Credit |
| [**getAllToolBalancesV1ApiToolsBalanceGet**](ToolsApi.md#getAllToolBalancesV1ApiToolsBalanceGet) | **GET** /v1/api/tools/balance | Get All Tool Balances |
| [**getAvailableToolsV1ApiToolsAvailableGet**](ToolsApi.md#getAvailableToolsV1ApiToolsAvailableGet) | **GET** /v1/api/tools/available | Get Available Tools |
| [**getToolBalanceV1ApiToolsBalanceToolNameGet**](ToolsApi.md#getToolBalanceV1ApiToolsBalanceToolNameGet) | **GET** /v1/api/tools/balance/{tool_name} | Get Tool Balance |
| [**verifyToolPurchaseV1ApiToolsPurchasePost**](ToolsApi.md#verifyToolPurchaseV1ApiToolsPurchasePost) | **POST** /v1/api/tools/purchase | Verify Tool Purchase |


<a id="checkToolCreditV1ApiToolsCheckToolNameGet"></a>
# **checkToolCreditV1ApiToolsCheckToolNameGet**
> ToolCreditCheckResponse checkToolCreditV1ApiToolsCheckToolNameGet(toolName, authorization)

Check Tool Credit

Quick credit check for a tool.  Lightweight endpoint to check if user has credit for a specific tool. Requires Google Sign-In authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ToolsApi()
val toolName : kotlin.String = toolName_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ToolCreditCheckResponse = apiInstance.checkToolCreditV1ApiToolsCheckToolNameGet(toolName, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ToolsApi#checkToolCreditV1ApiToolsCheckToolNameGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ToolsApi#checkToolCreditV1ApiToolsCheckToolNameGet")
    e.printStackTrace()
}
```

### Parameters
| **toolName** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ToolCreditCheckResponse**](ToolCreditCheckResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getAllToolBalancesV1ApiToolsBalanceGet"></a>
# **getAllToolBalancesV1ApiToolsBalanceGet**
> AllToolBalancesResponse getAllToolBalancesV1ApiToolsBalanceGet(authorization)

Get All Tool Balances

Get balance for all tools.  Returns the user&#39;s credit balance for all available tools. Requires Google Sign-In authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ToolsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : AllToolBalancesResponse = apiInstance.getAllToolBalancesV1ApiToolsBalanceGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ToolsApi#getAllToolBalancesV1ApiToolsBalanceGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ToolsApi#getAllToolBalancesV1ApiToolsBalanceGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**AllToolBalancesResponse**](AllToolBalancesResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getAvailableToolsV1ApiToolsAvailableGet"></a>
# **getAvailableToolsV1ApiToolsAvailableGet**
> AvailableToolsResponse getAvailableToolsV1ApiToolsAvailableGet(authorization)

Get Available Tools

Get list of available tools for this platform.  Returns tools available based on current platform capabilities. Some tools require specific platform features (e.g., Google Play Services).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ToolsApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : AvailableToolsResponse = apiInstance.getAvailableToolsV1ApiToolsAvailableGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ToolsApi#getAvailableToolsV1ApiToolsAvailableGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ToolsApi#getAvailableToolsV1ApiToolsAvailableGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**AvailableToolsResponse**](AvailableToolsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getToolBalanceV1ApiToolsBalanceToolNameGet"></a>
# **getToolBalanceV1ApiToolsBalanceToolNameGet**
> ToolBalanceResponse getToolBalanceV1ApiToolsBalanceToolNameGet(toolName, authorization)

Get Tool Balance

Get balance for a specific tool.  Returns the user&#39;s credit balance for the specified tool (e.g., web_search). Requires Google Sign-In authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ToolsApi()
val toolName : kotlin.String = toolName_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ToolBalanceResponse = apiInstance.getToolBalanceV1ApiToolsBalanceToolNameGet(toolName, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ToolsApi#getToolBalanceV1ApiToolsBalanceToolNameGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ToolsApi#getToolBalanceV1ApiToolsBalanceToolNameGet")
    e.printStackTrace()
}
```

### Parameters
| **toolName** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ToolBalanceResponse**](ToolBalanceResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="verifyToolPurchaseV1ApiToolsPurchasePost"></a>
# **verifyToolPurchaseV1ApiToolsPurchasePost**
> ToolPurchaseResponse verifyToolPurchaseV1ApiToolsPurchasePost(toolPurchaseRequest, authorization)

Verify Tool Purchase

Verify and process a Google Play tool credit purchase.  After a successful Google Play purchase, the app should call this endpoint with the purchase token to verify the purchase and grant credits. Requires Google Sign-In authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ToolsApi()
val toolPurchaseRequest : ToolPurchaseRequest =  // ToolPurchaseRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ToolPurchaseResponse = apiInstance.verifyToolPurchaseV1ApiToolsPurchasePost(toolPurchaseRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ToolsApi#verifyToolPurchaseV1ApiToolsPurchasePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ToolsApi#verifyToolPurchaseV1ApiToolsPurchasePost")
    e.printStackTrace()
}
```

### Parameters
| **toolPurchaseRequest** | [**ToolPurchaseRequest**](ToolPurchaseRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ToolPurchaseResponse**](ToolPurchaseResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
