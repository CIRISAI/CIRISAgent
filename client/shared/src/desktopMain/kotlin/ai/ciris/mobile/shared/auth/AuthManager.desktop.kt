package ai.ciris.mobile.shared.auth

import ai.ciris.mobile.shared.models.AuthState
import ai.ciris.mobile.shared.models.AuthResponse
import ai.ciris.mobile.shared.models.TokenData
import ai.ciris.mobile.shared.models.UserInfo
import ai.ciris.mobile.shared.platform.createSecureStorage
import io.ktor.client.*
import io.ktor.client.engine.cio.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.json.Json

actual class AuthManager {
    private val _authState = MutableStateFlow<AuthState>(AuthState.Unauthenticated)
    actual val authState: StateFlow<AuthState> = _authState.asStateFlow()

    private val secureStorage = createSecureStorage()
    private val httpClient = HttpClient(CIO)
    private val json = Json { ignoreUnknownKeys = true }

    private var cachedToken: String? = null
    private var cachedUser: UserInfo? = null

    actual fun initialize() {
        // Load cached token on init
        kotlinx.coroutines.runBlocking {
            cachedToken = secureStorage.getAccessToken().getOrNull()
            _authState.value = if (cachedToken != null) {
                // Create a placeholder user - will be updated on next API call
                val placeholderUser = UserInfo(
                    user_id = "desktop_user",
                    email = "desktop@local",
                    role = "ADMIN"
                )
                AuthState.Authenticated(cachedToken!!, placeholderUser)
            } else {
                AuthState.Unauthenticated
            }
        }
    }

    actual suspend fun login(
        username: String,
        password: String,
        serverUrl: String
    ): Result<AuthResponse> = runCatching {
        val response = httpClient.post("$serverUrl/v1/auth/login") {
            contentType(ContentType.Application.Json)
            setBody("""{"username":"$username","password":"$password"}""")
        }

        if (response.status != HttpStatusCode.OK) {
            throw Exception("Login failed: ${response.status}")
        }

        val body = response.bodyAsText()
        val authResponse = json.decodeFromString<AuthResponse>(body)

        cachedToken = authResponse.access_token
        cachedUser = authResponse.user
        secureStorage.saveAccessToken(authResponse.access_token)
        _authState.value = AuthState.Authenticated(authResponse.access_token, authResponse.user)

        authResponse
    }

    actual suspend fun loginWithGoogle(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> {
        // Desktop doesn't support Google sign-in natively
        return Result.failure(UnsupportedOperationException("Google sign-in not available on desktop"))
    }

    actual suspend fun loginWithApple(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> {
        // Desktop doesn't support Apple sign-in
        return Result.failure(UnsupportedOperationException("Apple sign-in not available on desktop"))
    }

    actual suspend fun loginWithNativeAuth(
        idToken: String,
        userId: String?,
        provider: String,
        serverUrl: String
    ): Result<AuthResponse> {
        return Result.failure(UnsupportedOperationException("Native auth not available on desktop"))
    }

    actual suspend fun logout(): Result<Unit> = runCatching {
        cachedToken = null
        secureStorage.deleteAccessToken()
        _authState.value = AuthState.Unauthenticated
    }

    actual suspend fun refreshToken(serverUrl: String): Result<AuthResponse> {
        // Desktop uses simple token storage, no refresh mechanism
        return Result.failure(UnsupportedOperationException("Token refresh not implemented for desktop"))
    }

    actual suspend fun getAccessToken(): String? {
        return cachedToken ?: secureStorage.getAccessToken().getOrNull()
    }

    actual suspend fun saveAccessToken(tokenData: TokenData): Result<Unit> = runCatching {
        cachedToken = tokenData.accessToken
        secureStorage.saveAccessToken(tokenData.accessToken)
        // Create a placeholder user for token-only save
        val user = cachedUser ?: UserInfo(
            user_id = "desktop_user",
            email = "desktop@local",
            role = "ADMIN"
        )
        _authState.value = AuthState.Authenticated(tokenData.accessToken, user)
    }

    actual suspend fun deleteAccessToken(): Result<Unit> = runCatching {
        cachedToken = null
        secureStorage.deleteAccessToken()
        _authState.value = AuthState.Unauthenticated
    }

    actual suspend fun getUserRole(): String? {
        // Would need to decode JWT or query API
        return null
    }

    actual suspend fun isAuthenticated(): Boolean {
        return getAccessToken() != null
    }
}

actual fun createAuthManager(): AuthManager = AuthManager()
