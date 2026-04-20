package ai.ciris.mobile.shared.platform

import androidx.compose.foundation.layout.imePadding
import androidx.compose.ui.Modifier

/**
 * iOS implementation - applies imePadding().
 * Compose Multiplatform in ComposeHostingViewController does NOT get native
 * iOS keyboard avoidance. The keyboard covers input fields without this.
 */
actual fun Modifier.platformImePadding(): Modifier = this.imePadding()
