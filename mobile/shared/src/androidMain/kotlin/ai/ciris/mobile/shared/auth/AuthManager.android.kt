package ai.ciris.mobile.shared.auth

import ai.ciris.mobile.shared.models.AuthState
import ai.ciris.mobile.shared.models.LoginRequest
import ai.ciris.mobile.shared.models.GoogleAuthRequest
import ai.ciris.mobile.shared.models.AuthResponse
import ai.ciris.mobile.shared.models.TokenData
import ai.ciris.mobile.shared.models.UserInfo
import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.encodeToString
import kotlinx.serialization.decodeFromString
import java.net.HttpURLConnection
import java.net.URL

/**
 * Android implementation of AuthManager using EncryptedSharedPreferences
 *
 * This implementation provides secure token storage using AES-256 encryption
 * through Android's EncryptedSharedPreferences API.
 *
 * Source logic extracted from:
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 826-852) - Encrypted preferences setup
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 1903-1964) - Google token exchange
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 2307-2343) - Local user authentication
 * - android/app/src/main/java/ai/ciris/mobile/MainActivity.kt (lines 2593-2637) - Logout flow
 */
actual class AuthManager {

    companion object {
        private const val TAG = "AuthManager"
        private const val PREFS_NAME = "ciris_auth_prefs"
        private const val KEY_TOKEN_DATA = "token_data"
        private const val KEY_AUTH_METHOD = "auth_method"
        private const val KEY_GOOGLE_USER_ID = "google_user_id"

        private var appContext: Context? = null

        /**
         * Set the application context (call from Application.onCreate())
         */
        fun setContext(context: Context) {
            appContext = context.applicationContext
        }
    }

    private val _authState = MutableStateFlow<AuthState>(AuthState.Unauthenticated)
    actual val authState: StateFlow<AuthState> = _authState

    private val json = Json { ignoreUnknownKeys = true }

    /**
     * Lazy-initialized master key for encryption
     * Source: MainActivity.kt lines 823-826
     */
    private val masterKey: MasterKey? by lazy {
        appContext?.let { ctx ->
            MasterKey.Builder(ctx)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
        }
    }

    /**
     * Lazy-initialized encrypted shared preferences
     * Source: MainActivity.kt lines 828-834
     */
    private val encryptedPrefs: SharedPreferences? by lazy {
        appContext?.let { ctx ->
            masterKey?.let { key ->
                EncryptedSharedPreferences.create(
                    ctx,
                    PREFS_NAME,
                    key,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                )
            }
        }
    }

    // Fallback in-memory storage when context isn't available
    private val memoryStorage = mutableMapOf<String, String>()

    /**
     * Initialize the AuthManager and restore previous auth state if available
     */
    actual fun initialize() {
        // Try to load existing token and restore auth state
        CoroutineScope(Dispatchers.IO).launch {
            try {
                val tokenData = getStoredTokenData()
                if (tokenData != null) {
                    val user = UserInfo(
                        user_id = tokenData.userId ?: "unknown",
                        email = "",
                        role = tokenData.role
                    )
                    _authState.value = AuthState.Authenticated(
                        token = tokenData.accessToken,
                        user = user
                    )
                    Log.i(TAG, "Restored auth state from storage")
                } else {
                    _authState.value = AuthState.Unauthenticated
                    Log.i(TAG, "No previous auth state found")
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error initializing auth state: ${e.message}", e)
                _authState.value = AuthState.Unauthenticated
            }
        }
    }

    /**
     * Login with username and password
     * Source: MainActivity.kt lines 2307-2343
     */
    actual suspend fun login(
        username: String,
        password: String,
        serverUrl: String
    ): Result<AuthResponse> = withContext(Dispatchers.IO) {
        try {
            _authState.value = AuthState.Loading
            Log.i(TAG, "Authenticating user: $username")

            val url = URL("$serverUrl/v1/auth/login")
            val conn = url.openConnection() as HttpURLConnection
            conn.requestMethod = "POST"
            conn.setRequestProperty("Content-Type", "application/json")
            conn.doOutput = true
            conn.connectTimeout = 10000
            conn.readTimeout = 10000

            val payload = org.json.JSONObject().apply {
                put("username", username)
                put("password", password)
            }

            conn.outputStream.bufferedWriter().use { it.write(payload.toString()) }

            val responseCode = conn.responseCode
            Log.d(TAG, "Auth response code: $responseCode")

            if (responseCode == 200) {
                val response = conn.inputStream.bufferedReader().use { it.readText() }
                val jsonResponse = org.json.JSONObject(response)

                val accessToken = jsonResponse.getString("access_token")
                val tokenType = jsonResponse.optString("token_type", "bearer")

                // Parse user info
                val userJson = jsonResponse.optJSONObject("user")
                val user = if (userJson != null) {
                    UserInfo(
                        user_id = userJson.optString("user_id", username),
                        email = userJson.optString("email", ""),
                        name = userJson.optString("name"),
                        role = userJson.optString("role", "OBSERVER")
                    )
                } else {
                    UserInfo(
                        user_id = username,
                        email = "",
                        role = "ADMIN" // Local users default to ADMIN
                    )
                }

                val authResponse = AuthResponse(
                    access_token = accessToken,
                    token_type = tokenType,
                    user = user
                )

                // Store token
                val tokenData = TokenData(
                    accessToken = accessToken,
                    role = user.role,
                    tokenType = tokenType,
                    userId = user.user_id
                )
                saveAccessToken(tokenData)

                // Update auth state
                _authState.value = AuthState.Authenticated(accessToken, user)

                Log.i(TAG, "Login successful for user: ${user.user_id}, role: ${user.role}")
                Result.success(authResponse)
            } else {
                val error = conn.errorStream?.bufferedReader()?.use { it.readText() }
                Log.e(TAG, "Auth failed: $responseCode - $error")
                _authState.value = AuthState.Error("Authentication failed: $responseCode")
                Result.failure(Exception("Authentication failed: $responseCode - $error"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Auth error: ${e.message}", e)
            _authState.value = AuthState.Error("Authentication error: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Login with Google ID token
     * Source: MainActivity.kt lines 1903-1964
     */
    actual suspend fun loginWithGoogle(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> = withContext(Dispatchers.IO) {
        try {
            _authState.value = AuthState.Loading
            Log.i(TAG, "Exchanging Google ID token for CIRIS token (length: ${idToken.length})")

            val url = URL("$serverUrl/v1/auth/native/google")
            val connection = url.openConnection() as HttpURLConnection
            connection.connectTimeout = 15000
            connection.readTimeout = 15000
            connection.requestMethod = "POST"
            connection.setRequestProperty("Content-Type", "application/json")
            connection.doOutput = true

            val payload = org.json.JSONObject().apply {
                put("id_token", idToken)
                userId?.let { put("user_id", it) }
            }

            connection.outputStream.bufferedWriter().use { it.write(payload.toString()) }

            val responseCode = connection.responseCode
            Log.d(TAG, "Token exchange response code: $responseCode")

            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                val jsonResponse = org.json.JSONObject(response)

                val accessToken = jsonResponse.getString("access_token")
                val role = jsonResponse.optString("role", "OBSERVER")
                val userIdFromResponse = jsonResponse.optString("user_id", userId ?: "unknown")

                val user = UserInfo(
                    user_id = userIdFromResponse,
                    email = "",
                    role = role
                )

                val authResponse = AuthResponse(
                    access_token = accessToken,
                    token_type = "Bearer",
                    user = user
                )

                // Store token
                val tokenData = TokenData(
                    accessToken = accessToken,
                    role = role,
                    tokenType = "Bearer",
                    userId = userIdFromResponse
                )
                saveAccessToken(tokenData)

                // Store auth method
                saveString(KEY_AUTH_METHOD, "google")
                userId?.let { saveString(KEY_GOOGLE_USER_ID, it) }

                // Update auth state
                _authState.value = AuthState.Authenticated(accessToken, user)

                Log.i(TAG, "Google token exchange successful - user: $userIdFromResponse, role: $role")
                connection.disconnect()
                Result.success(authResponse)
            } else {
                val error = connection.errorStream?.bufferedReader()?.use { it.readText() }
                Log.e(TAG, "Token exchange failed: $responseCode - $error")
                _authState.value = AuthState.Error("Token exchange failed: $responseCode")
                connection.disconnect()
                Result.failure(Exception("Token exchange failed: $responseCode - $error"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Token exchange error: ${e.message}", e)
            _authState.value = AuthState.Error("Token exchange error: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Logout and clear all stored tokens
     * Source: MainActivity.kt lines 2593-2637
     */
    actual suspend fun logout(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            Log.i(TAG, "Performing logout")

            // Clear all stored auth data
            deleteAccessToken()
            deleteString(KEY_AUTH_METHOD)
            deleteString(KEY_GOOGLE_USER_ID)

            // Update auth state
            _authState.value = AuthState.Unauthenticated

            Log.i(TAG, "Logout successful - all tokens cleared")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Logout error: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Refresh the current access token
     * Source: MainActivity.kt lines 1090-1109
     *
     * Note: Currently re-exchanges Google ID token if available
     * TODO: Implement proper refresh token flow when backend supports it
     */
    actual suspend fun refreshToken(serverUrl: String): Result<AuthResponse> = withContext(Dispatchers.IO) {
        try {
            val authMethod = getString(KEY_AUTH_METHOD)

            if (authMethod == "google") {
                // For Google auth, we would need to re-exchange the ID token
                // This requires the original Google ID token which we don't store for security
                Log.w(TAG, "Token refresh for Google auth requires re-authentication")
                Result.failure(Exception("Google auth token refresh requires re-authentication"))
            } else {
                // For local auth, we would use a refresh token endpoint
                // This is not yet implemented in the backend
                Log.w(TAG, "Refresh token endpoint not yet implemented")
                Result.failure(Exception("Refresh token not yet implemented"))
            }
        } catch (e: Exception) {
            Log.e(TAG, "Token refresh error: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Get the current stored access token
     * Source: MainActivity.kt lines 144-145
     */
    actual suspend fun getAccessToken(): String? = withContext(Dispatchers.IO) {
        getStoredTokenData()?.accessToken
    }

    /**
     * Save access token to secure storage
     * Source: MainActivity.kt lines 1947-1955
     */
    actual suspend fun saveAccessToken(tokenData: TokenData): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val json = json.encodeToString(tokenData)
            saveString(KEY_TOKEN_DATA, json)
            Log.i(TAG, "Saved access token (role: ${tokenData.role})")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Error saving access token: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Delete the stored access token
     * Source: MainActivity.kt lines 2593-2606
     */
    actual suspend fun deleteAccessToken(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            deleteString(KEY_TOKEN_DATA)
            Log.i(TAG, "Deleted access token")
            Result.success(Unit)
        } catch (e: Exception) {
            Log.e(TAG, "Error deleting access token: ${e.message}", e)
            Result.failure(e)
        }
    }

    /**
     * Get the current user role
     * Source: MainActivity.kt line 145
     */
    actual suspend fun getUserRole(): String? = withContext(Dispatchers.IO) {
        getStoredTokenData()?.role
    }

    /**
     * Check if user is currently authenticated
     */
    actual suspend fun isAuthenticated(): Boolean = withContext(Dispatchers.IO) {
        getAccessToken() != null
    }

    // Private helper methods

    private fun getStoredTokenData(): TokenData? {
        return try {
            val jsonString = getString(KEY_TOKEN_DATA)
            if (jsonString != null) {
                json.decodeFromString<TokenData>(jsonString)
            } else {
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error reading token data: ${e.message}", e)
            null
        }
    }

    private fun saveString(key: String, value: String) {
        val prefs = encryptedPrefs
        if (prefs != null) {
            prefs.edit().putString(key, value).apply()
        } else {
            memoryStorage[key] = value
            Log.w(TAG, "Context not available, using memory storage for $key")
        }
    }

    private fun getString(key: String): String? {
        val prefs = encryptedPrefs
        return if (prefs != null) {
            prefs.getString(key, null)
        } else {
            memoryStorage[key]
        }
    }

    private fun deleteString(key: String) {
        val prefs = encryptedPrefs
        if (prefs != null) {
            prefs.edit().remove(key).apply()
        } else {
            memoryStorage.remove(key)
        }
    }
}

/**
 * Factory function to create AuthManager instance
 */
actual fun createAuthManager(): AuthManager = AuthManager()
