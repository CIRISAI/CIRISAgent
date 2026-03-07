package ai.ciris.mobile.shared.platform

import androidx.compose.foundation.layout.imePadding
import androidx.compose.ui.Modifier

/**
 * Desktop implementation - applies imePadding() for keyboard avoidance.
 */
actual fun Modifier.platformImePadding(): Modifier = this.imePadding()
