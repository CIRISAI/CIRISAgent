
# AgentStatus

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **agentId** | **kotlin.String** | Agent identifier |  |
| **name** | **kotlin.String** | Agent name |  |
| **version** | **kotlin.String** | CIRIS version (e.g., 1.0.4-beta) |  |
| **codename** | **kotlin.String** | Release codename |  |
| **cognitiveState** | **kotlin.String** | Current cognitive state |  |
| **uptimeSeconds** | **kotlin.Double** | Time since startup |  |
| **messagesProcessed** | **kotlin.Int** | Total messages processed |  |
| **servicesActive** | **kotlin.Int** | Number of active services |  |
| **memoryUsageMb** | **kotlin.Double** | Current memory usage in MB |  |
| **codeHash** | **kotlin.String** |  |  [optional] |
| **lastActivity** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **currentTask** | **kotlin.String** |  |  [optional] |
| **multiProviderServices** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
