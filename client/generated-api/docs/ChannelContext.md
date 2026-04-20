
# ChannelContext

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **channelId** | **kotlin.String** | Unique channel identifier |  |
| **channelType** | **kotlin.String** | Type of channel (discord, cli, api) |  |
| **createdAt** | **kotlin.String** |  |  |
| **channelName** | **kotlin.String** |  |  [optional] |
| **isPrivate** | **kotlin.Boolean** | Whether channel is private |  [optional] |
| **participants** | **kotlin.collections.List&lt;kotlin.String&gt;** | Channel participants |  [optional] |
| **isActive** | **kotlin.Boolean** | Whether channel is active |  [optional] |
| **lastActivity** | **kotlin.String** |  |  [optional] |
| **messageCount** | **kotlin.Int** | Total messages in channel |  [optional] |
| **allowedActions** | **kotlin.collections.List&lt;kotlin.String&gt;** | Allowed actions in channel |  [optional] |
| **moderationLevel** | **kotlin.String** | Moderation level |  [optional] |
| **memorizedAttributes** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | Additional attributes the agent memorized about this channel |  [optional] |
