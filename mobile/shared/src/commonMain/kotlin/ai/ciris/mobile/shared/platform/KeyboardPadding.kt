package ai.ciris.mobile.shared.platform

import androidx.compose.ui.Modifier

/**
 * Platform-specific keyboard padding modifier.
 * - Android: Applies imePadding() for proper keyboard avoidance
 * - iOS: No-op, iOS native keyboard avoidance handles this automatically
 */
expect fun Modifier.platformImePadding(): Modifier
