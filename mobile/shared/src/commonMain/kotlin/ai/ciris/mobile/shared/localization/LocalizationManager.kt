package ai.ciris.mobile.shared.localization

import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.mobile.shared.viewmodels.SUPPORTED_LANGUAGES
import ai.ciris.mobile.shared.viewmodels.SupportedLanguage
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.*

/**
 * Runtime localization manager for the CIRIS mobile app.
 *
 * Loads localization JSON files at runtime and provides string lookup with interpolation.
 * Persists language preference to SecureStorage for cross-session persistence.
 *
 * Usage:
 * ```kotlin
 * val manager = LocalizationManager(scope, storage, resourceLoader)
 * manager.getString("mobile.interact_showing_messages", mapOf("count" to "10"))
 * // Returns: "Showing last 10 messages"
 * ```
 *
 * Fallback chain: Current language -> English -> key itself
 */
class LocalizationManager(
    private val scope: CoroutineScope,
    private val secureStorage: SecureStorage,
    private val resourceLoader: LocalizationResourceLoader
) {
    companion object {
        private const val TAG = "LocalizationManager"
        private const val PREF_KEY_LANGUAGE = "ciris_language"
        private const val DEFAULT_LANGUAGE = "en"
    }

    private val json = Json { ignoreUnknownKeys = true }

    // Current language code (ISO 639-1)
    private val _currentLanguage = MutableStateFlow(DEFAULT_LANGUAGE)
    val currentLanguage: StateFlow<String> = _currentLanguage.asStateFlow()

    // Current language info (full object)
    private val _currentLanguageInfo = MutableStateFlow(SUPPORTED_LANGUAGES.first { it.code == DEFAULT_LANGUAGE })
    val currentLanguageInfo: StateFlow<SupportedLanguage> = _currentLanguageInfo.asStateFlow()

    // Loaded strings for current language
    private var currentStrings: JsonObject = JsonObject(emptyMap())
    private var englishStrings: JsonObject = JsonObject(emptyMap()) // Fallback

    // Loading state
    private val _isLoading = MutableStateFlow(true)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Whether language was explicitly selected by user (vs default)
    private val _hasExplicitLanguageSelection = MutableStateFlow(false)
    val hasExplicitLanguageSelection: StateFlow<Boolean> = _hasExplicitLanguageSelection.asStateFlow()

    // Cache of loaded language strings for rotation
    private val languageStringsCache = mutableMapOf<String, JsonObject>()

    /**
     * Initialize the localization manager.
     * Loads persisted language preference and initializes strings.
     */
    suspend fun initialize() {
        PlatformLogger.i(TAG, "Initializing localization manager...")
        _isLoading.value = true

        // Load English strings first (always available as fallback)
        englishStrings = loadStrings("en") ?: JsonObject(emptyMap())
        languageStringsCache["en"] = englishStrings
        PlatformLogger.i(TAG, "Loaded English fallback: ${englishStrings.keys.size} top-level keys")

        // Load persisted language preference
        val savedLanguage = secureStorage.get(PREF_KEY_LANGUAGE).getOrNull()
        _hasExplicitLanguageSelection.value = savedLanguage != null

        val validLanguage = if (savedLanguage != null && SUPPORTED_LANGUAGES.any { it.code == savedLanguage }) {
            savedLanguage
        } else {
            if (savedLanguage != null) {
                PlatformLogger.w(TAG, "Invalid saved language '$savedLanguage', defaulting to English")
            }
            DEFAULT_LANGUAGE
        }

        // Set current language (will also load strings)
        setLanguageInternal(validLanguage, persist = false)
        _isLoading.value = false
        PlatformLogger.i(TAG, "Localization initialized with language: $validLanguage, explicit: ${_hasExplicitLanguageSelection.value}")
    }

    /**
     * Set the current language.
     * Loads the language's strings and persists the preference.
     * Marks the language as explicitly selected by user.
     */
    fun setLanguage(languageCode: String) {
        _hasExplicitLanguageSelection.value = true
        setLanguageInternal(languageCode, persist = true)
    }

    /**
     * Internal language setter with optional persistence.
     */
    private fun setLanguageInternal(languageCode: String, persist: Boolean) {
        val languageInfo = SUPPORTED_LANGUAGES.find { it.code == languageCode }
        if (languageInfo == null) {
            PlatformLogger.w(TAG, "Unsupported language code: $languageCode")
            return
        }

        scope.launch(Dispatchers.Default) {
            PlatformLogger.i(TAG, "Setting language to: ${languageInfo.englishName} ($languageCode)")

            // Load strings for the new language (use cache if available)
            val strings = languageStringsCache[languageCode] ?: loadStrings(languageCode)
            val loadedStrings = if (strings != null) {
                languageStringsCache[languageCode] = strings
                PlatformLogger.i(TAG, "Loaded ${strings.keys.size} top-level keys for $languageCode")
                strings
            } else {
                PlatformLogger.w(TAG, "Failed to load strings for $languageCode, using English fallback")
                englishStrings
            }

            // Switch to main thread to update state atomically
            // This ensures currentStrings is visible when recomposition happens
            withContext(Dispatchers.Main) {
                currentStrings = loadedStrings
                _currentLanguage.value = languageCode
                _currentLanguageInfo.value = languageInfo
            }

            // Persist preference only if requested (can be done on IO thread)
            if (persist) {
                secureStorage.save(PREF_KEY_LANGUAGE, languageCode)
            }
        }
    }

    /**
     * Get a string in a specific language (for rotation preview).
     * Does NOT change the current language setting.
     */
    suspend fun getStringInLanguage(languageCode: String, key: String, params: Map<String, String> = emptyMap()): String {
        // Get or load strings for the language
        val strings = languageStringsCache[languageCode] ?: loadStrings(languageCode)?.also {
            languageStringsCache[languageCode] = it
        }

        // Try requested language first
        var result = strings?.let { resolveKey(it, key) }

        // Fall back to English if not found
        if (result == null && languageCode != DEFAULT_LANGUAGE) {
            result = resolveKey(englishStrings, key)
        }

        // Fall back to key itself if still not found
        if (result == null) {
            return key
        }

        return interpolate(result, params)
    }

    /**
     * Set a temporary language for preview/rotation without persisting.
     * Used during startup screen to rotate through languages.
     * Does NOT persist the preference or mark as explicit selection.
     *
     * When the user explicitly selects a language later, call setLanguage() instead.
     */
    fun setTemporaryLanguage(languageCode: String) {
        val languageInfo = SUPPORTED_LANGUAGES.find { it.code == languageCode }
        if (languageInfo == null) {
            PlatformLogger.w(TAG, "Unsupported language code for rotation: $languageCode")
            return
        }

        // Load strings synchronously from cache if available, otherwise use English
        val strings = languageStringsCache[languageCode]
        if (strings != null) {
            currentStrings = strings
        } else {
            // Try to load in background for next rotation, use English for now
            currentStrings = englishStrings
            scope.launch(Dispatchers.Default) {
                loadStrings(languageCode)?.let { loaded ->
                    languageStringsCache[languageCode] = loaded
                }
            }
        }

        // Update state to trigger recomposition - but don't persist
        _currentLanguage.value = languageCode
        _currentLanguageInfo.value = languageInfo
        // Note: NOT setting hasExplicitLanguageSelection or persisting
    }

    /**
     * Reset language to the persisted/default language.
     * Called when leaving startup screen to restore the actual user preference.
     */
    fun resetToPersistedLanguage() {
        scope.launch(Dispatchers.Default) {
            val savedLanguage = secureStorage.get(PREF_KEY_LANGUAGE).getOrNull()
            val targetLanguage = if (savedLanguage != null && SUPPORTED_LANGUAGES.any { it.code == savedLanguage }) {
                savedLanguage
            } else {
                DEFAULT_LANGUAGE
            }

            // Only reset if we're not already at the target
            if (_currentLanguage.value != targetLanguage) {
                PlatformLogger.i(TAG, "Resetting from temporary language ${_currentLanguage.value} to $targetLanguage")
                setLanguageInternal(targetLanguage, persist = false)
            }
        }
    }

    /**
     * Preload language strings into cache for smooth rotation.
     * Call during startup to avoid loading delays during rotation.
     */
    suspend fun preloadLanguages(languageCodes: List<String>) {
        for (code in languageCodes) {
            if (!languageStringsCache.containsKey(code)) {
                loadStrings(code)?.let { strings ->
                    languageStringsCache[code] = strings
                    PlatformLogger.d(TAG, "Preloaded localization: $code")
                }
            }
        }
    }

    /**
     * Get a localized string by key with optional parameter interpolation.
     *
     * @param key Dot-notation key (e.g., "mobile.interact_showing_messages")
     * @param params Map of parameter names to values for interpolation
     * @return Localized string, or English fallback, or the key itself if not found
     */
    fun getString(key: String, params: Map<String, String> = emptyMap()): String {
        val lang = _currentLanguage.value
        val stringsKeys = currentStrings.keys.size

        // Try current language first
        var result = resolveKey(currentStrings, key)

        // Fall back to English if not found
        if (result == null && lang != DEFAULT_LANGUAGE) {
            result = resolveKey(englishStrings, key)
            if (result != null) {
                PlatformLogger.d(TAG, "getString($key): fallback to EN, currentLang=$lang, currentStringsKeys=$stringsKeys")
            }
        }

        // Fall back to key itself if still not found
        if (result == null) {
            PlatformLogger.w(TAG, "Missing localization key: $key (lang=$lang, stringsKeys=$stringsKeys)")
            return key
        }

        // Apply parameter interpolation
        return interpolate(result, params)
    }

    /**
     * Resolve a dot-notation key from a JSON object.
     * e.g., "mobile.interact_showing_messages" -> jsonObject["mobile"]["interact_showing_messages"]
     */
    private fun resolveKey(obj: JsonObject, key: String): String? {
        val parts = key.split(".")
        var current: JsonElement = obj

        for (part in parts) {
            current = when (current) {
                is JsonObject -> current[part] ?: return null
                else -> return null
            }
        }

        return when (current) {
            is JsonPrimitive -> current.contentOrNull
            else -> null
        }
    }

    /**
     * Interpolate parameters into a string.
     * Supports {param} syntax: "Showing last {count} messages" -> "Showing last 10 messages"
     */
    private fun interpolate(template: String, params: Map<String, String>): String {
        var result = template
        for ((name, value) in params) {
            result = result.replace("{$name}", value)
        }
        return result
    }

    /**
     * Load localization strings from a JSON file.
     */
    private suspend fun loadStrings(languageCode: String): JsonObject? {
        return try {
            val content = resourceLoader.loadLocalizationJson(languageCode)
            if (content != null) {
                json.parseToJsonElement(content).jsonObject
            } else {
                PlatformLogger.w(TAG, "No localization file found for: $languageCode")
                null
            }
        } catch (e: Exception) {
            PlatformLogger.e(TAG, "Error loading localization for $languageCode: ${e.message}")
            null
        }
    }

    /**
     * Get all available languages.
     */
    fun getAvailableLanguages(): List<SupportedLanguage> = SUPPORTED_LANGUAGES
}
