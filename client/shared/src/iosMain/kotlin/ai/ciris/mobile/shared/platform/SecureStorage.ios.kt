@file:OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)

package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.*
import platform.CoreFoundation.*
import platform.Foundation.*
import platform.Security.*

/**
 * iOS implementation using Keychain Services
 *
 * Uses the Security framework for secure credential storage:
 * - SecItemAdd() - Add item to keychain
 * - SecItemCopyMatching() - Retrieve item
 * - SecItemUpdate() - Update item
 * - SecItemDelete() - Delete item
 */
actual class SecureStorage {
    private val serviceName = "ai.ciris.mobile"

    actual suspend fun saveApiKey(key: String, value: String): Result<Unit> {
        return save("api_key_$key", value)
    }

    actual suspend fun getApiKey(key: String): Result<String?> {
        return get("api_key_$key")
    }

    actual suspend fun saveAccessToken(token: String): Result<Unit> {
        platform.Foundation.NSLog("[SecureStorage] saveAccessToken called, token length: ${token.length}")
        val result = save("access_token", token)
        platform.Foundation.NSLog("[SecureStorage] saveAccessToken result: ${if (result.isSuccess) "SUCCESS" else "FAILURE: ${result.exceptionOrNull()?.message}"}")
        return result
    }

    actual suspend fun getAccessToken(): Result<String?> {
        platform.Foundation.NSLog("[SecureStorage] getAccessToken called")
        val result = get("access_token")
        result.onSuccess { token ->
            platform.Foundation.NSLog("[SecureStorage] getAccessToken result: ${if (token != null) "found token (${token.length} chars)" else "NULL/not found"}")
        }.onFailure { e ->
            platform.Foundation.NSLog("[SecureStorage] getAccessToken FAILED: ${e.message}")
        }
        return result
    }

    actual suspend fun deleteAccessToken(): Result<Unit> {
        return delete("access_token")
    }

    actual suspend fun save(key: String, value: String): Result<Unit> {
        return try {
            // First try to delete any existing item
            delete(key)

            // Create the query dictionary
            val valueData = value.encodeToByteArray().toNSData()

            memScoped {
                val query = CFDictionaryCreateMutable(
                    kCFAllocatorDefault,
                    4,
                    null,
                    null
                )

                CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword)
                CFDictionarySetValue(query, kSecAttrService, CFBridgingRetain(serviceName))
                CFDictionarySetValue(query, kSecAttrAccount, CFBridgingRetain(key))
                CFDictionarySetValue(query, kSecValueData, CFBridgingRetain(valueData))

                val status = SecItemAdd(query, null)

                CFRelease(query)

                if (status == errSecSuccess) {
                    Result.success(Unit)
                } else {
                    Result.failure(Exception("Failed to save to Keychain: $status"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun get(key: String): Result<String?> {
        return try {
            memScoped {
                val query = CFDictionaryCreateMutable(
                    kCFAllocatorDefault,
                    5,
                    null,
                    null
                )

                CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword)
                CFDictionarySetValue(query, kSecAttrService, CFBridgingRetain(serviceName))
                CFDictionarySetValue(query, kSecAttrAccount, CFBridgingRetain(key))
                CFDictionarySetValue(query, kSecReturnData, kCFBooleanTrue)
                CFDictionarySetValue(query, kSecMatchLimit, kSecMatchLimitOne)

                val resultPtr = alloc<CFTypeRefVar>()
                val status = SecItemCopyMatching(query, resultPtr.ptr)

                CFRelease(query)

                when (status) {
                    errSecSuccess -> {
                        val data = CFBridgingRelease(resultPtr.value) as? NSData
                        val value = data?.toByteArray()?.decodeToString()
                        Result.success(value)
                    }
                    errSecItemNotFound -> {
                        Result.success(null)
                    }
                    else -> {
                        Result.failure(Exception("Failed to retrieve from Keychain: $status"))
                    }
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun delete(key: String): Result<Unit> {
        return try {
            memScoped {
                val query = CFDictionaryCreateMutable(
                    kCFAllocatorDefault,
                    3,
                    null,
                    null
                )

                CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword)
                CFDictionarySetValue(query, kSecAttrService, CFBridgingRetain(serviceName))
                CFDictionarySetValue(query, kSecAttrAccount, CFBridgingRetain(key))

                val status = SecItemDelete(query)

                CFRelease(query)

                if (status == errSecSuccess || status == errSecItemNotFound) {
                    Result.success(Unit)
                } else {
                    Result.failure(Exception("Failed to delete from Keychain: $status"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    actual suspend fun clear(): Result<Unit> {
        return try {
            memScoped {
                val query = CFDictionaryCreateMutable(
                    kCFAllocatorDefault,
                    2,
                    null,
                    null
                )

                CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword)
                CFDictionarySetValue(query, kSecAttrService, CFBridgingRetain(serviceName))

                val status = SecItemDelete(query)

                CFRelease(query)

                if (status == errSecSuccess || status == errSecItemNotFound) {
                    Result.success(Unit)
                } else {
                    Result.failure(Exception("Failed to clear Keychain: $status"))
                }
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

// Helper extension to convert ByteArray to NSData
private fun ByteArray.toNSData(): NSData {
    if (this.isEmpty()) return NSData()
    return this.usePinned { pinned ->
        NSData.dataWithBytes(pinned.addressOf(0), this.size.toULong())
    }
}

// Helper extension to convert NSData to ByteArray
private fun NSData.toByteArray(): ByteArray {
    val length = this.length.toInt()
    if (length == 0) return ByteArray(0)
    val bytes = this.bytes ?: return ByteArray(0)
    return ByteArray(length) { index ->
        bytes.reinterpret<ByteVar>()[index]
    }
}

/**
 * Factory function
 */
actual fun createSecureStorage(): SecureStorage = SecureStorage()
