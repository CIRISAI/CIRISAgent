# ConnectorsApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**deleteConnectorV1ConnectorsConnectorIdDelete**](ConnectorsApi.md#deleteConnectorV1ConnectorsConnectorIdDelete) | **DELETE** /v1/connectors/{connector_id} | Delete Connector |
| [**listConnectorsV1ConnectorsGet**](ConnectorsApi.md#listConnectorsV1ConnectorsGet) | **GET** /v1/connectors/ | List Connectors |
| [**registerSqlConnectorV1ConnectorsSqlPost**](ConnectorsApi.md#registerSqlConnectorV1ConnectorsSqlPost) | **POST** /v1/connectors/sql | Register Sql Connector |
| [**testConnectorV1ConnectorsConnectorIdTestPost**](ConnectorsApi.md#testConnectorV1ConnectorsConnectorIdTestPost) | **POST** /v1/connectors/{connector_id}/test | Test Connector |
| [**updateConnectorV1ConnectorsConnectorIdPatch**](ConnectorsApi.md#updateConnectorV1ConnectorsConnectorIdPatch) | **PATCH** /v1/connectors/{connector_id} | Update Connector |


<a id="deleteConnectorV1ConnectorsConnectorIdDelete"></a>
# **deleteConnectorV1ConnectorsConnectorIdDelete**
> StandardResponse deleteConnectorV1ConnectorsConnectorIdDelete(connectorId)

Delete Connector

Remove a connector from the system.  This is a destructive operation and cannot be undone.  Requires admin privileges.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConnectorsApi()
val connectorId : kotlin.String = connectorId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.deleteConnectorV1ConnectorsConnectorIdDelete(connectorId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConnectorsApi#deleteConnectorV1ConnectorsConnectorIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConnectorsApi#deleteConnectorV1ConnectorsConnectorIdDelete")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **connectorId** | **kotlin.String**|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listConnectorsV1ConnectorsGet"></a>
# **listConnectorsV1ConnectorsGet**
> StandardResponse listConnectorsV1ConnectorsGet(connectorType)

List Connectors

List all registered connectors.  Optionally filter by connector_type (sql, rest, hl7).  Requires admin privileges.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConnectorsApi()
val connectorType : kotlin.String = connectorType_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.listConnectorsV1ConnectorsGet(connectorType)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConnectorsApi#listConnectorsV1ConnectorsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConnectorsApi#listConnectorsV1ConnectorsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **connectorType** | **kotlin.String**|  | [optional] |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="registerSqlConnectorV1ConnectorsSqlPost"></a>
# **registerSqlConnectorV1ConnectorsSqlPost**
> StandardResponse registerSqlConnectorV1ConnectorsSqlPost(connectorRegistrationRequest)

Register Sql Connector

Register a new SQL database connector.  Requires admin privileges.  The connector will be registered with the tool bus and made available for multi-source DSAR operations.  Configuration must include: - connector_name: Human-readable name - database_type: postgres, mysql, sqlite, etc. - host, port, database, username, password - privacy_schema: YAML defining PII columns (optional)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConnectorsApi()
val connectorRegistrationRequest : ConnectorRegistrationRequest =  // ConnectorRegistrationRequest |
try {
    val result : StandardResponse = apiInstance.registerSqlConnectorV1ConnectorsSqlPost(connectorRegistrationRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConnectorsApi#registerSqlConnectorV1ConnectorsSqlPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConnectorsApi#registerSqlConnectorV1ConnectorsSqlPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **connectorRegistrationRequest** | [**ConnectorRegistrationRequest**](ConnectorRegistrationRequest.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="testConnectorV1ConnectorsConnectorIdTestPost"></a>
# **testConnectorV1ConnectorsConnectorIdTestPost**
> StandardResponse testConnectorV1ConnectorsConnectorIdTestPost(connectorId)

Test Connector

Test connector connection health.  Attempts a test query or connection to verify the connector is working.  Requires admin privileges.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConnectorsApi()
val connectorId : kotlin.String = connectorId_example // kotlin.String |
try {
    val result : StandardResponse = apiInstance.testConnectorV1ConnectorsConnectorIdTestPost(connectorId)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConnectorsApi#testConnectorV1ConnectorsConnectorIdTestPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConnectorsApi#testConnectorV1ConnectorsConnectorIdTestPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **connectorId** | **kotlin.String**|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="updateConnectorV1ConnectorsConnectorIdPatch"></a>
# **updateConnectorV1ConnectorsConnectorIdPatch**
> StandardResponse updateConnectorV1ConnectorsConnectorIdPatch(connectorId, connectorUpdateRequest)

Update Connector

Update connector configuration.  Can update configuration fields or enable/disable the connector.  Requires admin privileges.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = ConnectorsApi()
val connectorId : kotlin.String = connectorId_example // kotlin.String |
val connectorUpdateRequest : ConnectorUpdateRequest =  // ConnectorUpdateRequest |
try {
    val result : StandardResponse = apiInstance.updateConnectorV1ConnectorsConnectorIdPatch(connectorId, connectorUpdateRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling ConnectorsApi#updateConnectorV1ConnectorsConnectorIdPatch")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling ConnectorsApi#updateConnectorV1ConnectorsConnectorIdPatch")
    e.printStackTrace()
}
```

### Parameters
| **connectorId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **connectorUpdateRequest** | [**ConnectorUpdateRequest**](ConnectorUpdateRequest.md)|  | |

### Return type

[**StandardResponse**](StandardResponse.md)

### Authorization


Configure HTTPBearer:
    ApiClient.accessToken = ""

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
