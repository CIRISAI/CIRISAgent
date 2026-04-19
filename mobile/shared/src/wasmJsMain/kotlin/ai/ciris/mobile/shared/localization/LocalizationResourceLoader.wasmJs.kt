package ai.ciris.mobile.shared.localization

actual class LocalizationResourceLoader actual constructor() {
    actual suspend fun loadLocalizationJson(languageCode: String): String? {
        // TODO: Fetch from server or bundled resources
        return null
    }
}

actual fun createLocalizationResourceLoader(): LocalizationResourceLoader = LocalizationResourceLoader()
