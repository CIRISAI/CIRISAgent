
# ConfigurableAdapterInfo

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **adapterType** | **kotlin.String** | Type identifier for the adapter |  |
| **name** | **kotlin.String** | Human-readable name |  |
| **description** | **kotlin.String** | Description of the adapter |  |
| **workflowType** | **kotlin.String** | Type of configuration workflow |  |
| **stepCount** | **kotlin.Int** | Number of steps in the configuration workflow |  |
| **requiresOauth** | **kotlin.Boolean** | Whether this adapter requires OAuth authentication |  [optional] |
| **steps** | [**kotlin.collections.List&lt;ConfigStepInfo&gt;**](ConfigStepInfo.md) | Configuration steps |  [optional] |
