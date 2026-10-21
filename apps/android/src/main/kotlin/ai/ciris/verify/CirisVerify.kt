package ai.ciris.verify

import android.content.Context
import android.util.Log
import java.io.File

/**
 * JNI wrapper for libciris_verify_ffi.so
 *
 * This class MUST be in package ai.ciris.verify to match the native JNI exports:
 * - Java_ai_ciris_verify_CirisVerify_nativeInit
 * - Java_ai_ciris_verify_CirisVerify_nativeGetIntegrityNonce
 * - etc.
 */
class CirisVerify {
    companion object {
        private const val TAG = "CirisVerify"
        private var libraryLoaded = false
        private var loadError: String? = null
        private var initialized = false

        /**
         * Initialize CirisVerify with Android context.
         * MUST be called before using the library to set up environment variables.
         *
         * Call this from Application.onCreate() to ensure paths are set before
         * any native code runs.
         */
        @JvmStatic
        fun setup(context: Context) {
            if (initialized) {
                Log.d(TAG, "Already initialized, skipping setup")
                return
            }

            Log.i(TAG, "=== CirisVerify.setup() starting ===")

            // Set CIRIS_DATA_DIR environment variable BEFORE loading native library
            // This is critical for Ed25519 key storage to work correctly
            val cirisDataDir = File(context.filesDir, "ciris/data")
            cirisDataDir.mkdirs()
            val cirisHome = File(context.filesDir, "ciris").absolutePath

            // Get native library directory for executable binaries (llama-server, etc.)
            val nativeLibDir = context.applicationInfo.nativeLibraryDir

            // IMPORTANT: Use android.system.Os.setenv() for native code to see the env vars
            // Java's System.getenv() reflection hack only affects Java code, not native!
            var nativeEnvSet = false
            try {
                // API 21+ direct call - this actually calls native setenv()
                android.system.Os.setenv("CIRIS_DATA_DIR", cirisDataDir.absolutePath, true)
                android.system.Os.setenv("CIRIS_HOME", cirisHome, true)
                android.system.Os.setenv("CIRIS_NATIVE_LIB_DIR", nativeLibDir, true)
                nativeEnvSet = true
                Log.i(TAG, "Set CIRIS_DATA_DIR=${cirisDataDir.absolutePath} via Os.setenv (native)")
                Log.i(TAG, "Set CIRIS_NATIVE_LIB_DIR=${nativeLibDir} via Os.setenv (native)")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to set env via Os.setenv: ${e.message}")
                // Try reflection as fallback (for older API levels)
                try {
                    val osClass = Class.forName("android.system.Os")
                    val setenvMethod = osClass.getMethod("setenv", String::class.java, String::class.java, Boolean::class.javaPrimitiveType)
                    setenvMethod.invoke(null, "CIRIS_DATA_DIR", cirisDataDir.absolutePath, true)
                    setenvMethod.invoke(null, "CIRIS_HOME", cirisHome, true)
                    setenvMethod.invoke(null, "CIRIS_NATIVE_LIB_DIR", nativeLibDir, true)
                    nativeEnvSet = true
                    Log.i(TAG, "Set CIRIS_DATA_DIR=${cirisDataDir.absolutePath} via Os.setenv (reflection)")
                    Log.i(TAG, "Set CIRIS_NATIVE_LIB_DIR=${nativeLibDir} via Os.setenv (reflection)")
                } catch (e2: Exception) {
                    Log.e(TAG, "Failed to set env via Os.setenv reflection: ${e2.message}")
                }
            }

            // Also set in Java's env map for any Java code that checks
            try {
                val env = System.getenv()
                val cl = env.javaClass
                val field = cl.getDeclaredField("m")
                field.isAccessible = true
                @Suppress("UNCHECKED_CAST")
                val writableEnv = field.get(env) as MutableMap<String, String>
                writableEnv["CIRIS_DATA_DIR"] = cirisDataDir.absolutePath
                writableEnv["CIRIS_HOME"] = cirisHome
                writableEnv["CIRIS_NATIVE_LIB_DIR"] = nativeLibDir
                Log.d(TAG, "Also set CIRIS_DATA_DIR and CIRIS_NATIVE_LIB_DIR in Java env map")
            } catch (e: Exception) {
                Log.w(TAG, "Could not set Java env map (non-critical): ${e.message}")
            }

            if (!nativeEnvSet) {
                Log.e(TAG, "WARNING: Could not set native env vars - Ed25519 key persistence may fail!")
            }

            // Now load the native library
            loadLibrary()
            initialized = true
            Log.i(TAG, "=== CirisVerify.setup() complete ===")
        }

        private fun loadLibrary() {
            Log.w(TAG, "=== CirisVerify loading native library ===")
            try {
                Log.i(TAG, "Attempting to load ciris_verify_ffi...")
                System.loadLibrary("ciris_verify_ffi")
                libraryLoaded = true
                Log.i(TAG, "libciris_verify_ffi.so loaded successfully via JNI")
            } catch (e: UnsatisfiedLinkError) {
                loadError = e.message ?: e.toString()
                Log.e(TAG, "UnsatisfiedLinkError loading libciris_verify_ffi.so: $loadError")
                Log.e(TAG, "Stack trace: ${e.stackTraceToString()}")
                libraryLoaded = false
            } catch (e: Exception) {
                loadError = e.message ?: e.toString()
                Log.e(TAG, "Exception loading libciris_verify_ffi.so: $loadError")
                libraryLoaded = false
            }
            Log.w(TAG, "=== CirisVerify library load complete: loaded=$libraryLoaded ===")
        }

        fun isLibraryLoaded(): Boolean {
            // Auto-initialize if someone calls this without setup()
            // (for backwards compatibility, though env vars won't be set)
            if (!initialized && !libraryLoaded) {
                Log.w(TAG, "isLibraryLoaded() called before setup() - loading without context")
                loadLibrary()
            }
            Log.d(TAG, "isLibraryLoaded() called, returning $libraryLoaded (error: $loadError)")
            return libraryLoaded
        }
    }

