package ai.ciris.mobile.shared.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * CIRIS Brand Colors
 * Matches the Android app design exactly
 */
object CIRISColors {
    // Background colors
    val BackgroundDark = Color(0xFF1a1a2e)      // Main dark navy background
    val BackgroundDarker = Color(0xFF0d0d1a)    // Console/darker background

    // Brand colors
    val SignetTeal = Color(0xFF419CA0)          // CIRIS signet color
    val AccentCyan = Color(0xFF00d4ff)          // Primary accent (cyan)
    val SuccessGreen = Color(0xFF00ff88)        // Success/ready state
    val WarningYellow = Color(0xFFFFCC00)       // Warning/setup state
    val ErrorRed = Color(0xFFff4444)            // Error state

    // Service light colors
    val LightOff = Color(0xFF2a2a3e)            // Inactive light (dark gray)
    val LightOn = Color(0xFF00d4ff)             // Active light (cyan)

    // Text colors
    val TextPrimary = Color(0xFFffffff)         // White text
    val TextSecondary = Color(0xFFaaaaaa)       // Gray text
    val TextTertiary = Color(0xFF888888)        // Lighter gray
    val TextDim = Color(0xFF666666)             // Dimmer gray
    val TextConsole = Color(0xFF00ff88)         // Console green

    // Navigation colors (for future use)
    val NavSignetLight = Color(0xFF5DD3D8)      // Lighter signet for dark toolbar

    // ---------------------------------------------------------------------
    // Cell-visualization bus palette (load-bearing — see FSD §2).
    // ---------------------------------------------------------------------
    //
    // These are the six membrane-arc colours. They are architectural (each
    // bus always has the same colour regardless of user theme) and
    // intentionally chosen to avoid reading as the Google Material
    // primary palette (blue / yellow / red / green) that earlier drafts
    // drifted into.
    //
    // Design constraints:
    //   - COMM / LLM anchor on brand tokens (SignetTeal, AccentCyan)
    //     so the most-frequently-firing buses ARE the brand.
    //   - TOOL / WISE use warm tones from outside Google's primary range:
    //     rust + brass, not orange + yellow.
    //   - RUNTIME shifts red toward magenta, away from Google red.
    //   - MEMORY keeps cool violet, saturated into the brand family.
    //
    // Hue distribution on the wheel is intentionally non-uniform (the big
    // gap between violet → rust skips the bright-yellow zone) so the
    // ring doesn't geometrically echo Material's four-primary layout.
    val BusComm = Color(0xFF419CA0)             // Exact brand SignetTeal
    val BusLLM = Color(0xFF22C0E8)              // Derived from AccentCyan, toned
    val BusMemory = Color(0xFF7A6FD6)           // Cool violet — brand-adjacent
    val BusTool = Color(0xFFC96A38)             // Burnt rust — industrial, not Google orange
    val BusWise = Color(0xFFB08A3E)             // Vintage brass — wisdom patina, not Google yellow
    val BusRuntime = Color(0xFFE14B7F)          // Magenta-rose — alarm without Google red
}

/**
 * CIRIS Typography Sizes (from Android design)
 */
object CIRISTextSizes {
    const val LOGO_LARGE = 24f       // Large CIRIS text
    const val TITLE = 16f            // Section titles
    const val BODY = 14f             // Body text
    const val LABEL = 12f            // Labels
    const val SMALL = 10f            // Small text
}
