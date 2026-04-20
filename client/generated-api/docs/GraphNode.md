
# GraphNode

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **id** | **kotlin.String** | Unique node identifier |  |
| **type** | [**NodeType**](NodeType.md) | Type of node |  |
| **scope** | [**GraphScope**](GraphScope.md) | Scope of the node |  |
| **attributes** | [**Attributes**](Attributes.md) |  |  |
| **version** | **kotlin.Int** | Version number |  [optional] |
| **updatedBy** | **kotlin.String** |  |  [optional] |
| **updatedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **consentStream** | [**ConsentStream**](ConsentStream.md) | Consent stream for this node (TEMPORARY&#x3D;14-day, PARTNERED&#x3D;persistent, ANONYMOUS&#x3D;stats-only) |  [optional] |
| **expiresAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
