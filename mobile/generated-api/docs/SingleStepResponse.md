
# SingleStepResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **success** | **kotlin.Boolean** | Whether action succeeded |  |
| **message** | **kotlin.String** | Human-readable status message |  |
| **processorState** | **kotlin.String** | Current processor state |  |
| **cognitiveState** | **kotlin.String** |  |  [optional] |
| **queueDepth** | **kotlin.Int** | Number of items in processing queue |  [optional] |
| **stepPoint** | [**StepPoint**](StepPoint.md) |  |  [optional] |
| **stepResult** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
| **pipelineState** | [**PipelineState**](PipelineState.md) |  |  [optional] |
| **processingTimeMs** | **kotlin.Double** | Total processing time for this step in milliseconds |  [optional] |
| **tokensUsed** | **kotlin.Int** |  |  [optional] |
| **transparencyData** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
