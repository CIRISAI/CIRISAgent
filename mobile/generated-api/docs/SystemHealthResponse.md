
# SystemHealthResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **status** | **kotlin.String** | Overall health status (healthy/degraded/critical) |  |
| **version** | **kotlin.String** | System version |  |
| **uptimeSeconds** | **kotlin.Double** | System uptime in seconds |  |
| **services** | **kotlin.collections.Map&lt;kotlin.String, kotlin.collections.Map&lt;kotlin.String, kotlin.Int&gt;&gt;** | Service health summary |  |
| **initializationComplete** | **kotlin.Boolean** | Whether system initialization is complete |  |
| **timestamp** | **kotlin.String** |  |  |
| **cognitiveState** | **kotlin.String** |  |  [optional] |
