package ai.ciris.mobile.shared.localization

import ai.ciris.mobile.shared.platform.PlatformLogger
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.BufferedReader

/**
 * Android implementation of LocalizationResourceLoader.
 * Loads localization JSON files from the assets directory.
 */
actual class LocalizationResourceLoader {
    companion object {
        private const val TAG = "LocalizationResourceLoader"
        private var appContext: Context? = null

        /**
         * Initialize with application context.
         * Must be called before using the loader (typically in Application.onCreate).
         */
        fun init(context: Context) {
            appContext = context.applicationContext
            PlatformLogger.i(TAG, "Initialized with context")
        }
    }

    /**
     * Load localization JSON from assets/localization/{code}.json
     */
    actual suspend fun loadLocalizationJson(languageCode: String): String? {
        val context = appContext
        if (context == null) {
            PlatformLogger.e(TAG, "Context not initialized! Call LocalizationResourceLoader.init() first")
            return null
        }

        return withContext(Dispatchers.IO) {
            try {
                val assetPath = "localization/$languageCode.json"
                PlatformLogger.d(TAG, "Loading: $assetPath")

                context.assets.open(assetPath).bufferedReader().use { reader ->
                    reader.readText()
                }
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "Failed to load localization for $languageCode: ${e.message}")
                null
            }
        }
    }
}

/**
 * Factory function for Android.
 */
actual fun createLocalizationResourceLoader(): LocalizationResourceLoader {
    return LocalizationResourceLoader()
}
