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

    private val envFile: File by lazy {
        File(System.getenv("CIRIS_HOME") ?: "${System.getProperty("user.home")}/ciris", ".env")
    }

    private fun readEnvVars(): MutableMap<String, String> {
        val envVars = mutableMapOf<String, String>()
        if (envFile.exists()) {
            envFile.readLines().forEach { line ->
                val trimmed = line.trim()
                if (trimmed.isNotEmpty() && !trimmed.startsWith("#") && trimmed.contains("=")) {
                    val (k, v) = trimmed.split("=", limit = 2)
                    envVars[k.trim()] = v.trim().removeSurrounding("\"")
                }
            }
        }
        return envVars
    }

    private fun getEnvKeyName(provider: String): String = when (provider.lowercase()) {
        "openrouter" -> "OPENAI_API_KEY"  // OpenRouter uses OPENAI_API_KEY with custom base URL
        "openai" -> "OPENAI_API_KEY"
        "anthropic" -> "ANTHROPIC_API_KEY"
        else -> "OPENAI_API_KEY"
    }

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> = runCatching {
        // Save to Java Preferences (cache)
        prefs.put("apikey_$key", encrypt(value))
        prefs.flush()

        // Save to .env file (source of truth)
        val envKeyName = getEnvKeyName(key)
        val envVars = readEnvVars()
        envVars[envKeyName] = value

        // Rebuild .env file preserving comments and order
        val lines = if (envFile.exists()) envFile.readLines().toMutableList() else mutableListOf()
        var found = false
        for (i in lines.indices) {
            val trimmed = lines[i].trim()
            if (trimmed.startsWith("$envKeyName=")) {
                lines[i] = "$envKeyName=\"$value\""
                found = true
                break
            }
        }
        if (!found) {
            lines.add("$envKeyName=\"$value\"")
        }
        envFile.parentFile?.mkdirs()
        envFile.writeText(lines.joinToString("\n"))
    }

    actual suspend fun getApiKey(key: String): Result<String?> = runCatching {
        // Read from .env file (source of truth)
        val envVars = readEnvVars()
        val envKeyName = getEnvKeyName(key)
        val envValue = envVars[envKeyName]
        if (!envValue.isNullOrEmpty()) {
            return@runCatching envValue
        }

        // Fall back to Java Preferences (legacy/cache)
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
