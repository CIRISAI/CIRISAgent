package ai.ciris.mobile.shared.localization

import ai.ciris.mobile.shared.viewmodels.SupportedCurrency
import androidx.compose.runtime.*

/**
 * CompositionLocal for accessing the CurrencyManager throughout the Compose tree.
 *
 * Usage:
 * ```kotlin
 * // At the root of your app:
 * CompositionLocalProvider(LocalCurrency provides currencyManager) {
 *     // Your app content
 * }
 *
 * // Anywhere in your composables:
 * val converted = convertedCurrency(100.0) // Returns "$100.00" or "€92.00" etc
 * ```
 */
val LocalCurrency = staticCompositionLocalOf<CurrencyManager?> { null }

/**
 * Composable function to convert USDC to the user's selected currency.
 * Automatically recomposes when currency changes.
 *
 * @param usdcAmount Amount in USDC
 * @return Formatted string with currency symbol (e.g., "$100.00", "€92.00")
 */
@Composable
fun convertedCurrency(usdcAmount: Double): String {
    val currency = LocalCurrency.current

    // Subscribe to currency changes to trigger recomposition
    val currentCurrency by currency?.currentCurrency?.collectAsState()
        ?: remember { mutableStateOf("USD") }

    return if (currency != null) {
        currency.convertFromUsdc(usdcAmount)
    } else {
        // Fallback if currency manager not available
        "$${"%.2f".format(usdcAmount)}"
    }
}

/**
 * Composable function to convert USDC to a specific currency.
 *
 * @param usdcAmount Amount in USDC
 * @param currencyCode Target currency code
 * @return Formatted string with currency symbol
 */
@Composable
fun convertedCurrencyTo(usdcAmount: Double, currencyCode: String): String {
    val currency = LocalCurrency.current
    return currency?.convertFromUsdcTo(usdcAmount, currencyCode)
        ?: "$${"%.2f".format(usdcAmount)}"
}

/**
 * Composable function to get current currency info.
 *
 * @return Current SupportedCurrency, or USD default
 */
@Composable
fun currentCurrencyInfo(): SupportedCurrency {
    val currency = LocalCurrency.current
    return currency?.currentCurrencyInfo?.collectAsState()?.value
        ?: SupportedCurrency("USD", "$", "US Dollar", "US Dollar", 2)
}

/**
 * Composable function to get all available currencies.
 *
 * @return List of all supported currencies
 */
@Composable
fun availableCurrencies(): List<SupportedCurrency> {
    val currency = LocalCurrency.current
    return currency?.getAvailableCurrencies() ?: emptyList()
}

/**
 * Non-composable helper to get the CurrencyManager for ViewModels.
 * Use this when you need to access currency outside of Compose context.
 */
object CurrencyHelper {
    private var manager: CurrencyManager? = null

    fun setManager(currencyManager: CurrencyManager) {
        manager = currencyManager
    }

    fun convertFromUsdc(usdcAmount: Double): String {
        return manager?.convertFromUsdc(usdcAmount) ?: "$${"%.2f".format(usdcAmount)}"
    }

    fun getCurrentCurrency(): String {
        return manager?.currentCurrency?.value ?: "USD"
    }

    fun getManager(): CurrencyManager? = manager
}
