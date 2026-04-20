
# QueryRequest

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **nodeId** | **kotlin.String** |  |  [optional] |
| **type** | [**NodeType**](NodeType.md) |  |  [optional] |
| **query** | **kotlin.String** |  |  [optional] |
| **since** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **until** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **relatedTo** | **kotlin.String** |  |  [optional] |
| **scope** | [**GraphScope**](GraphScope.md) |  |  [optional] |
| **tags** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  [optional] |
| **limit** | **kotlin.Int** | Maximum results |  [optional] |
| **offset** | **kotlin.Int** | Pagination offset |  [optional] |
| **includeEdges** | **kotlin.Boolean** | Include relationship data |  [optional] |
| **depth** | **kotlin.Int** | Graph traversal depth for relationships |  [optional] |
