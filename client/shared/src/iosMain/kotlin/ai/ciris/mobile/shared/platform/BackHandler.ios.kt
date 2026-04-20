package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

@Composable
actual fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit) {
    // iOS doesn't have a system back button - uses swipe gestures
    // No-op implementation
}
