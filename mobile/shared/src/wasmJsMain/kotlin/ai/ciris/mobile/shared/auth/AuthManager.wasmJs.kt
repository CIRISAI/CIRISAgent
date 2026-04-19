package ai.ciris.mobile.shared.auth

import ai.ciris.mobile.shared.models.AuthState
import ai.ciris.mobile.shared.models.AuthResponse
import ai.ciris.mobile.shared.models.TokenData
import ai.ciris.mobile.shared.models.UserInfo
import kotlinx.browser.localStorage
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Web/WASM implementation of AuthManager.
 * Uses localStorage for token storage.
 * OAuth flows redirect through the backend.
 */
actual class AuthManager {
    private val _authState = MutableStateFlow<AuthState>(AuthState.Unauthenticated)
    actual val authState: StateFlow<AuthState> = _authState.asStateFlow()

    actual fun initialize() {
        // Check if we have a stored token
        val token = localStorage.getItem("ciris_access_token")
        if (token != null) {
            val userId = localStorage.getItem("ciris_user_id") ?: "unknown"
            val role = localStorage.getItem("ciris_user_role") ?: "OBSERVER"
            val user = UserInfo(user_id = userId, email = "", role = role)
            _authState.value = AuthState.Authenticated(token, user)
        } else {
            _authState.value = AuthState.Unauthenticated
        }
    }

    actual suspend fun login(
        username: String,
        password: String,
        serverUrl: String
    ): Result<AuthResponse> {
        // Web login would go through backend API - stub for now
        return Result.failure(UnsupportedOperationException("Web login not implemented - use OAuth"))
    }

    actual suspend fun loginWithGoogle(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> {
        return Result.failure(UnsupportedOperationException("Google Sign-In on web uses backend OAuth redirect"))
    }

    actual suspend fun loginWithApple(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> {
        return Result.failure(UnsupportedOperationException("Apple Sign-In on web uses backend OAuth redirect"))
    }

    actual suspend fun loginWithNativeAuth(
        idToken: String,
        userId: String?,
        provider: String,
        serverUrl: String
    ): Result<AuthResponse> {
        return Result.failure(UnsupportedOperationException("Native auth on web uses backend OAuth redirect"))
    }

    actual suspend fun logout(): Result<Unit> = runCatching {
        localStorage.removeItem("ciris_access_token")
        localStorage.removeItem("ciris_refresh_token")
        localStorage.removeItem("ciris_user_id")
        localStorage.removeItem("ciris_user_role")
        _authState.value = AuthState.Unauthenticated
    }

    actual suspend fun refreshToken(serverUrl: String): Result<AuthResponse> {
        // Token refresh would go through backend API - stub for now
        return Result.failure(UnsupportedOperationException("Token refresh not implemented for web"))
    }

    actual suspend fun getAccessToken(): String? {
        return localStorage.getItem("ciris_access_token")
    }

    actual suspend fun saveAccessToken(tokenData: TokenData): Result<Unit> = runCatching {
        localStorage.setItem("ciris_access_token", tokenData.accessToken)
        tokenData.userId?.let { localStorage.setItem("ciris_user_id", it) }
        localStorage.setItem("ciris_user_role", tokenData.role)
        val user = UserInfo(
            user_id = tokenData.userId ?: "unknown",
            email = "",
            role = tokenData.role
        )
        _authState.value = AuthState.Authenticated(tokenData.accessToken, user)
    }

    actual suspend fun deleteAccessToken(): Result<Unit> = runCatching {
        localStorage.removeItem("ciris_access_token")
        localStorage.removeItem("ciris_refresh_token")
        localStorage.removeItem("ciris_user_id")
        localStorage.removeItem("ciris_user_role")
        _authState.value = AuthState.Unauthenticated
    }

    actual suspend fun getUserRole(): String? {
        return localStorage.getItem("ciris_user_role")
    }

    actual suspend fun isAuthenticated(): Boolean {
        return localStorage.getItem("ciris_access_token") != null
    }
}

actual fun createAuthManager(): AuthManager = AuthManager()
