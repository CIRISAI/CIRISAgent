
# DMADecision

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **dmaType** | **kotlin.String** | Type of DMA: PDMA, CSDMA, DSDMA, ActionSelection |  |
| **decision** | **kotlin.String** | The decision: approve, reject, defer, etc. |  |
| **reasoning** | **kotlin.String** | Explanation of the decision |  |
| **timestamp** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | Decision timestamp |  |
| **factorsConsidered** | **kotlin.collections.List&lt;kotlin.String&gt;** | Factors in decision |  [optional] |
| **alternativesEvaluated** | **kotlin.collections.List&lt;kotlin.String&gt;** | Alternatives considered |  [optional] |
