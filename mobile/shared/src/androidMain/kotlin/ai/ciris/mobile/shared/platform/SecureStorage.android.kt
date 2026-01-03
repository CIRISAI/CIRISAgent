package ai.ciris.mobile.shared.platform

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Android implementation using EncryptedSharedPreferences
 * Provides AES-256 encryption for sensitive data
 *
 * Note: Context must be set via companion object before use
 */
actual class SecureStorage {

    companion object {
        private var appContext: Context? = null

        /**
         * Set the application context (call from Application.onCreate())
         */
        fun setContext(context: Context) {
            appContext = context.applicationContext
        }
    }

    private val masterKey: MasterKey? by lazy {
        appContext?.let { ctx ->
            MasterKey.Builder(ctx)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()
        }
    }

    private val sharedPrefs: SharedPreferences? by lazy {
        appContext?.let { ctx ->
            masterKey?.let { key ->
                EncryptedSharedPreferences.create(
                    ctx,
                    "ciris_secure_prefs",
                    key,
                    EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                    EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
                )
            }
        }
    }

    // Fallback in-memory storage when context isn't available
    private val memoryStorage = mutableMapOf<String, String>()

    private fun getPrefs(): SharedPreferences? = sharedPrefs

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            if (prefs != null) {
                prefs.edit().putString("api_key_$key", value).apply()
            } else {
                memoryStorage["api_key_$key"] = value
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to save API key: ${e.message}", e))
        }
    }

    actual suspend fun getApiKey(key: String): Result<String?> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            val value = if (prefs != null) {
                prefs.getString("api_key_$key", null)
            } else {
                memoryStorage["api_key_$key"]
            }
            Result.success(value)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to get API key: ${e.message}", e))
        }
    }

    actual suspend fun saveAccessToken(token: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            if (prefs != null) {
                prefs.edit().putString("access_token", token).apply()
            } else {
                memoryStorage["access_token"] = token
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to save access token: ${e.message}", e))
        }
    }

    actual suspend fun getAccessToken(): Result<String?> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            val token = if (prefs != null) {
                prefs.getString("access_token", null)
            } else {
                memoryStorage["access_token"]
            }
            Result.success(token)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to get access token: ${e.message}", e))
        }
    }

    actual suspend fun deleteAccessToken(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            if (prefs != null) {
                prefs.edit().remove("access_token").apply()
            } else {
                memoryStorage.remove("access_token")
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to delete access token: ${e.message}", e))
        }
    }

    actual suspend fun save(key: String, value: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            if (prefs != null) {
                prefs.edit().putString(key, value).apply()
            } else {
                memoryStorage[key] = value
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to save: ${e.message}", e))
        }
    }

    actual suspend fun get(key: String): Result<String?> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            val value = if (prefs != null) {
                prefs.getString(key, null)
            } else {
                memoryStorage[key]
            }
            Result.success(value)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to get: ${e.message}", e))
        }
    }

    actual suspend fun delete(key: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            if (prefs != null) {
                prefs.edit().remove(key).apply()
            } else {
                memoryStorage.remove(key)
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to delete: ${e.message}", e))
        }
    }

    actual suspend fun clear(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            val prefs = getPrefs()
            if (prefs != null) {
                prefs.edit().clear().apply()
            } else {
                memoryStorage.clear()
            }
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to clear: ${e.message}", e))
        }
    }
}

/**
 * Factory function
 */
actual fun createSecureStorage(): SecureStorage = SecureStorage()
