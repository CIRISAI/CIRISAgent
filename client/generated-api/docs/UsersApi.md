# UsersApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**changePasswordV1UsersUserIdPasswordPut**](UsersApi.md#changePasswordV1UsersUserIdPasswordPut) | **PUT** /v1/users/{user_id}/password | Change Password |
| [**checkWaKeyExistsV1UsersWaKeyCheckGet**](UsersApi.md#checkWaKeyExistsV1UsersWaKeyCheckGet) | **GET** /v1/users/wa/key-check | Check Wa Key Exists |
| [**createUserV1UsersPost**](UsersApi.md#createUserV1UsersPost) | **POST** /v1/users | Create User |
| [**deactivateUserV1UsersUserIdDelete**](UsersApi.md#deactivateUserV1UsersUserIdDelete) | **DELETE** /v1/users/{user_id} | Deactivate User |
| [**getMySettingsV1UsersMeSettingsGet**](UsersApi.md#getMySettingsV1UsersMeSettingsGet) | **GET** /v1/users/me/settings | Get My Settings |
| [**getPermissionRequestsV1UsersPermissionRequestsGet**](UsersApi.md#getPermissionRequestsV1UsersPermissionRequestsGet) | **GET** /v1/users/permission-requests | Get Permission Requests |
| [**getUserV1UsersUserIdGet**](UsersApi.md#getUserV1UsersUserIdGet) | **GET** /v1/users/{user_id} | Get User |
| [**linkOauthAccountV1UsersUserIdOauthLinksPost**](UsersApi.md#linkOauthAccountV1UsersUserIdOauthLinksPost) | **POST** /v1/users/{user_id}/oauth-links | Link Oauth Account |
| [**listUserApiKeysV1UsersUserIdApiKeysGet**](UsersApi.md#listUserApiKeysV1UsersUserIdApiKeysGet) | **GET** /v1/users/{user_id}/api-keys | List User Api Keys |
| [**listUsersV1UsersGet**](UsersApi.md#listUsersV1UsersGet) | **GET** /v1/users | List Users |
| [**mintWiseAuthorityV1UsersUserIdMintWaPost**](UsersApi.md#mintWiseAuthorityV1UsersUserIdMintWaPost) | **POST** /v1/users/{user_id}/mint-wa | Mint Wise Authority |
| [**requestPermissionsV1UsersRequestPermissionsPost**](UsersApi.md#requestPermissionsV1UsersRequestPermissionsPost) | **POST** /v1/users/request-permissions | Request Permissions |
| [**unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete**](UsersApi.md#unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete) | **DELETE** /v1/users/{user_id}/oauth-links/{provider}/{external_id} | Unlink Oauth Account |
| [**updateMySettingsV1UsersMeSettingsPut**](UsersApi.md#updateMySettingsV1UsersMeSettingsPut) | **PUT** /v1/users/me/settings | Update My Settings |
| [**updateUserPermissionsV1UsersUserIdPermissionsPut**](UsersApi.md#updateUserPermissionsV1UsersUserIdPermissionsPut) | **PUT** /v1/users/{user_id}/permissions | Update User Permissions |
| [**updateUserV1UsersUserIdPut**](UsersApi.md#updateUserV1UsersUserIdPut) | **PUT** /v1/users/{user_id} | Update User |


<a id="changePasswordV1UsersUserIdPasswordPut"></a>
# **changePasswordV1UsersUserIdPasswordPut**
> kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt; changePasswordV1UsersUserIdPasswordPut(userId, changePasswordRequest, authorization)

Change Password

Change user password.  Users can change their own password. SYSTEM_ADMIN can change any password without knowing current.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val changePasswordRequest : ChangePasswordRequest =  // ChangePasswordRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.collections.Map<kotlin.String, kotlin.String> = apiInstance.changePasswordV1UsersUserIdPasswordPut(userId, changePasswordRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#changePasswordV1UsersUserIdPasswordPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#changePasswordV1UsersUserIdPasswordPut")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| **changePasswordRequest** | [**ChangePasswordRequest**](ChangePasswordRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

**kotlin.collections.Map&lt;kotlin.String, kotlin.String&gt;**

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="checkWaKeyExistsV1UsersWaKeyCheckGet"></a>
# **checkWaKeyExistsV1UsersWaKeyCheckGet**
> WAKeyCheckResponse checkWaKeyExistsV1UsersWaKeyCheckGet(path, authorization)

Check Wa Key Exists

Check if a WA private key exists at the given filename.  Requires: wa.mint permission (SYSTEM_ADMIN only)  This is used by the UI to determine if auto-signing is available. Only checks files within ~/.ciris/wa_keys/ for security.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val path : kotlin.String = path_example // kotlin.String | Filename of private key to check
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : WAKeyCheckResponse = apiInstance.checkWaKeyExistsV1UsersWaKeyCheckGet(path, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#checkWaKeyExistsV1UsersWaKeyCheckGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#checkWaKeyExistsV1UsersWaKeyCheckGet")
    e.printStackTrace()
}
```

### Parameters
| **path** | **kotlin.String**| Filename of private key to check | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**WAKeyCheckResponse**](WAKeyCheckResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="createUserV1UsersPost"></a>
# **createUserV1UsersPost**
> UserDetail createUserV1UsersPost(createUserRequest, authorization)

Create User

Create a new user account.  Requires: users.write permission (SYSTEM_ADMIN only)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val createUserRequest : CreateUserRequest =  // CreateUserRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserDetail = apiInstance.createUserV1UsersPost(createUserRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#createUserV1UsersPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#createUserV1UsersPost")
    e.printStackTrace()
}
```

### Parameters
| **createUserRequest** | [**CreateUserRequest**](CreateUserRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserDetail**](UserDetail.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="deactivateUserV1UsersUserIdDelete"></a>
# **deactivateUserV1UsersUserIdDelete**
> DeactivateUserResponse deactivateUserV1UsersUserIdDelete(userId, authorization)

Deactivate User

Deactivate a user account.  Requires: users.delete permission (SYSTEM_ADMIN only)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : DeactivateUserResponse = apiInstance.deactivateUserV1UsersUserIdDelete(userId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#deactivateUserV1UsersUserIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#deactivateUserV1UsersUserIdDelete")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**DeactivateUserResponse**](DeactivateUserResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getMySettingsV1UsersMeSettingsGet"></a>
# **getMySettingsV1UsersMeSettingsGet**
> UserSettingsResponse getMySettingsV1UsersMeSettingsGet(authorization)

Get My Settings

Get the current user&#39;s personal settings.  Requires: Must be authenticated (any role)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserSettingsResponse = apiInstance.getMySettingsV1UsersMeSettingsGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#getMySettingsV1UsersMeSettingsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#getMySettingsV1UsersMeSettingsGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserSettingsResponse**](UserSettingsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getPermissionRequestsV1UsersPermissionRequestsGet"></a>
# **getPermissionRequestsV1UsersPermissionRequestsGet**
> kotlin.collections.List&lt;PermissionRequestUser&gt; getPermissionRequestsV1UsersPermissionRequestsGet(includeGranted, authorization)

Get Permission Requests

Get list of users who have requested permissions.  Requires: ADMIN role or higher

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val includeGranted : kotlin.Boolean = true // kotlin.Boolean | Include users who already have permissions
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.collections.List<PermissionRequestUser> = apiInstance.getPermissionRequestsV1UsersPermissionRequestsGet(includeGranted, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#getPermissionRequestsV1UsersPermissionRequestsGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#getPermissionRequestsV1UsersPermissionRequestsGet")
    e.printStackTrace()
}
```

### Parameters
| **includeGranted** | **kotlin.Boolean**| Include users who already have permissions | [optional] [default to false] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**kotlin.collections.List&lt;PermissionRequestUser&gt;**](PermissionRequestUser.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getUserV1UsersUserIdGet"></a>
# **getUserV1UsersUserIdGet**
> UserDetail getUserV1UsersUserIdGet(userId, authorization)

Get User

Get detailed information about a specific user.  Requires: users.read permission (ADMIN or higher)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserDetail = apiInstance.getUserV1UsersUserIdGet(userId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#getUserV1UsersUserIdGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#getUserV1UsersUserIdGet")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserDetail**](UserDetail.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="linkOauthAccountV1UsersUserIdOauthLinksPost"></a>
# **linkOauthAccountV1UsersUserIdOauthLinksPost**
> UserDetail linkOauthAccountV1UsersUserIdOauthLinksPost(userId, linkOAuthAccountRequest, authorization)

Link Oauth Account

Link an OAuth identity to an existing user.  Users can link accounts to themselves without special permissions. Only SYSTEM_ADMIN can link accounts to other users.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val linkOAuthAccountRequest : LinkOAuthAccountRequest =  // LinkOAuthAccountRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserDetail = apiInstance.linkOauthAccountV1UsersUserIdOauthLinksPost(userId, linkOAuthAccountRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#linkOauthAccountV1UsersUserIdOauthLinksPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#linkOauthAccountV1UsersUserIdOauthLinksPost")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| **linkOAuthAccountRequest** | [**LinkOAuthAccountRequest**](LinkOAuthAccountRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserDetail**](UserDetail.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="listUserApiKeysV1UsersUserIdApiKeysGet"></a>
# **listUserApiKeysV1UsersUserIdApiKeysGet**
> kotlin.collections.List&lt;APIKeyInfo&gt; listUserApiKeysV1UsersUserIdApiKeysGet(userId, authorization)

List User Api Keys

List API keys for a user.  Users can view their own keys. ADMIN+ can view any user&#39;s keys.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : kotlin.collections.List<APIKeyInfo> = apiInstance.listUserApiKeysV1UsersUserIdApiKeysGet(userId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#listUserApiKeysV1UsersUserIdApiKeysGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#listUserApiKeysV1UsersUserIdApiKeysGet")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**kotlin.collections.List&lt;APIKeyInfo&gt;**](APIKeyInfo.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listUsersV1UsersGet"></a>
# **listUsersV1UsersGet**
> PaginatedResponseUserSummary listUsersV1UsersGet(page, pageSize, search, authType, apiRole, waRole, isActive, authorization)

List Users

List all users with optional filtering.  Requires: users.read permission (ADMIN or higher)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val page : kotlin.Int = 56 // kotlin.Int |
val pageSize : kotlin.Int = 56 // kotlin.Int |
val search : kotlin.String = search_example // kotlin.String |
val authType : kotlin.String = authType_example // kotlin.String |
val apiRole : APIRole =  // APIRole |
val waRole : WARole =  // WARole |
val isActive : kotlin.Boolean = true // kotlin.Boolean |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : PaginatedResponseUserSummary = apiInstance.listUsersV1UsersGet(page, pageSize, search, authType, apiRole, waRole, isActive, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#listUsersV1UsersGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#listUsersV1UsersGet")
    e.printStackTrace()
}
```

### Parameters
| **page** | **kotlin.Int**|  | [optional] [default to 1] |
| **pageSize** | **kotlin.Int**|  | [optional] [default to 20] |
| **search** | **kotlin.String**|  | [optional] |
| **authType** | **kotlin.String**|  | [optional] |
| **apiRole** | [**APIRole**](.md)|  | [optional] [enum: OBSERVER, ADMIN, AUTHORITY, SYSTEM_ADMIN, SERVICE_ACCOUNT] |
| **waRole** | [**WARole**](.md)|  | [optional] [enum: root, authority, observer] |
| **isActive** | **kotlin.Boolean**|  | [optional] |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**PaginatedResponseUserSummary**](PaginatedResponseUserSummary.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="mintWiseAuthorityV1UsersUserIdMintWaPost"></a>
# **mintWiseAuthorityV1UsersUserIdMintWaPost**
> UserDetail mintWiseAuthorityV1UsersUserIdMintWaPost(userId, mintWARequest, authorization)

Mint Wise Authority

Mint a user as a Wise Authority.  Requires: ADMIN role or higher and valid Ed25519 signature from ROOT private key.  The signature should be over the message: \&quot;MINT_WA:{user_id}:{wa_role}:{timestamp}\&quot;  If no signature is provided and private_key_path is specified, will attempt to sign automatically using the key at that path.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val mintWARequest : MintWARequest =  // MintWARequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserDetail = apiInstance.mintWiseAuthorityV1UsersUserIdMintWaPost(userId, mintWARequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#mintWiseAuthorityV1UsersUserIdMintWaPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#mintWiseAuthorityV1UsersUserIdMintWaPost")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| **mintWARequest** | [**MintWARequest**](MintWARequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserDetail**](UserDetail.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="requestPermissionsV1UsersRequestPermissionsPost"></a>
# **requestPermissionsV1UsersRequestPermissionsPost**
> PermissionRequestResponse requestPermissionsV1UsersRequestPermissionsPost(authorization)

Request Permissions

Request communication permissions for the current user.  Requires: Must be authenticated (any role)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : PermissionRequestResponse = apiInstance.requestPermissionsV1UsersRequestPermissionsPost(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#requestPermissionsV1UsersRequestPermissionsPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#requestPermissionsV1UsersRequestPermissionsPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**PermissionRequestResponse**](PermissionRequestResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete"></a>
# **unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete**
> UserDetail unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete(userId, provider, externalId, authorization)

Unlink Oauth Account

Remove a linked OAuth identity from a user.  Users can unlink accounts from themselves without special permissions. Only SYSTEM_ADMIN can unlink accounts from other users.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val provider : kotlin.String = provider_example // kotlin.String |
val externalId : kotlin.String = externalId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserDetail = apiInstance.unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete(userId, provider, externalId, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#unlinkOauthAccountV1UsersUserIdOauthLinksProviderExternalIdDelete")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| **provider** | **kotlin.String**|  | |
| **externalId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserDetail**](UserDetail.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="updateMySettingsV1UsersMeSettingsPut"></a>
# **updateMySettingsV1UsersMeSettingsPut**
> UserSettingsResponse updateMySettingsV1UsersMeSettingsPut(updateUserSettingsRequest, authorization)

Update My Settings

Update the current user&#39;s personal settings.  Requires: Must be authenticated (any role)  Note: This endpoint bypasses the MANAGED_USER_ATTRIBUTES protection because users are allowed to modify their own settings.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val updateUserSettingsRequest : UpdateUserSettingsRequest =  // UpdateUserSettingsRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserSettingsResponse = apiInstance.updateMySettingsV1UsersMeSettingsPut(updateUserSettingsRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#updateMySettingsV1UsersMeSettingsPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#updateMySettingsV1UsersMeSettingsPut")
    e.printStackTrace()
}
```

### Parameters
| **updateUserSettingsRequest** | [**UpdateUserSettingsRequest**](UpdateUserSettingsRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserSettingsResponse**](UserSettingsResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="updateUserPermissionsV1UsersUserIdPermissionsPut"></a>
# **updateUserPermissionsV1UsersUserIdPermissionsPut**
> UserDetail updateUserPermissionsV1UsersUserIdPermissionsPut(userId, updatePermissionsRequest, authorization)

Update User Permissions

Update user&#39;s custom permissions.  Requires: users.permissions permission (AUTHORITY or higher)  This allows granting specific permissions to users beyond their role defaults. For example, granting SEND_MESSAGES permission to an OBSERVER.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val updatePermissionsRequest : UpdatePermissionsRequest =  // UpdatePermissionsRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserDetail = apiInstance.updateUserPermissionsV1UsersUserIdPermissionsPut(userId, updatePermissionsRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#updateUserPermissionsV1UsersUserIdPermissionsPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#updateUserPermissionsV1UsersUserIdPermissionsPut")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| **updatePermissionsRequest** | [**UpdatePermissionsRequest**](UpdatePermissionsRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserDetail**](UserDetail.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="updateUserV1UsersUserIdPut"></a>
# **updateUserV1UsersUserIdPut**
> UserDetail updateUserV1UsersUserIdPut(userId, updateUserRequest, authorization)

Update User

Update user information (role, active status).  Requires: users.write permission (SYSTEM_ADMIN only)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = UsersApi()
val userId : kotlin.String = userId_example // kotlin.String |
val updateUserRequest : UpdateUserRequest =  // UpdateUserRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserDetail = apiInstance.updateUserV1UsersUserIdPut(userId, updateUserRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling UsersApi#updateUserV1UsersUserIdPut")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling UsersApi#updateUserV1UsersUserIdPut")
    e.printStackTrace()
}
```

### Parameters
| **userId** | **kotlin.String**|  | |
| **updateUserRequest** | [**UpdateUserRequest**](UpdateUserRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserDetail**](UserDetail.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
