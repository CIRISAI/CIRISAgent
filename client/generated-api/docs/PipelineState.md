
# PipelineState

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **isPaused** | **kotlin.Boolean** | Whether pipeline is paused |  [optional] |
| **currentRound** | **kotlin.Int** | Current processing round |  [optional] |
| **thoughtsByStep** | **kotlin.collections.Map&lt;kotlin.String, kotlin.collections.List&lt;ThoughtInPipeline&gt;&gt;** | Thoughts grouped by their current step point |  [optional] |
| **taskQueue** | [**kotlin.collections.List&lt;QueuedTask&gt;**](QueuedTask.md) | Tasks waiting to generate thoughts |  [optional] |
| **thoughtQueue** | [**kotlin.collections.List&lt;QueuedThought&gt;**](QueuedThought.md) | Thoughts waiting to enter pipeline |  [optional] |
| **totalThoughtsProcessed** | **kotlin.Int** | Total thoughts processed |  [optional] |
| **totalThoughtsInFlight** | **kotlin.Int** | Thoughts currently in pipeline |  [optional] |
