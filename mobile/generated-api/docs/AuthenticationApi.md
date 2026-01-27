# AuthenticationApi

All URIs are relative to *http://localhost*

| Method | HTTP request | Description |
| ------------- | ------------- | ------------- |
| [**configureOauthProviderV1AuthOauthProvidersPost**](AuthenticationApi.md#configureOauthProviderV1AuthOauthProvidersPost) | **POST** /v1/auth/oauth/providers | Configure Oauth Provider |
| [**createApiKeyV1AuthApiKeysPost**](AuthenticationApi.md#createApiKeyV1AuthApiKeysPost) | **POST** /v1/auth/api-keys | Create Api Key |
| [**deleteApiKeyV1AuthApiKeysKeyIdDelete**](AuthenticationApi.md#deleteApiKeyV1AuthApiKeysKeyIdDelete) | **DELETE** /v1/auth/api-keys/{key_id} | Delete Api Key |
| [**getCurrentUserV1AuthMeGet**](AuthenticationApi.md#getCurrentUserV1AuthMeGet) | **GET** /v1/auth/me | Get Current User |
| [**listApiKeysV1AuthApiKeysGet**](AuthenticationApi.md#listApiKeysV1AuthApiKeysGet) | **GET** /v1/auth/api-keys | List Api Keys |
| [**listOauthProvidersV1AuthOauthProvidersGet**](AuthenticationApi.md#listOauthProvidersV1AuthOauthProvidersGet) | **GET** /v1/auth/oauth/providers | List Oauth Providers |
| [**loginV1AuthLoginPost**](AuthenticationApi.md#loginV1AuthLoginPost) | **POST** /v1/auth/login | Login |
| [**logoutV1AuthLogoutPost**](AuthenticationApi.md#logoutV1AuthLogoutPost) | **POST** /v1/auth/logout | Logout |
| [**nativeGoogleTokenExchangeV1AuthNativeGooglePost**](AuthenticationApi.md#nativeGoogleTokenExchangeV1AuthNativeGooglePost) | **POST** /v1/auth/native/google | Native Google Token Exchange |
| [**oauthCallbackV1AuthOauthProviderCallbackGet**](AuthenticationApi.md#oauthCallbackV1AuthOauthProviderCallbackGet) | **GET** /v1/auth/oauth/{provider}/callback | Oauth Callback |
| [**oauthLoginV1AuthOauthProviderLoginGet**](AuthenticationApi.md#oauthLoginV1AuthOauthProviderLoginGet) | **GET** /v1/auth/oauth/{provider}/login | Oauth Login |
| [**refreshTokenV1AuthRefreshPost**](AuthenticationApi.md#refreshTokenV1AuthRefreshPost) | **POST** /v1/auth/refresh | Refresh Token |


<a id="configureOauthProviderV1AuthOauthProvidersPost"></a>
# **configureOauthProviderV1AuthOauthProvidersPost**
> ConfigureOAuthProviderResponse configureOauthProviderV1AuthOauthProvidersPost(configureOAuthProviderRequest, authorization)

Configure Oauth Provider

Configure an OAuth provider.  Requires: users.write permission (SYSTEM_ADMIN only)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val configureOAuthProviderRequest : ConfigureOAuthProviderRequest =  // ConfigureOAuthProviderRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : ConfigureOAuthProviderResponse = apiInstance.configureOauthProviderV1AuthOauthProvidersPost(configureOAuthProviderRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#configureOauthProviderV1AuthOauthProvidersPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#configureOauthProviderV1AuthOauthProvidersPost")
    e.printStackTrace()
}
```

### Parameters
| **configureOAuthProviderRequest** | [**ConfigureOAuthProviderRequest**](ConfigureOAuthProviderRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**ConfigureOAuthProviderResponse**](ConfigureOAuthProviderResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="createApiKeyV1AuthApiKeysPost"></a>
# **createApiKeyV1AuthApiKeysPost**
> APIKeyResponse createApiKeyV1AuthApiKeysPost(apIKeyCreateRequest, authorization)

Create Api Key

Create a new API key for the authenticated user.  Users can create API keys for their OAuth identity with configurable expiry (30min - 7 days). The key is only shown once and cannot be retrieved later.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val apIKeyCreateRequest : APIKeyCreateRequest =  // APIKeyCreateRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : APIKeyResponse = apiInstance.createApiKeyV1AuthApiKeysPost(apIKeyCreateRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#createApiKeyV1AuthApiKeysPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#createApiKeyV1AuthApiKeysPost")
    e.printStackTrace()
}
```

### Parameters
| **apIKeyCreateRequest** | [**APIKeyCreateRequest**](APIKeyCreateRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**APIKeyResponse**](APIKeyResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="deleteApiKeyV1AuthApiKeysKeyIdDelete"></a>
# **deleteApiKeyV1AuthApiKeysKeyIdDelete**
> deleteApiKeyV1AuthApiKeysKeyIdDelete(keyId, authorization)

Delete Api Key

Delete an API key.  Users can only delete their own API keys.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val keyId : kotlin.String = keyId_example // kotlin.String |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    apiInstance.deleteApiKeyV1AuthApiKeysKeyIdDelete(keyId, authorization)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#deleteApiKeyV1AuthApiKeysKeyIdDelete")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#deleteApiKeyV1AuthApiKeysKeyIdDelete")
    e.printStackTrace()
}
```

### Parameters
| **keyId** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

null (empty response body)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="getCurrentUserV1AuthMeGet"></a>
# **getCurrentUserV1AuthMeGet**
> UserInfo getCurrentUserV1AuthMeGet(authorization)

Get Current User

Get current authenticated user information.  Returns details about the currently authenticated user including their role and all permissions based on that role.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : UserInfo = apiInstance.getCurrentUserV1AuthMeGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#getCurrentUserV1AuthMeGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#getCurrentUserV1AuthMeGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**UserInfo**](UserInfo.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listApiKeysV1AuthApiKeysGet"></a>
# **listApiKeysV1AuthApiKeysGet**
> APIKeyListResponse listApiKeysV1AuthApiKeysGet(authorization)

List Api Keys

List all API keys for the authenticated user.  Returns information about all API keys created by the user (excluding the actual key values).

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : APIKeyListResponse = apiInstance.listApiKeysV1AuthApiKeysGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#listApiKeysV1AuthApiKeysGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#listApiKeysV1AuthApiKeysGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**APIKeyListResponse**](APIKeyListResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="listOauthProvidersV1AuthOauthProvidersGet"></a>
# **listOauthProvidersV1AuthOauthProvidersGet**
> OAuthProvidersResponse listOauthProvidersV1AuthOauthProvidersGet(authorization)

List Oauth Providers

List configured OAuth providers.  Requires: users.write permission (SYSTEM_ADMIN only)

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : OAuthProvidersResponse = apiInstance.listOauthProvidersV1AuthOauthProvidersGet(authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#listOauthProvidersV1AuthOauthProvidersGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#listOauthProvidersV1AuthOauthProvidersGet")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**OAuthProvidersResponse**](OAuthProvidersResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="loginV1AuthLoginPost"></a>
# **loginV1AuthLoginPost**
> LoginResponse loginV1AuthLoginPost(loginRequest)

Login

Authenticate with username/password.  Currently supports system admin user only. In production, this would integrate with a proper user database.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val loginRequest : LoginRequest =  // LoginRequest |
try {
    val result : LoginResponse = apiInstance.loginV1AuthLoginPost(loginRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#loginV1AuthLoginPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#loginV1AuthLoginPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **loginRequest** | [**LoginRequest**](LoginRequest.md)|  | |

### Return type

[**LoginResponse**](LoginResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="logoutV1AuthLogoutPost"></a>
# **logoutV1AuthLogoutPost**
> logoutV1AuthLogoutPost(authorization)

Logout

End the current session by revoking the API key.  This endpoint invalidates the current authentication token, effectively logging out the user.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    apiInstance.logoutV1AuthLogoutPost(authorization)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#logoutV1AuthLogoutPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#logoutV1AuthLogoutPost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

null (empty response body)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="nativeGoogleTokenExchangeV1AuthNativeGooglePost"></a>
# **nativeGoogleTokenExchangeV1AuthNativeGooglePost**
> NativeTokenResponse nativeGoogleTokenExchangeV1AuthNativeGooglePost(nativeTokenRequest)

Native Google Token Exchange

Exchange a native Google ID token for a CIRIS API token.  This endpoint is used by native Android/iOS apps that perform Google Sign-In directly and need to exchange their Google ID token for a CIRIS API token.  Unlike the web OAuth flow (which uses authorization codes), native apps get ID tokens directly from Google Sign-In SDK and send them here.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val nativeTokenRequest : NativeTokenRequest =  // NativeTokenRequest |
try {
    val result : NativeTokenResponse = apiInstance.nativeGoogleTokenExchangeV1AuthNativeGooglePost(nativeTokenRequest)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#nativeGoogleTokenExchangeV1AuthNativeGooglePost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#nativeGoogleTokenExchangeV1AuthNativeGooglePost")
    e.printStackTrace()
}
```

### Parameters
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **nativeTokenRequest** | [**NativeTokenRequest**](NativeTokenRequest.md)|  | |

### Return type

[**NativeTokenResponse**](NativeTokenResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json

<a id="oauthCallbackV1AuthOauthProviderCallbackGet"></a>
# **oauthCallbackV1AuthOauthProviderCallbackGet**
> kotlin.Any oauthCallbackV1AuthOauthProviderCallbackGet(provider, code, state, marketingOptIn)

Oauth Callback

Handle OAuth callback.  Exchanges authorization code for tokens and creates/updates user. Extracts marketing_opt_in from redirect_uri if present.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val provider : kotlin.String = provider_example // kotlin.String |
val code : kotlin.String = code_example // kotlin.String |
val state : kotlin.String = state_example // kotlin.String |
val marketingOptIn : kotlin.Boolean = true // kotlin.Boolean |
try {
    val result : kotlin.Any = apiInstance.oauthCallbackV1AuthOauthProviderCallbackGet(provider, code, state, marketingOptIn)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#oauthCallbackV1AuthOauthProviderCallbackGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#oauthCallbackV1AuthOauthProviderCallbackGet")
    e.printStackTrace()
}
```

### Parameters
| **provider** | **kotlin.String**|  | |
| **code** | **kotlin.String**|  | |
| **state** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **marketingOptIn** | **kotlin.Boolean**|  | [optional] [default to false] |

### Return type

[**kotlin.Any**](kotlin.Any.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="oauthLoginV1AuthOauthProviderLoginGet"></a>
# **oauthLoginV1AuthOauthProviderLoginGet**
> kotlin.Any oauthLoginV1AuthOauthProviderLoginGet(provider, redirectUri)

Oauth Login

Initiate OAuth login flow.  Redirects to the OAuth provider&#39;s authorization URL. Accepts optional redirect_uri to specify where to send tokens after OAuth.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val provider : kotlin.String = provider_example // kotlin.String |
val redirectUri : kotlin.String = redirectUri_example // kotlin.String |
try {
    val result : kotlin.Any = apiInstance.oauthLoginV1AuthOauthProviderLoginGet(provider, redirectUri)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#oauthLoginV1AuthOauthProviderLoginGet")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#oauthLoginV1AuthOauthProviderLoginGet")
    e.printStackTrace()
}
```

### Parameters
| **provider** | **kotlin.String**|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **redirectUri** | **kotlin.String**|  | [optional] |

### Return type

[**kotlin.Any**](kotlin.Any.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: Not defined
 - **Accept**: application/json

<a id="refreshTokenV1AuthRefreshPost"></a>
# **refreshTokenV1AuthRefreshPost**
> LoginResponse refreshTokenV1AuthRefreshPost(tokenRefreshRequest, authorization)

Refresh Token

Refresh access token.  Creates a new access token and revokes the old one. Supports both API key and OAuth refresh flows. The user must be authenticated to refresh their token.

### Example
```kotlin
// Import classes:
//import ai.ciris.api.infrastructure.*
//import ai.ciris.api.models.*

val apiInstance = AuthenticationApi()
val tokenRefreshRequest : TokenRefreshRequest =  // TokenRefreshRequest |
val authorization : kotlin.String = authorization_example // kotlin.String |
try {
    val result : LoginResponse = apiInstance.refreshTokenV1AuthRefreshPost(tokenRefreshRequest, authorization)
    println(result)
} catch (e: ClientException) {
    println("4xx response calling AuthenticationApi#refreshTokenV1AuthRefreshPost")
    e.printStackTrace()
} catch (e: ServerException) {
    println("5xx response calling AuthenticationApi#refreshTokenV1AuthRefreshPost")
    e.printStackTrace()
}
```

### Parameters
| **tokenRefreshRequest** | [**TokenRefreshRequest**](TokenRefreshRequest.md)|  | |
| Name | Type | Description  | Notes |
| ------------- | ------------- | ------------- | ------------- |
| **authorization** | **kotlin.String**|  | [optional] |

### Return type

[**LoginResponse**](LoginResponse.md)

### Authorization

No authorization required

### HTTP request headers

 - **Content-Type**: application/json
 - **Accept**: application/json
