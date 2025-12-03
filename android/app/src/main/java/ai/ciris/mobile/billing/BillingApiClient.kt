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
 * HTTP client for communicating with CIRISBilling server.
 *
 * Sends purchase tokens to the server for verification and credit grants.
 * Server endpoint: POST /v1/billing/google-play/verify
 */
class BillingApiClient(
    private val context: Context,
    private val billingApiUrl: String = DEFAULT_BILLING_API_URL
) {
    companion object {
        private const val TAG = "CIRISBillingAPI"

        // Default billing API URL - can be overridden in settings
        const val DEFAULT_BILLING_API_URL = "https://billing.ciris.ai"

        private const val PREFS_NAME = "ciris_settings"
        private const val KEY_BILLING_API_URL = "billing_api_url"
        private const val KEY_GOOGLE_USER_ID = "google_user_id"
        private const val KEY_GOOGLE_EMAIL = "google_email"
        private const val KEY_GOOGLE_DISPLAY_NAME = "google_display_name"
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
     * Verify a purchase with the CIRISBilling server.
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
        val googleUserId = getGoogleUserId()
        if (googleUserId == null) {
            Log.e(TAG, "No Google user ID configured - cannot verify purchase")
            return VerifyResult(
                success = false,
                error = "Not signed in with Google. Please sign in first."
            )
        }

        val requestBody = VerifyRequest(
            oauthProvider = "oauth:google",  // Must be "oauth:google" not "google"
            externalId = googleUserId,
            email = getGoogleEmail(),
            displayName = getGoogleDisplayName(),
            purchaseToken = purchaseToken,
            productId = productId,
            packageName = packageName
        )

        val json = gson.toJson(requestBody)
        Log.d(TAG, "Verify request: $json")

        // Build request with API key header if available
        val requestBuilder = Request.Builder()
            .url("${getBillingUrl()}/v1/billing/google-play/verify")
            .post(json.toRequestBody(jsonMediaType))

        // Add API key header if configured
        getApiKey()?.let { apiKey ->
            requestBuilder.addHeader("x-api-key", apiKey)
        }

        val request = requestBuilder.build()

        return try {
            val response = httpClient.newCall(request).execute()
            val responseBody = response.body?.string()

            Log.d(TAG, "Verify response (${response.code}): $responseBody")

            if (response.isSuccessful && responseBody != null) {
                val result = gson.fromJson(responseBody, VerifyResponse::class.java)
                VerifyResult(
                    success = result.success,
                    creditsAdded = result.creditsAdded ?: 0,
                    newBalance = result.newBalance ?: 0,
                    alreadyProcessed = result.alreadyProcessed ?: false,
                    error = if (!result.success) "Server returned success=false" else null
                )
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
     * Uses POST /v1/billing/credits/check endpoint with API key auth.
     */
    fun getBalance(): BalanceResult {
        val googleUserId = getGoogleUserId()
        if (googleUserId == null) {
            return BalanceResult(success = false, error = "Not signed in")
        }

        // Build request body matching server expectation
        val requestBody = BalanceCheckRequest(
            oauthProvider = "oauth:google",  // Must be "oauth:google" not "google"
            externalId = googleUserId,
            email = getGoogleEmail(),
            displayName = getGoogleDisplayName(),
            context = mapOf("source" to "android_app")
        )

        val json = gson.toJson(requestBody)
        Log.d(TAG, "Balance check request: $json")

        // Build request with API key header
        val requestBuilder = Request.Builder()
            .url("${getBillingUrl()}/v1/billing/credits/check")
            .post(json.toRequestBody(jsonMediaType))

        // Add API key header if configured
        getApiKey()?.let { apiKey ->
            requestBuilder.addHeader("x-api-key", apiKey)
        }

        val request = requestBuilder.build()

        return try {
            val response = httpClient.newCall(request).execute()
            val responseBody = response.body?.string()

            Log.d(TAG, "Balance check response (${response.code}): $responseBody")

            if (response.isSuccessful && responseBody != null) {
                val result = gson.fromJson(responseBody, BalanceCheckResponse::class.java)
                BalanceResult(
                    success = true,
                    balance = result.credits ?: 0
                )
            } else {
                BalanceResult(success = false, error = "Server error: ${response.code}")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Balance request failed", e)
            BalanceResult(success = false, error = "Network error: ${e.message}")
        }
    }
}

// Request/Response models

data class VerifyRequest(
    @SerializedName("oauth_provider") val oauthProvider: String,
    @SerializedName("external_id") val externalId: String,
    @SerializedName("email") val email: String?,
    @SerializedName("display_name") val displayName: String?,
    @SerializedName("purchase_token") val purchaseToken: String,
    @SerializedName("product_id") val productId: String,
    @SerializedName("package_name") val packageName: String
)

data class VerifyResponse(
    val success: Boolean,
    @SerializedName("credits_added") val creditsAdded: Int?,
    @SerializedName("new_balance") val newBalance: Int?,
    @SerializedName("already_processed") val alreadyProcessed: Boolean?
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

data class BalanceCheckResponse(
    val credits: Int?,
    @SerializedName("user_id") val userId: String?,
    @SerializedName("display_name") val displayName: String?
)

data class BalanceResponse(
    val balance: Int?
)

data class BalanceResult(
    val success: Boolean,
    val balance: Int = 0,
    val error: String? = null
)
