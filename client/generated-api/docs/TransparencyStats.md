
# TransparencyStats

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **periodStart** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | Start of reporting period |  |
| **periodEnd** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | End of reporting period |  |
| **totalInteractions** | **kotlin.Int** | Total interactions processed |  |
| **actionsTaken** | [**kotlin.collections.List&lt;ActionCount&gt;**](ActionCount.md) | Breakdown by action type |  |
| **deferralsToHuman** | **kotlin.Int** | Deferrals to human judgment |  |
| **deferralsUncertainty** | **kotlin.Int** | Deferrals due to uncertainty |  |
| **deferralsEthical** | **kotlin.Int** | Deferrals for ethical review |  |
| **harmfulRequestsBlocked** | **kotlin.Int** | Harmful requests rejected |  |
| **rateLimitTriggers** | **kotlin.Int** | Rate limit activations |  |
| **emergencyShutdowns** | **kotlin.Int** | Emergency shutdown attempts |  |
| **uptimePercentage** | **kotlin.Double** | System uptime % |  |
| **averageResponseMs** | **kotlin.Double** | Average response time |  |
| **activeAgents** | **kotlin.Int** | Number of active agents |  |
| **dataRequestsReceived** | **kotlin.Int** | DSAR requests received |  |
| **dataRequestsCompleted** | **kotlin.Int** | DSAR requests completed |  |
