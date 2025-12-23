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
 * Based on android/app/.../SettingsActivity.kt secure storage
 */
actual class SecureStorage(private val context: Context) {

    private val masterKey: MasterKey by lazy {
        MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
    }

    private val sharedPrefs: SharedPreferences by lazy {
        EncryptedSharedPreferences.create(
            context,
            "ciris_secure_prefs",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            sharedPrefs.edit().putString("api_key_$key", value).apply()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to save API key: ${e.message}", e))
        }
    }

    actual suspend fun getApiKey(key: String): Result<String?> = withContext(Dispatchers.IO) {
        try {
            val value = sharedPrefs.getString("api_key_$key", null)
            Result.success(value)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to get API key: ${e.message}", e))
        }
    }

    actual suspend fun saveAccessToken(token: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            sharedPrefs.edit().putString("access_token", token).apply()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to save access token: ${e.message}", e))
        }
    }

    actual suspend fun getAccessToken(): Result<String?> = withContext(Dispatchers.IO) {
        try {
            val token = sharedPrefs.getString("access_token", null)
            Result.success(token)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to get access token: ${e.message}", e))
        }
    }

    actual suspend fun deleteAccessToken(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            sharedPrefs.edit().remove("access_token").apply()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to delete access token: ${e.message}", e))
        }
    }

    actual suspend fun save(key: String, value: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            sharedPrefs.edit().putString(key, value).apply()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to save: ${e.message}", e))
        }
    }

    actual suspend fun get(key: String): Result<String?> = withContext(Dispatchers.IO) {
        try {
            val value = sharedPrefs.getString(key, null)
            Result.success(value)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to get: ${e.message}", e))
        }
    }

    actual suspend fun delete(key: String): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            sharedPrefs.edit().remove(key).apply()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to delete: ${e.message}", e))
        }
    }

    actual suspend fun clear(): Result<Unit> = withContext(Dispatchers.IO) {
        try {
            sharedPrefs.edit().clear().apply()
            Result.success(Unit)
        } catch (e: Exception) {
            Result.failure(Exception("Failed to clear: ${e.message}", e))
        }
    }
}

/**
 * Factory function - requires Android Context
 * Note: This will be provided by the Android application
 */
actual fun createSecureStorage(): SecureStorage {
    // This will throw if called without context
    // In practice, Android app will create this with proper context
    throw IllegalStateException("createSecureStorage() requires Context. Use SecureStorage(context) directly.")
}

/**
 * Android-specific factory with context
 */
fun createSecureStorage(context: Context): SecureStorage {
    return SecureStorage(context)
}
