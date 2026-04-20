import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.window.CanvasBasedWindow
import ai.ciris.mobile.shared.CIRISApp
import kotlinx.browser.window

@OptIn(ExperimentalComposeUiApi::class)
fun main() {
    // Note: Loading overlay is hidden by timeout in index.html
    // Compose-ready event would require WASM-specific JS interop

    CanvasBasedWindow(
        canvasElementId = "ComposeTarget",
        title = "CIRIS Agent"
    ) {
        CIRISApp(
            accessToken = "",
            baseUrl = getBaseUrl(),
            googleSignInCallback = null
        )
    }
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
