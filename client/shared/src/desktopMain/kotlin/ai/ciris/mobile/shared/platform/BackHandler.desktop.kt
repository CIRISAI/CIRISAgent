package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

@Composable
actual fun PlatformBackHandler(enabled: Boolean, onBack: () -> Unit) {
    // Desktop doesn't have a system back button
    // Could add ESC key handling here if needed
    // No-op implementation for now
}
