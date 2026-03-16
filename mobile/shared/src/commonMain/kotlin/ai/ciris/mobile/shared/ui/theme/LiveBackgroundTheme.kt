package ai.ciris.mobile.shared.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Centralized theme for live background mode.
 * Edit values here to tweak the entire dark theme in one place.
 */
object LiveBackgroundTheme {
    // Base colors
    val background = Color(0xFF0D1117)  // Dark background behind animation
    val surface = Color.Black.copy(alpha = 0.7f)  // Semi-transparent surfaces
    val surfaceLight = Color.Black.copy(alpha = 0.5f)  // Lighter semi-transparent
    val surfaceBorder = Color.White.copy(alpha = 0.1f)  // Subtle borders

    // Text colors
    val textPrimary = Color.White
    val textSecondary = Color.White.copy(alpha = 0.7f)
    val textMuted = Color.White.copy(alpha = 0.5f)
    val textAccent = Color(0xFF7DD3FC)  // Light cyan accent

    // Status colors (adjusted for dark background)
    val statusConnected = Color(0xFF4ADE80)  // Brighter green
    val statusDisconnected = Color(0xFFF87171)  // Brighter red
    val statusWarning = Color(0xFFFBBF24)  // Bright amber

    // Warning banner
    val warningBackground = Color(0xFFB45309).copy(alpha = 0.8f)
    val warningText = Color(0xFFFEF3C7)

    // Bubble net / timeline
    val timelineBackground = Color(0xFF059669).copy(alpha = 0.3f)
    val timelineText = Color(0xFF4ADE80)

    // Input bar
    val inputBackground = surface
    val inputBorder = Color.White.copy(alpha = 0.2f)
    val inputText = textPrimary
    val inputPlaceholder = textMuted
    val inputButtonEnabled = Color(0xFF419CA0)
    val inputButtonDisabled = Color.White.copy(alpha = 0.2f)

    // Chat bubbles (keep mostly opaque for readability)
    val userBubble = Color(0xFF2563EB)  // Blue - same as light mode
    val agentBubble = Color.White.copy(alpha = 0.95f)  // Nearly opaque white
    val agentBubbleText = Color(0xFF1F2937)  // Dark text on light bubble

    // Action bubbles - slightly transparent versions
    val actionSpeakBg = Color(0xFF1E40AF).copy(alpha = 0.8f)
    val actionToolBg = Color(0xFF065F46).copy(alpha = 0.8f)

    // Message count indicator
    val messageCountBackground = surfaceLight
    val messageCountText = textSecondary

    // Shutdown buttons
    val shutdownOutline = Color(0xFFF87171)
    val stopBackground = Color(0xFFEF4444)

    // Trust shield colors
    val trustLevel5 = Color(0xFF4ADE80)  // Green
    val trustLevel4 = Color(0xFFFBBF24)  // Amber
    val trustLevelLow = Color(0xFFF87171)  // Red
    val trustDefault = Color.White.copy(alpha = 0.5f)
}

/**
 * Standard light theme colors (for when live background is disabled).
 * Mirrors the original InteractScreen colors.
 */
object LightTheme {
    val background = Color(0xFFFAFAFA)
    val surface = Color.White
    val surfaceBorder = Color(0xFFE5E7EB)

    val textPrimary = Color(0xFF1F2937)
    val textSecondary = Color(0xFF6B7280)
    val textMuted = Color(0xFF9CA3AF)
    val textAccent = Color(0xFF419CA0)

    val statusConnected = Color(0xFF10B981)
    val statusDisconnected = Color(0xFFEF4444)
    val statusWarning = Color(0xFFD97706)

    val warningBackground = Color(0xFFFEF3C7)
    val warningText = Color(0xFFB45309)

    val timelineBackground = Color(0xFFF0FDF4)
    val timelineText = Color(0xFF059669)

    val inputBackground = Color.White
    val inputBorder = Color(0xFFE5E7EB)
    val inputText = textPrimary
    val inputPlaceholder = textMuted
    val inputButtonEnabled = Color(0xFF419CA0)
    val inputButtonDisabled = Color(0xFFE5E7EB)

    val userBubble = Color(0xFF2563EB)
    val agentBubble = Color.White
    val agentBubbleText = Color(0xFF1F2937)

    val messageCountBackground = Color.White
    val messageCountText = Color(0xFF9CA3AF)

    val shutdownOutline = Color(0xFFEF4444)
    val stopBackground = Color(0xFFEF4444)

    val trustLevel5 = Color(0xFF059669)
    val trustLevel4 = Color(0xFFD97706)
    val trustLevelLow = Color(0xFFDC2626)
    val trustDefault = Color(0xFF6B7280)
}

/**
 * Helper to pick theme based on live background state and color theme.
 */
