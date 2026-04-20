
# ConfigurationStatusResponse

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **sessionId** | **kotlin.String** | Session identifier |  |
| **adapterType** | **kotlin.String** | Adapter being configured |  |
| **status** | **kotlin.String** | Current session status |  |
| **currentStepIndex** | **kotlin.Int** | Index of current step |  |
| **totalSteps** | **kotlin.Int** | Total number of steps in workflow |  |
| **collectedConfig** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) | Configuration collected so far |  |
| **createdAt** | **kotlin.String** |  |  |
| **updatedAt** | **kotlin.String** |  |  |
| **currentStep** | [**ConfigurationStep**](ConfigurationStep.md) |  |  [optional] |
