
# ThoughtInPipeline

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **thoughtId** | **kotlin.String** | Unique thought ID |  |
| **taskId** | **kotlin.String** | Source task ID |  |
| **thoughtType** | **kotlin.String** | Type of thought |  |
| **currentStep** | [**StepPoint**](StepPoint.md) | Current step point in pipeline |  |
| **enteredStepAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When thought entered current step |  |
| **lastCompletedStep** | [**StepPoint**](StepPoint.md) |  |  [optional] |
| **processingTimeMs** | **kotlin.Double** | Total processing time so far |  [optional] |
| **contextBuilt** | [**DMAContext**](DMAContext.md) |  |  [optional] |
| **ethicalDma** | [**EthicalDMAResult**](EthicalDMAResult.md) |  |  [optional] |
| **commonSenseDma** | [**CSDMAResult**](CSDMAResult.md) |  |  [optional] |
| **domainDma** | [**DSDMAResult**](DSDMAResult.md) |  |  [optional] |
| **aspdmaResult** | [**ActionSelectionDMAResult**](ActionSelectionDMAResult.md) |  |  [optional] |
| **conscienceResults** | [**kotlin.collections.List&lt;ConscienceResult&gt;**](ConscienceResult.md) |  |  [optional] |
| **selectedAction** | **kotlin.String** |  |  [optional] |
| **handlerResult** | [**HandlerResult**](HandlerResult.md) |  |  [optional] |
| **busOperations** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  [optional] |
| **isRecursive** | **kotlin.Boolean** | Whether in recursive ASPDMA |  [optional] |
| **recursionCount** | **kotlin.Int** | Number of ASPDMA recursions |  [optional] |
