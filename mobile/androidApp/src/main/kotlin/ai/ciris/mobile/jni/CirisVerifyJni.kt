package ai.ciris.mobile.jni

import android.util.Log

/**
 * JNI wrapper for libciris_verify_ffi.so
 *
 * NOTE: The native library currently does NOT export JNI functions.
 * The library is built for Python FFI (ctypes/cffi), not JNI.
 * JNI requires specific C function names like:
 *   Java_ai_ciris_mobile_jni_CirisVerifyJni_nativeGetIntegrityNonce
 *
 * Until ciris-verify is updated to export JNI functions, Play Integrity
 * via native calls is disabled. The 5-level attestation still works
 * through Python (Chaquopy).
 */
object CirisVerifyJni {
    private const val TAG = "CirisVerifyJni"

    // JNI is not available - native library doesn't export JNI functions
    // The library is loaded by Python/Chaquopy, but we can't call it via JNI

    /**
     * Check if the native library is loaded with JNI support.
     * Currently always returns false - JNI not available.
     */
    fun isLoaded(): Boolean {
        Log.d(TAG, "JNI not available - native library doesn't export JNI functions")
        return false
    }

    /**
     * Get a nonce from the registry for Play Integrity API.
     * Currently not available - JNI not supported.
     */
    fun getIntegrityNonce(): String? {
        Log.d(TAG, "getIntegrityNonce not available - JNI not supported")
        return null
    }

    /**
     * Verify a Play Integrity token via the registry.
     * Currently not available - JNI not supported.
     */
    fun verifyIntegrityToken(token: String, nonce: String): String? {
        Log.d(TAG, "verifyIntegrityToken not available - JNI not supported")
        return null
    }
}
