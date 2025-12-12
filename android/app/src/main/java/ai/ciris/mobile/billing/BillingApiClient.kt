package ai.ciris.mobile.billing

import android.content.Context
import android.util.Log
import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.util.concurrent.TimeUnit

/**
 * Callback interface for requesting fresh Google ID tokens.
 * This allows BillingApiClient to trigger native Google Sign-In refresh
 * when the stored token is expired.
 */
interface GoogleTokenRefreshCallback {
    /**
     * Request a fresh Google ID token via silent sign-in.
     * @param onResult Called with the fresh token, or null if refresh failed
     */
    fun requestFreshToken(onResult: (String?) -> Unit)
}

/**
 * HTTP client for communicating with the local CIRIS agent's billing API.
 *
 * All billing operations go through the local Python server, which handles:
 * - Credit balance checks via /api/billing/credits
 * - Purchase verification via the billing backend
 *
 * The local server URL is http://localhost:8080 (same as WebView).
 */
class BillingApiClient(
    private val context: Context,
    private val billingApiUrl: String = DEFAULT_LOCAL_API_URL,
    private var tokenRefreshCallback: GoogleTokenRefreshCallback? = null
) {
    companion object {
        private const val TAG = "CIRISBillingAPI"

        // Local Python server URL - must match MainActivity.SERVER_URL
        const val DEFAULT_LOCAL_API_URL = "http://localhost:8080"

        // External billing API URL for Google Play purchase verification only
        const val BILLING_BACKEND_URL = "https://billing.ciris.ai"

        private const val PREFS_NAME = "ciris_settings"
        private const val KEY_BILLING_API_URL = "billing_api_url"
        private const val KEY_GOOGLE_USER_ID = "google_user_id"
        private const val KEY_GOOGLE_EMAIL = "google_email"
        private const val KEY_GOOGLE_DISPLAY_NAME = "google_display_name"
        private const val KEY_GOOGLE_ID_TOKEN = "google_id_token"
        private const val KEY_API_KEY = "billing_api_key"
    }

    private val httpClient = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    private val gson = Gson()
    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    /**
     * Get the configured billing API URL.
     */
    fun getBillingUrl(): String {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_BILLING_API_URL, billingApiUrl) ?: billingApiUrl
    }

    /**
     * Set the billing API URL.
     */
    fun setBillingUrl(url: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_BILLING_API_URL, url).apply()
    }

    /**
     * Get the stored Google user ID.
     */
    fun getGoogleUserId(): String? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_GOOGLE_USER_ID, null)
    }

    /**
     * Set the Google user ID (from Google Sign-In).
     */
    fun setGoogleUserId(userId: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_GOOGLE_USER_ID, userId).apply()
    }

    /**
     * Get the stored API key for billing.ciris.ai.
     */
    fun getApiKey(): String? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_API_KEY, null)
    }

    /**
     * Set the API key for billing.ciris.ai.
     */
    fun setApiKey(apiKey: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_API_KEY, apiKey).apply()
    }

    /**
     * Clear the stored API key.
     * Used when the server returns 401 indicating the key is stale/invalid.
     */
    fun clearApiKey() {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().remove(KEY_API_KEY).apply()
        Log.i(TAG, "Cleared stale API key from storage")
    }

    /**
     * Set the token refresh callback.
     * This should be set by the activity/fragment that has access to GoogleSignInHelper.
     */
    fun setTokenRefreshCallback(callback: GoogleTokenRefreshCallback?) {
        this.tokenRefreshCallback = callback
    }

    /**
     * Force refresh the API key by clearing the old one and exchanging for a new one.
     * If a token refresh callback is set, this will first request a fresh Google ID token
     * via native silent sign-in before attempting the exchange.
     *
     * Returns true if we successfully obtained a new API key.
     */
    fun refreshApiKey(): Boolean {
        Log.i(TAG, "Forcing API key refresh...")
        clearApiKey()

        // If we have a token refresh callback, get a fresh Google ID token first
        val callback = tokenRefreshCallback
        if (callback != null) {
            Log.i(TAG, "Requesting fresh Google ID token via native sign-in...")
            var freshToken: String? = null
            val latch = java.util.concurrent.CountDownLatch(1)

            callback.requestFreshToken { token ->
                freshToken = token
                latch.countDown()
            }

            // Wait up to 30 seconds for the token refresh
            try {
                val completed = latch.await(30, java.util.concurrent.TimeUnit.SECONDS)
                if (!completed) {
                    Log.e(TAG, "Token refresh timed out after 30 seconds")
                    return false
                }

                if (freshToken != null) {
                    Log.i(TAG, "Got fresh Google ID token, storing it")
                    setGoogleIdToken(freshToken!!)
                } else {
                    Log.e(TAG, "Token refresh callback returned null - native sign-in may have failed")
                    return false
                }
            } catch (e: InterruptedException) {
                Log.e(TAG, "Token refresh interrupted: ${e.message}")
                return false
            }
        } else {
            Log.w(TAG, "No token refresh callback set - using stored (possibly expired) token")
        }

        val result = exchangeGoogleTokenForApiKey()
        if (result.success) {
            Log.i(TAG, "API key refresh successful")
        } else {
            Log.e(TAG, "API key refresh failed: ${result.error}")
        }
        return result.success
    }

    /**
     * Get the stored Google email.
     */
    fun getGoogleEmail(): String? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_GOOGLE_EMAIL, null)
    }

    /**
     * Set the Google email.
     */
    fun setGoogleEmail(email: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_GOOGLE_EMAIL, email).apply()
    }

    /**
     * Get the stored Google display name.
     */
    fun getGoogleDisplayName(): String? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_GOOGLE_DISPLAY_NAME, null)
    }

    /**
     * Set the Google display name.
     */
    fun setGoogleDisplayName(displayName: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_GOOGLE_DISPLAY_NAME, displayName).apply()
    }

    /**
     * Get the stored Google ID token for Bearer authentication.
     */
    fun getGoogleIdToken(): String? {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        return prefs.getString(KEY_GOOGLE_ID_TOKEN, null)
    }

    /**
     * Set the Google ID token for Bearer authentication.
     */
    fun setGoogleIdToken(idToken: String) {
        val prefs = context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
        prefs.edit().putString(KEY_GOOGLE_ID_TOKEN, idToken).apply()
        Log.i(TAG, "Stored Google ID token (${idToken.length} chars)")
    }

    /**
     * Add authentication headers to the request.
     * Uses CIRIS API key for local server auth and Google ID token for billing backend pass-through.
     */
    private fun addAuthHeaders(requestBuilder: Request.Builder) {
        // Use CIRIS API key for local server authentication
        val apiKey = getApiKey()
        if (!apiKey.isNullOrEmpty()) {
            requestBuilder.addHeader("Authorization", "Bearer $apiKey")
            Log.d(TAG, "Using CIRIS API key auth (key: ${apiKey.take(20)}...)")
        } else {
            Log.w(TAG, "No CIRIS API key available - request will likely fail!")
        }

        // Also send Google ID token for billing backend pass-through
        val googleIdToken = getGoogleIdToken()
        if (!googleIdToken.isNullOrEmpty()) {
            requestBuilder.addHeader("X-Google-ID-Token", googleIdToken)
            Log.d(TAG, "Added Google ID token for billing pass-through (${googleIdToken.take(20)}...)")
        }
    }

    /**
     * Exchange Google ID token for a CIRIS API key.
     *
     * Calls POST /v1/auth/native/google with the Google ID token to get a
     * session-based CIRIS API key that can be used for authenticated requests.
     *
     * @return TokenExchangeResult with success/failure and the API key
     */
    fun exchangeGoogleTokenForApiKey(): TokenExchangeResult {
        val idToken = getGoogleIdToken()
        if (idToken.isNullOrEmpty()) {
            Log.e(TAG, "No Google ID token - cannot exchange for API key")
            return TokenExchangeResult(
                success = false,
                error = "Not signed in with Google. Please sign in first."
            )
        }

        val requestBody = NativeTokenRequest(
            idToken = idToken,
            provider = "google"
        )

        val json = gson.toJson(requestBody)
        val url = "${getBillingUrl()}/v1/auth/native/google"
        Log.i(TAG, "Token exchange URL: $url")

        val request = Request.Builder()
            .url(url)
            .post(json.toRequestBody(jsonMediaType))
            .build()

        return try {
            val response = httpClient.newCall(request).execute()
            val responseBody = response.body?.string()

            Log.i(TAG, "Token exchange response code: ${response.code}")
            Log.d(TAG, "Token exchange response body: $responseBody")

            if (response.isSuccessful && responseBody != null) {
                val result = gson.fromJson(responseBody, NativeTokenResponse::class.java)
                // Store the exchanged API key
                setApiKey(result.accessToken)
                Log.i(TAG, "Token exchange successful - stored API key (${result.accessToken.take(20)}...)")
                TokenExchangeResult(
                    success = true,
                    apiKey = result.accessToken,
                    userId = result.userId,
                    role = result.role
                )
            } else {
                Log.e(TAG, "Token exchange failed: ${response.code} - $responseBody")
                TokenExchangeResult(
                    success = false,
                    error = "Token exchange failed: ${response.code} - ${responseBody ?: "No response"}"
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Token exchange request failed", e)
            TokenExchangeResult(
                success = false,
                error = "Network error: ${e.message}"
            )
        }
    }

    /**
     * Ensure we have a valid CIRIS API key.
     * If not, exchange the Google ID token for one.
     *
     * @return true if we have a valid API key (existing or newly exchanged)
     */
    fun ensureApiKey(): Boolean {
        val existingKey = getApiKey()
        if (!existingKey.isNullOrEmpty()) {
            Log.d(TAG, "Already have CIRIS API key")
            return true
        }

        Log.i(TAG, "No CIRIS API key - exchanging Google ID token...")
        val result = exchangeGoogleTokenForApiKey()
        return result.success
    }

    /**
     * Verify a purchase with the local CIRIS agent (which proxies to billing backend).
     *
     * The local server's /api/billing/google-play/verify endpoint handles:
     * 1. Authenticating the user via Bearer token
     * 2. Forwarding to billing.ciris.ai for Google Play verification
     * 3. Adding credits to the user's account
     *
     * Handles stale API keys by automatically refreshing on 401 errors.
     *
     * @param purchaseToken Google Play purchase token
     * @param productId Product SKU (e.g., "credits_100")
     * @param packageName App package name
     * @return VerifyResult with success/failure and credit info
     */
    fun verifyPurchase(
        purchaseToken: String,
        productId: String,
        packageName: String
    ): VerifyResult {
        return verifyPurchaseInternal(purchaseToken, productId, packageName, allowRetry = true)
    }

    private fun verifyPurchaseInternal(
        purchaseToken: String,
        productId: String,
        packageName: String,
        allowRetry: Boolean
    ): VerifyResult {
        // Ensure we have a valid CIRIS API key (exchange Google ID token if needed)
        if (!ensureApiKey()) {
            Log.e(TAG, "Failed to obtain CIRIS API key - cannot verify purchase")
            return VerifyResult(
                success = false,
                error = "Authentication failed. Please sign in again."
            )
        }

        // Simple request body - local server extracts user identity from Bearer token
        val requestBody = GooglePlayVerifyRequest(
            purchaseToken = purchaseToken,
            productId = productId,
            packageName = packageName
        )

        val json = gson.toJson(requestBody)
        val url = "${getBillingUrl()}/v1/api/billing/google-play/verify"
        Log.i(TAG, "Verify purchase URL: $url")
        Log.i(TAG, "Verify request: $json")

        // Build request with authentication headers
        val requestBuilder = Request.Builder()
            .url(url)
            .post(json.toRequestBody(jsonMediaType))

        // Add Bearer token authentication
        addAuthHeaders(requestBuilder)

        val request = requestBuilder.build()

        return try {
            val response = httpClient.newCall(request).execute()
            val responseBody = response.body?.string()

            Log.i(TAG, "Verify response code: ${response.code}")
            Log.i(TAG, "Verify response body: $responseBody")

            if (response.isSuccessful && responseBody != null) {
                val result = gson.fromJson(responseBody, VerifyResponse::class.java)
                VerifyResult(
                    success = result.success,
                    creditsAdded = result.creditsAdded ?: 0,
                    newBalance = result.newBalance ?: 0,
                    alreadyProcessed = result.alreadyProcessed ?: false,
                    error = if (!result.success) result.error ?: "Server returned success=false" else null
                )
            } else if (response.code == 401 && allowRetry) {
                // API key is stale/invalid - refresh and retry once
                Log.w(TAG, "Verify purchase got 401 - API key stale, refreshing...")
                if (refreshApiKey()) {
                    Log.i(TAG, "API key refreshed, retrying purchase verification...")
                    return verifyPurchaseInternal(purchaseToken, productId, packageName, allowRetry = false)
                } else {
                    Log.e(TAG, "Failed to refresh API key")
                    VerifyResult(
                        success = false,
                        error = "Authentication failed. Please sign in again."
                    )
                }
            } else {
                VerifyResult(
                    success = false,
                    error = "Server error: ${response.code} - ${responseBody ?: "No response"}"
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Verify request failed", e)
            VerifyResult(
                success = false,
                error = "Network error: ${e.message}"
            )
        }
    }

    /**
     * Get current credit balance for the user.
     * Calls local Python server's GET /api/billing/credits endpoint.
     * This is the same endpoint used by the WebView billing page.
     *
     * Handles stale API keys by automatically refreshing on 401 errors.
     */
    fun getBalance(): BalanceResult {
        return getBalanceInternal(allowRetry = true)
    }

    private fun getBalanceInternal(allowRetry: Boolean): BalanceResult {
        Log.i(TAG, "getBalance() called (allowRetry=$allowRetry)")

        // Ensure we have a valid CIRIS API key (exchange Google ID token if needed)
        if (!ensureApiKey()) {
            Log.w(TAG, "getBalance() - failed to obtain CIRIS API key")
            return BalanceResult(success = false, error = "Not signed in")
        }

        // Call local Python server's billing endpoint (same as WebView uses)
        val url = "${getBillingUrl()}/v1/api/billing/credits"
        Log.i(TAG, "Balance check URL: $url")

        // Build GET request with Bearer authentication
        val requestBuilder = Request.Builder()
            .url(url)
            .get()

        // Add Bearer token authentication
        addAuthHeaders(requestBuilder)

        val request = requestBuilder.build()

        return try {
            val response = httpClient.newCall(request).execute()
            val responseBody = response.body?.string()

            Log.i(TAG, "Balance check response code: ${response.code}")
            Log.i(TAG, "Balance check response body: $responseBody")

            if (response.isSuccessful && responseBody != null) {
                val result = gson.fromJson(responseBody, BalanceCheckResponse::class.java)
                Log.i(TAG, "Parsed balance: creditsRemaining=${result.creditsRemaining}, freeUsesRemaining=${result.freeUsesRemaining}, dailyFreeUsesRemaining=${result.dailyFreeUsesRemaining}, hasCredit=${result.hasCredit}, planName=${result.planName}")

                // Check if server is returning "unlimited" fallback (credit provider not yet initialized)
                // This returns 999+999=1998 which is confusing - treat as "not ready"
                if (result.planName == "unlimited") {
                    Log.w(TAG, "Server returned 'unlimited' plan - credit provider not yet ready")
                    BalanceResult(success = false, error = "Credit provider initializing")
                } else {
                    val totalCredits = result.getTotalCredits()
                    Log.i(TAG, "Total credits calculated: $totalCredits")
                    BalanceResult(
                        success = true,
                        balance = totalCredits
                    )
                }
            } else if (response.code == 401 && allowRetry) {
                // API key is stale/invalid - refresh and retry once
                Log.w(TAG, "Balance check got 401 - API key stale, refreshing...")
                if (refreshApiKey()) {
                    Log.i(TAG, "API key refreshed, retrying balance check...")
                    return getBalanceInternal(allowRetry = false)
                } else {
                    Log.e(TAG, "Failed to refresh API key")
                    BalanceResult(success = false, error = "Authentication failed")
                }
            } else {
                Log.e(TAG, "Balance check failed: ${response.code} - $responseBody")
                BalanceResult(success = false, error = "Server error: ${response.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Balance request failed", e)
            BalanceResult(success = false, error = "Network error: ${e.message}")
        }
    }
}

// Request/Response models

/**
 * Request to verify a Google Play purchase via local server.
 * User identity is extracted from Bearer token, so no user info needed here.
 */
data class GooglePlayVerifyRequest(
    @SerializedName("purchase_token") val purchaseToken: String,
    @SerializedName("product_id") val productId: String,
    @SerializedName("package_name") val packageName: String
)

data class VerifyResponse(
    val success: Boolean,
    @SerializedName("credits_added") val creditsAdded: Int?,
    @SerializedName("new_balance") val newBalance: Int?,
    @SerializedName("already_processed") val alreadyProcessed: Boolean?,
    val error: String?
)

data class VerifyResult(
    val success: Boolean,
    val creditsAdded: Int = 0,
    val newBalance: Int = 0,
    val alreadyProcessed: Boolean = false,
    val error: String? = null
)

data class BalanceCheckRequest(
    @SerializedName("oauth_provider") val oauthProvider: String,
    @SerializedName("external_id") val externalId: String,
    @SerializedName("email") val email: String?,
    @SerializedName("display_name") val displayName: String?,
    val context: Map<String, String>? = null
)

/**
 * Response from /api/billing/credits endpoint.
 * Matches Python CreditStatusResponse exactly.
 */
data class BalanceCheckResponse(
    @SerializedName("has_credit") val hasCredit: Boolean = false,
    @SerializedName("credits_remaining") val creditsRemaining: Int = 0,
    @SerializedName("free_uses_remaining") val freeUsesRemaining: Int = 0,
    @SerializedName("daily_free_uses_remaining") val dailyFreeUsesRemaining: Int = 0,
    @SerializedName("total_uses") val totalUses: Int = 0,
    @SerializedName("plan_name") val planName: String? = null,
    @SerializedName("purchase_required") val purchaseRequired: Boolean = false,
    @SerializedName("purchase_options") val purchaseOptions: Map<String, Any>? = null
) {
    /**
     * Get total credits available (paid + free + daily free).
     */
    fun getTotalCredits(): Int {
        return creditsRemaining + freeUsesRemaining + dailyFreeUsesRemaining
    }
}

data class BalanceResponse(
    val balance: Int?
)

data class BalanceResult(
    val success: Boolean,
    val balance: Int = 0,
    val error: String? = null
)

// Token Exchange models for native Google Sign-In

/**
 * Request to exchange Google ID token for CIRIS API key.
 * Matches Python NativeTokenRequest model.
 */
data class NativeTokenRequest(
    @SerializedName("id_token") val idToken: String,
    @SerializedName("provider") val provider: String = "google"
)

/**
 * Response from /v1/auth/native/google endpoint.
 * Matches Python NativeTokenResponse model.
 */
data class NativeTokenResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer",
    @SerializedName("expires_in") val expiresIn: Int = 2592000,
    @SerializedName("user_id") val userId: String,
    @SerializedName("role") val role: String,
    @SerializedName("email") val email: String? = null,
    @SerializedName("name") val name: String? = null
)

/**
 * Result of token exchange operation.
 */
data class TokenExchangeResult(
    val success: Boolean,
    val apiKey: String? = null,
    val userId: String? = null,
    val role: String? = null,
    val error: String? = null
)
