package ai.ciris.mobile.shared.localization

import io.ktor.client.*
import io.ktor.client.request.*
import io.ktor.client.statement.*
import io.ktor.http.*
import kotlinx.browser.window

/**
 * WASM/Browser implementation of LocalizationResourceLoader.
 * Fetches localization JSON files from the server relative to the current page URL.
 * Uses Ktor HttpClient which works with Kotlin/WASM.
 *
 * IMPORTANT: Must use absolute URLs because Ktor relative URLs resolve against
 * the host root, not the current page path. For HA ingress URLs like
 * /api/hassio_ingress/TOKEN/, we need to construct the full URL.
 */
actual class LocalizationResourceLoader actual constructor() {

    private val client = HttpClient()

    /**
     * Get the base URL from the current browser location.
     * For HA ingress: http://homeassistant.local:8123/api/hassio_ingress/TOKEN/
     */
    private fun getBaseUrl(): String {
        val href = window.location.href
        // Remove any trailing filename or query params, keep the directory path
        return if (href.endsWith("/")) {
            href
        } else {
            href.substringBeforeLast("/") + "/"
        }
    }

    actual suspend fun loadLocalizationJson(languageCode: String): String? {
        return try {
            // Construct absolute URL using the current page's base URL
            val baseUrl = getBaseUrl()
            val url = "${baseUrl}localization/$languageCode.json"
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
