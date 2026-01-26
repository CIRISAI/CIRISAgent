package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.CreditStatusData
import ai.ciris.mobile.shared.ui.screens.CreditProduct
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Shared ViewModel for billing/credits interface
 * Uses CIRISApiClient for all API calls (centralized auth handling)
 *
 * Features:
 * - Credit balance tracking
 * - Product catalog display
 * - Balance refresh
 * - Purchase status tracking
 *
 * Note: Actual Google Play purchase flow is platform-specific and handled
 * by platform adapters. This ViewModel provides the shared state management
 * and API communication layer.
 */
class BillingViewModel(
    private val apiClient: CIRISApiClient,
    baseUrl: String = "http://localhost:8080"
) : ViewModel() {

    companion object {
        private const val TAG = "BillingViewModel"
        private const val BALANCE_POLL_INTERVAL_MS = 30000L // Poll every 30 seconds

        // Product catalog - must match server-side configuration
        // These are the default credit packages available
        val DEFAULT_PRODUCTS = listOf(
            CreditProduct(
                productId = "credits_100",
                credits = 100,
                price = "$0.99",
                description = "Starter pack - great for trying out CIRIS"
            ),
            CreditProduct(
                productId = "credits_250",
                credits = 250,
                price = "$1.99",
                description = "Standard pack - best value for regular use"
            ),
            CreditProduct(
                productId = "credits_600",
                credits = 600,
                price = "$3.99",
                description = "Power user pack - maximum savings"
            )
        )
    }

    private fun log(level: String, method: String, message: String) {
        println("[$TAG][$level][$method] $message")
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logWarn(method: String, message: String) = log("WARN", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    private fun logException(method: String, e: Exception, context: String = "") {
        val contextStr = if (context.isNotEmpty()) " | Context: $context" else ""
        logError(method, "Exception: ${e::class.simpleName}: ${e.message}$contextStr")
        logError(method, "Stack trace: ${e.stackTraceToString().take(500)}")
    }

    // Current credit balance (-1 means not loaded or requires sign-in)
    private val _currentBalance = MutableStateFlow(-1)
    val currentBalance: StateFlow<Int> = _currentBalance.asStateFlow()

    // Available products
    private val _products = MutableStateFlow<List<CreditProduct>>(DEFAULT_PRODUCTS)
    val products: StateFlow<List<CreditProduct>> = _products.asStateFlow()

    // Loading state
    private val _isLoading = MutableStateFlow(false)
    val isLoading: StateFlow<Boolean> = _isLoading.asStateFlow()

    // Error state
    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    // Success message (e.g., after purchase)
    private val _successMessage = MutableStateFlow<String?>(null)
    val successMessage: StateFlow<String?> = _successMessage.asStateFlow()

    // BYOK mode indicator (user provides their own key, no billing needed)
    private val _isByokMode = MutableStateFlow(false)
    val isByokMode: StateFlow<Boolean> = _isByokMode.asStateFlow()

    // Detailed credit status
    private val _creditStatus = MutableStateFlow<CreditStatusData?>(null)
    val creditStatus: StateFlow<CreditStatusData?> = _creditStatus.asStateFlow()

    // Purchase in progress
    private val _isPurchasing = MutableStateFlow(false)
    val isPurchasing: StateFlow<Boolean> = _isPurchasing.asStateFlow()

    // Balance polling job
    private var balancePollingJob: Job? = null

    init {
        logInfo("init", "BillingViewModel initialized")
        // Don't auto-load balance in init - wait for token to be set via CIRISApp
    }

    /**
     * Load current credit balance from API
     */
    fun loadBalance() {
        val method = "loadBalance"
        logInfo(method, "Loading credit balance...")

        viewModelScope.launch {
            _isLoading.value = true
            _errorMessage.value = null

            try {
                logDebug(method, "Calling apiClient.getCredits()")
                val creditStatus = apiClient.getCredits()
                logInfo(method, "Credit status loaded: hasCredit=${creditStatus.hasCredit}, " +
                    "creditsRemaining=${creditStatus.creditsRemaining}, " +
                    "freeUsesRemaining=${creditStatus.freeUsesRemaining}, " +
                    "dailyFreeUsesRemaining=${creditStatus.dailyFreeUsesRemaining}, " +
                    "planName=${creditStatus.planName}")

                // Check for BYOK/unlimited mode
                if (creditStatus.planName == "unlimited") {
                    logInfo(method, "BYOK mode detected - user has unlimited credits")
                    _isByokMode.value = true
                    _currentBalance.value = -1 // Show "unlimited" in UI
                    _creditStatus.value = creditStatus
                } else {
                    _isByokMode.value = false
                    // Calculate total credits (paid + free + daily free)
                    val totalCredits = creditStatus.creditsRemaining +
                        creditStatus.freeUsesRemaining +
                        (creditStatus.dailyFreeUsesRemaining ?: 0)
                    logInfo(method, "Total credits calculated: $totalCredits")
                    _currentBalance.value = totalCredits
                    _creditStatus.value = creditStatus
                }

            } catch (e: Exception) {
                logException(method, e)
                handleBalanceError("Failed to load balance: ${e.message}")
            } finally {
                _isLoading.value = false
            }
        }
    }

    /**
     * Handle balance loading error
     */
    private fun handleBalanceError(message: String) {
        val method = "handleBalanceError"
        logError(method, message)
        _errorMessage.value = message
        _currentBalance.value = -1
    }

    /**
     * Refresh balance (manual refresh button)
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Manual refresh triggered")
        loadBalance()
    }

    /**
     * Start periodic balance polling
     */
    fun startBalancePolling() {
        val method = "startBalancePolling"
        logInfo(method, "Starting balance polling (interval=${BALANCE_POLL_INTERVAL_MS}ms)")

        balancePollingJob?.cancel()
        balancePollingJob = viewModelScope.launch {
            var pollCount = 0
            while (isActive) {
                pollCount++
                try {
                    if (pollCount > 1) { // Skip first poll since loadBalance() runs in init
                        logDebug(method, "Balance poll #$pollCount")
                        loadBalanceSilently()
                    }
                } catch (e: Exception) {
                    logWarn(method, "Balance poll failed: ${e.message}")
                }
                delay(BALANCE_POLL_INTERVAL_MS)
            }
        }
    }

    /**
     * Stop balance polling
     */
    fun stopBalancePolling() {
        val method = "stopBalancePolling"
        logInfo(method, "Stopping balance polling")
        balancePollingJob?.cancel()
        balancePollingJob = null
    }

    /**
     * Load balance silently (no loading indicator, no error messages)
     * Used for background polling
     */
    private suspend fun loadBalanceSilently() {
        val method = "loadBalanceSilently"
        try {
            val creditStatus = apiClient.getCredits()
            if (creditStatus.planName == "unlimited") {
                _isByokMode.value = true
                _currentBalance.value = -1
            } else {
                _isByokMode.value = false
                val totalCredits = creditStatus.creditsRemaining +
                    creditStatus.freeUsesRemaining +
                    (creditStatus.dailyFreeUsesRemaining ?: 0)
                _currentBalance.value = totalCredits
            }
            _creditStatus.value = creditStatus
            logDebug(method, "Silent balance update: ${_currentBalance.value}")
        } catch (e: Exception) {
            logWarn(method, "Silent balance load failed: ${e.message}")
            // Don't update error state for silent polls
        }
    }

    /**
     * Handle product selection
     * This prepares for purchase but actual purchase flow is platform-specific
     *
     * @param product The selected product
     * @param onPurchaseReady Callback when ready to initiate platform-specific purchase
     */
    fun onProductSelected(
        product: CreditProduct,
        onPurchaseReady: (CreditProduct) -> Unit
    ) {
        val method = "onProductSelected"
        logInfo(method, "Product selected: ${product.productId} (${product.credits} credits, ${product.price})")

        // Check if user can make purchases
        if (_isByokMode.value) {
            logWarn(method, "Purchase not needed - BYOK mode active")
            _errorMessage.value = "You have unlimited credits (BYOK mode)"
            return
        }

        if (_isPurchasing.value) {
            logWarn(method, "Purchase already in progress, ignoring")
            return
        }

        logInfo(method, "Ready to initiate purchase flow for ${product.productId}")
        onPurchaseReady(product)
    }

    /**
     * Mark purchase as started
     * Called by platform-specific code when purchase flow begins
     */
    fun onPurchaseStarted(productId: String) {
        val method = "onPurchaseStarted"
        logInfo(method, "Purchase started for product: $productId")
        _isPurchasing.value = true
        _errorMessage.value = null
        _successMessage.value = null
    }

    /**
     * Handle successful purchase
     * Called by platform-specific code after purchase verification
     *
     * @param creditsAdded Number of credits added
     * @param newBalance New total balance
     */
    fun onPurchaseSuccess(creditsAdded: Int, newBalance: Int) {
        val method = "onPurchaseSuccess"
        logInfo(method, "Purchase successful! Credits added: $creditsAdded, new balance: $newBalance")

        _isPurchasing.value = false
        _currentBalance.value = newBalance
        _successMessage.value = "Purchase complete! Added $creditsAdded credits."
        _errorMessage.value = null

        // Refresh to get updated credit status
        viewModelScope.launch {
            delay(1000) // Short delay before refresh
            loadBalanceSilently()
        }
    }

    /**
     * Handle purchase cancellation
     */
    fun onPurchaseCancelled() {
        val method = "onPurchaseCancelled"
        logInfo(method, "Purchase cancelled by user")
        _isPurchasing.value = false
        // No error message for user cancellation
    }

    /**
     * Handle purchase error
     */
    fun onPurchaseError(error: String) {
        val method = "onPurchaseError"
        logError(method, "Purchase failed: $error")
        _isPurchasing.value = false
        _errorMessage.value = "Purchase failed: $error"
    }

    /**
     * Clear error message
     */
    fun clearError() {
        val method = "clearError"
        logDebug(method, "Clearing error message")
        _errorMessage.value = null
    }

    /**
     * Clear success message
     */
    fun clearSuccess() {
        val method = "clearSuccess"
        logDebug(method, "Clearing success message")
        _successMessage.value = null
    }

    /**
     * Get formatted balance string for display
     */
    fun getFormattedBalance(): String {
        val method = "getFormattedBalance"
        val balance = _currentBalance.value
        val formatted = when {
            _isByokMode.value -> "Unlimited (BYOK)"
            balance < 0 -> "Sign in to view"
            else -> "$balance credits"
        }
        logDebug(method, "Formatted balance: $formatted")
        return formatted
    }

    /**
     * Check if purchase is required (no credits remaining)
     */
    fun isPurchaseRequired(): Boolean {
        val method = "isPurchaseRequired"
        val creditStatus = _creditStatus.value
        val required = creditStatus?.purchaseRequired == true
        logDebug(method, "Purchase required: $required")
        return required
    }

    /**
     * Get breakdown of credit sources
     */
    fun getCreditBreakdown(): CreditBreakdown {
        val method = "getCreditBreakdown"
        val status = _creditStatus.value
        val breakdown = if (status != null) {
            CreditBreakdown(
                paidCredits = status.creditsRemaining,
                freeUses = status.freeUsesRemaining,
                dailyFreeUses = status.dailyFreeUsesRemaining ?: 0,
                totalUses = status.totalUses,
                planName = status.planName
            )
        } else {
            CreditBreakdown()
        }
        logDebug(method, "Credit breakdown: paid=${breakdown.paidCredits}, " +
            "free=${breakdown.freeUses}, daily=${breakdown.dailyFreeUses}")
        return breakdown
    }

    override fun onCleared() {
        val method = "onCleared"
        logInfo(method, "ViewModel cleared, stopping polling")
        super.onCleared()
        stopBalancePolling()
    }
}

/**
 * Credit breakdown for detailed display
 */
data class CreditBreakdown(
    val paidCredits: Int = 0,
    val freeUses: Int = 0,
    val dailyFreeUses: Int = 0,
    val totalUses: Int = 0,
    val planName: String? = null
) {
    val total: Int get() = paidCredits + freeUses + dailyFreeUses
}
