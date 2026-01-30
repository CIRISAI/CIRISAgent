package ai.ciris.mobile.shared.auth

import ai.ciris.mobile.shared.models.AuthState
import ai.ciris.mobile.shared.models.AuthResponse
import ai.ciris.mobile.shared.models.TokenData
import ai.ciris.mobile.shared.models.UserInfo
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * iOS implementation of AuthManager
 *
 * Uses iOS Keychain for secure token storage (via SecureStorage)
 * and URLSession for HTTP requests.
 */
actual class AuthManager {
    private val _authState = MutableStateFlow<AuthState>(AuthState.Unauthenticated)
    actual val authState: StateFlow<AuthState> = _authState.asStateFlow()

    private var accessToken: String? = null
    private var userRole: String? = null
    private var currentUser: UserInfo? = null

    actual fun initialize() {
        // Load any stored tokens from Keychain
        println("[AuthManager.iOS] Initializing...")
    }

    actual suspend fun login(
        username: String,
        password: String,
        serverUrl: String
    ): Result<AuthResponse> {
        return try {
            // TODO: Implement HTTP POST to /v1/auth/login
            // For now, return a stub result
            _authState.value = AuthState.Unauthenticated
            Result.failure(Exception("iOS local login not yet implemented"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun loginWithGoogle(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> {
        return try {
            // TODO: Implement HTTP POST to /v1/auth/google/token
            // For now, return a stub result
            _authState.value = AuthState.Unauthenticated
            Result.failure(Exception("iOS Google login not yet implemented"))
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun logout(): Result<Unit> {
        return try {
            accessToken = null
            userRole = null
            currentUser = null
            _authState.value = AuthState.Unauthenticated
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun refreshToken(serverUrl: String): Result<AuthResponse> {
        return Result.failure(Exception("iOS token refresh not yet implemented"))
    }

    actual suspend fun getAccessToken(): String? {
        return accessToken
    }

    actual suspend fun saveAccessToken(tokenData: TokenData): Result<Unit> {
        return try {
            accessToken = tokenData.accessToken
            userRole = tokenData.role
            currentUser = UserInfo(
                user_id = "ios_user",
                email = "ios@ciris.ai",
                name = null,
                role = tokenData.role
            )
            _authState.value = AuthState.Authenticated(
                token = tokenData.accessToken,
                user = currentUser!!
            )
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun deleteAccessToken(): Result<Unit> {
        return try {
            accessToken = null
            userRole = null
            currentUser = null
            _authState.value = AuthState.Unauthenticated
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun getUserRole(): String? {
        return userRole
    }

    actual suspend fun isAuthenticated(): Boolean {
        return accessToken != null
    }
}

actual fun createAuthManager(): AuthManager = AuthManager()
