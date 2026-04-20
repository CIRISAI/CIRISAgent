
# UserDetail

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **userId** | **kotlin.String** |  |  |
| **username** | **kotlin.String** |  |  |
| **authType** | **kotlin.String** | password, oauth, api_key |  |
| **apiRole** | [**APIRole**](APIRole.md) |  |  |
| **createdAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  |
| **permissions** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  |
| **waRole** | [**WARole**](WARole.md) |  |  [optional] |
| **waId** | **kotlin.String** |  |  [optional] |
| **oauthProvider** | **kotlin.String** |  |  [optional] |
| **oauthEmail** | **kotlin.String** |  |  [optional] |
| **oauthName** | **kotlin.String** |  |  [optional] |
| **oauthPicture** | **kotlin.String** |  |  [optional] |
| **permissionRequestedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **lastLogin** | [**kotlin.time.Instant**](kotlin.time.Instant.md) |  |  [optional] |
| **isActive** | **kotlin.Boolean** |  |  [optional] |
| **linkedOauthAccounts** | [**kotlin.collections.List&lt;LinkedOAuthAccount&gt;**](LinkedOAuthAccount.md) |  |  [optional] |
| **customPermissions** | **kotlin.collections.List&lt;kotlin.String&gt;** |  |  [optional] |
| **oauthExternalId** | **kotlin.String** |  |  [optional] |
| **waParentId** | **kotlin.String** |  |  [optional] |
| **waAutoMinted** | **kotlin.Boolean** |  |  [optional] |
| **apiKeysCount** | **kotlin.Int** |  |  [optional] |
