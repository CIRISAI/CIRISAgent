
# ConversationMessage

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **id** | **kotlin.String** | Message ID |  |
| **author** | **kotlin.String** | Message author |  |
| **content** | **kotlin.String** | Message content |  |
| **timestamp** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When sent |  |
| **isAgent** | **kotlin.Boolean** | Whether this was from the agent |  |
| **messageType** | [**inline**](#MessageType) | Type of message (user, agent, system, error) |  [optional] |


<a id="MessageType"></a>
## Enum: message_type
| Name | Value |
| ---- | ----- |
| messageType | user, agent, system, error |
