import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.window.CanvasBasedWindow
import ai.ciris.mobile.shared.CIRISApp
import kotlinx.browser.window

@OptIn(ExperimentalComposeUiApi::class)
fun main() {
    // Note: Loading overlay is hidden by timeout in index.html
    // Compose-ready event would require WASM-specific JS interop

    // Detect HA addon mode from URL path or query param
    // HA embeds the app via ingress which adds X-Ingress-Path header
    // and typically uses /api/hassio_ingress/<token>/ path pattern
    val isHAMode = detectHAAddonMode()

    CanvasBasedWindow(
        canvasElementId = "ComposeTarget",
        title = "CIRIS Agent"
    ) {
        CIRISApp(
            accessToken = "",
            baseUrl = getBaseUrl(),
            googleSignInCallback = null,
            isHAAddonMode = isHAMode
        )
    }
}

/**
 * Detect if running as HA addon (embedded via ingress).
 * Checks for:
 * - URL path containing /api/hassio_ingress/
 * - Query param ?ha=1 or ?addon=1
 * - Referrer from Home Assistant
 */
private fun detectHAAddonMode(): Boolean {
    val path = window.location.pathname
    val search = window.location.search
    val referrer = try { window.document.referrer } catch (_: Exception) { "" }

    // Check for HA ingress path pattern
    if (path.contains("/api/hassio_ingress/") ||
        path.contains("/hassio/ingress/")) {
        return true
    }

    // Check for explicit query params
    if (search.contains("ha=1") ||
        search.contains("addon=1") ||
        search.contains("ingress=1")) {
        return true
    }

    // Check if referred from Home Assistant
    if (referrer.contains("homeassistant") ||
        referrer.contains(":8123")) {
        return true
    }

    return false
}

/**
 * Get the API base URL from the current window location
 * For production: same origin
 * For development: can be overridden via query param
 */
private fun getBaseUrl(): String {
    val params = window.location.search
    val urlParam = params.substringAfter("api=", "").substringBefore("&")
    return if (urlParam.isNotEmpty()) {
        urlParam
    } else {
        "${window.location.protocol}//${window.location.host}"
    }
}
