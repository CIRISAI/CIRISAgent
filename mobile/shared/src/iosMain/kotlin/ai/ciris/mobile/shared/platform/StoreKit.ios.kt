package ai.ciris.mobile.shared.platform

import platform.Foundation.NSLog

/**
 * iOS StoreKit product information
 */
data class StoreKitProduct(
    val id: String,
    val displayName: String,
    val description: String,
    val displayPrice: String,
    val price: Double
)

/**
 * Result of a StoreKit purchase
 */
sealed class StoreKitPurchaseResult {
    data class Success(val creditsAdded: Int, val newBalance: Int) : StoreKitPurchaseResult()
    object Cancelled : StoreKitPurchaseResult()
    object Pending : StoreKitPurchaseResult()
    data class Failed(val error: String) : StoreKitPurchaseResult()
}

/**
 * Callback interface for StoreKit operations.
 * Implemented in Swift and passed to Kotlin.
 */
interface StoreKitCallback {
    /**
     * Load available products
     */
    fun loadProducts(onResult: (List<StoreKitProduct>) -> Unit)

    /**
     * Purchase a product
     * @param productId The product ID to purchase
     * @param appleIDToken The Apple ID token for authentication with billing backend
     * @param onResult Callback with purchase result
     */
    fun purchase(productId: String, appleIDToken: String, onResult: (StoreKitPurchaseResult) -> Unit)

    /**
     * Check if products are loading
     */
    fun isLoading(): Boolean

    /**
     * Get current error message if any
     */
    fun getErrorMessage(): String?
}

/**
 * Bridge class for StoreKit results from Swift.
 * This class is visible to Swift and provides a simple interface for passing results.
 */
class StoreKitProductBridge private constructor(
    val id: String,
    val displayName: String,
    val description: String,
    val displayPrice: String,
    val price: Double
) {
    companion object {
        fun create(
            id: String,
            displayName: String,
            description: String,
            displayPrice: String,
            price: Double
        ): StoreKitProductBridge {
            return StoreKitProductBridge(id, displayName, description, displayPrice, price)
        }
    }

    fun toProduct(): StoreKitProduct {
        return StoreKitProduct(
            id = id,
            displayName = displayName,
            description = description,
            displayPrice = displayPrice,
            price = price
        )
    }
}

/**
 * Bridge class for StoreKit purchase results from Swift.
 */
class StoreKitPurchaseResultBridge private constructor(
    val type: String,  // "success", "cancelled", "pending", "failed"
    val creditsAdded: Int = 0,
    val newBalance: Int = 0,
    val errorMessage: String? = null
) {
    companion object {
        fun success(creditsAdded: Int, newBalance: Int): StoreKitPurchaseResultBridge {
            return StoreKitPurchaseResultBridge(
                type = "success",
                creditsAdded = creditsAdded,
                newBalance = newBalance
            )
        }

        fun cancelled(): StoreKitPurchaseResultBridge {
            return StoreKitPurchaseResultBridge(type = "cancelled")
        }

        fun pending(): StoreKitPurchaseResultBridge {
            return StoreKitPurchaseResultBridge(type = "pending")
        }

        fun failed(error: String): StoreKitPurchaseResultBridge {
            return StoreKitPurchaseResultBridge(type = "failed", errorMessage = error)
        }
    }

    fun toResult(): StoreKitPurchaseResult {
        return when (type) {
            "success" -> StoreKitPurchaseResult.Success(creditsAdded, newBalance)
            "cancelled" -> StoreKitPurchaseResult.Cancelled
            "pending" -> StoreKitPurchaseResult.Pending
            else -> StoreKitPurchaseResult.Failed(errorMessage ?: "Unknown error")
        }
    }
}
