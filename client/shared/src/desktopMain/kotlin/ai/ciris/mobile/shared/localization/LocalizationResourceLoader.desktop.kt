package ai.ciris.mobile.shared.localization

import ai.ciris.mobile.shared.platform.PlatformLogger
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Desktop (JVM) implementation of LocalizationResourceLoader.
 * Loads localization JSON files from the resources directory or file system.
 */
actual class LocalizationResourceLoader {
    companion object {
        private const val TAG = "LocalizationResourceLoader"
        private var localizationDir: File? = null

        /**
         * Initialize with a custom localization directory.
         * If not called, will try to load from classpath resources.
         */
        fun init(directory: File) {
            localizationDir = directory
            PlatformLogger.i(TAG, "Initialized with directory: ${directory.absolutePath}")
        }
    }

    /**
     * Load localization JSON from resources or file system.
     */
    actual suspend fun loadLocalizationJson(languageCode: String): String? {
        return withContext(Dispatchers.IO) {
            // Try custom directory first (if set)
            localizationDir?.let { dir ->
                val file = File(dir, "$languageCode.json")
                if (file.exists()) {
                    PlatformLogger.d(TAG, "Loading from file: ${file.absolutePath}")
                    return@withContext file.readText()
                }
            }

            // Try classpath resources (packaged in JAR)
            try {
                val resourcePath = "localization/$languageCode.json"
                PlatformLogger.d(TAG, "Trying classpath resource: $resourcePath")

                // Try multiple classloaders
                val classLoaders = listOf(
                    Thread.currentThread().contextClassLoader,
                    LocalizationResourceLoader::class.java.classLoader,
                    ClassLoader.getSystemClassLoader()
                )

                for (cl in classLoaders) {
                    val inputStream = cl?.getResourceAsStream(resourcePath)
                    if (inputStream != null) {
                        val content = inputStream.bufferedReader().use { it.readText() }
                        PlatformLogger.i(TAG, "Loaded $languageCode from classpath (${content.length} chars)")
                        return@withContext content
                    }
                }
            } catch (e: Exception) {
                PlatformLogger.w(TAG, "Failed to load from classpath: ${e.message}")
            }

            // Try file system paths (development mode)
            val cwd = System.getProperty("user.dir")
            PlatformLogger.d(TAG, "Trying file system, cwd: $cwd")

            val devPaths = listOf(
                File(cwd, "localization/$languageCode.json"),           // From repo root
                File(cwd, "../localization/$languageCode.json"),        // From mobile
                File(cwd, "../../localization/$languageCode.json"),     // From mobile/desktopApp
            )

            for (devFile in devPaths) {
                if (devFile.exists()) {
                    PlatformLogger.i(TAG, "Loaded $languageCode from: ${devFile.absolutePath}")
                    return@withContext devFile.readText()
                }
            }

            // Try user home based paths (for installed apps)
            val homePaths = listOf(
                File(System.getProperty("user.home"), ".ciris/localization/$languageCode.json"),
                File(System.getProperty("user.home"), "CIRISAgent/localization/$languageCode.json"),
            )

            for (homeFile in homePaths) {
                if (homeFile.exists()) {
                    PlatformLogger.i(TAG, "Loaded $languageCode from: ${homeFile.absolutePath}")
                    return@withContext homeFile.readText()
                }
            }

            PlatformLogger.w(TAG, "Failed to load localization for $languageCode from any source")
            null
        }
    }
}

/**
 * Factory function for Desktop.
 */
actual fun createLocalizationResourceLoader(): LocalizationResourceLoader {
    return LocalizationResourceLoader()
}
