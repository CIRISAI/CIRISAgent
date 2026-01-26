
# ConfigurationStep

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **stepId** | **kotlin.String** | Unique identifier for this step |  |
| **stepType** | [**inline**](#StepType) | Type of configuration step |  |
| **title** | **kotlin.String** | Human-readable step title |  |
| **description** | **kotlin.String** | Description of what this step does |  |
| **discoveryMethod** | **kotlin.String** |  |  [optional] |
| **oauthConfig** | [**AdapterOAuthConfig**](AdapterOAuthConfig.md) |  |  [optional] |
| **optionsMethod** | **kotlin.String** |  |  [optional] |
| **multiple** | **kotlin.Boolean** | Whether multiple selections are allowed |  [optional] |
| **fields** | [**kotlin.collections.List&lt;ConfigurationFieldDefinition&gt;**](ConfigurationFieldDefinition.md) |  |  [optional] |
| **dynamicFields** | **kotlin.Boolean** | Whether fields are dynamically generated |  [optional] |
| **&#x60;field&#x60;** | **kotlin.String** |  |  [optional] |
| **fieldName** | **kotlin.String** |  |  [optional] |
| **inputType** | **kotlin.String** |  |  [optional] |
| **placeholder** | **kotlin.String** |  |  [optional] |
| **required** | **kotlin.Boolean** | Whether this step is required |  [optional] |
| **optional** | **kotlin.Boolean** | Whether this step/field is optional |  [optional] |
| **default** | [**AnyOfLessThanGreaterThan**](AnyOfLessThanGreaterThan.md) | Default value for the field |  [optional] |
| **validation** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) |  |  [optional] |
| **dependsOn** | [**DependsOn**](DependsOn.md) |  |  [optional] |
| **condition** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) |  |  [optional] |
| **action** | **kotlin.String** |  |  [optional] |


<a id="StepType"></a>
## Enum: step_type
| Name | Value |
| ---- | ----- |
| stepType | discovery, oauth, select, input, confirm |
