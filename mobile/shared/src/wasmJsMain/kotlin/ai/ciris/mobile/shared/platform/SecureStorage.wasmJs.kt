package ai.ciris.mobile.shared.platform

import kotlinx.browser.localStorage

actual class SecureStorage actual constructor() {

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> = runCatching {
        localStorage.setItem("apikey_$key", value)
    }

    actual suspend fun getApiKey(key: String): Result<String?> = runCatching {
        localStorage.getItem("apikey_$key")
    }

    actual suspend fun saveAccessToken(token: String): Result<Unit> = runCatching {
        localStorage.setItem("ciris_access_token", token)
    }

    actual suspend fun getAccessToken(): Result<String?> = runCatching {
        localStorage.getItem("ciris_access_token")
    }

    actual suspend fun deleteAccessToken(): Result<Unit> = runCatching {
        localStorage.removeItem("ciris_access_token")
    }

    actual suspend fun save(key: String, value: String): Result<Unit> = runCatching {
        localStorage.setItem(key, value)
    }

    actual suspend fun get(key: String): Result<String?> = runCatching {
        localStorage.getItem(key)
    }

    actual suspend fun delete(key: String): Result<Unit> = runCatching {
        localStorage.removeItem(key)
    }

    actual suspend fun clear(): Result<Unit> = runCatching {
        localStorage.clear()
    }
}

actual fun createSecureStorage(): SecureStorage = SecureStorage()
