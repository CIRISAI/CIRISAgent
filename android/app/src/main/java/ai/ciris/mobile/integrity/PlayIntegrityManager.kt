package ai.ciris.mobile.integrity

import android.content.Context
import android.util.Log
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest
import com.google.android.gms.tasks.Tasks
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL
import com.google.gson.Gson

/**
 * Manages Play Integrity API interactions for device/app attestation.
 *
 * Flow:
 * 1. Get nonce from billing.ciris.ai
 * 2. Request integrity token from Google Play
 * 3. Send token to billing.ciris.ai for verification
 *
 * This adds security on top of JWT auth by verifying:
 * - Device is genuine (not rooted/emulator)
 * - App is unmodified (matches Play Store version)
 * - App was installed from Play Store
 */
class PlayIntegrityManager(private val context: Context) {

    companion object {
        private const val TAG = "PlayIntegrity"

        // Google Cloud Project: ciris-oauth
        private const val CLOUD_PROJECT_NUMBER: Long = 265882853697L

        // Billing API base URL
        private const val BILLING_API_BASE = "https://billing.ciris.ai"
    }

    private val integrityManager = IntegrityManagerFactory.create(context)
    private val gson = Gson()

    // Cache the last successful nonce for reuse in auth flow
    private var cachedNonce: String? = null

    /**
     * Perform full integrity check flow.
     *
     * @return IntegrityResult with verification status and any error details
     */
    suspend fun verifyIntegrity(): IntegrityResult = withContext(Dispatchers.IO) {
        try {
            // Step 1: Get nonce from billing server
            Log.i(TAG, "Step 1: Fetching nonce from billing server...")
            val nonceResponse = fetchNonce()
            if (nonceResponse == null) {
                return@withContext IntegrityResult(
                    verified = false,
                    error = "Failed to fetch nonce from billing server"
                )
            }
            val nonce = nonceResponse.nonce
            cachedNonce = nonce
            Log.i(TAG, "Got nonce: ${nonce.take(20)}...")

            // Step 2: Request integrity token from Google Play
            Log.i(TAG, "Step 2: Requesting integrity token from Google Play...")
            val integrityToken = requestIntegrityToken(nonce)
            if (integrityToken == null) {
                return@withContext IntegrityResult(
                    verified = false,
                    error = "Failed to get integrity token from Google Play"
                )
            }
            Log.i(TAG, "Got integrity token: ${integrityToken.take(20)}...")

            // Step 3: Verify token with billing server (include nonce for replay protection)
            Log.i(TAG, "Step 3: Verifying token with billing server...")
            val verifyResponse = verifyToken(integrityToken, nonce)
            if (verifyResponse == null) {
                return@withContext IntegrityResult(
                    verified = false,
                    error = "Failed to verify token with billing server"
                )
            }

            Log.i(TAG, "Verification result: verified=${verifyResponse.verified}")
            if (verifyResponse.device_integrity != null) {
                Log.i(TAG, "Device integrity: ${verifyResponse.device_integrity.verdicts}")
            }
            if (verifyResponse.app_integrity != null) {
                Log.i(TAG, "App integrity: ${verifyResponse.app_integrity.verdict}")
            }
            if (verifyResponse.account_details != null) {
                Log.i(TAG, "License: ${verifyResponse.account_details.licensing_verdict}")
            }

            return@withContext IntegrityResult(
                verified = verifyResponse.verified,
                deviceIntegrity = verifyResponse.device_integrity?.verdicts,
                appIntegrity = verifyResponse.app_integrity?.verdict,
                licenseVerdict = verifyResponse.account_details?.licensing_verdict,
                error = verifyResponse.error
            )

        } catch (e: Exception) {
            Log.e(TAG, "Integrity check failed: ${e.message}", e)
            return@withContext IntegrityResult(
                verified = false,
                error = "Exception: ${e.message}"
            )
        }
    }

