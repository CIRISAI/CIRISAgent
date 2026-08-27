package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.ExperimentalForeignApi
import platform.CoreFoundation.CFDictionaryCreateMutable
import platform.CoreFoundation.CFDictionarySetValue
import platform.CoreFoundation.kCFAllocatorDefault
import platform.Foundation.CFBridgingRetain
import platform.Foundation.NSFileManager
import platform.Foundation.NSHomeDirectory
import platform.Security.SecItemDelete
import platform.Security.errSecItemNotFound
import platform.Security.errSecSuccess
import platform.Security.kSecAttrService
import platform.Security.kSecClass
import platform.Security.kSecClassGenericPassword

/**
 * iOS wipe: the state directory AND the Keychain.
 *
 * The Keychain half is not optional. `SecureStorage.ios` stores provider
 * credentials as `api_key_*` under the `ai.ciris.mobile` service, and
 * `SettingsViewModel.logout()` removes only the access token, refresh token and
 * user fields — not `clear()`. Deleting `Documents/ciris` alone would therefore
 * leave live API keys in the Keychain for whoever configures the device next,
 * under a dialog that says "erase all local data". That is the same false
 * promise this whole change exists to remove, one layer down.
 *
 * Deletes the service rather than enumerating keys: `api_key_<provider>` is
 * open-ended, so any list would drift the moment a provider is added.
 */
@OptIn(ExperimentalForeignApi::class)
actual fun wipeLocalData(): Boolean {
    var ok = true

    // 1. The node's state directory.
    val path = "${NSHomeDirectory()}/Documents/ciris"
    val fm = NSFileManager.defaultManager
    if (fm.fileExistsAtPath(path)) {
        runCatching { fm.removeItemAtPath(path, null) }
        if (fm.fileExistsAtPath(path)) ok = false
    }

    // 2. The Keychain service. Mirrors SecureStorage.clear()'s query; that
    //    function is `suspend` and this is not, but SecItemDelete is a
    //    synchronous call, so the work is identical.
    val status = runCatching {
        val query = CFDictionaryCreateMutable(kCFAllocatorDefault, 2, null, null)
        CFDictionarySetValue(query, kSecClass, kSecClassGenericPassword)
        CFDictionarySetValue(query, kSecAttrService, CFBridgingRetain("ai.ciris.mobile"))
        SecItemDelete(query)
    }.getOrElse { errSecSuccess - 1 }

    // errSecItemNotFound means there was nothing stored — already the goal.
    if (status != errSecSuccess && status != errSecItemNotFound) ok = false

    return ok
}
