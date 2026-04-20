package ai.ciris.mobile.shared.localization

import io.ktor.client.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*

/**
 * WASM/Browser implementation of LocalizationResourceLoader.
 * Fetches localization JSON files from the server relative to the current page URL.
 * Uses Ktor HttpClient which works with Kotlin/WASM.
 */
actual class LocalizationResourceLoader actual constructor() {

    private val client = HttpClient()

    actual suspend fun loadLocalizationJson(languageCode: String): String? {
        return try {
            // Fetch from /localization/{lang}.json relative to the app's base URL
            val url = "localization/$languageCode.json"
            console.log("[LocalizationResourceLoader] Fetching: $url")

            val response: HttpResponse = client.get(url)

            if (response.status.isSuccess()) {
                val text = response.bodyAsText()
                console.log("[LocalizationResourceLoader] Loaded $languageCode (${text.length} chars)")
                text
            } else {
                console.log("[LocalizationResourceLoader] Failed to load $languageCode: ${response.status}")
                null
            }
        } catch (e: Exception) {
            console.log("[LocalizationResourceLoader] Error loading $languageCode: ${e.message}")
            null
        }
    }
}

actual fun createLocalizationResourceLoader(): LocalizationResourceLoader = LocalizationResourceLoader()

// External declaration for browser console
private external object console {
    fun log(message: String)
}
