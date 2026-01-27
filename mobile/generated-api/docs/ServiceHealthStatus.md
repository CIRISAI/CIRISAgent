
# ServiceHealthStatus

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **overallHealth** | **kotlin.String** | Overall health: healthy, degraded, unhealthy |  |
| **healthyServices** | **kotlin.Int** | Number of healthy services |  |
| **unhealthyServices** | **kotlin.Int** | Number of unhealthy services |  |
| **serviceDetails** | **kotlin.collections.Map&lt;kotlin.String, kotlin.collections.Map&lt;kotlin.String, ServiceDetailsValueValue&gt;&gt;** | Per-service health details |  |
| **timestamp** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **recommendations** | **kotlin.collections.List&lt;kotlin.String&gt;** | Health recommendations |  [optional] |
