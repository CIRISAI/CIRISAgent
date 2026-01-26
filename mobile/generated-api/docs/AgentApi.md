# AgentApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**getChannelsV1AgentChannelsGet**](AgentApi.md#getChannelsV1AgentChannelsGet) | **GET** /v1/agent/channels | Get Channels |
| [**getHistoryV1AgentHistoryGet**](AgentApi.md#getHistoryV1AgentHistoryGet) | **GET** /v1/agent/history | Get History |
| [**getIdentityV1AgentIdentityGet**](AgentApi.md#getIdentityV1AgentIdentityGet) | **GET** /v1/agent/identity | Get Identity |
| [**getStatusV1AgentStatusGet**](AgentApi.md#getStatusV1AgentStatusGet) | **GET** /v1/agent/status | Get Status |
| [**interactV1AgentInteractPost**](AgentApi.md#interactV1AgentInteractPost) | **POST** /v1/agent/interact | Interact |
| [**submitMessageV1AgentMessagePost**](AgentApi.md#submitMessageV1AgentMessagePost) | **POST** /v1/agent/message | Submit Message |


<a id="getChannelsV1AgentChannelsGet"></a>
# **getChannelsV1AgentChannelsGet**
> SuccessResponseChannelList getChannelsV1AgentChannelsGet(authorization)

Get Channels

List active communication channels.  Get all channels where the agent is currently active or has been active.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AgentApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseChannelList = apiInstance.getChannelsV1AgentChannelsGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AgentApi#getChannelsV1AgentChannelsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AgentApi#getChannelsV1AgentChannelsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseChannelList**](SuccessResponseChannelList.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getHistoryV1AgentHistoryGet"></a>
# **getHistoryV1AgentHistoryGet**
> SuccessResponseConversationHistory getHistoryV1AgentHistoryGet(limit, before, authorization)

Get History

Conversation history.  Get the conversation history for the current user.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AgentApi()
val limit : kotlin.Int = 56 // kotlin.Int | Maximum messages to return
val before : kotlin.time.Instant = 2013-10-20T19:20:30+01:00 // kotlin.time.Instant | Get messages before this time
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseConversationHistory = apiInstance.getHistoryV1AgentHistoryGet(limit, before, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AgentApi#getHistoryV1AgentHistoryGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AgentApi#getHistoryV1AgentHistoryGet")
    e.printStackTrace()
}
```

### Parameters
| **limit** | **kotlin.Int**| Maximum messages to return | [optional] [default to 50] |
| **before** | **kotlin.time.Instant**| Get messages before this time | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseConversationHistory**](SuccessResponseConversationHistory.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getIdentityV1AgentIdentityGet"></a>
# **getIdentityV1AgentIdentityGet**
> SuccessResponseAgentIdentity getIdentityV1AgentIdentityGet(authorization)

Get Identity

Agent identity and capabilities.  Get comprehensive agent identity including capabilities, tools, and permissions.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AgentApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAgentIdentity = apiInstance.getIdentityV1AgentIdentityGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AgentApi#getIdentityV1AgentIdentityGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AgentApi#getIdentityV1AgentIdentityGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAgentIdentity**](SuccessResponseAgentIdentity.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getStatusV1AgentStatusGet"></a>
# **getStatusV1AgentStatusGet**
> SuccessResponseAgentStatus getStatusV1AgentStatusGet(authorization)

Get Status

Agent status and cognitive state.  Get comprehensive agent status including state, metrics, and current activity.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AgentApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseAgentStatus = apiInstance.getStatusV1AgentStatusGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AgentApi#getStatusV1AgentStatusGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AgentApi#getStatusV1AgentStatusGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseAgentStatus**](SuccessResponseAgentStatus.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="interactV1AgentInteractPost"></a>
# **interactV1AgentInteractPost**
> SuccessResponseInteractResponse interactV1AgentInteractPost(interactRequest, authorization)

Interact

Send message and get response.  This endpoint combines the old send/ask functionality into a single interaction. It sends the message and waits for the agent&#39;s response (with a reasonable timeout).  Requires: SEND_MESSAGES permission (ADMIN+ by default, or OBSERVER with explicit grant)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AgentApi()
val interactRequest : InteractRequest =  // InteractRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseInteractResponse = apiInstance.interactV1AgentInteractPost(interactRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AgentApi#interactV1AgentInteractPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AgentApi#interactV1AgentInteractPost")
    e.printStackTrace()
}
```

### Parameters
| **interactRequest** | [**InteractRequest**](InteractRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseInteractResponse**](SuccessResponseInteractResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="submitMessageV1AgentMessagePost"></a>
# **submitMessageV1AgentMessagePost**
> SuccessResponseMessageSubmissionResponse submitMessageV1AgentMessagePost(messageRequest, authorization)

Submit Message

Submit a message to the agent (async pattern - returns immediately).  This endpoint returns immediately with a task_id for tracking or rejection reason. Use GET /agent/history to poll for the agent&#39;s response.  This is the recommended way to interact with the agent via API, as it doesn&#39;t block waiting for processing to complete.  Requires: SEND_MESSAGES permission (ADMIN+ by default, or OBSERVER with explicit grant)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AgentApi()
val messageRequest : MessageRequest =  // MessageRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : SuccessResponseMessageSubmissionResponse = apiInstance.submitMessageV1AgentMessagePost(messageRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AgentApi#submitMessageV1AgentMessagePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AgentApi#submitMessageV1AgentMessagePost")
    e.printStackTrace()
}
```

### Parameters
| **messageRequest** | [**MessageRequest**](MessageRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**SuccessResponseMessageSubmissionResponse**](SuccessResponseMessageSubmissionResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