data class InteractTheme(
    val background: Color,
    val surface: Color,
    val surfaceLight: Color,
    val surfaceBorder: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val textMuted: Color,
    val textAccent: Color,
    val statusConnected: Color,
    val statusDisconnected: Color,
    val statusWarning: Color,
    val warningBackground: Color,
    val warningText: Color,
    val timelineBackground: Color,
    val timelineText: Color,
    val inputBackground: Color,
    val inputBorder: Color,
    val inputText: Color,
    val inputPlaceholder: Color,
    val inputButtonEnabled: Color,
    val inputButtonDisabled: Color,
    val userBubble: Color,
    val agentBubble: Color,
    val agentBubbleText: Color,
    val messageCountBackground: Color,
    val messageCountText: Color,
    val shutdownOutline: Color,
    val stopBackground: Color,
    val trustLevel5: Color,
    val trustLevel4: Color,
    val trustLevelLow: Color,
    val trustDefault: Color,
    val isDark: Boolean,
    val colorTheme: ColorTheme
) {
    companion object {
        /**
         * Create theme for live background mode with color theme support.
         * @param enabled Whether live background is enabled
         * @param colorTheme The selected color theme for accents
         * @param isDark Whether to use dark mode colors (from brightness preference)
         */
        fun forLiveBackground(
            enabled: Boolean,
            colorTheme: ColorTheme = ColorTheme.DEFAULT,
            isDark: Boolean = true
        ): InteractTheme {
            // Respect user's brightness preference - they control dark/light mode
            return if (isDark) {
                InteractTheme(
                    background = LiveBackgroundTheme.background,
                    surface = LiveBackgroundTheme.surface,
                    surfaceLight = LiveBackgroundTheme.surfaceLight,
                    surfaceBorder = LiveBackgroundTheme.surfaceBorder,
                    textPrimary = LiveBackgroundTheme.textPrimary,
                    textSecondary = LiveBackgroundTheme.textSecondary,
                    textMuted = LiveBackgroundTheme.textMuted,
                    textAccent = colorTheme.primary,  // Use theme primary as accent
                    statusConnected = LiveBackgroundTheme.statusConnected,
                    statusDisconnected = LiveBackgroundTheme.statusDisconnected,
                    statusWarning = LiveBackgroundTheme.statusWarning,
                    warningBackground = LiveBackgroundTheme.warningBackground,
                    warningText = LiveBackgroundTheme.warningText,
                    timelineBackground = colorTheme.tertiary.copy(alpha = 0.3f),  // Use theme tertiary
                    timelineText = colorTheme.tertiary,
                    inputBackground = LiveBackgroundTheme.inputBackground,
                    inputBorder = LiveBackgroundTheme.inputBorder,
                    inputText = LiveBackgroundTheme.inputText,
                    inputPlaceholder = LiveBackgroundTheme.inputPlaceholder,
                    inputButtonEnabled = colorTheme.primary,  // Use theme primary for buttons
                    inputButtonDisabled = LiveBackgroundTheme.inputButtonDisabled,
                    userBubble = colorTheme.primary,  // Use theme primary for user bubbles
                    agentBubble = LiveBackgroundTheme.agentBubble,
                    agentBubbleText = LiveBackgroundTheme.agentBubbleText,
                    messageCountBackground = LiveBackgroundTheme.messageCountBackground,
                    messageCountText = LiveBackgroundTheme.messageCountText,
                    shutdownOutline = LiveBackgroundTheme.shutdownOutline,
                    stopBackground = LiveBackgroundTheme.stopBackground,
                    trustLevel5 = LiveBackgroundTheme.trustLevel5,
                    trustLevel4 = LiveBackgroundTheme.trustLevel4,
                    trustLevelLow = LiveBackgroundTheme.trustLevelLow,
                    trustDefault = LiveBackgroundTheme.trustDefault,
                    isDark = true,
                    colorTheme = colorTheme
                )
            } else {
                InteractTheme(
                    background = LightTheme.background,
                    surface = LightTheme.surface,
                    surfaceLight = LightTheme.surface,
                    surfaceBorder = LightTheme.surfaceBorder,
                    textPrimary = LightTheme.textPrimary,
                    textSecondary = LightTheme.textSecondary,
                    textMuted = LightTheme.textMuted,
                    textAccent = colorTheme.primary,  // Use theme primary as accent
                    statusConnected = LightTheme.statusConnected,
                    statusDisconnected = LightTheme.statusDisconnected,
                    statusWarning = LightTheme.statusWarning,
                    warningBackground = LightTheme.warningBackground,
                    warningText = LightTheme.warningText,
                    timelineBackground = colorTheme.tertiary.copy(alpha = 0.1f),  // Lighter for light mode
                    timelineText = colorTheme.tertiary,
                    inputBackground = LightTheme.inputBackground,
                    inputBorder = LightTheme.inputBorder,
                    inputText = LightTheme.inputText,
                    inputPlaceholder = LightTheme.inputPlaceholder,
                    inputButtonEnabled = colorTheme.primary,  // Use theme primary for buttons
                    inputButtonDisabled = LightTheme.inputButtonDisabled,
                    userBubble = colorTheme.primary,  // Use theme primary for user bubbles
                    agentBubble = LightTheme.agentBubble,
                    agentBubbleText = LightTheme.agentBubbleText,
                    messageCountBackground = LightTheme.messageCountBackground,
                    messageCountText = LightTheme.messageCountText,
                    shutdownOutline = LightTheme.shutdownOutline,
                    stopBackground = LightTheme.stopBackground,
                    trustLevel5 = LightTheme.trustLevel5,
                    trustLevel4 = LightTheme.trustLevel4,
                    trustLevelLow = LightTheme.trustLevelLow,
                    trustDefault = LightTheme.trustDefault,
                    isDark = false,
                    colorTheme = colorTheme
                )
            }
        }
    }
}
