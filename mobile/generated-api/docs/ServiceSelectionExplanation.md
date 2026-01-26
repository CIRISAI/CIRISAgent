
# ServiceSelectionExplanation

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **overview** | **kotlin.String** | Overview of selection logic |  |
| **priorityGroups** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | Priority group explanations |  |
| **selectionStrategies** | **kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;** | Strategy explanations |  |
| **examples** | **kotlin.collections.List&lt;kotlin.collections.Map&lt;kotlin.String, ServiceSelectionExplanationPrioritiesValueValue&gt;?&gt;** | Example scenarios |  |
| **configurationTips** | **kotlin.collections.List&lt;kotlin.String&gt;** | Configuration recommendations |  |
| **priorities** | **kotlin.collections.Map&lt;kotlin.String, kotlin.collections.Map&lt;kotlin.String, ServiceSelectionExplanationPrioritiesValueValue&gt;&gt;** |  |  [optional] |
| **selectionFlow** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  [optional] |
| **circuitBreakerInfo** | [**kotlin.collections.Map&lt;kotlin.String, ServiceSelectionExplanationPrioritiesValueValue&gt;**](ServiceSelectionExplanationPrioritiesValueValue.md) |  |  [optional] |
