package ai.ciris.mobile.shared.platform

import androidx.compose.runtime.Composable

/**
 * Cross-platform back handler for system back button/gesture.
 *
 * On Android: Intercepts system back button press
 * On iOS: No-op (iOS uses swipe gestures handled by navigation)
 * On Desktop: No-op (could handle ESC key if needed)
 *
 * @param enabled Whether the back handler is active
 * @param onBack Callback when back is pressed
 */
@Composable
expect fun PlatformBackHandler(enabled: Boolean = true, onBack: () -> Unit)
