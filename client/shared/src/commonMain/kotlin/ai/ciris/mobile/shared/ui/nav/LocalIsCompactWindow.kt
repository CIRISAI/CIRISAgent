package ai.ciris.mobile.shared.ui.nav

import androidx.compose.runtime.staticCompositionLocalOf

/**
 * CompositionLocal flag — true when the app is running on a "compact" window
 * (Material 3 `WindowWidthSizeClass.Compact`, < 600.dp wide). Screens that
 * paint their own top-bar back arrow read this to suppress that arrow on
 * compact viewports, where the global drawer overlay button at the top-left
 * already handles back navigation through a 3-state icon (signet on
 * top-level, back arrow on sub-screens, hamburger when the drawer is open).
 *
 * On wider viewports (tablet / desktop) the permanent sidebar is visible
 * and there is no overlay button, so the federation Scaffolds keep their
 * own back arrows — this Local stays false and the navigationIcon renders
 * as before.
 *
 * Set in `CIRISApp.kt` via `CompositionLocalProvider` around the screen
 * switch, computed from `BoxWithConstraints.maxWidth < 600.dp`.
 */
val LocalIsCompactWindow = staticCompositionLocalOf<Boolean> { false }
