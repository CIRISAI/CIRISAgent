
# ResourceUsageResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **currentUsage** | [**ResourceSnapshot**](ResourceSnapshot.md) | Current resource usage |  |
| **limits** | [**ResourceBudget**](ResourceBudget.md) | Configured resource limits |  |
| **healthStatus** | **kotlin.String** | Resource health (healthy/warning/critical) |  |
| **warnings** | **kotlin.collections.List&lt;kotlin.String&gt;** | Resource warnings |  [optional] |
| **critical** | **kotlin.collections.List&lt;kotlin.String&gt;** | Critical resource issues |  [optional] |
