
# RuntimeControlResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **success** | **kotlin.Boolean** | Whether action succeeded |  |
| **message** | **kotlin.String** | Human-readable status message |  |
| **processorState** | **kotlin.String** | Current processor state |  |
| **cognitiveState** | **kotlin.String** |  |  [optional] |
| **queueDepth** | **kotlin.Int** | Number of items in processing queue |  [optional] |
| **currentStep** | **kotlin.String** |  |  [optional] |
| **currentStepSchema** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
| **pipelineState** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
