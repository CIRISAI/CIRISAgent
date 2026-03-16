package ai.ciris.mobile.shared.ui.theme

import androidx.compose.ui.graphics.Color

/**
 * Color themes inspired by VeilidChat's Radix-based theme system.
 * Each theme has primary, secondary, and tertiary colors for both light and dark modes.
 *
 * Source: https://gitlab.com/veilid/veilidchat (MPL-2.0)
 * Colors: https://www.radix-ui.com/colors
 */
enum class ColorTheme(
    val displayName: String,
    val description: String,
    /** Primary accent color for the theme */
    val primary: Color,
    /** Secondary accent color */
    val secondary: Color,
    /** Tertiary accent color */
    val tertiary: Color,
    /** Gray scale base (for backgrounds in dark mode) */
    val grayBase: Color,
    /** Whether primary text should be dark (for light primary colors) */
    val primaryTextDark: Boolean = false
) {
    // Radix-based themes
    SCARLET(
        displayName = "Scarlet",
        description = "Red + Violet + Tomato",
        primary = Color(0xFFE5484D),      // red9
        secondary = Color(0xFF6E56CF),    // violet9
        tertiary = Color(0xFFE54D2E),     // tomato9
        grayBase = Color(0xFF6F6D78)      // mauve9
    ),
    BABYDOLL(
        displayName = "Babydoll",
        description = "Crimson + Pink + Purple",
        primary = Color(0xFFE93D82),      // crimson9
        secondary = Color(0xFFD6409F),    // pink9
        tertiary = Color(0xFF8E4EC6),     // purple9
        grayBase = Color(0xFF6F6D78)      // mauve9
    ),
    VAPOR(
        displayName = "Vapor",
        description = "Pink + Cyan + Plum",
        primary = Color(0xFFD6409F),      // pink9
        secondary = Color(0xFF00A2C7),    // cyan9
        tertiary = Color(0xFFAB4ABA),     // plum9
        grayBase = Color(0xFF6F6D78)      // mauve9
    ),
    GOLD(
        displayName = "Gold",
        description = "Yellow + Amber + Orange",
        primary = Color(0xFFFFE629),      // yellow9
        secondary = Color(0xFFFFC53D),    // amber9
        tertiary = Color(0xFFF76B15),     // orange9
        grayBase = Color(0xFF6F6D66),     // sand9
        primaryTextDark = true
    ),
    GARDEN(
        displayName = "Garden",
        description = "Grass + Orange + Brown",
        primary = Color(0xFF46A758),      // grass9
        secondary = Color(0xFFF76B15),    // orange9
        tertiary = Color(0xFFAD7F58),     // brown9
        grayBase = Color(0xFF687066)      // olive9
    ),
    FOREST(
        displayName = "Forest",
        description = "Green + Brown + Amber",
        primary = Color(0xFF30A46C),      // green9
        secondary = Color(0xFFAD7F58),    // brown9
        tertiary = Color(0xFFFFC53D),     // amber9
        grayBase = Color(0xFF63706B)      // sage9
    ),
    ARCTIC(
        displayName = "Arctic",
        description = "Sky + Teal + Violet",
        primary = Color(0xFF7CE2FE),      // sky9
        secondary = Color(0xFF12A594),    // teal9
        tertiary = Color(0xFF6E56CF),     // violet9
        grayBase = Color(0xFF696E77),     // slate9
        primaryTextDark = true
    ),
    LAPIS(
        displayName = "Lapis",
        description = "Blue + Indigo + Mint",
        primary = Color(0xFF0090FF),      // blue9
        secondary = Color(0xFF3E63DD),    // indigo9
        tertiary = Color(0xFF86EAD4),     // mint9
        grayBase = Color(0xFF696E77)      // slate9
    ),
    EGGPLANT(
        displayName = "Eggplant",
        description = "Violet + Purple + Indigo",
        primary = Color(0xFF6E56CF),      // violet9
        secondary = Color(0xFF8E4EC6),    // purple9
        tertiary = Color(0xFF3E63DD),     // indigo9
        grayBase = Color(0xFF6F6D78)      // mauve9
    ),
    LIME(
        displayName = "Lime",
        description = "Lime + Yellow + Orange",
        primary = Color(0xFFBDEE63),      // lime9
        secondary = Color(0xFFFFE629),    // yellow9
        tertiary = Color(0xFFF76B15),     // orange9
        grayBase = Color(0xFF687066),     // olive9
        primaryTextDark = true
    ),
    GRIM(
        displayName = "Grim",
        description = "Gray + Purple + Brown",
        primary = Color(0xFF8D8D8D),      // gray9
        secondary = Color(0xFF8E4EC6),    // purple9
        tertiary = Color(0xFFAD7F58),     // brown9
        grayBase = Color(0xFF6E6E6E)      // gray9
    ),

    // Accessible themes
    ELITE(
        displayName = "Elite",
        description = "Neon hacker style",
        primary = Color(0xFF00FF00),      // neon green
        secondary = Color(0xFF00FFFF),    // cyan
        tertiary = Color(0xFFFF00FF),     // magenta
        grayBase = Color(0xFF000000),     // black
        primaryTextDark = true
    ),
    CONTRAST(
        displayName = "Contrast",
        description = "High contrast for accessibility",
        primary = Color(0xFFFFFFFF),      // white
        secondary = Color(0xFFFFFFFF),    // white
        tertiary = Color(0xFFFFFFFF),     // white
        grayBase = Color(0xFF000000),     // black
        primaryTextDark = true
    );

    companion object {
        /** Default theme */
        val DEFAULT = VAPOR

        fun fromString(value: String?): ColorTheme {
            return entries.find { it.name.equals(value, ignoreCase = true) } ?: DEFAULT
        }
    }
}

/**
 * Brightness preference (separate from color theme).
 */
enum class BrightnessPreference(val displayName: String) {
    SYSTEM("System"),
    LIGHT("Light"),
    DARK("Dark");

    companion object {
        fun fromString(value: String?): BrightnessPreference {
            return entries.find { it.name.equals(value, ignoreCase = true) } ?: SYSTEM
        }
    }
}

/**
 * Complete theme configuration combining color theme and brightness.
 */
data class ThemeConfig(
    val colorTheme: ColorTheme = ColorTheme.DEFAULT,
    val brightness: BrightnessPreference = BrightnessPreference.SYSTEM
)
