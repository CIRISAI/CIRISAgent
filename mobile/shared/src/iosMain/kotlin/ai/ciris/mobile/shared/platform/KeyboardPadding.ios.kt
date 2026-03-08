package ai.ciris.mobile.shared.platform

import androidx.compose.ui.Modifier

/**
 * iOS implementation - no-op.
 * iOS native keyboard avoidance handles input field visibility automatically
 * via the hosting UIViewController. Using imePadding() causes a permanent
 * white gap because WindowInsets.ime doesn't reset to 0 after keyboard dismiss.
 */
actual fun Modifier.platformImePadding(): Modifier = this
