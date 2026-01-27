
# RuntimeAdapterStatus

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **adapterId** | **kotlin.String** | Unique Adapter ID |  |
| **adapterType** | **kotlin.String** | Type of adapter |  |
| **isRunning** | **kotlin.Boolean** | Whether adapter is running |  |
| **loadedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **servicesRegistered** | **kotlin.collections.List&lt;kotlin.String&gt;** | Services registered by adapter |  [optional] |
| **configParams** | [**CirisEngineSchemasRuntimeAdapterManagementAdapterConfig**](CirisEngineSchemasRuntimeAdapterManagementAdapterConfig.md) |  |  [optional] |
| **metrics** | [**AdapterMetrics**](AdapterMetrics.md) |  |  [optional] |
| **lastActivity** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **tools** | [**kotlin.collections.List&lt;ToolInfo&gt;**](ToolInfo.md) |  |  [optional] |
