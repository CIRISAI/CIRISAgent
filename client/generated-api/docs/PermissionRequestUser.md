
# PermissionRequestUser

## Properties
| Name | Type | Description | Notes |
| ------------ | ------------- | ------------- | ------------- |
| **id** | **kotlin.String** | User ID |  |
| **role** | [**UserRole**](UserRole.md) | Current role |  |
| **permissionRequestedAt** | [**kotlin.time.Instant**](kotlin.time.Instant.md) | When permissions were requested |  |
| **hasSendMessages** | **kotlin.Boolean** | Whether user already has SEND_MESSAGES permission |  |
| **email** | **kotlin.String** |  |  [optional] |
| **oauthName** | **kotlin.String** |  |  [optional] |
| **oauthPicture** | **kotlin.String** |  |  [optional] |
