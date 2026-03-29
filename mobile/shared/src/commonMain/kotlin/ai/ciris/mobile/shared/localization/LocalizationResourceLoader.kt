package ai.ciris.mobile.shared.localization

/**
 * Platform-specific loader for localization JSON files.
 *
 * Each platform implements this to load JSON from the appropriate location:
 * - Android: assets/localization/{code}.json
 * - iOS: Bundle resources
 * - Desktop: resources/localization/{code}.json
 */
expect class LocalizationResourceLoader() {
    /**
     * Load localization JSON content for a given language code.
     *
     * @param languageCode ISO 639-1 language code (e.g., "en", "am", "es")
     * @return JSON string content, or null if not found
     */
    suspend fun loadLocalizationJson(languageCode: String): String?
}

/**
 * Factory function for creating the platform-specific resource loader.
 */
expect fun createLocalizationResourceLoader(): LocalizationResourceLoader
