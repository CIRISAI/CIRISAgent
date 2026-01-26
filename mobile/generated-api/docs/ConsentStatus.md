
# ConsentStatus

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **userId** | **kotlin.String** | User identifier |  |
| **stream** | [**ConsentStream**](ConsentStream.md) | Current consent stream |  |
| **categories** | [**kotlin.collections.List&lt;ConsentCategory&gt;**](ConsentCategory.md) | What they consented to |  |
| **grantedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When consent was granted |  |
| **lastModified** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | Last modification time |  |
| **expiresAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **impactScore** | **kotlin.Double** | Contribution to collective learning |  [optional] |
| **attributionCount** | **kotlin.Int** | Number of patterns attributed |  [optional] |
