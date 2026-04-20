
# LogNodeAttributes

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **createdBy** | **kotlin.String** | Service or user that created this node |  |
| **logMessage** | **kotlin.String** | The log message content |  |
| **logLevel** | **kotlin.String** | Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was created |  [optional] |
| **updatedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When this node was last updated |  [optional] |
| **updatedBy** | **kotlin.String** |  |  [optional] |
| **tags** | **kotlin.collections.List&lt;kotlin.String&gt;** | Tags for categorization and search |  [optional] |
| **version** | **kotlin.Int** | Schema version for migration support |  [optional] |
| **secretRefs** | **kotlin.collections.List&lt;kotlin.String&gt;** | Secret reference UUIDs for encrypted data |  [optional] |
| **logTags** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | Additional tags for the log entry |  [optional] |
| **retentionPolicy** | **kotlin.String** | Retention policy for this log |  [optional] |
