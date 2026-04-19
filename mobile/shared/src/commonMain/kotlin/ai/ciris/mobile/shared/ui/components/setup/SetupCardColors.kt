package ai.ciris.mobile.shared.ui.components.setup

import ai.ciris.mobile.shared.ui.theme.ColorTheme
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.ui.graphics.Color

/**
 * Shared color definitions for setup wizard cards.
 * These match the existing SetupScreen colors for consistency.
 */
object SetupCardColors {
    private val semantic = SemanticColors.forTheme(ColorTheme.DEFAULT, isDark = false)

    val Background = Color.White
    val CardBackground = Color(0xFFF9FAFB)
    val TextPrimary = Color(0xFF1F2937)
    val TextSecondary = Color(0xFF6B7280)
    val TextTertiary = Color(0xFF9CA3AF)

    // Success (green)
    val SuccessLight = semantic.surfaceSuccess
    val SuccessBorder = Color(0xFF6EE7B7)
    val SuccessDark = semantic.onSuccess
    val SuccessText = semantic.success

    // Info (blue)
    val InfoLight = semantic.surfaceInfo
    val InfoBorder = Color(0xFF93C5FD)
    val InfoDark = semantic.onInfo
    val InfoText = semantic.info

    // Error (red)
    val ErrorLight = semantic.surfaceError
    val ErrorDark = semantic.onError
    val ErrorText = semantic.error

    // Gray for cards
    val GrayLight = Color(0xFFF3F4F6)
    val GrayBorder = Color(0xFFE5E7EB)

    // Primary accent
    val Primary = Color(0xFF667eea)
    val PrimaryLight = Color(0xFFEEF2FF)
}
