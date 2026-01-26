
# AdapterOAuthConfig

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **providerName** | **kotlin.String** | OAuth provider name |  |
| **authorizationPath** | **kotlin.String** | OAuth authorization endpoint path |  [optional] |
| **tokenPath** | **kotlin.String** | OAuth token endpoint path |  [optional] |
| **clientIdSource** | [**inline**](#ClientIdSource) | Source of client ID (static value or IndieAuth discovery) |  [optional] |
| **scopes** | **kotlin.collections.List&lt;kotlin.String&gt;** | OAuth scopes to request |  [optional] |
| **pkceRequired** | **kotlin.Boolean** | Whether PKCE is required for this OAuth flow |  [optional] |


<a id="ClientIdSource"></a>
## Enum: client_id_source
| Name | Value |
| ---- | ----- |
| clientIdSource | static, indieauth |
