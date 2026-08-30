package ai.ciris.mobile.integrity

import ai.ciris.mobile.shared.api.CIRISApiClient
import android.content.Context
import android.util.Log
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Manages Google Play Integrity attestation flow via Python API:
 * 1. Get nonce from Python backend (which calls CIRISVerify FFI)
 * 2. Request token from Google Play Integrity API
 * 3. Verify token via Python backend (which calls CIRISVerify FFI)
 *
 * IMPORTANT: All CIRISVerify calls go through Python to ensure single instance.
 */
class PlayIntegrityManager(
    private val context: Context,
    private val apiClient: CIRISApiClient
) {
    companion object {
        private const val TAG = "PlayIntegrityManager"
    }

    private val integrityManager = IntegrityManagerFactory.create(context)

    /**
     * Perform full Play Integrity attestation via Python API.
     * @return PlayIntegrityResult with attestation details
     */
    suspend fun attestDevice(): PlayIntegrityResult = withContext(Dispatchers.IO) {
        Log.i(TAG, "Starting Play Integrity attestation via Python API...")

        // Step 1: Get nonce from Python backend
        val nonceResult = try {
            apiClient.getPlayIntegrityNonce()
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get nonce from API: ${e.message}")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to get nonce: ${e.message}"
            )
        }

        if (nonceResult.error != null) {
            Log.e(TAG, "Nonce request failed: ${nonceResult.error}")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = nonceResult.error
            )
        }

        val nonce = nonceResult.nonce
        if (nonce == null) {
            Log.e(TAG, "No nonce in response")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "No nonce returned from server"
            )
        }

        Log.d(TAG, "Got nonce from Python API: ${nonce.take(20)}...")

        // Step 2: Request token from Google Play Integrity API
        val token = try {
            requestIntegrityToken(nonce)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get Play Integrity token: ${e.message}")

            // Extract error code from exception message (e.g., "-16: Integrity API error")
            val errorCode = Regex("""-(\d+):""").find(e.message ?: "")?.groupValues?.get(1)?.toIntOrNull() ?: -1

            // Report failure to CIRISVerify so level_pending becomes false (v1.5.3+)
            try {
                apiClient.reportPlayIntegrityFailed(errorCode, e.message ?: "Unknown error")
                Log.i(TAG, "Reported Play Integrity failure to CIRISVerify")
            } catch (reportError: Exception) {
                Log.w(TAG, "Failed to report Play Integrity failure: ${reportError.message}")
            }

            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to get Play Integrity token: ${e.message}"
            )
        }

        Log.d(TAG, "Got Play Integrity token: ${token.take(50)}...")

        // Step 3: Verify token via Python backend
        val verifyResult = try {
            apiClient.verifyPlayIntegrity(token, nonce)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to verify token via API: ${e.message}")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to verify token: ${e.message}"
            )
        }

        if (verifyResult.error != null) {
            Log.w(TAG, "Play Integrity verification failed: ${verifyResult.error}")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = verifyResult.error
            )
        }

        if (verifyResult.verified) {
            Log.i(TAG, "Play Integrity verified: ${verifyResult.verdict}")
            return@withContext PlayIntegrityResult(
                verified = true,
                verdict = verifyResult.verdict,
                meetsStrongIntegrity = verifyResult.meetsStrongIntegrity,
                meetsDeviceIntegrity = verifyResult.meetsDeviceIntegrity,
                meetsBasicIntegrity = verifyResult.meetsBasicIntegrity
            )
        } else {
            Log.w(TAG, "Play Integrity not verified")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Verification returned false"
            )
        }
    }

    /**
     * Request integrity token from Google Play Integrity API.
     */
    private suspend fun requestIntegrityToken(nonce: String): String {
        return suspendCancellableCoroutine { continuation ->
            val request = IntegrityTokenRequest.builder()
                .setNonce(nonce)
                .build()

            integrityManager.requestIntegrityToken(request)
                .addOnSuccessListener { response ->
                    continuation.resume(response.token())
                }
                .addOnFailureListener { e ->
                    continuation.resumeWithException(e)
                }
        }
    }
}

/**
 * Result of Play Integrity attestation.
 */
data class PlayIntegrityResult(
    val verified: Boolean,
    val verdict: String? = null,
    val meetsStrongIntegrity: Boolean = false,
    val meetsDeviceIntegrity: Boolean = false,
    val meetsBasicIntegrity: Boolean = false,
    val error: String? = null
)
