
# AdapterConfig

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **id** | **kotlin.String** | Adapter ID (api, cli, discord, reddit) |  |
| **name** | **kotlin.String** | Display name |  |
| **description** | **kotlin.String** | Adapter description |  |
| **enabledByDefault** | **kotlin.Boolean** | Whether enabled by default |  [optional] |
| **requiredEnvVars** | **kotlin.collections.List&lt;kotlin.String&gt;** | Required environment variables |  [optional] |
| **optionalEnvVars** | **kotlin.collections.List&lt;kotlin.String&gt;** | Optional environment variables |  [optional] |
| **platformRequirements** | **kotlin.collections.List&lt;kotlin.String&gt;** | Platform requirements (e.g., &#39;android_play_integrity&#39;) |  [optional] |
| **platformAvailable** | **kotlin.Boolean** | Whether available on current platform |  [optional] |
