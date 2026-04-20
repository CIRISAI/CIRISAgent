
# SystemOverview

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **uptimeSeconds** | **kotlin.Double** | System uptime |  |
| **cognitiveState** | **kotlin.String** | Current cognitive state |  |
| **messagesProcessed24h** | **kotlin.Int** | Messages in last 24 hours |  [optional] |
| **thoughtsProcessed24h** | **kotlin.Int** | Thoughts in last 24 hours |  [optional] |
| **tasksCompleted24h** | **kotlin.Int** | Tasks completed in last 24 hours |  [optional] |
| **errors24h** | **kotlin.Int** | Errors in last 24 hours |  [optional] |
| **tokensLastHour** | **kotlin.Double** | Total tokens in last hour |  [optional] |
| **costLastHourCents** | **kotlin.Double** | Total cost in last hour (cents) |  [optional] |
| **carbonLastHourGrams** | **kotlin.Double** | Total carbon in last hour (grams) |  [optional] |
| **energyLastHourKwh** | **kotlin.Double** | Total energy in last hour (kWh) |  [optional] |
| **tokens24h** | **kotlin.Double** | Total tokens in last 24 hours |  [optional] |
| **cost24hCents** | **kotlin.Double** | Total cost in last 24 hours (cents) |  [optional] |
| **carbon24hGrams** | **kotlin.Double** | Total carbon in last 24 hours (grams) |  [optional] |
| **energy24hKwh** | **kotlin.Double** | Total energy in last 24 hours (kWh) |  [optional] |
| **memoryMb** | **kotlin.Double** | Current memory usage |  [optional] |
| **cpuPercent** | **kotlin.Double** | Current CPU usage |  [optional] |
| **healthyServices** | **kotlin.Int** | Number of healthy services |  [optional] |
| **degradedServices** | **kotlin.Int** | Number of degraded services |  [optional] |
| **errorRatePercent** | **kotlin.Double** | System error rate |  [optional] |
| **currentTask** | **kotlin.String** |  |  [optional] |
| **reasoningDepth** | **kotlin.Int** | Current reasoning depth |  [optional] |
| **activeDeferrals** | **kotlin.Int** | Pending WA deferrals |  [optional] |
| **recentIncidents** | **kotlin.Int** | Incidents in last hour |  [optional] |
| **totalMetrics** | **kotlin.Int** | Total metrics collected |  [optional] |
| **activeServices** | **kotlin.Int** | Number of active services reporting telemetry |  [optional] |
| **metricsPerSecond** | **kotlin.Double** | Current metric ingestion rate |  [optional] |
| **cacheHitRate** | **kotlin.Double** | Telemetry cache hit rate |  [optional] |
