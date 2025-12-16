package ai.ciris.mobile.setup

import android.util.Log
import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel

/**
 * ViewModel for Setup Wizard state management.
 *
 * Supports two LLM modes:
 * - CIRIS Proxy (free for Google OAuth users): Uses Google ID token with CIRIS hosted proxy
 * - BYOK (Bring Your Own Key): User provides their own API key from OpenAI/Anthropic/etc
 */
class SetupViewModel : ViewModel() {

    companion object {
        private const val TAG = "SetupViewModel"
    }

    // === Google OAuth State ===
    private val _isGoogleAuth = MutableLiveData<Boolean>(false)
    val isGoogleAuth: LiveData<Boolean> = _isGoogleAuth

    private val _googleIdToken = MutableLiveData<String?>()
    val googleIdToken: LiveData<String?> = _googleIdToken

    private val _googleEmail = MutableLiveData<String?>()
    val googleEmail: LiveData<String?> = _googleEmail

    private val _googleUserId = MutableLiveData<String?>()
    val googleUserId: LiveData<String?> = _googleUserId

    // === LLM Mode Selection ===
    enum class LlmMode {
        CIRIS_PROXY,  // Free AI via CIRIS proxy (Google OAuth required)
        BYOK          // Bring Your Own Key
    }

    private val _llmMode = MutableLiveData<LlmMode?>(null)
    val llmMode: LiveData<LlmMode?> = _llmMode

    // === LLM Configuration (for BYOK mode) ===
    private val _llmProvider = MutableLiveData<String>("OpenAI")
    val llmProvider: LiveData<String> = _llmProvider

    private val _llmApiKey = MutableLiveData<String>("")
    val llmApiKey: LiveData<String> = _llmApiKey

    private val _llmBaseUrl = MutableLiveData<String>("")
    val llmBaseUrl: LiveData<String> = _llmBaseUrl

    private val _llmModel = MutableLiveData<String>("")
    val llmModel: LiveData<String> = _llmModel

    // === User Account (only for non-Google users) ===
    private val _username = MutableLiveData<String>("")
    val username: LiveData<String> = _username

    private val _email = MutableLiveData<String>("")
    val email: LiveData<String> = _email

    private val _userPassword = MutableLiveData<String>("")
    val userPassword: LiveData<String> = _userPassword

    // === Setters with logging ===

    fun setGoogleAuthState(isAuth: Boolean, idToken: String?, email: String?, userId: String?) {
        Log.i(TAG, "setGoogleAuthState: isAuth=$isAuth, hasToken=${idToken != null}, email=$email, userId=$userId")
        _isGoogleAuth.value = isAuth
        _googleIdToken.value = idToken
        _googleEmail.value = email
        _googleUserId.value = userId

        // If Google auth is available, default to CIRIS proxy mode
        if (isAuth && _llmMode.value == null) {
            Log.i(TAG, "Google auth detected, defaulting to CIRIS_PROXY mode")
            _llmMode.value = LlmMode.CIRIS_PROXY
        }
    }

    fun setLlmMode(mode: LlmMode) {
        Log.i(TAG, "setLlmMode: $mode (was ${_llmMode.value})")
        _llmMode.value = mode
    }

    fun setLlmProvider(provider: String) {
        Log.d(TAG, "setLlmProvider: $provider")
        _llmProvider.value = provider
    }

    fun setLlmApiKey(key: String) {
        Log.d(TAG, "setLlmApiKey: length=${key.length}")
        _llmApiKey.value = key
    }

    fun setLlmBaseUrl(url: String) {
        Log.d(TAG, "setLlmBaseUrl: $url")
        _llmBaseUrl.value = url
    }

    fun setLlmModel(model: String) {
        Log.d(TAG, "setLlmModel: $model")
        _llmModel.value = model
    }

    fun setUsername(username: String) {
        Log.d(TAG, "setUsername: $username")
        _username.value = username
    }

    fun setEmail(email: String) {
        Log.d(TAG, "setEmail: $email")
        _email.value = email
    }

    fun setUserPassword(password: String) {
        Log.d(TAG, "setUserPassword: length=${password.length}")
        _userPassword.value = password
    }

    /**
     * Check if using CIRIS proxy mode.
     */
    fun useCirisProxy(): Boolean {
        return _llmMode.value == LlmMode.CIRIS_PROXY
    }

    /**
     * Check if local user account fields should be shown.
     * Hidden for Google OAuth users since they'll sign in with Google.
     */
    fun showLocalUserFields(): Boolean {
        return _isGoogleAuth.value != true
    }

    /**
     * Generate a random admin password (32 chars).
     * Admin password is always auto-generated - users don't need to enter it.
     */
    fun generateAdminPassword(): String {
        val chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#\$%^&*"
        val password = (1..32).map { chars.random() }.joinToString("")
        Log.i(TAG, "generateAdminPassword: Generated 32-char random admin password")
        return password
    }

    /**
     * Log current state for debugging.
     */
    fun logCurrentState() {
        Log.i(TAG, "=== SetupViewModel State ===")
        Log.i(TAG, "  isGoogleAuth: ${_isGoogleAuth.value}")
        Log.i(TAG, "  googleEmail: ${_googleEmail.value}")
        Log.i(TAG, "  googleUserId: ${_googleUserId.value}")
        Log.i(TAG, "  hasGoogleIdToken: ${_googleIdToken.value != null}")
        Log.i(TAG, "  llmMode: ${_llmMode.value}")
        Log.i(TAG, "  llmProvider: ${_llmProvider.value}")
        Log.i(TAG, "  llmApiKey.length: ${_llmApiKey.value?.length ?: 0}")
        Log.i(TAG, "  llmBaseUrl: ${_llmBaseUrl.value}")
        Log.i(TAG, "  llmModel: ${_llmModel.value}")
        Log.i(TAG, "  username: ${_username.value}")
        Log.i(TAG, "  showLocalUserFields: ${showLocalUserFields()}")
        Log.i(TAG, "  useCirisProxy: ${useCirisProxy()}")
        Log.i(TAG, "============================")
    }
}
