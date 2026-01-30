package ai.ciris.mobile.shared.auth

import ai.ciris.mobile.shared.models.AuthState
import ai.ciris.mobile.shared.models.LoginRequest
import ai.ciris.mobile.shared.models.GoogleAuthRequest
import ai.ciris.mobile.shared.models.AuthResponse
import ai.ciris.mobile.shared.models.TokenData
import kotlinx.coroutines.flow.StateFlow

/**
 * Authentication manager for CIRIS mobile apps
 *
 * Handles authentication, token management, and session persistence.
 * Platform-specific implementations provide secure token storage.
 *
 * Key responsibilities:
 * - Login/logout operations
 * - Token storage and retrieval
 * - Token refresh
 * - Auth state management
 *
 * Source logic from:
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1752-1836, 2231-2342)
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1025-1120) - Encrypted preferences
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 2569-2637) - Logout flow
 */
expect class AuthManager {

    /**
     * Current authentication state as a Flow
     */
    val authState: StateFlow<AuthState>

    /**
     * Initialize the AuthManager
     * Platform implementations may need context/configuration
     */
    fun initialize()

    /**
     * Login with username and password (local authentication)
     *
     * Source: MainActivity.kt lines 2307-2343 (authenticateLocalUser)
     *
     * @param username The username
     * @param password The password
     * @param serverUrl The API server URL (e.g., "http://127.0.0.1:8000")
     * @return Result with AuthResponse on success
     */
    suspend fun login(
        username: String,
        password: String,
        serverUrl: String
    ): Result<AuthResponse>

    /**
     * Login with Google ID token (OAuth authentication) - Android
     *
     * Source: MainActivity.kt lines 1903-1964 (exchangeGoogleIdToken)
     *
     * @param idToken Google ID token
     * @param userId Optional user ID
     * @param serverUrl The API server URL
     * @return Result with AuthResponse on success
     */
    suspend fun loginWithGoogle(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse>

    /**
     * Login with Apple ID token (OAuth authentication) - iOS
     *
     * Uses Sign in with Apple to authenticate with the CIRIS backend.
     *
     * @param idToken Apple identity token
     * @param userId Apple user ID
     * @param serverUrl The API server URL
     * @return Result with AuthResponse on success
     */
    suspend fun loginWithApple(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse>

    /**
     * Login with native OAuth token (Google on Android, Apple on iOS)
     *
     * Platform-agnostic method that delegates to the appropriate provider.
     *
     * @param idToken OAuth ID token
     * @param userId User ID
     * @param provider OAuth provider ("google" or "apple")
     * @param serverUrl The API server URL
     * @return Result with AuthResponse on success
     */
    suspend fun loginWithNativeAuth(
        idToken: String,
        userId: String?,
        provider: String,
        serverUrl: String
    ): Result<AuthResponse>

    /**
     * Logout and clear all stored tokens
     *
     * Source: MainActivity.kt lines 2569-2637 (performLogout, returnToLogin)
     *
     * @return Result indicating success or failure
     */
    suspend fun logout(): Result<Unit>

    /**
     * Refresh the current access token
     *
     * Source: MainActivity.kt lines 1090-1109 (refreshToken)
     *
     * @param serverUrl The API server URL
     * @return Result with new AuthResponse on success
     */
    suspend fun refreshToken(serverUrl: String): Result<AuthResponse>

    /**
     * Get the current stored access token
     *
     * Source: MainActivity.kt lines 144-145, 264-267 (cirisAccessToken variable)
     *
     * @return The access token if available, null otherwise
     */
    suspend fun getAccessToken(): String?

    /**
     * Save access token to secure storage
     *
     * Source: MainActivity.kt lines 1947-1955 (storing token after exchange)
     *
     * @param tokenData Token data to store
     * @return Result indicating success or failure
     */
    suspend fun saveAccessToken(tokenData: TokenData): Result<Unit>

    /**
     * Delete the stored access token
     *
     * Source: MainActivity.kt lines 2593-2606 (clearing tokens on logout)
     *
     * @return Result indicating success or failure
     */
    suspend fun deleteAccessToken(): Result<Unit>

    /**
     * Get the current user role
     *
     * Source: MainActivity.kt line 145 (userRole variable)
     *
     * @return The user role (ADMIN, OBSERVER, etc.) or null if not authenticated
     */
    suspend fun getUserRole(): String?

    /**
     * Check if user is currently authenticated
     *
     * @return true if authenticated with valid token
     */
    suspend fun isAuthenticated(): Boolean
}

/**
 * Factory function to create platform-specific AuthManager instance
 *
 * Usage:
 * ```kotlin
 * val authManager = createAuthManager()
 * authManager.initialize()
 * ```
 */
expect fun createAuthManager(): AuthManager