    private var handle: Long = 0

    /**
     * Initialize the CIRISVerify instance.
     * @return true if initialization succeeded
     */
    fun initialize(): Boolean {
        if (!libraryLoaded) {
            Log.e(TAG, "Cannot initialize - library not loaded")
            return false
        }
        return try {
            handle = nativeInit()
            val success = handle != 0L
            Log.i(TAG, "Initialized: handle=$handle, success=$success")
            success
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize: ${e.message}")
            false
        }
    }

    /**
     * Get the library version.
     */
    fun version(): String? {
        if (handle == 0L) return null
        return try {
            nativeVersion(handle)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get version: ${e.message}")
            null
        }
    }

    /**
     * Get a nonce from the registry for Play Integrity API.
     * @return JSON string with "nonce" field, or null on error
     */
    fun getIntegrityNonce(): String? {
        if (handle == 0L) {
            Log.e(TAG, "Cannot get nonce - not initialized")
            return null
        }
        return try {
            val result = nativeGetIntegrityNonce(handle)
            Log.d(TAG, "Got integrity nonce: ${result?.take(50)}...")
            result
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get integrity nonce: ${e.message}")
            null
        }
    }

    /**
     * Verify a Play Integrity token via the registry.
     * @param token The token from Google Play Integrity API
     * @param nonce The nonce used when requesting the token
     * @return JSON string with verification result, or null on error
     */
    fun verifyIntegrityToken(token: String, nonce: String): String? {
        if (handle == 0L) {
            Log.e(TAG, "Cannot verify token - not initialized")
            return null
        }
        return try {
            val result = nativeVerifyIntegrityToken(handle, token, nonce)
            Log.d(TAG, "Verify integrity result: ${result?.take(100)}...")
            result
        } catch (e: Exception) {
            Log.e(TAG, "Failed to verify integrity token: ${e.message}")
            null
        }
    }

    /**
     * Run full attestation.
     * @param challenge Challenge bytes (hex string)
     * @param agentVersion Agent version string
     * @param agentRoot Agent root directory path
     * @return JSON string with attestation result
     */
    fun runAttestation(challenge: String, agentVersion: String, agentRoot: String): String? {
        if (handle == 0L) {
            Log.e(TAG, "Cannot run attestation - not initialized")
            return null
        }
        return try {
            val result = nativeRunAttestation(handle, challenge, agentVersion, agentRoot)
            Log.d(TAG, "Attestation result: ${result?.take(200)}...")
            result
        } catch (e: Exception) {
            Log.e(TAG, "Failed to run attestation: ${e.message}")
            null
        }
    }

    /**
     * Get license status.
     * @return JSON string with status
     */
    fun getStatus(): String? {
        if (handle == 0L) return null
        return try {
            nativeGetStatus(handle)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get status: ${e.message}")
            null
        }
    }

    /**
     * Clean up native resources.
     */
    fun destroy() {
        if (handle != 0L) {
            try {
                nativeDestroy(handle)
                Log.i(TAG, "Destroyed handle=$handle")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to destroy: ${e.message}")
            }
            handle = 0
        }
    }

    // Native methods - must match JNI exports exactly
    private external fun nativeInit(): Long
    private external fun nativeDestroy(handle: Long)
    private external fun nativeVersion(handle: Long): String?
    private external fun nativeGetStatus(handle: Long): String?
    private external fun nativeGetIntegrityNonce(handle: Long): String?
    private external fun nativeVerifyIntegrityToken(handle: Long, token: String, nonce: String): String?
    private external fun nativeRunAttestation(handle: Long, challenge: String, agentVersion: String, agentRoot: String): String?
    private external fun nativeExportAttestation(handle: Long, challenge: String): String?
    private external fun nativeGetPublicKey(handle: Long): String?
    private external fun nativeGetEd25519PublicKey(handle: Long): String?
    private external fun nativeSign(handle: Long, data: String): String?
    private external fun nativeSignEd25519(handle: Long, data: String): String?
    private external fun nativeHasKey(handle: Long, alias: String): Boolean
    private external fun nativeImportKey(handle: Long, alias: String, keyData: String): Boolean
    private external fun nativeDeleteKey(handle: Long, alias: String): Boolean
}
