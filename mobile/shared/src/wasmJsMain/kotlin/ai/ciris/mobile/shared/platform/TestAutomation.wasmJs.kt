package ai.ciris.mobile.shared.platform

import androidx.compose.ui.Modifier

actual object TestAutomation {
    actual val isEnabled: Boolean = false
    actual fun registerElement(tag: String, bounds: Any?) {}
    actual fun unregisterElement(tag: String) {}
    actual fun setCurrentScreen(screen: String) {}
    actual fun getElements(): Map<String, Any?> = emptyMap()
    actual fun getCurrentScreen(): String = ""
}

actual fun Modifier.testable(tag: String, text: String?): Modifier = this
actual fun Modifier.testableClickable(tag: String, text: String?, onClick: () -> Unit): Modifier = this
actual fun Modifier.testableWithHandler(tag: String, onClick: () -> Unit): Modifier = this
