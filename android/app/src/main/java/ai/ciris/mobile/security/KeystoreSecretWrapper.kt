package ai.ciris.mobile.security

import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import android.util.Log
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Wraps/unwraps secrets using Android Keystore.
 *
 * This provides hardware-backed key protection on devices with secure elements.
 * The wrapping key never leaves the Keystore - only wrapped data is stored on disk.
 */
object KeystoreSecretWrapper {
    private const val TAG = "KeystoreSecretWrapper"
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val WRAPPER_KEY_ALIAS = "ciris_secrets_wrapper_key"
    private const val TRANSFORMATION = "AES/GCM/NoPadding"
    private const val GCM_TAG_LENGTH = 128
    private const val GCM_IV_LENGTH = 12

    /**
     * Wrap (encrypt) a secret key using Android Keystore.
     *
     * @param plainKey The raw secret key bytes to wrap
     * @return Base64-encoded wrapped key (IV + ciphertext), or null on error
     */
    @JvmStatic
    fun wrapKey(plainKey: ByteArray): String? {
        return try {
            val wrapperKey = getOrCreateWrapperKey()
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, wrapperKey)

            val iv = cipher.iv
            val encryptedKey = cipher.doFinal(plainKey)

            // Prepend IV to ciphertext
            val combined = ByteArray(iv.size + encryptedKey.size)
            System.arraycopy(iv, 0, combined, 0, iv.size)
            System.arraycopy(encryptedKey, 0, combined, iv.size, encryptedKey.size)

            Base64.encodeToString(combined, Base64.NO_WRAP)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to wrap key", e)
            null
        }
    }

    /**
     * Unwrap (decrypt) a secret key using Android Keystore.
     *
     * @param wrappedKeyBase64 Base64-encoded wrapped key (IV + ciphertext)
     * @return The unwrapped raw secret key bytes, or null on error
     */
    @JvmStatic
    fun unwrapKey(wrappedKeyBase64: String): ByteArray? {
        return try {
            val combined = Base64.decode(wrappedKeyBase64, Base64.NO_WRAP)

            if (combined.size < GCM_IV_LENGTH + 1) {
                Log.e(TAG, "Wrapped key too short")
                return null
            }

            // Extract IV and ciphertext
            val iv = combined.copyOfRange(0, GCM_IV_LENGTH)
            val encryptedKey = combined.copyOfRange(GCM_IV_LENGTH, combined.size)

            val wrapperKey = getWrapperKey() ?: run {
                Log.e(TAG, "Wrapper key not found in Keystore")
                return null
            }

            val cipher = Cipher.getInstance(TRANSFORMATION)
            val spec = GCMParameterSpec(GCM_TAG_LENGTH, iv)
            cipher.init(Cipher.DECRYPT_MODE, wrapperKey, spec)

            cipher.doFinal(encryptedKey)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to unwrap key", e)
            null
        }
    }

    /**
     * Check if a wrapper key exists in the Keystore.
     */
    @JvmStatic
    fun hasWrapperKey(): Boolean {
        return try {
            val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE)
            keyStore.load(null)
            keyStore.containsAlias(WRAPPER_KEY_ALIAS)
        } catch (e: Exception) {
            Log.e(TAG, "Failed to check wrapper key", e)
            false
        }
    }

    /**
     * Delete the wrapper key from Keystore (for key rotation).
     * WARNING: This will make all previously wrapped keys unrecoverable!
     */
    @JvmStatic
    fun deleteWrapperKey(): Boolean {
        return try {
            val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE)
            keyStore.load(null)
            if (keyStore.containsAlias(WRAPPER_KEY_ALIAS)) {
                keyStore.deleteEntry(WRAPPER_KEY_ALIAS)
                Log.i(TAG, "Wrapper key deleted from Keystore")
            }
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to delete wrapper key", e)
            false
        }
    }

    private fun getOrCreateWrapperKey(): SecretKey {
        return getWrapperKey() ?: createWrapperKey()
    }

    private fun getWrapperKey(): SecretKey? {
        return try {
            val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE)
            keyStore.load(null)
            keyStore.getKey(WRAPPER_KEY_ALIAS, null) as? SecretKey
        } catch (e: Exception) {
            Log.e(TAG, "Failed to get wrapper key", e)
            null
        }
    }

    private fun createWrapperKey(): SecretKey {
        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES,
            ANDROID_KEYSTORE
        )

        val spec = KeyGenParameterSpec.Builder(
            WRAPPER_KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            // Require user authentication for extra security (optional)
            // .setUserAuthenticationRequired(true)
            // .setUserAuthenticationValidityDurationSeconds(300)
            .build()

        keyGenerator.init(spec)
        val key = keyGenerator.generateKey()
        Log.i(TAG, "Created new wrapper key in Android Keystore")
        return key
    }
}
