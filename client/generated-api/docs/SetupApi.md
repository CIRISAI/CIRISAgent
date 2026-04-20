# SetupApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**completeSetupV1SetupCompletePost**](SetupApi.md#completeSetupV1SetupCompletePost) | **POST** /v1/setup/complete | Complete Setup |
| [**getCurrentConfigV1SetupConfigGet**](SetupApi.md#getCurrentConfigV1SetupConfigGet) | **GET** /v1/setup/config | Get Current Config |
| [**getModelCapabilitiesEndpointV1SetupModelsGet**](SetupApi.md#getModelCapabilitiesEndpointV1SetupModelsGet) | **GET** /v1/setup/models | Get Model Capabilities Endpoint |
| [**getProviderModelsV1SetupModelsProviderIdGet**](SetupApi.md#getProviderModelsV1SetupModelsProviderIdGet) | **GET** /v1/setup/models/{provider_id} | Get Provider Models |
| [**getSetupStatusV1SetupStatusGet**](SetupApi.md#getSetupStatusV1SetupStatusGet) | **GET** /v1/setup/status | Get Setup Status |
| [**listAdaptersV1SetupAdaptersGet**](SetupApi.md#listAdaptersV1SetupAdaptersGet) | **GET** /v1/setup/adapters | List Adapters |
| [**listProvidersV1SetupProvidersGet**](SetupApi.md#listProvidersV1SetupProvidersGet) | **GET** /v1/setup/providers | List Providers |
| [**listTemplatesV1SetupTemplatesGet**](SetupApi.md#listTemplatesV1SetupTemplatesGet) | **GET** /v1/setup/templates | List Templates |
| [**updateConfigV1SetupConfigPut**](SetupApi.md#updateConfigV1SetupConfigPut) | **PUT** /v1/setup/config | Update Config |
| [**validateLlmV1SetupValidateLlmPost**](SetupApi.md#validateLlmV1SetupValidateLlmPost) | **POST** /v1/setup/validate-llm | Validate Llm |


<a id="completeSetupV1SetupCompletePost"></a>
# **completeSetupV1SetupCompletePost**
> SuccessResponseDictStrStr completeSetupV1SetupCompletePost(setupCompleteRequest)

Complete Setup

Complete initial setup.  Saves configuration and creates initial admin user. Only accessible during first-run (no authentication required). After setup, authentication is required for reconfiguration.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
val setupCompleteRequest : SetupCompleteRequest =  // SetupCompleteRequest |
try {
    val result : SuccessResponseDictStrStr = apiInstance.completeSetupV1SetupCompletePost(setupCompleteRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#completeSetupV1SetupCompletePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#completeSetupV1SetupCompletePost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **setupCompleteRequest** | [**SetupCompleteRequest**](SetupCompleteRequest.md)|  | |

### Return type

[**SuccessResponseDictStrStr**](SuccessResponseDictStrStr.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="getCurrentConfigV1SetupConfigGet"></a>
# **getCurrentConfigV1SetupConfigGet**
> SuccessResponseSetupConfigResponse getCurrentConfigV1SetupConfigGet()

Get Current Config

Get current configuration.  Returns current setup configuration for editing. Requires authentication if setup is already completed.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
try {
    val result : SuccessResponseSetupConfigResponse = apiInstance.getCurrentConfigV1SetupConfigGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#getCurrentConfigV1SetupConfigGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#getCurrentConfigV1SetupConfigGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseSetupConfigResponse**](SuccessResponseSetupConfigResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getModelCapabilitiesEndpointV1SetupModelsGet"></a>
# **getModelCapabilitiesEndpointV1SetupModelsGet**
> SuccessResponseDictStrAny getModelCapabilitiesEndpointV1SetupModelsGet()

Get Model Capabilities Endpoint

Get CIRIS-compatible LLM model capabilities.  Returns the on-device model capabilities database for BYOK model selection. Used by the wizard&#39;s Advanced settings to show compatible models per provider. This endpoint is always accessible without authentication.  Returns model info including: - CIRIS compatibility requirements (128K+ context, tool use, vision) - Per-provider model listings with capability flags - Tiers (default, fast, fallback, premium) - Recommendations and rejection reasons

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
try {
    val result : SuccessResponseDictStrAny = apiInstance.getModelCapabilitiesEndpointV1SetupModelsGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#getModelCapabilitiesEndpointV1SetupModelsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#getModelCapabilitiesEndpointV1SetupModelsGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseDictStrAny**](SuccessResponseDictStrAny.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getProviderModelsV1SetupModelsProviderIdGet"></a>
# **getProviderModelsV1SetupModelsProviderIdGet**
> SuccessResponseDictStrAny getProviderModelsV1SetupModelsProviderIdGet(providerId)

Get Provider Models

Get CIRIS-compatible models for a specific provider.  Returns models for the given provider with compatibility information. Used by the wizard to populate model dropdown after provider selection.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
val providerId : kotlin.String = providerId_example // kotlin.String |
try {
    val result : SuccessResponseDictStrAny = apiInstance.getProviderModelsV1SetupModelsProviderIdGet(providerId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#getProviderModelsV1SetupModelsProviderIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#getProviderModelsV1SetupModelsProviderIdGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **providerId** | **kotlin.String**|  | |

### Return type

[**SuccessResponseDictStrAny**](SuccessResponseDictStrAny.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getSetupStatusV1SetupStatusGet"></a>
# **getSetupStatusV1SetupStatusGet**
> SuccessResponseSetupStatusResponse getSetupStatusV1SetupStatusGet()

Get Setup Status

Check setup status.  Returns information about whether setup is required. This endpoint is always accessible without authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
try {
    val result : SuccessResponseSetupStatusResponse = apiInstance.getSetupStatusV1SetupStatusGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#getSetupStatusV1SetupStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#getSetupStatusV1SetupStatusGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseSetupStatusResponse**](SuccessResponseSetupStatusResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listAdaptersV1SetupAdaptersGet"></a>
# **listAdaptersV1SetupAdaptersGet**
> SuccessResponseListAdapterConfig listAdaptersV1SetupAdaptersGet()

List Adapters

List available adapters.  Returns configuration for available communication adapters. This endpoint is always accessible without authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
try {
    val result : SuccessResponseListAdapterConfig = apiInstance.listAdaptersV1SetupAdaptersGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#listAdaptersV1SetupAdaptersGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#listAdaptersV1SetupAdaptersGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseListAdapterConfig**](SuccessResponseListAdapterConfig.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listProvidersV1SetupProvidersGet"></a>
# **listProvidersV1SetupProvidersGet**
> SuccessResponseListLLMProvider listProvidersV1SetupProvidersGet()

List Providers

List available LLM providers.  Returns configuration templates for supported LLM providers. This endpoint is always accessible without authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
try {
    val result : SuccessResponseListLLMProvider = apiInstance.listProvidersV1SetupProvidersGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#listProvidersV1SetupProvidersGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#listProvidersV1SetupProvidersGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseListLLMProvider**](SuccessResponseListLLMProvider.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listTemplatesV1SetupTemplatesGet"></a>
# **listTemplatesV1SetupTemplatesGet**
> SuccessResponseListAgentTemplate listTemplatesV1SetupTemplatesGet()

List Templates

List available agent templates.  Returns pre-configured agent identity templates. This endpoint is always accessible without authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
try {
    val result : SuccessResponseListAgentTemplate = apiInstance.listTemplatesV1SetupTemplatesGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#listTemplatesV1SetupTemplatesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#listTemplatesV1SetupTemplatesGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**SuccessResponseListAgentTemplate**](SuccessResponseListAgentTemplate.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="updateConfigV1SetupConfigPut"></a>
# **updateConfigV1SetupConfigPut**
> SuccessResponseDictStrStr updateConfigV1SetupConfigPut(setupCompleteRequest, authorization)

Update Config

Update configuration.  Updates setup configuration after initial setup. Requires admin authentication.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
val setupCompleteRequest : SetupCompleteRequest =  // SetupCompleteRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseDictStrStr = apiInstance.updateConfigV1SetupConfigPut(setupCompleteRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#updateConfigV1SetupConfigPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#updateConfigV1SetupConfigPut")
    e.printStackTrace()
}
```

### Parameters
| **setupCompleteRequest** | [**SetupCompleteRequest**](SetupCompleteRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseDictStrStr**](SuccessResponseDictStrStr.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="validateLlmV1SetupValidateLlmPost"></a>
# **validateLlmV1SetupValidateLlmPost**
> SuccessResponseLLMValidationResponse validateLlmV1SetupValidateLlmPost(llMValidationRequest)

Validate Llm

Validate LLM configuration.  Tests the provided LLM configuration by attempting a connection. This endpoint is always accessible without authentication during first-run.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = SetupApi()
val llMValidationRequest : LLMValidationRequest =  // LLMValidationRequest |
try {
    val result : SuccessResponseLLMValidationResponse = apiInstance.validateLlmV1SetupValidateLlmPost(llMValidationRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling SetupApi#validateLlmV1SetupValidateLlmPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling SetupApi#validateLlmV1SetupValidateLlmPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **llMValidationRequest** | [**LLMValidationRequest**](LLMValidationRequest.md)|  | |

### Return type

[**SuccessResponseLLMValidationResponse**](SuccessResponseLLMValidationResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
