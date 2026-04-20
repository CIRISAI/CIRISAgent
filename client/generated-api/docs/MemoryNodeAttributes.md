
# MemoryNodeAttributes

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **createdBy** | **kotlin.String** | Service or user that created this node |  |
| **content** | **kotlin.String** | The actual memory content |  |
| **memoryType** | **kotlin.String** | Type: fact, experience, learning, insight, observation |  |
| **source** | **kotlin.String** | Where this memory originated |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was created |  [optional] |
| **updatedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was last updated |  [optional] |
| **updatedBy** | **kotlin.String** |  |  [optional] |
| **tags** | **kotlin.collections.List&lt;kotlin.String&gt;** | Tags for categorization and search |  [optional] |
| **version** | **kotlin.Int** | Schema version for migration support |  [optional] |
| **secretRefs** | **kotlin.collections.List&lt;kotlin.String&gt;** | Secret reference UUIDs for encrypted data |  [optional] |
| **contentType** | **kotlin.String** | Type of content: text, embedding, reference |  [optional] |
| **importance** | **kotlin.Double** | Importance score from 0.0 to 1.0 |  [optional] |
| **confidence** | **kotlin.Double** | Confidence in this memory from 0.0 to 1.0 |  [optional] |
| **sourceType** | **kotlin.String** | Source type: internal, user, system, external |  [optional] |
| **channelId** | **kotlin.String** |  |  [optional] |
| **userId** | **kotlin.String** |  |  [optional] |
| **taskId** | **kotlin.String** |  |  [optional] |
| **accessCount** | **kotlin.Int** | Number of times accessed |  [optional] |
| **lastAccessed** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **relatedMemories** | **kotlin.collections.List&lt;kotlin.String&gt;** | IDs of related memory nodes |  [optional] |
| **derivedFrom** | **kotlin.String** |  |  [optional] |
| **embeddingModel** | **kotlin.String** |  |  [optional] |
| **embeddingDimensions** | **kotlin.Int** |  |  [optional] |