    /**
     * Perform combined JWT + integrity authentication.
     * Use this instead of separate token exchange when integrity is required.
     *
     * @param googleIdToken The Google ID token for authentication
     * @return IntegrityAuthResult with verification status
     */
    suspend fun authenticateWithIntegrity(googleIdToken: String): IntegrityAuthResult = withContext(Dispatchers.IO) {
        try {
            Log.i(TAG, "Starting combined integrity + auth flow...")

            // Get nonce
            val nonceResponse = fetchNonce() ?: return@withContext IntegrityAuthResult(
                success = false,
                error = "Failed to fetch nonce"
            )
            val nonce = nonceResponse.nonce
            cachedNonce = nonce

            // Get integrity token
            val integrityToken = requestIntegrityToken(nonce)
                ?: return@withContext IntegrityAuthResult(
                    success = false,
                    error = "Failed to get integrity token"
                )

            // Combined auth request - send Google ID token in Authorization header
            val url = URL("$BILLING_API_BASE/v1/integrity/auth")
            val connection = url.openConnection() as HttpURLConnection
            connection.apply {
                requestMethod = "POST"
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Authorization", "Bearer $googleIdToken")
                connectTimeout = 15000
                readTimeout = 15000
                doOutput = true
            }

            // Include both integrity token and nonce as per billing API spec
            val requestBody = gson.toJson(mapOf(
                "integrity_token" to integrityToken,
                "nonce" to nonce
            ))
            connection.outputStream.bufferedWriter().use { it.write(requestBody) }

            val responseCode = connection.responseCode
            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                Log.i(TAG, "Integrity auth response: ${response.take(200)}...")
                val authResponse = gson.fromJson(response, IntegrityAuthResponse::class.java)
                connection.disconnect()

                Log.i(TAG, "Integrity auth result: verified=${authResponse.verified}, user=${authResponse.user_email}")

                return@withContext IntegrityAuthResult(
                    success = authResponse.verified,
                    accessToken = authResponse.access_token,
                    integrityVerified = authResponse.verified,
                    userEmail = authResponse.user_email,
                    googleId = authResponse.google_id,
                    error = authResponse.error ?: if (!authResponse.verified) "Integrity verification failed" else null
                )
            } else {
                val error = connection.errorStream?.bufferedReader()?.use { it.readText() }
                Log.e(TAG, "Integrity auth failed: HTTP $responseCode - $error")
                connection.disconnect()
                return@withContext IntegrityAuthResult(
                    success = false,
                    error = "HTTP $responseCode: $error"
                )
            }

        } catch (e: Exception) {
            Log.e(TAG, "Integrity auth failed: ${e.message}", e)
            return@withContext IntegrityAuthResult(
                success = false,
                error = "Exception: ${e.message}"
            )
        }
    }

    /**
     * Fetch nonce from billing server.
     */
    private fun fetchNonce(): NonceResponse? {
        return try {
            val url = URL("$BILLING_API_BASE/v1/integrity/nonce")
            val connection = url.openConnection() as HttpURLConnection
            connection.apply {
                requestMethod = "GET"
                connectTimeout = 10000
                readTimeout = 10000
            }

            val responseCode = connection.responseCode
            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                connection.disconnect()
                gson.fromJson(response, NonceResponse::class.java)
            } else {
                Log.e(TAG, "Nonce request failed: HTTP $responseCode")
                connection.disconnect()
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Nonce request exception: ${e.message}")
            null
        }
    }

    /**
     * Request integrity token from Google Play.
     */
    private suspend fun requestIntegrityToken(nonce: String): String? {
        return try {
            if (CLOUD_PROJECT_NUMBER == 0L) {
                Log.e(TAG, "CLOUD_PROJECT_NUMBER not configured!")
                return null
            }

            val request = IntegrityTokenRequest.builder()
                .setNonce(nonce)
                .setCloudProjectNumber(CLOUD_PROJECT_NUMBER)
                .build()

            val task = integrityManager.requestIntegrityToken(request)
            val response = Tasks.await(task)

            response.token()
        } catch (e: Exception) {
            Log.e(TAG, "Integrity token request failed: ${e.message}", e)
            null
        }
    }

    /**
     * Verify integrity token with billing server.
     */
    private fun verifyToken(integrityToken: String, nonce: String): VerifyResponse? {
        return try {
            // Billing API expects query parameters
            val encodedToken = java.net.URLEncoder.encode(integrityToken, "UTF-8")
            val encodedNonce = java.net.URLEncoder.encode(nonce, "UTF-8")
            val url = URL("$BILLING_API_BASE/v1/integrity/verify?integrity_token=$encodedToken&nonce=$encodedNonce")
            val connection = url.openConnection() as HttpURLConnection
            connection.apply {
                requestMethod = "POST"
                connectTimeout = 15000
                readTimeout = 15000
            }

            val responseCode = connection.responseCode
            Log.i(TAG, "Verify request returned HTTP $responseCode")
            if (responseCode == 200) {
                val response = connection.inputStream.bufferedReader().use { it.readText() }
                Log.i(TAG, "Verify response: ${response.take(200)}...")
                connection.disconnect()
                val verifyResponse = gson.fromJson(response, VerifyResponse::class.java)
                // Check if server returned an error in the response
                if (verifyResponse.error != null) {
                    Log.e(TAG, "Verify returned error: ${verifyResponse.error}")
                }
                verifyResponse
            } else {
                val error = connection.errorStream?.bufferedReader()?.use { it.readText() }
                Log.e(TAG, "Verify request failed: HTTP $responseCode - $error")
                connection.disconnect()
                null
            }
        } catch (e: Exception) {
            Log.e(TAG, "Verify request exception: ${e.message}")
            null
        }
    }

    // Response models matching billing.ciris.ai API spec
    data class NonceResponse(
        val nonce: String,
        val expires_at: String?
    )

    data class VerifyResponse(
        val verified: Boolean,
        val device_integrity: DeviceIntegrity?,
        val app_integrity: AppIntegrity?,
        val account_details: AccountDetails?,
        val error: String?
    )

    data class DeviceIntegrity(
        val meets_strong_integrity: Boolean?,
        val meets_device_integrity: Boolean?,
        val meets_basic_integrity: Boolean?,
        val verdicts: List<String>?
    )

    data class AppIntegrity(
        val verdict: String?,
        val package_name: String?,
        val version_code: String?
    )

    data class AccountDetails(
        val licensing_verdict: String?
    )

    data class IntegrityAuthResponse(
        val verified: Boolean,
        val user_email: String?,
        val google_id: String?,
        val device_integrity: DeviceIntegrity?,
        val app_integrity: AppIntegrity?,
        val access_token: String?,
        val error: String?
    )
}

/**
 * Result of integrity verification.
 */
data class IntegrityResult(
    val verified: Boolean,
    val deviceIntegrity: List<String>? = null,
    val appIntegrity: String? = null,
    val licenseVerdict: String? = null,
    val error: String? = null
)

/**
 * Result of combined integrity + auth flow.
 */
data class IntegrityAuthResult(
    val success: Boolean,
    val accessToken: String? = null,
    val integrityVerified: Boolean? = null,
    val userEmail: String? = null,
    val googleId: String? = null,
    val error: String? = null
)
