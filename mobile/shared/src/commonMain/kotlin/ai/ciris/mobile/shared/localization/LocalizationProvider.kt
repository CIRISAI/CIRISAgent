package ai.ciris.mobile.shared.localization

import ai.ciris.mobile.shared.viewmodels.SupportedLanguage
import androidx.compose.runtime.*
import kotlinx.coroutines.flow.StateFlow

/**
 * CompositionLocal for accessing the LocalizationManager throughout the Compose tree.
 *
 * Usage:
 * ```kotlin
 * // At the root of your app:
 * CompositionLocalProvider(LocalLocalization provides localizationManager) {
 *     // Your app content
 * }
 *
 * // Anywhere in your composables:
 * val text = localizedString("mobile.interact_showing_messages", mapOf("count" to "10"))
 * ```
 */
val LocalLocalization = staticCompositionLocalOf<LocalizationManager?> { null }

/**
 * Composable function to get a localized string.
 * Automatically recomposes when the language changes.
 *
 * @param key Dot-notation key (e.g., "mobile.interact_showing_messages")
 * @param params Map of parameter names to values for interpolation
 * @return Localized string, or the key itself if localization is not available
 */
@Composable
fun localizedString(key: String, params: Map<String, String> = emptyMap()): String {
    val localization = LocalLocalization.current ?: return key

    // Collect state to trigger recomposition when language or loading state changes
    // These collectAsState() calls establish Compose state dependencies
    val currentLanguageState = localization.currentLanguage.collectAsState()
    val isLoadingState = localization.isLoading.collectAsState()

    // Read the state values - Compose tracks these reads for recomposition
    val currentLanguage = currentLanguageState.value
    val isLoading = isLoadingState.value

    // During initial loading, return the key as fallback
    // This will recompose when loading completes
    if (isLoading) {
        return key
    }

    // Use produceState to create a derived state that depends on language
    // This ensures Compose properly tracks the dependency and recomposes
    val result = remember(currentLanguage, key, params) {
        localization.getString(key, params)
    }

    return result
}

/**
 * Composable function to get a localized string with a single parameter.
 * Convenience overload for common case of single interpolation.
 *
 * @param key Dot-notation key
 * @param paramName Name of the parameter
 * @param paramValue Value of the parameter
 * @return Localized string with parameter interpolated
 */
@Composable
fun localizedString(key: String, paramName: String, paramValue: String): String {
    return localizedString(key, mapOf(paramName to paramValue))
}

/**
 * Composable function to get current language info.
 *
 * @return Current SupportedLanguage, or English default
 */
@Composable
fun currentLanguageInfo(): SupportedLanguage {
    val localization = LocalLocalization.current
    return localization?.currentLanguageInfo?.collectAsState()?.value
        ?: SupportedLanguage("en", "English", "English")
}

/**
 * Composable function to get all available languages.
 *
 * @return List of all supported languages
 */
@Composable
fun availableLanguages(): List<SupportedLanguage> {
    val localization = LocalLocalization.current
    return localization?.getAvailableLanguages() ?: emptyList()
}

/**
 * Composable function to check if localization is loading.
 *
 * @return True if localization files are still loading
 */
@Composable
fun isLocalizationLoading(): Boolean {
    val localization = LocalLocalization.current
    return localization?.isLoading?.collectAsState()?.value ?: false
}

/**
 * Non-composable helper to get the LocalizationManager for ViewModels.
 * Use this when you need to access localization outside of Compose context.
 *
 * Note: This requires manual language state observation in ViewModels.
 */
object LocalizationHelper {
    private var manager: LocalizationManager? = null

    fun setManager(localizationManager: LocalizationManager) {
        manager = localizationManager
    }

    fun getString(key: String, params: Map<String, String> = emptyMap()): String {
        return manager?.getString(key, params) ?: key
    }

    fun getCurrentLanguage(): String {
        return manager?.currentLanguage?.value ?: "en"
    }

    fun getManager(): LocalizationManager? = manager
}
