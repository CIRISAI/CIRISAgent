package ai.ciris.mobile.shared.platform

import java.io.File
import java.util.prefs.Preferences
import javax.crypto.Cipher
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.IvParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec
import java.security.SecureRandom
import java.util.Base64

/**
 * Desktop SecureStorage implementation using Java Preferences with AES encryption.
 * Stores encrypted values in the system preferences.
 */
actual class SecureStorage actual constructor() {
    private val prefs = Preferences.userNodeForPackage(SecureStorage::class.java)
    private val secretKey: SecretKeySpec by lazy { deriveKey() }

    private fun deriveKey(): SecretKeySpec {
        // Use machine-specific key derivation
        val machineId = System.getProperty("user.name") + System.getProperty("os.name")
        val salt = "CIRISDesktopSalt".toByteArray()
        val factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256")
        val spec = PBEKeySpec(machineId.toCharArray(), salt, 65536, 256)
        val key = factory.generateSecret(spec).encoded
        return SecretKeySpec(key, "AES")
    }

    private fun encrypt(value: String): String {
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        val iv = ByteArray(16)
        SecureRandom().nextBytes(iv)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey, IvParameterSpec(iv))
        val encrypted = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val combined = iv + encrypted
        return Base64.getEncoder().encodeToString(combined)
    }

    private fun decrypt(value: String): String {
        val combined = Base64.getDecoder().decode(value)
        val iv = combined.sliceArray(0 until 16)
        val encrypted = combined.sliceArray(16 until combined.size)
        val cipher = Cipher.getInstance("AES/CBC/PKCS5Padding")
        cipher.init(Cipher.DECRYPT_MODE, secretKey, IvParameterSpec(iv))
        return String(cipher.doFinal(encrypted), Charsets.UTF_8)
    }

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> = runCatching {
        prefs.put("apikey_$key", encrypt(value))
        prefs.flush()
    }

    actual suspend fun getApiKey(key: String): Result<String?> = runCatching {
        prefs.get("apikey_$key", null)?.let { decrypt(it) }
    }

    actual suspend fun saveAccessToken(token: String): Result<Unit> = runCatching {
        prefs.put("access_token", encrypt(token))
        prefs.flush()
    }

    actual suspend fun getAccessToken(): Result<String?> = runCatching {
        prefs.get("access_token", null)?.let { decrypt(it) }
    }

    actual suspend fun deleteAccessToken(): Result<Unit> = runCatching {
        prefs.remove("access_token")
        prefs.flush()
    }

    actual suspend fun save(key: String, value: String): Result<Unit> = runCatching {
        prefs.put(key, encrypt(value))
        prefs.flush()
    }

    actual suspend fun get(key: String): Result<String?> = runCatching {
        prefs.get(key, null)?.let { decrypt(it) }
    }

    actual suspend fun delete(key: String): Result<Unit> = runCatching {
        prefs.remove(key)
        prefs.flush()
    }

    actual suspend fun clear(): Result<Unit> = runCatching {
        prefs.clear()
        prefs.flush()
    }
}

actual fun createSecureStorage(): SecureStorage = SecureStorage()
