package ai.ciris.mobile.integrity

import ai.ciris.verify.CirisVerify
import android.content.Context
import android.util.Log
import com.google.android.play.core.integrity.IntegrityManagerFactory
import com.google.android.play.core.integrity.IntegrityTokenRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONObject
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Manages Google Play Integrity attestation flow:
 * 1. Get nonce from CIRISVerify registry
 * 2. Request token from Google Play Integrity API
 * 3. Verify token via CIRISVerify registry
 */
class PlayIntegrityManager(private val context: Context) {
    companion object {
        private const val TAG = "PlayIntegrityManager"
    }

    private val integrityManager = IntegrityManagerFactory.create(context)
    private var cirisVerify: CirisVerify? = null

    /**
     * Initialize the manager.
     * @return true if library is available and initialized
     */
    fun initialize(): Boolean {
        if (!CirisVerify.isLibraryLoaded()) {
            Log.e(TAG, "CIRISVerify native library not loaded")
            return false
        }

        cirisVerify = CirisVerify()
        val initialized = cirisVerify?.initialize() ?: false
        Log.i(TAG, "PlayIntegrityManager initialized: $initialized")

        // Note: Skip version() call - JNI returns byte[] but we declared String?
        // This causes a JNI crash. Version can be checked via Python side.

        return initialized
    }

    /**
     * Perform full Play Integrity attestation.
     * @return PlayIntegrityResult with attestation details
     */
    suspend fun attestDevice(): PlayIntegrityResult = withContext(Dispatchers.IO) {
        Log.i(TAG, "Starting Play Integrity attestation...")

        val verifier = cirisVerify
        if (verifier == null) {
            Log.e(TAG, "CIRISVerify not initialized")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "CIRISVerify not initialized"
            )
        }

        // Step 1: Get nonce from registry
        val nonceJson = verifier.getIntegrityNonce()
        if (nonceJson == null) {
            Log.e(TAG, "Failed to get nonce from registry")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to get nonce from registry"
            )
        }

        val nonce = try {
            JSONObject(nonceJson).getString("nonce")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse nonce JSON: ${e.message}")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to parse nonce: ${e.message}"
            )
        }

        Log.d(TAG, "Got nonce from registry: ${nonce.take(20)}...")

        // Step 2: Request token from Google Play Integrity API
        val token = try {
            requestIntegrityToken(nonce)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get Play Integrity token: ${e.message}")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to get Play Integrity token: ${e.message}"
            )
        }

        Log.d(TAG, "Got Play Integrity token: ${token.take(50)}...")

        // Step 3: Verify token via registry
        val resultJson = verifier.verifyIntegrityToken(token, nonce)
        if (resultJson == null) {
            Log.e(TAG, "Failed to verify token via registry")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to verify token via registry"
            )
        }

        // Parse result
        try {
            val result = JSONObject(resultJson)
            val verified = result.optBoolean("verified", false)

            if (verified) {
                val deviceIntegrity = result.optJSONObject("device_integrity")
                val verdict = parseDeviceIntegrity(deviceIntegrity)

                Log.i(TAG, "Play Integrity verified: $verdict")
                return@withContext PlayIntegrityResult(
                    verified = true,
                    verdict = verdict,
                    meetsStrongIntegrity = deviceIntegrity?.optBoolean("meets_strong_integrity") ?: false,
                    meetsDeviceIntegrity = deviceIntegrity?.optBoolean("meets_device_integrity") ?: false,
                    meetsBasicIntegrity = deviceIntegrity?.optBoolean("meets_basic_integrity") ?: false
                )
            } else {
                val error = result.optString("error", "Verification failed")
                Log.w(TAG, "Play Integrity verification failed: $error")
                return@withContext PlayIntegrityResult(
                    verified = false,
                    error = error
                )
            }
        } catch (e: Exception) {
            Log.e(TAG, "Failed to parse verification result: ${e.message}")
            return@withContext PlayIntegrityResult(
                verified = false,
                error = "Failed to parse result: ${e.message}"
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

    /**
     * Parse device integrity verdict into a human-readable string.
     */
    private fun parseDeviceIntegrity(integrity: JSONObject?): String {
        if (integrity == null) return "UNKNOWN"

        return when {
            integrity.optBoolean("meets_strong_integrity") -> "MEETS_STRONG_INTEGRITY"
            integrity.optBoolean("meets_device_integrity") -> "MEETS_DEVICE_INTEGRITY"
            integrity.optBoolean("meets_basic_integrity") -> "MEETS_BASIC_INTEGRITY"
            else -> "NO_INTEGRITY"
        }
    }

    /**
     * Clean up resources.
     */
    fun destroy() {
        cirisVerify?.destroy()
        cirisVerify = null
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
