package ai.ciris.mobile.shared.localization

actual class LocalizationResourceLoader actual constructor() {
    actual suspend fun loadStrings(languageCode: String): Map<String, String> {
        // TODO: Fetch from server or bundled resources
        return emptyMap()
    }
}

actual fun createLocalizationResourceLoader(): LocalizationResourceLoader = LocalizationResourceLoader()
