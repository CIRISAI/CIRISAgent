package ai.ciris.mobile.shared.platform

/**
 * iOS implementation using Keychain Services
 * TODO: Implement using Security framework
 *
 * Will use:
 * - SecItemAdd() - Add item to keychain
 * - SecItemCopyMatching() - Retrieve item
 * - SecItemUpdate() - Update item
 * - SecItemDelete() - Delete item
 */
actual class SecureStorage {

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> {
        // TODO: Implement Keychain Services
        // kSecClass = kSecClassGenericPassword
        // kSecAttrAccount = "api_key_$key"
        // kSecValueData = value.encodeToByteArray()
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun getApiKey(key: String): Result<String?> {
        // TODO: Implement Keychain Services lookup
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun saveAccessToken(token: String): Result<Unit> {
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun getAccessToken(): Result<String?> {
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun deleteAccessToken(): Result<Unit> {
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun save(key: String, value: String): Result<Unit> {
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun get(key: String): Result<String?>  {
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun delete(key: String): Result<Unit> {
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }

    actual suspend fun clear(): Result<Unit> {
        return Result.failure(Exception("iOS SecureStorage not yet implemented"))
    }
}

/**
 * Factory function
 */
actual fun createSecureStorage(): SecureStorage = SecureStorage()
