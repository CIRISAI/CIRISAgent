# EmergencyApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**emergencyShutdownEmergencyShutdownPost**](EmergencyApi.md#emergencyShutdownEmergencyShutdownPost) | **POST** /emergency/shutdown | Emergency Shutdown |
| [**testEmergencyEndpointEmergencyTestGet**](EmergencyApi.md#testEmergencyEndpointEmergencyTestGet) | **GET** /emergency/test | Test Emergency Endpoint |


<a id="emergencyShutdownEmergencyShutdownPost"></a>
# **emergencyShutdownEmergencyShutdownPost**
> SuccessResponseEmergencyShutdownStatus emergencyShutdownEmergencyShutdownPost(waSignedCommand)

Emergency Shutdown

Execute emergency shutdown with cryptographically signed command.  This endpoint requires no authentication - the signature IS the authentication. Only accepts SHUTDOWN_NOW commands signed by authorized Wise Authorities.  Security checks: 1. Valid Ed25519 signature 2. Timestamp within 5-minute window 3. Public key is authorized (ROOT WA or in trust tree) 4. Command type is SHUTDOWN_NOW  Args:     command: Cryptographically signed shutdown command  Returns:     Status of the emergency shutdown process  Raises:     HTTPException: If any security check fails

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = EmergencyApi()
val waSignedCommand : WASignedCommand =  // WASignedCommand |
try {
    val result : SuccessResponseEmergencyShutdownStatus = apiInstance.emergencyShutdownEmergencyShutdownPost(waSignedCommand)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling EmergencyApi#emergencyShutdownEmergencyShutdownPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling EmergencyApi#emergencyShutdownEmergencyShutdownPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **waSignedCommand** | [**WASignedCommand**](WASignedCommand.md)|  | |

### Return type

[**SuccessResponseEmergencyShutdownStatus**](SuccessResponseEmergencyShutdownStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="testEmergencyEndpointEmergencyTestGet"></a>
# **testEmergencyEndpointEmergencyTestGet**
> kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt; testEmergencyEndpointEmergencyTestGet()

Test Emergency Endpoint

Test endpoint to verify emergency routes are mounted.  This endpoint requires no authentication and simply confirms the emergency routes are accessible.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = EmergencyApi()
try {
    val result : kotlin.collections.Map<kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue> = apiInstance.testEmergencyEndpointEmergencyTestGet()
    println(result)
} catch (e: ClientException) {
    println("4xx response calling EmergencyApi#testEmergencyEndpointEmergencyTestGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling EmergencyApi#testEmergencyEndpointEmergencyTestGet")
    e.printStackTrace()
}
```

### Parameters
This endpoint does not need any parameter.

### Return type

[**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json
