
# SetupCompleteRequest

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **llmProvider** | **kotlin.String** | LLM provider ID |  |
| **llmApiKey** | **kotlin.String** | LLM API key |  |
| **llmBaseUrl** | **kotlin.String** |  |  [optional] |
| **llmModel** | **kotlin.String** |  |  [optional] |
| **backupLlmApiKey** | **kotlin.String** |  |  [optional] |
| **backupLlmBaseUrl** | **kotlin.String** |  |  [optional] |
| **backupLlmModel** | **kotlin.String** |  |  [optional] |
| **templateId** | **kotlin.String** | Agent template ID |  [optional] |
| **enabledAdapters** | **kotlin.collections.List&lt;kotlin.String?&gt;** | List of enabled adapters |  [optional] |
| **adapterConfig** | [**kotlin.collections.Map&lt;kotlin.String, kotlin.Any&gt;**](kotlin.Any.md) | Adapter-specific configuration |  [optional] |
| **adminUsername** | **kotlin.String** | New user&#39;s username |  [optional] |
| **adminPassword** | **kotlin.String** |  |  [optional] |
| **systemAdminPassword** | **kotlin.String** |  |  [optional] |
| **oauthProvider** | **kotlin.String** |  |  [optional] |
| **oauthExternalId** | **kotlin.String** |  |  [optional] |
| **oauthEmail** | **kotlin.String** |  |  [optional] |
| **agentPort** | **kotlin.Int** | Agent API port |  [optional] |
