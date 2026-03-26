package ai.ciris.mobile.shared.localization

import ai.ciris.mobile.shared.platform.PlatformLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import platform.Foundation.*

/**
 * iOS implementation of LocalizationResourceLoader.
 * Loads localization JSON files from the app bundle.
 */
actual class LocalizationResourceLoader {
    companion object {
        private const val TAG = "LocalizationResourceLoader"
    }

    /**
     * Load localization JSON from the app bundle.
     */
    actual suspend fun loadLocalizationJson(languageCode: String): String? {
        return withContext(Dispatchers.Main) {
            try {
                // Try to find the file in the main bundle
                val bundle = NSBundle.mainBundle
                val path = bundle.pathForResource(languageCode, ofType = "json", inDirectory = "localization")

                if (path != null) {
                    PlatformLogger.d(TAG, "Loading from bundle: $path")
                    val content = NSString.stringWithContentsOfFile(
                        path,
                        encoding = NSUTF8StringEncoding,
                        error = null
                    )
                    return@withContext content
                }

                // Try without subdirectory (flat structure)
                val flatPath = bundle.pathForResource("$languageCode", ofType = "json")
                if (flatPath != null) {
                    PlatformLogger.d(TAG, "Loading from flat bundle: $flatPath")
                    val content = NSString.stringWithContentsOfFile(
                        flatPath,
                        encoding = NSUTF8StringEncoding,
                        error = null
                    )
                    return@withContext content
                }

                PlatformLogger.w(TAG, "Localization file not found in bundle for: $languageCode")
                null
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "Failed to load localization for $languageCode: ${e.message}")
                null
            }
        }
    }
}

/**
 * Factory function for iOS.
 */
actual fun createLocalizationResourceLoader(): LocalizationResourceLoader {
    return LocalizationResourceLoader()
}
