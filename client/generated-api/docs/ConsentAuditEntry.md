
# ConsentAuditEntry

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **entryId** | **kotlin.String** | Unique audit entry ID |  |
| **userId** | **kotlin.String** | User whose consent changed |  |
| **timestamp** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When change occurred |  |
| **previousStream** | [**ConsentStream**](ConsentStream.md) | Stream before change |  |
| **newStream** | [**ConsentStream**](ConsentStream.md) | Stream after change |  |
| **previousCategories** | [**kotlin.collections.List&lt;ConsentCategory&gt;**](ConsentCategory.md) | Categories before |  |
| **newCategories** | [**kotlin.collections.List&lt;ConsentCategory&gt;**](ConsentCategory.md) | Categories after |  |
| **initiatedBy** | **kotlin.String** | Who initiated change (user/system/dsar) |  |
| **reason** | **kotlin.String** |  |  [optional] |
