@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.auth

import ai.ciris.mobile.shared.models.AuthState
import ai.ciris.mobile.shared.models.AuthResponse
import ai.ciris.mobile.shared.models.TokenData
import ai.ciris.mobile.shared.models.UserInfo
import kotlinx.cinterop.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.withContext
import platform.Foundation.*
import platform.darwin.*

/**
 * iOS implementation of AuthManager
 *
 * Uses iOS Keychain for secure token storage (via SecureStorage)
 * and URLSession for HTTP requests.
 *
 * Supports:
 * - Local username/password authentication
 * - Apple Sign-In (Sign in with Apple)
 * - Google Sign-In is NOT supported on iOS (use Apple Sign-In instead)
 */
actual class AuthManager {

    companion object {
        private const val TAG = "AuthManager.iOS"
        private const val KEY_TOKEN_DATA = "token_data"
        private const val KEY_AUTH_METHOD = "auth_method"
        private const val KEY_APPLE_USER_ID = "apple_user_id"
    }

    private val _authState = MutableStateFlow<AuthState>(AuthState.Unauthenticated)
    actual val authState: StateFlow<AuthState> = _authState.asStateFlow()

    private var accessToken: String? = null
    private var userRole: String? = null
    private var currentUser: UserInfo? = null

    actual fun initialize() {
        // Load any stored tokens from Keychain
        println("[$TAG] Initializing...")
        // TODO: Load from SecureStorage/Keychain
    }

    actual suspend fun login(
        username: String,
        password: String,
        serverUrl: String
    ): Result<AuthResponse> = withContext(Dispatchers.Default) {
        try {
            _authState.value = AuthState.Loading
            println("[$TAG] Authenticating user: $username")

            val url = NSURL.URLWithString("$serverUrl/v1/auth/login")!!
            val request = NSMutableURLRequest.requestWithURL(url)
            request.setHTTPMethod("POST")
            request.setValue("application/json", forHTTPHeaderField = "Content-Type")

            val payload = """{"username":"$username","password":"$password"}"""
            request.setHTTPBody(payload.encodeToByteArray().toNSData())

            // Use synchronous request for simplicity (we're already on IO dispatcher)
            val response = performSynchronousRequest(request)

            if (response.isSuccess) {
                val jsonData = response.data!!
                val jsonString = NSString.create(data = jsonData, encoding = NSUTF8StringEncoding) as String

                // Parse response
                val accessTokenMatch = Regex(""""access_token"\s*:\s*"([^"]+)"""").find(jsonString)
                val token = accessTokenMatch?.groupValues?.get(1)
                    ?: throw Exception("No access_token in response")

                val user = UserInfo(
                    user_id = username,
                    email = "",
                    role = "ADMIN"
                )

                val authResponse = AuthResponse(
                    access_token = token,
                    token_type = "bearer",
                    user = user
                )

                // Store token
                accessToken = token
                userRole = user.role
                currentUser = user
                _authState.value = AuthState.Authenticated(token, user)

                println("[$TAG] Login successful for user: ${user.user_id}")
                Result.success(authResponse)
            } else {
                println("[$TAG] Auth failed: ${response.error}")
                _authState.value = AuthState.Error("Authentication failed: ${response.error}")
                Result.failure(Exception("Authentication failed: ${response.error}"))
            }
        } catch (e: Exception) {
            println("[$TAG] Auth error: ${e.message}")
            _authState.value = AuthState.Error("Authentication error: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Login with Google ID token - Not supported on iOS
     * Use loginWithApple instead.
     */
    actual suspend fun loginWithGoogle(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> = withContext(Dispatchers.Default) {
        println("[$TAG] Google Sign-In is not supported on iOS. Use Apple Sign-In instead.")
        _authState.value = AuthState.Error("Google Sign-In is not supported on iOS")
        Result.failure(Exception("Google Sign-In is not supported on iOS. Use Apple Sign-In instead."))
    }

    /**
     * Login with Apple ID token (Sign in with Apple)
     */
    actual suspend fun loginWithApple(
        idToken: String,
        userId: String?,
        serverUrl: String
    ): Result<AuthResponse> = withContext(Dispatchers.Default) {
        try {
            _authState.value = AuthState.Loading
            println("[$TAG] Exchanging Apple ID token for CIRIS token (length: ${idToken.length})")

            val url = NSURL.URLWithString("$serverUrl/v1/auth/native/apple")!!
            val request = NSMutableURLRequest.requestWithURL(url)
            request.setHTTPMethod("POST")
            request.setValue("application/json", forHTTPHeaderField = "Content-Type")

            val payload = if (userId != null) {
                """{"id_token":"$idToken","user_id":"$userId"}"""
            } else {
                """{"id_token":"$idToken"}"""
            }
            request.setHTTPBody(payload.encodeToByteArray().toNSData())

            val response = performSynchronousRequest(request)

            if (response.isSuccess) {
                val jsonData = response.data!!
                val jsonString = NSString.create(data = jsonData, encoding = NSUTF8StringEncoding) as String

                // Parse response
                val accessTokenMatch = Regex(""""access_token"\s*:\s*"([^"]+)"""").find(jsonString)
                val token = accessTokenMatch?.groupValues?.get(1)
                    ?: throw Exception("No access_token in response")

                val roleMatch = Regex(""""role"\s*:\s*"([^"]+)"""").find(jsonString)
                val role = roleMatch?.groupValues?.get(1) ?: "OBSERVER"

                val userIdMatch = Regex(""""user_id"\s*:\s*"([^"]+)"""").find(jsonString)
                val userIdFromResponse = userIdMatch?.groupValues?.get(1) ?: userId ?: "unknown"

                val user = UserInfo(
                    user_id = userIdFromResponse,
                    email = "",
                    role = role
                )

                val authResponse = AuthResponse(
                    access_token = token,
                    token_type = "Bearer",
                    user = user
                )

                // Store token
                accessToken = token
                userRole = role
                currentUser = user
                _authState.value = AuthState.Authenticated(token, user)

                println("[$TAG] Apple token exchange successful - user: $userIdFromResponse, role: $role")
                Result.success(authResponse)
            } else {
                println("[$TAG] Apple token exchange failed: ${response.error}")
                _authState.value = AuthState.Error("Token exchange failed: ${response.error}")
                Result.failure(Exception("Token exchange failed: ${response.error}"))
            }
        } catch (e: Exception) {
            println("[$TAG] Apple token exchange error: ${e.message}")
            _authState.value = AuthState.Error("Token exchange error: ${e.message}")
            Result.failure(e)
        }
    }

    /**
     * Login with native OAuth token (Apple on iOS)
     */
    actual suspend fun loginWithNativeAuth(
        idToken: String,
        userId: String?,
        provider: String,
        serverUrl: String
    ): Result<AuthResponse> = withContext(Dispatchers.Default) {
        when (provider.lowercase()) {
            "apple" -> loginWithApple(idToken, userId, serverUrl)
            "google" -> {
                println("[$TAG] Google Sign-In requested on iOS - redirecting to Apple Sign-In")
                Result.failure(Exception("Google Sign-In is not supported on iOS. Use Apple Sign-In instead."))
            }
            else -> Result.failure(Exception("Unknown OAuth provider: $provider"))
        }
    }

    actual suspend fun logout(): Result<Unit> = withContext(Dispatchers.Default) {
        try {
            println("[$TAG] Performing logout")

            accessToken = null
            userRole = null
            currentUser = null
            _authState.value = AuthState.Unauthenticated

            // TODO: Clear from SecureStorage/Keychain

            println("[$TAG] Logout successful")
            Result.success(Unit)
        } catch (e: Exception) {
            println("[$TAG] Logout error: ${e.message}")
            Result.failure(e)
        }
    }

    actual suspend fun refreshToken(serverUrl: String): Result<AuthResponse> = withContext(Dispatchers.Default) {
        println("[$TAG] Token refresh not yet implemented for iOS")
        Result.failure(Exception("Token refresh requires re-authentication"))
    }

    actual suspend fun getAccessToken(): String? {
        return accessToken
    }

    actual suspend fun saveAccessToken(tokenData: TokenData): Result<Unit> {
        return try {
            accessToken = tokenData.accessToken
            userRole = tokenData.role
            currentUser = UserInfo(
                user_id = tokenData.userId ?: "ios_user",
                email = "",
                name = null,
                role = tokenData.role
            )
            _authState.value = AuthState.Authenticated(
                token = tokenData.accessToken,
                user = currentUser!!
            )
            println("[$TAG] Saved access token (role: ${tokenData.role})")
            Result.success(Unit)
        } catch (e: Exception) {
            println("[$TAG] Error saving access token: ${e.message}")
            Result.failure(e)
        }
    }

    actual suspend fun deleteAccessToken(): Result<Unit> {
        return try {
            accessToken = null
            userRole = null
            currentUser = null
            _authState.value = AuthState.Unauthenticated
            println("[$TAG] Deleted access token")
            Result.success(Unit)
        } catch (e: Exception) {
            println("[$TAG] Error deleting access token: ${e.message}")
            Result.failure(e)
        }
    }

    actual suspend fun getUserRole(): String? {
        return userRole
    }

    actual suspend fun isAuthenticated(): Boolean {
        return accessToken != null
    }

    // Helper classes and functions

    private data class HttpResponse(
        val isSuccess: Boolean,
        val data: NSData?,
        val error: String?
    )

    private fun performSynchronousRequest(request: NSURLRequest): HttpResponse {
        val semaphore = dispatch_semaphore_create(0)
        var result: HttpResponse? = null

        val session = NSURLSession.sharedSession
        val task = session.dataTaskWithRequest(request) { data, response, error ->
            val httpResponse = response as? NSHTTPURLResponse
            val statusCode = httpResponse?.statusCode?.toInt() ?: 0

            result = if (error != null) {
                HttpResponse(false, null, error.localizedDescription)
            } else if (statusCode in 200..299) {
                HttpResponse(true, data, null)
            } else {
                val errorBody = data?.let {
                    NSString.create(data = it, encoding = NSUTF8StringEncoding) as? String
                }
                HttpResponse(false, null, "HTTP $statusCode: $errorBody")
            }

            dispatch_semaphore_signal(semaphore)
        }
        task.resume()

        // Wait for completion (with 30 second timeout)
        dispatch_semaphore_wait(semaphore, dispatch_time(DISPATCH_TIME_NOW, 30_000_000_000L))

        return result ?: HttpResponse(false, null, "Request timed out")
    }

    private fun ByteArray.toNSData(): NSData {
        return this.usePinned { pinned ->
            NSData.create(bytes = pinned.addressOf(0), length = this.size.toULong())
        }
    }
}

actual fun createAuthManager(): AuthManager = AuthManager()
