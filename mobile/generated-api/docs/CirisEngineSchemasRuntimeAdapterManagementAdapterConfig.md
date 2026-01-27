
# CirisEngineSchemasRuntimeAdapterManagementAdapterConfig

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **adapterType** | **kotlin.String** | Type of adapter (cli, api, discord, etc.) |  |
| **enabled** | **kotlin.Boolean** | Whether adapter is enabled |  [optional] |
| **persist** | **kotlin.Boolean** | Whether to persist this adapter config for auto-load on restart. When True, the adapter will be automatically restored after agent restart. |  [optional] |
| **settings** | [**kotlin.collections.Map&lt;kotlin.String, SettingsValue&gt;**](SettingsValue.md) | Simple adapter settings (flat primitives only). Use adapter_config for complex nested configurations. |  [optional] |
| **adapterConfig** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) |  |  [optional] |
