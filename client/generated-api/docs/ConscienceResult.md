
# ConscienceResult

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **conscienceName** | **kotlin.String** | Name of the conscience |  |
| **passed** | **kotlin.Boolean** | Whether the conscience check passed |  |
| **severity** | [**inline**](#Severity) | Severity level of the result |  |
| **message** | **kotlin.String** | Result message |  |
| **overrideAction** | **kotlin.String** |  |  [optional] |
| **details** | [**kotlin.collections.Map&lt;kotlin.String, ConscienceResultDetailsValue&gt;**](ConscienceResultDetailsValue.md) |  |  [optional] |


<a id="Severity"></a>
## Enum: severity
| Name | Value |
| ---- | ----- |
| severity | info, warning, error, critical |
