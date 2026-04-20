
# ActionParameters

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **content** | **kotlin.String** |  |  |
| **name** | **kotlin.String** |  |  |
| **questions** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  |
| **reason** | **kotlin.String** |  |  |
| **node** | [**GraphNode**](GraphNode.md) |  |  |
| **channelId** | **kotlin.String** |  |  [optional] |
| **channelContext** | [**ChannelContext**](ChannelContext.md) |  |  [optional] |
| **active** | **kotlin.Boolean** |  |  [optional] |
| **context** | [**kotlin.collections.Map&lt;kotlin.String, DeferParamsContextValue&gt;**](DeferParamsContextValue.md) |  |  [optional] |
| **parameters** | [**kotlin.collections.Map&lt;kotlin.String, ParametersValue&gt;**](ParametersValue.md) |  |  [optional] |
| **createFilter** | **kotlin.Boolean** | Whether to create an adaptive filter to prevent similar requests |  [optional] |
| **filterPattern** | **kotlin.String** |  |  [optional] |
| **filterType** | **kotlin.String** |  |  [optional] |
| **filterPriority** | **kotlin.String** |  |  [optional] |
| **deferUntil** | **kotlin.String** |  |  [optional] |
| **query** | **kotlin.String** |  |  [optional] |
| **nodeType** | **kotlin.String** |  |  [optional] |
| **nodeId** | **kotlin.String** |  |  [optional] |
| **scope** | [**GraphScope**](GraphScope.md) |  |  [optional] |
| **limit** | **kotlin.Int** | Maximum number of results |  [optional] |
| **noAudit** | **kotlin.Boolean** |  |  [optional] |
| **completionReason** | **kotlin.String** |  |  [optional] |
| **positiveMoment** | **kotlin.String** |  |  [optional] |
| **persistImages** | **kotlin.Boolean** | If True, preserve task images after completion. Default False purges images for privacy/storage. |  [optional] |
