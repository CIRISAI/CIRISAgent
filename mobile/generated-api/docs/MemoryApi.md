# MemoryApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**forgetMemoryV1MemoryNodeIdDelete**](MemoryApi.md#forgetMemoryV1MemoryNodeIdDelete) | **DELETE** /v1/memory/{node_id} | Forget Memory |
| [**getNodeEdgesV1MemoryNodeIdEdgesGet**](MemoryApi.md#getNodeEdgesV1MemoryNodeIdEdgesGet) | **GET** /v1/memory/{node_id}/edges | Get Node Edges |
| [**getNodeV1MemoryNodeIdGet**](MemoryApi.md#getNodeV1MemoryNodeIdGet) | **GET** /v1/memory/{node_id} | Get Node |
| [**getStatsV1MemoryStatsGet**](MemoryApi.md#getStatsV1MemoryStatsGet) | **GET** /v1/memory/stats | Get Stats |
| [**getTimelineV1MemoryTimelineGet**](MemoryApi.md#getTimelineV1MemoryTimelineGet) | **GET** /v1/memory/timeline | Get Timeline |
| [**queryMemoryV1MemoryQueryPost**](MemoryApi.md#queryMemoryV1MemoryQueryPost) | **POST** /v1/memory/query | Query Memory |
| [**recallByIdV1MemoryRecallNodeIdGet**](MemoryApi.md#recallByIdV1MemoryRecallNodeIdGet) | **GET** /v1/memory/recall/{node_id} | Recall By Id |
| [**storeMemoryV1MemoryStorePost**](MemoryApi.md#storeMemoryV1MemoryStorePost) | **POST** /v1/memory/store | Store Memory |
| [**visualizeGraphV1MemoryVisualizeGraphGet**](MemoryApi.md#visualizeGraphV1MemoryVisualizeGraphGet) | **GET** /v1/memory/visualize/graph | Visualize Graph |


<a id="forgetMemoryV1MemoryNodeIdDelete"></a>
# **forgetMemoryV1MemoryNodeIdDelete**
> SuccessResponseMemoryOpResultGraphNode forgetMemoryV1MemoryNodeIdDelete(nodeId, authorization)

Forget Memory

Forget a specific memory node (FORGET).  Requires ADMIN role as this permanently removes data.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val nodeId : kotlin.String = nodeId_example // kotlin.String | Node ID to forget
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseMemoryOpResultGraphNode = apiInstance.forgetMemoryV1MemoryNodeIdDelete(nodeId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#forgetMemoryV1MemoryNodeIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#forgetMemoryV1MemoryNodeIdDelete")
    e.printStackTrace()
}
```

### Parameters
| **nodeId** | **kotlin.String**| Node ID to forget | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseMemoryOpResultGraphNode**](SuccessResponseMemoryOpResultGraphNode.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getNodeEdgesV1MemoryNodeIdEdgesGet"></a>
# **getNodeEdgesV1MemoryNodeIdEdgesGet**
> SuccessResponseListGraphEdge getNodeEdgesV1MemoryNodeIdEdgesGet(nodeId, authorization)

Get Node Edges

Get all edges connected to a node.  Returns both incoming and outgoing edges.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val nodeId : kotlin.String = nodeId_example // kotlin.String | Node ID
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseListGraphEdge = apiInstance.getNodeEdgesV1MemoryNodeIdEdgesGet(nodeId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#getNodeEdgesV1MemoryNodeIdEdgesGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#getNodeEdgesV1MemoryNodeIdEdgesGet")
    e.printStackTrace()
}
```

### Parameters
| **nodeId** | **kotlin.String**| Node ID | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseListGraphEdge**](SuccessResponseListGraphEdge.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getNodeV1MemoryNodeIdGet"></a>
# **getNodeV1MemoryNodeIdGet**
> SuccessResponseGraphNode getNodeV1MemoryNodeIdGet(nodeId, authorization)

Get Node

Get a specific node by ID.  Standard RESTful endpoint for node retrieval.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val nodeId : kotlin.String = nodeId_example // kotlin.String | Node ID
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseGraphNode = apiInstance.getNodeV1MemoryNodeIdGet(nodeId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#getNodeV1MemoryNodeIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#getNodeV1MemoryNodeIdGet")
    e.printStackTrace()
}
```

### Parameters
| **nodeId** | **kotlin.String**| Node ID | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseGraphNode**](SuccessResponseGraphNode.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getStatsV1MemoryStatsGet"></a>
# **getStatsV1MemoryStatsGet**
> SuccessResponseMemoryStats getStatsV1MemoryStatsGet(authorization)

Get Stats

Get statistics about memory storage.  Returns counts, distributions, and metadata about the memory graph.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseMemoryStats = apiInstance.getStatsV1MemoryStatsGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#getStatsV1MemoryStatsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#getStatsV1MemoryStatsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseMemoryStats**](SuccessResponseMemoryStats.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getTimelineV1MemoryTimelineGet"></a>
# **getTimelineV1MemoryTimelineGet**
> SuccessResponseTimelineResponse getTimelineV1MemoryTimelineGet(hours, scope, type, authorization)

Get Timeline

Get a timeline view of recent memories.  Returns memories organized chronologically with time buckets.  SECURITY: OBSERVER users only see nodes they created or participated in.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val hours : kotlin.Int = 56 // kotlin.Int | Hours to look back
val scope : kotlin.String = scope_example // kotlin.String | Filter by scope
val type : kotlin.String = type_example // kotlin.String | Filter by node type
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseTimelineResponse = apiInstance.getTimelineV1MemoryTimelineGet(hours, scope, type, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#getTimelineV1MemoryTimelineGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#getTimelineV1MemoryTimelineGet")
    e.printStackTrace()
}
```

### Parameters
| **hours** | **kotlin.Int**| Hours to look back | [optional] [default to 24] |
| **scope** | **kotlin.String**| Filter by scope | [optional] |
| **type** | **kotlin.String**| Filter by node type | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseTimelineResponse**](SuccessResponseTimelineResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="queryMemoryV1MemoryQueryPost"></a>
# **queryMemoryV1MemoryQueryPost**
> SuccessResponseListGraphNode queryMemoryV1MemoryQueryPost(queryRequest, authorization)

Query Memory

Query memories with flexible filters (RECALL).  Supports querying by ID, type, text, time range, and relationships.  SECURITY: OBSERVER users only see nodes they created or participated in.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val queryRequest : QueryRequest =  // QueryRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseListGraphNode = apiInstance.queryMemoryV1MemoryQueryPost(queryRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#queryMemoryV1MemoryQueryPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#queryMemoryV1MemoryQueryPost")
    e.printStackTrace()
}
```

### Parameters
| **queryRequest** | [**QueryRequest**](QueryRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseListGraphNode**](SuccessResponseListGraphNode.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="recallByIdV1MemoryRecallNodeIdGet"></a>
# **recallByIdV1MemoryRecallNodeIdGet**
> SuccessResponseGraphNode recallByIdV1MemoryRecallNodeIdGet(nodeId, authorization)

Recall By Id

Recall a specific node by ID (legacy endpoint).  Use GET /memory/{node_id} for new implementations.  SECURITY: OBSERVER users can only access nodes they created or participated in.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val nodeId : kotlin.String = nodeId_example // kotlin.String | Node ID to recall
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseGraphNode = apiInstance.recallByIdV1MemoryRecallNodeIdGet(nodeId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#recallByIdV1MemoryRecallNodeIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#recallByIdV1MemoryRecallNodeIdGet")
    e.printStackTrace()
}
```

### Parameters
| **nodeId** | **kotlin.String**| Node ID to recall | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseGraphNode**](SuccessResponseGraphNode.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="storeMemoryV1MemoryStorePost"></a>
# **storeMemoryV1MemoryStorePost**
> SuccessResponseMemoryOpResultGraphNode storeMemoryV1MemoryStorePost(storeRequest, authorization)

Store Memory

Store typed nodes in memory (MEMORIZE).  This is the primary way to add information to the agent&#39;s memory. Requires ADMIN role as this modifies system state.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val storeRequest : StoreRequest =  // StoreRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseMemoryOpResultGraphNode = apiInstance.storeMemoryV1MemoryStorePost(storeRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#storeMemoryV1MemoryStorePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#storeMemoryV1MemoryStorePost")
    e.printStackTrace()
}
```

### Parameters
| **storeRequest** | [**StoreRequest**](StoreRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseMemoryOpResultGraphNode**](SuccessResponseMemoryOpResultGraphNode.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="visualizeGraphV1MemoryVisualizeGraphGet"></a>
# **visualizeGraphV1MemoryVisualizeGraphGet**
> kotlin.Any visualizeGraphV1MemoryVisualizeGraphGet(hours, layout, width, height, scope, type, authorization)

Visualize Graph

Generate an interactive SVG visualization of the memory graph.  Returns an HTML page with an embedded SVG visualization.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = MemoryApi()
val hours : kotlin.Int = 56 // kotlin.Int | Hours to look back
val layout : kotlin.String = layout_example // kotlin.String | Layout: hierarchy, timeline, circular
val width : kotlin.Int = 56 // kotlin.Int | SVG width
val height : kotlin.Int = 56 // kotlin.Int | SVG height
val scope : kotlin.String = scope_example // kotlin.String | Filter by scope
val type : kotlin.String = type_example // kotlin.String | Filter by node type
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.Any = apiInstance.visualizeGraphV1MemoryVisualizeGraphGet(hours, layout, width, height, scope, type, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling MemoryApi#visualizeGraphV1MemoryVisualizeGraphGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling MemoryApi#visualizeGraphV1MemoryVisualizeGraphGet")
    e.printStackTrace()
}
```

### Parameters
| **hours** | **kotlin.Int**| Hours to look back | [optional] [default to 24] |
| **layout** | **kotlin.String**| Layout: hierarchy, timeline, circular | [optional] [default to &quot;hierarchy&quot;] |
| **width** | **kotlin.Int**| SVG width | [optional] [default to 800] |
| **height** | **kotlin.Int**| SVG height | [optional] [default to 600] |
| **scope** | **kotlin.String**| Filter by scope | [optional] |
| **type** | **kotlin.String**| Filter by node type | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**kotlin.Any**](kotlin.Any.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json
