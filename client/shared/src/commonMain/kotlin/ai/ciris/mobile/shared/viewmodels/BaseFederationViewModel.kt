package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Shared scaffolding for the 10 federation sub-screen ViewModels.
 *
 * Intentionally minimal — the federation sub-screens have very
 * different state shapes (peer list, peer detail, SAS verification,
 * events stream, content fetch, ...), so this base only carries the
 * pieces every screen actually shares:
 *
 *  - the injected [CIRISApiClient]
 *  - a [loading] flag for spinner state
 *  - an [error] string for surface-level failure messaging
 *  - a [runApi] helper that wraps a suspend call with consistent
 *    loading-flag + try/catch wiring
 *
 * Sub-screens add their own typed [StateFlow]s and call [runApi] for
 * the network round-trips. Do not push specialised state into this
 * base; the temptation to grow it into a god-base is real.
 */
abstract class BaseFederationViewModel(
    protected val apiClient: CIRISApiClient,
) : ViewModel() {

    protected abstract val tag: String

    protected val _loading = MutableStateFlow(false)
    val loading: StateFlow<Boolean> = _loading.asStateFlow()

    protected val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    /** Acknowledge a transient error after the user sees it. */
    fun clearError() {
        _error.value = null
    }

    /**
     * Execute one network round-trip with shared loading + error
     * scaffolding. Returns the call's result on success, or ``null``
     * on exception (the exception message lands in [error]).
     *
     * Sub-screens should call this from inside their own
     * ``viewModelScope.launch`` blocks when they need to compose
     * multiple round-trips into one user action; otherwise prefer
     * [launchApi] which handles the launch boilerplate too.
     */
    protected suspend fun <T> runApi(
        operation: String,
        block: suspend () -> T,
    ): T? = try {
        _loading.value = true
        _error.value = null
        block()
    } catch (e: Exception) {
        val msg = e.message ?: e::class.simpleName ?: "unknown error"
        _error.value = msg
        PlatformLogger.e(tag, "[$operation] $msg", e)
        null
    } finally {
        _loading.value = false
    }

    /**
     * Convenience launch + [runApi] for single-call user actions.
     * Optional [onSuccess] handler runs only when the call succeeded.
     */
    protected fun <T> launchApi(
        operation: String,
        block: suspend () -> T,
        onSuccess: (T) -> Unit = {},
    ) {
        viewModelScope.launch {
            val result = runApi(operation, block) ?: return@launch
            onSuccess(result)
        }
    }
}
