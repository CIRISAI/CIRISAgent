
# StepExecutionResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **stepId** | **kotlin.String** | ID of the executed step |  |
| **success** | **kotlin.Boolean** | Whether step execution succeeded |  |
| **&#x60;data&#x60;** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) | Data returned by the step |  [optional] |
| **nextStepIndex** | **kotlin.Int** |  |  [optional] |
| **error** | **kotlin.String** |  |  [optional] |
| **awaitingCallback** | **kotlin.Boolean** | Whether step is waiting for external callback |  [optional] |
