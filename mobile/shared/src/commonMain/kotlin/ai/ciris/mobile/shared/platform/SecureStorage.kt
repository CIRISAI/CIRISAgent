package ai.ciris.mobile.shared.platform

/**
 * Secure storage abstraction for sensitive data
 *
 * Implementations:
 * - Android: EncryptedSharedPreferences (AES-256)
 * - iOS: Keychain Services
 */
expect class SecureStorage() {
    /**
     * Save API key securely
     * @param key The key (e.g., "llm_api_key")
     * @param value The API key value
     */
    suspend fun saveApiKey(key: String, value: String): Result<Unit>

    /**
     * Get API key
     * @param key The key
     * @return API key or null if not found
     */
    suspend fun getApiKey(key: String): Result<String?>

    /**
     * Save access token
     */
    suspend fun saveAccessToken(token: String): Result<Unit>

    /**
     * Get access token
     */
    suspend fun getAccessToken(): Result<String?>

    /**
     * Delete access token (logout)
     */
    suspend fun deleteAccessToken(): Result<Unit>

    /**
     * Save arbitrary string securely
     */
    suspend fun save(key: String, value: String): Result<Unit>

    /**
     * Get arbitrary string
     */
    suspend fun get(key: String): Result<String?>

    /**
     * Delete key
     */
    suspend fun delete(key: String): Result<Unit>

    /**
     * Clear all stored data
     */
    suspend fun clear(): Result<Unit>
}

/**
 * Factory function
 */
expect fun createSecureStorage(): SecureStorage
