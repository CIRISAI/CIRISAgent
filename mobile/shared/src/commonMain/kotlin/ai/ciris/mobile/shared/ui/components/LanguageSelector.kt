package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.LocalLocalization
import ai.ciris.mobile.shared.localization.availableLanguages
import ai.ciris.mobile.shared.localization.currentLanguageInfo
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.viewmodels.SupportedLanguage
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Compact language selector dropdown for the login screen and settings.
 *
 * Shows the current language's native name with a dropdown to select from
 * all 15 supported languages. Triggers immediate language change.
 *
 * @param modifier Modifier for positioning
 * @param compact If true, shows minimal style suitable for login screen overlay
 * @param onLanguageChanged Optional callback when language changes
 */
@Composable
fun LanguageSelector(
    modifier: Modifier = Modifier,
    compact: Boolean = true,
    onLanguageChanged: ((String) -> Unit)? = null
) {
    val localization = LocalLocalization.current
    val currentLanguage = currentLanguageInfo()
    val languages = availableLanguages()
    var expanded by remember { mutableStateOf(false) }

    Box(modifier = modifier.testable("language_selector")) {
        // Current language button
        Surface(
            shape = RoundedCornerShape(20.dp),
            color = if (compact) Color.White.copy(alpha = 0.15f) else MaterialTheme.colorScheme.surfaceVariant,
            modifier = Modifier.clickable { expanded = true }
        ) {
            Row(
                modifier = Modifier.padding(horizontal = 12.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                if (!compact) {
                    // Globe indicator for language
                    Text(
                        text = "\uD83C\uDF10", // Globe emoji
                        fontSize = 14.sp
                    )
                }
                Text(
                    text = currentLanguage.nativeName,
                    fontSize = if (compact) 13.sp else 14.sp,
                    fontWeight = FontWeight.Medium,
                    color = if (compact) Color.White else MaterialTheme.colorScheme.onSurfaceVariant
                )
                Icon(
                    imageVector = Icons.Default.KeyboardArrowDown,
                    contentDescription = "Expand",
                    modifier = Modifier.size(16.dp),
                    tint = if (compact) Color.White.copy(alpha = 0.7f) else MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }

        // Dropdown menu
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
            modifier = Modifier
                .background(MaterialTheme.colorScheme.surface)
                .testable("language_dropdown")
        ) {
            languages.forEach { language ->
                val isSelected = language.code == currentLanguage.code
                DropdownMenuItem(
                    text = {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text(
                                text = language.nativeName,
                                fontWeight = if (isSelected) FontWeight.Bold else FontWeight.Normal,
                                color = if (isSelected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface
                            )
                            if (language.nativeName != language.englishName) {
                                Text(
                                    text = "(${language.englishName})",
                                    fontSize = 12.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    },
                    onClick = {
                        PlatformLogger.i("LanguageSelector", "Language selected: ${language.code} (${language.englishName})")
                        localization?.setLanguage(language.code)
                        onLanguageChanged?.invoke(language.code)
                        expanded = false
                    },
                    modifier = Modifier.testable("language_option_${language.code}")
                )
            }
        }
    }
}

/**
 * Full-width language selector with label, suitable for settings screens.
 *
 * @param label Section label (e.g., "Language")
 * @param modifier Modifier
 * @param onLanguageChanged Optional callback when language changes
 */
@Composable
fun LanguageSelectorWithLabel(
    label: String,
    modifier: Modifier = Modifier,
    onLanguageChanged: ((String) -> Unit)? = null
) {
    Column(modifier = modifier) {
        Text(
            text = label,
            fontSize = 14.sp,
            fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 8.dp)
        )
        LanguageSelector(
            compact = false,
            onLanguageChanged = onLanguageChanged
        )
    }
}
