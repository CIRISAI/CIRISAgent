
# ActionSelectionDMAResult

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **selectedAction** | [**HandlerActionType**](HandlerActionType.md) | The chosen handler action |  |
| **actionParameters** | [**ActionParameters**](ActionParameters.md) |  |  |
| **rationale** | **kotlin.String** | Reasoning for this action selection (REQUIRED) |  |
| **rawLlmResponse** | **kotlin.String** |  |  [optional] |
| **reasoning** | **kotlin.String** |  |  [optional] |
| **evaluationTimeMs** | **kotlin.Double** |  |  [optional] |
| **resourceUsage** | [**kotlin.collections.Map&lt;kotlin.String, ResponseGetSystemStatusV1TransparencyStatusGetValue&gt;**](ResponseGetSystemStatusV1TransparencyStatusGetValue.md) |  |  [optional] |
| **userPrompt** | **kotlin.String** |  |  [optional] |
