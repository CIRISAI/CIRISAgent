package ai.ciris.mobile.shared.localization

import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.SecureStorage
import ai.ciris.mobile.shared.viewmodels.SUPPORTED_CURRENCIES
import ai.ciris.mobile.shared.viewmodels.SupportedCurrency
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlin.math.pow
import kotlin.math.roundToLong

/**
 * Currency manager for wallet balance display.
 *
 * Handles currency preference persistence and provides conversion utilities
 * for displaying USDC wallet balances in the user's preferred currency.
 *
 * Note: USDC is pegged 1:1 to USD, so USD rates apply directly.
 * For other currencies, exchange rates are approximations that update periodically.
 *
 * Usage:
 * ```kotlin
 * val manager = CurrencyManager(scope, storage)
 * manager.convertFromUsdc(100.0) // Returns "€92.50" if EUR selected
 * ```
 */
class CurrencyManager(
    private val scope: CoroutineScope,
    private val secureStorage: SecureStorage
) {
    companion object {
        private const val TAG = "CurrencyManager"
        private const val PREF_KEY_CURRENCY = "ciris_display_currency"
        private const val DEFAULT_CURRENCY = "USD"

        // Default exchange rates (USD to currency)
        // These are approximations - in production, fetch from an API
        // Updated periodically via background refresh
        private val DEFAULT_RATES = mapOf(
            "USDC" to 1.0,       // 1:1 peg
            "USD" to 1.0,
            "EUR" to 0.92,
            "GBP" to 0.79,
            "JPY" to 149.50,
            "CNY" to 7.24,
            "ETB" to 56.50,      // Ethiopian Birr
            "INR" to 83.12,
            "KRW" to 1320.0,
            "BRL" to 4.97,
            "MXN" to 17.15,
            "RUB" to 92.0,
            "TRY" to 32.0,
            "ZAR" to 18.50,
            "NGN" to 1550.0,
            "KES" to 153.0,
            "BTC" to 0.000015,   // ~$67,000 per BTC
            "ETH" to 0.00029     // ~$3,450 per ETH
        )
    }

    // Current currency code
    private val _currentCurrency = MutableStateFlow(DEFAULT_CURRENCY)
    val currentCurrency: StateFlow<String> = _currentCurrency.asStateFlow()

    // Current currency info
    private val _currentCurrencyInfo = MutableStateFlow(
        SUPPORTED_CURRENCIES.first { it.code == DEFAULT_CURRENCY }
    )
    val currentCurrencyInfo: StateFlow<SupportedCurrency> = _currentCurrencyInfo.asStateFlow()

    // Exchange rates (USD to target currency)
    private val _exchangeRates = MutableStateFlow(DEFAULT_RATES)
    val exchangeRates: StateFlow<Map<String, Double>> = _exchangeRates.asStateFlow()

    // Last update timestamp
    private val _lastRateUpdate = MutableStateFlow(0L)
    val lastRateUpdate: StateFlow<Long> = _lastRateUpdate.asStateFlow()

    /**
     * Initialize the currency manager.
     * Loads persisted currency preference.
     */
    suspend fun initialize() {
        PlatformLogger.i(TAG, "Initializing currency manager...")

        // Load persisted currency preference
        val savedCurrency = secureStorage.get(PREF_KEY_CURRENCY).getOrNull()
        val validCurrency = if (savedCurrency != null && SUPPORTED_CURRENCIES.any { it.code == savedCurrency }) {
            savedCurrency
        } else {
            DEFAULT_CURRENCY
        }

        val currencyInfo = SUPPORTED_CURRENCIES.find { it.code == validCurrency }
            ?: SUPPORTED_CURRENCIES.first { it.code == DEFAULT_CURRENCY }

        _currentCurrency.value = validCurrency
        _currentCurrencyInfo.value = currencyInfo

        PlatformLogger.i(TAG, "Currency initialized: ${currencyInfo.name} (${currencyInfo.code})")
    }

    /**
     * Set the display currency.
     */
    fun setCurrency(currencyCode: String) {
        val currencyInfo = SUPPORTED_CURRENCIES.find { it.code == currencyCode }
        if (currencyInfo == null) {
            PlatformLogger.w(TAG, "Unsupported currency code: $currencyCode")
            return
        }

        scope.launch(Dispatchers.IO) {
            _currentCurrency.value = currencyCode
            _currentCurrencyInfo.value = currencyInfo
            secureStorage.save(PREF_KEY_CURRENCY, currencyCode)
            PlatformLogger.i(TAG, "Currency set to: ${currencyInfo.name} (${currencyInfo.code})")
        }
    }

    /**
     * Convert USDC amount to the user's selected currency.
     * Returns formatted string with symbol.
     *
     * @param usdcAmount Amount in USDC (1:1 with USD)
     * @return Formatted string like "$100.00" or "€92.00" or "¥14,950"
     */
    fun convertFromUsdc(usdcAmount: Double): String {
        val currencyInfo = _currentCurrencyInfo.value
        val rate = _exchangeRates.value[currencyInfo.code] ?: 1.0
        val converted = usdcAmount * rate

        return formatCurrency(converted, currencyInfo)
    }

    /**
     * Convert USDC amount to a specific currency.
     *
     * @param usdcAmount Amount in USDC
     * @param currencyCode Target currency code
     * @return Formatted string with symbol
     */
    fun convertFromUsdcTo(usdcAmount: Double, currencyCode: String): String {
        val currencyInfo = SUPPORTED_CURRENCIES.find { it.code == currencyCode }
            ?: _currentCurrencyInfo.value
        val rate = _exchangeRates.value[currencyCode] ?: 1.0
        val converted = usdcAmount * rate

        return formatCurrency(converted, currencyInfo)
    }

    /**
     * Get the raw converted value (not formatted).
     */
    fun convertValueFromUsdc(usdcAmount: Double): Double {
        val rate = _exchangeRates.value[_currentCurrency.value] ?: 1.0
        return usdcAmount * rate
    }

    /**
     * Format a currency value with the appropriate symbol and decimals.
     */
    fun formatCurrency(amount: Double, currency: SupportedCurrency = _currentCurrencyInfo.value): String {
        val multiplier = 10.0.pow(currency.decimals.toDouble())
        val rounded = (amount * multiplier).roundToLong() / multiplier

        // Format with proper decimal places
        val formatted = if (currency.decimals == 0) {
            rounded.toLong().toString()
        } else {
            // Format with thousands separators for large numbers
            val intPart = rounded.toLong()
            val decPart = ((rounded - intPart) * multiplier).roundToLong()
            val decStr = decPart.toString().padStart(currency.decimals, '0')

            if (intPart >= 1000) {
                formatWithThousandsSeparator(intPart) + "." + decStr
            } else {
                "$intPart.$decStr"
            }
        }

        // Place symbol based on currency conventions
        return when (currency.code) {
            // Currencies where symbol follows the number
            "ETB", "KES" -> "$formatted ${currency.symbol}"
            // Most currencies: symbol before
            else -> "${currency.symbol}$formatted"
        }
    }

    /**
     * Format number with thousands separators.
     */
    private fun formatWithThousandsSeparator(value: Long): String {
        val str = value.toString()
        val result = StringBuilder()
        var count = 0
        for (i in str.length - 1 downTo 0) {
            if (count > 0 && count % 3 == 0) {
                result.insert(0, ',')
            }
            result.insert(0, str[i])
            count++
        }
        return result.toString()
    }

    /**
     * Update exchange rates (called when rates are fetched from API).
     */
    fun updateRates(rates: Map<String, Double>) {
        scope.launch {
            _exchangeRates.value = rates
            _lastRateUpdate.value = System.currentTimeMillis()
            PlatformLogger.i(TAG, "Exchange rates updated: ${rates.size} currencies")
        }
    }

    /**
     * Get all available currencies.
     */
    fun getAvailableCurrencies(): List<SupportedCurrency> = SUPPORTED_CURRENCIES
}
