package ai.ciris.mobile.shared.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Semantic color mappings that work with ColorTheme.
 * Use these instead of hardcoded Color(0x...) values.
 *
 * Example usage:
 * ```
 * val colors = SemanticColors.forTheme(colorTheme, isDark = true)
 * Text(color = colors.success)
 * ```
 */
data class SemanticColors(
    // Status colors
    val success: Color,
    val warning: Color,
    val error: Color,
    val info: Color,

    // Primary accent (from theme)
    val accent: Color,
    val accentSecondary: Color,
    val accentTertiary: Color,

    // Surface colors
    val surfaceSuccess: Color,
    val surfaceWarning: Color,
    val surfaceError: Color,
    val surfaceInfo: Color,
    val surfaceAccent: Color,

    // Text on colored surfaces
    val onSuccess: Color,
    val onWarning: Color,
    val onError: Color,
    val onInfo: Color,
    val onAccent: Color,

    // Chart/graph colors (derived from theme)
    val chartPrimary: Color,
    val chartSecondary: Color,
    val chartTertiary: Color,
    val chartNeutral: Color,

    // Common semantic meanings
    val online: Color,
    val offline: Color,
    val pending: Color,
    val active: Color,
    val inactive: Color,

    // Badge/chip colors
    val badgeNew: Color,
    val badgeUpdated: Color,
    val badgeDeprecated: Color
) {
    companion object {
        // Standard semantic colors (status-based, don't change with theme)
        private val successGreen = Color(0xFF10B981)
        private val successGreenLight = Color(0xFFD1FAE5)
        private val warningAmber = Color(0xFFF59E0B)
        private val warningAmberLight = Color(0xFFFEF3C7)
        private val errorRed = Color(0xFFEF4444)
        private val errorRedLight = Color(0xFFFEE2E2)
        private val infoBlue = Color(0xFF3B82F6)
        private val infoBlueLight = Color(0xFFDBEAFE)

        /**
         * Create semantic colors for a given theme.
         */
        fun forTheme(theme: ColorTheme, isDark: Boolean = true): SemanticColors {
            return SemanticColors(
                // Status colors (consistent across themes for accessibility)
                success = if (isDark) Color(0xFF4ADE80) else successGreen,
                warning = if (isDark) Color(0xFFFBBF24) else warningAmber,
                error = if (isDark) Color(0xFFF87171) else errorRed,
                info = if (isDark) Color(0xFF60A5FA) else infoBlue,

                // Theme accents
                accent = theme.primary,
                accentSecondary = theme.secondary,
                accentTertiary = theme.tertiary,

                // Surfaces
                surfaceSuccess = if (isDark) Color(0xFF064E3B) else successGreenLight,
                surfaceWarning = if (isDark) Color(0xFF78350F) else warningAmberLight,
                surfaceError = if (isDark) Color(0xFF7F1D1D) else errorRedLight,
                surfaceInfo = if (isDark) Color(0xFF1E3A8A) else infoBlueLight,
                surfaceAccent = theme.primary.copy(alpha = if (isDark) 0.2f else 0.1f),

                // Text on surfaces
                onSuccess = if (isDark) Color(0xFFD1FAE5) else Color(0xFF064E3B),
                onWarning = if (isDark) Color(0xFFFEF3C7) else Color(0xFF78350F),
                onError = if (isDark) Color(0xFFFEE2E2) else Color(0xFF7F1D1D),
                onInfo = if (isDark) Color(0xFFDBEAFE) else Color(0xFF1E3A8A),
                onAccent = if (theme.primaryTextDark) Color(0xFF1F2937) else Color.White,

                // Chart colors (from theme)
                chartPrimary = theme.primary,
                chartSecondary = theme.secondary,
                chartTertiary = theme.tertiary,
                chartNeutral = theme.grayBase,

                // Status meanings
                online = if (isDark) Color(0xFF4ADE80) else successGreen,
                offline = if (isDark) Color(0xFFF87171) else errorRed,
                pending = if (isDark) Color(0xFFFBBF24) else warningAmber,
                active = theme.primary,
                inactive = theme.grayBase,

                // Badges
                badgeNew = theme.primary,
                badgeUpdated = theme.secondary,
                badgeDeprecated = theme.grayBase
            )
        }

        /**
         * Default colors (VAPOR theme, dark mode).
         */
        val Default = forTheme(ColorTheme.DEFAULT, isDark = true)
    }
}
