# ConfigApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**deleteConfigV1ConfigKeyDelete**](ConfigApi.md#deleteConfigV1ConfigKeyDelete) | **DELETE** /v1/config/{key} | Delete Config |
| [**getConfigV1ConfigKeyGet**](ConfigApi.md#getConfigV1ConfigKeyGet) | **GET** /v1/config/{key} | Get Config |
| [**listConfigsV1ConfigGet**](ConfigApi.md#listConfigsV1ConfigGet) | **GET** /v1/config | List Configs |
| [**updateConfigV1ConfigKeyPut**](ConfigApi.md#updateConfigV1ConfigKeyPut) | **PUT** /v1/config/{key} | Update Config |


<a id="deleteConfigV1ConfigKeyDelete"></a>
# **deleteConfigV1ConfigKeyDelete**
> SuccessResponseDictStrStr deleteConfigV1ConfigKeyDelete(key, authorization)

Delete Config

Delete config.  Remove a configuration value. Requires ADMIN role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConfigApi()
val key : kotlin.String = key_example // kotlin.String | Configuration key
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseDictStrStr = apiInstance.deleteConfigV1ConfigKeyDelete(key, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConfigApi#deleteConfigV1ConfigKeyDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConfigApi#deleteConfigV1ConfigKeyDelete")
    e.printStackTrace()
}
```

### Parameters
| **key** | **kotlin.String**| Configuration key | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseDictStrStr**](SuccessResponseDictStrStr.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getConfigV1ConfigKeyGet"></a>
# **getConfigV1ConfigKeyGet**
> SuccessResponseConfigItemResponse getConfigV1ConfigKeyGet(key, authorization)

Get Config

Get specific config.  Get a specific configuration value.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConfigApi()
val key : kotlin.String = key_example // kotlin.String | Configuration key
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseConfigItemResponse = apiInstance.getConfigV1ConfigKeyGet(key, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConfigApi#getConfigV1ConfigKeyGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConfigApi#getConfigV1ConfigKeyGet")
    e.printStackTrace()
}
```

### Parameters
| **key** | **kotlin.String**| Configuration key | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseConfigItemResponse**](SuccessResponseConfigItemResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listConfigsV1ConfigGet"></a>
# **listConfigsV1ConfigGet**
> SuccessResponseConfigListResponse listConfigsV1ConfigGet(prefix, authorization)

List Configs

List all configurations.  Get all configuration values, with sensitive values filtered based on role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConfigApi()
val prefix : kotlin.String = prefix_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseConfigListResponse = apiInstance.listConfigsV1ConfigGet(prefix, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConfigApi#listConfigsV1ConfigGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConfigApi#listConfigsV1ConfigGet")
    e.printStackTrace()
}
```

### Parameters
| **prefix** | **kotlin.String**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseConfigListResponse**](SuccessResponseConfigListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="updateConfigV1ConfigKeyPut"></a>
# **updateConfigV1ConfigKeyPut**
> SuccessResponseConfigItemResponse updateConfigV1ConfigKeyPut(key, configUpdate, authorization)

Update Config

Update config.  Update a configuration value. Requires ADMIN role, or SYSTEM_ADMIN for sensitive configs.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConfigApi()
val key : kotlin.String = key_example // kotlin.String | Configuration key
val configUpdate : ConfigUpdate =  // ConfigUpdate |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseConfigItemResponse = apiInstance.updateConfigV1ConfigKeyPut(key, configUpdate, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConfigApi#updateConfigV1ConfigKeyPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConfigApi#updateConfigV1ConfigKeyPut")
    e.printStackTrace()
}
```

### Parameters
| **key** | **kotlin.String**| Configuration key | |
| **configUpdate** | [**ConfigUpdate**](ConfigUpdate.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseConfigItemResponse**](SuccessResponseConfigItemResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
