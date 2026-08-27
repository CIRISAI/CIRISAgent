package ai.ciris.mobile.shared.platform

/**
 * Web: no filesystem to write to, and the clipboard API is async + permissioned,
 * so both report failure rather than pretending. The UI falls back to showing
 * the bundle inline for manual selection, which is the honest affordance here.
 */
actual fun saveDebugBundle(fileName: String, content: String): String? = null

actual fun copyToClipboard(text: String): Boolean = false
