package ai.ciris.mobile.shared.models

import kotlinx.serialization.Serializable

/**
 * Authentication state for the application
 *
 * This sealed class represents the different authentication states the app can be in.
 * Extracted from MainActivity.kt to support shared authentication logic across platforms.
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 238-270)
 */
sealed class AuthState {
    /**
     * User is not authenticated
     */
    data object Unauthenticated : AuthState()

    /**
     * User is authenticated with valid token
     * @param token The CIRIS access token
     * @param user User information
     */
    data class Authenticated(
        val token: String,
        val user: UserInfo
    ) : AuthState()

    /**
     * Authentication in progress
     */
    data object Loading : AuthState()

    /**
     * Authentication error occurred
     * @param message Error message
     * @param throwable Optional exception
     */
    data class Error(
        val message: String,
        val throwable: Throwable? = null
    ) : AuthState()
}

/**
 * Authentication configuration for the app
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 252-267)
 */
@Serializable
data class AuthConfig(
    /**
     * Authentication method: "google", "api_key", etc.
     */
    val authMethod: String = "api_key",

    /**
     * Google user ID (if using Google OAuth)
     */
    val googleUserId: String? = null,

    /**
     * Google ID token (if using Google OAuth)
     */
    val googleIdToken: String? = null,

    /**
     * User email address
     */
    val userEmail: String? = null,

    /**
     * User display name
     */
    val userName: String? = null,

    /**
     * User photo URL (for Google OAuth)
     */
    val userPhotoUrl: String? = null,

    /**
     * Whether to show setup wizard on first run
     */
    val showSetup: Boolean = true
)

/**
 * Token data stored in secure storage
 *
 * Source: android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1947-1950)
 */
@Serializable
data class TokenData(
    /**
     * CIRIS access token
     */
    val accessToken: String,

    /**
     * User role (ADMIN, OBSERVER, etc.)
     */
    val role: String = "OBSERVER",

    /**
     * Token type (usually "Bearer")
     */
    val tokenType: String = "Bearer",

    /**
     * Token expiration timestamp (milliseconds since epoch)
     * Null if no expiration tracking
     */
    val expiresAt: Long? = null,

    /**
     * User ID associated with this token
     */
    val userId: String? = null
)
