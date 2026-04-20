
# AuditEntryResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **id** | **kotlin.String** | Audit entry ID |  |
| **action** | **kotlin.String** | Action performed |  |
| **actor** | **kotlin.String** | Who performed the action |  |
| **timestamp** | **kotlin.String** |  |  |
| **context** | [**AuditContext**](AuditContext.md) | Action context |  |
| **signature** | **kotlin.String** |  |  [optional] |
| **hashChain** | **kotlin.String** |  |  [optional] |
| **storageSources** | **kotlin.collections.List&lt;kotlin.String&gt;** | Storage locations: graph, jsonl, sqlite |  [optional] |
