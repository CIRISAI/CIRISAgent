
# ReasoningTraceData

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **traceId** | **kotlin.String** | Unique trace ID |  |
| **startTime** | **kotlin.String** |  |  |
| **durationMs** | **kotlin.Double** | Total duration |  |
| **taskId** | **kotlin.String** |  |  [optional] |
| **taskDescription** | **kotlin.String** |  |  [optional] |
| **thoughtCount** | **kotlin.Int** | Number of thoughts |  [optional] |
| **decisionCount** | **kotlin.Int** | Number of decisions |  [optional] |
| **reasoningDepth** | **kotlin.Int** | Maximum reasoning depth |  [optional] |
| **thoughts** | [**kotlin.collections.List&lt;APIResponseThoughtStep&gt;**](APIResponseThoughtStep.md) | Thought steps |  [optional] |
| **outcome** | **kotlin.String** |  |  [optional] |
