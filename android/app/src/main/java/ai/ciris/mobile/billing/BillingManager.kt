package ai.ciris.mobile.billing

import android.app.Activity
import android.content.Context
import android.util.Log
import com.android.billingclient.api.*
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * Manages Google Play Billing interactions for CIRIS credit purchases.
 *
 * Product catalog (must match server-side and Play Console):
 * - credits_100: 100 credits
 * - credits_250: 250 credits
 * - credits_600: 600 credits
 *
 * Flow:
 * 1. User selects product
 * 2. BillingManager launches Google Play purchase flow
 * 3. On success, purchase token is sent to CIRISBilling for verification
 * 4. Server verifies with Google, grants credits, acknowledges purchase
 */
class BillingManager(
    private val context: Context,
    private val billingApiClient: BillingApiClient
) : PurchasesUpdatedListener {

    companion object {
        private const val TAG = "CIRISBilling"

        // Product IDs - must match CIRISBilling server catalog
        val PRODUCT_IDS = listOf(
            "credits_100",
            "credits_250",
            "credits_600"
        )
    }

    // Billing client for Google Play
    private var billingClient: BillingClient? = null

    // Available products loaded from Google Play
    private val _products = MutableStateFlow<List<ProductDetails>>(emptyList())
    val products: StateFlow<List<ProductDetails>> = _products.asStateFlow()

    // Connection state
    private val _isConnected = MutableStateFlow(false)
    val isConnected: StateFlow<Boolean> = _isConnected.asStateFlow()

    // Purchase result callback
    var onPurchaseResult: ((PurchaseResult) -> Unit)? = null

    /**
     * Initialize billing client and connect to Google Play.
     */
    fun initialize() {
        Log.d(TAG, "Initializing billing client...")

        billingClient = BillingClient.newBuilder(context)
            .setListener(this)
            .enablePendingPurchases(
                PendingPurchasesParams.newBuilder()
                    .enableOneTimeProducts()
                    .build()
            )
            .build()

        startConnection()
    }

    private fun startConnection() {
        billingClient?.startConnection(object : BillingClientStateListener {
            override fun onBillingSetupFinished(result: BillingResult) {
                if (result.responseCode == BillingClient.BillingResponseCode.OK) {
                    Log.i(TAG, "Billing client connected")
                    _isConnected.value = true
                    queryProducts()
                } else {
                    Log.e(TAG, "Billing setup failed: ${result.debugMessage}")
                    _isConnected.value = false
                }
            }

            override fun onBillingServiceDisconnected() {
                Log.w(TAG, "Billing service disconnected")
                _isConnected.value = false
                // Retry connection
                startConnection()
            }
        })
    }

    /**
     * Query available products from Google Play.
     */
    private fun queryProducts() {
        val productList = PRODUCT_IDS.map { productId ->
            QueryProductDetailsParams.Product.newBuilder()
                .setProductId(productId)
                .setProductType(BillingClient.ProductType.INAPP)
                .build()
        }

        val params = QueryProductDetailsParams.newBuilder()
            .setProductList(productList)
            .build()

        billingClient?.queryProductDetailsAsync(params) { billingResult, productDetailsList ->
            if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                Log.i(TAG, "Loaded ${productDetailsList.size} products")
                _products.value = productDetailsList
            } else {
                Log.e(TAG, "Failed to load products: ${billingResult.debugMessage}")
            }
        }
    }

    /**
     * Launch the Google Play purchase flow for a product.
     */
    fun launchPurchaseFlow(activity: Activity, productDetails: ProductDetails) {
        val productDetailsParams = BillingFlowParams.ProductDetailsParams.newBuilder()
            .setProductDetails(productDetails)
            .build()

        val billingFlowParams = BillingFlowParams.newBuilder()
            .setProductDetailsParamsList(listOf(productDetailsParams))
            .build()

        val result = billingClient?.launchBillingFlow(activity, billingFlowParams)
        Log.d(TAG, "Launch billing flow result: ${result?.responseCode}")
    }

    /**
     * Called by Google Play when purchase is updated.
     */
    override fun onPurchasesUpdated(billingResult: BillingResult, purchases: List<Purchase>?) {
        when (billingResult.responseCode) {
            BillingClient.BillingResponseCode.OK -> {
                purchases?.forEach { purchase ->
                    handlePurchase(purchase)
                }
            }
            BillingClient.BillingResponseCode.USER_CANCELED -> {
                Log.i(TAG, "User cancelled purchase")
                onPurchaseResult?.invoke(PurchaseResult.Cancelled)
            }
            else -> {
                Log.e(TAG, "Purchase error: ${billingResult.debugMessage}")
                onPurchaseResult?.invoke(
                    PurchaseResult.Error("Purchase failed: ${billingResult.debugMessage}")
                )
            }
        }
    }

    /**
     * Handle a completed purchase - verify with server and grant credits.
     */
    private fun handlePurchase(purchase: Purchase) {
        if (purchase.purchaseState != Purchase.PurchaseState.PURCHASED) {
            Log.w(TAG, "Purchase not in PURCHASED state: ${purchase.purchaseState}")
            return
        }

        Log.i(TAG, "Processing purchase: ${purchase.products.firstOrNull()}")

        CoroutineScope(Dispatchers.IO).launch {
            try {
                // Send purchase token to CIRISBilling for verification
                val result = billingApiClient.verifyPurchase(
                    purchaseToken = purchase.purchaseToken,
                    productId = purchase.products.firstOrNull() ?: "",
                    packageName = context.packageName
                )

                withContext(Dispatchers.Main) {
                    if (result.success) {
                        Log.i(TAG, "Purchase verified! Credits added: ${result.creditsAdded}")
                        onPurchaseResult?.invoke(
                            PurchaseResult.Success(
                                creditsAdded = result.creditsAdded,
                                newBalance = result.newBalance,
                                alreadyProcessed = result.alreadyProcessed
                            )
                        )
                    } else {
                        Log.e(TAG, "Purchase verification failed: ${result.error}")
                        onPurchaseResult?.invoke(
                            PurchaseResult.Error(result.error ?: "Verification failed")
                        )
                    }
                }
            } catch (e: Exception) {
                Log.e(TAG, "Error verifying purchase", e)
                withContext(Dispatchers.Main) {
                    onPurchaseResult?.invoke(
                        PurchaseResult.Error("Verification error: ${e.message}")
                    )
                }
            }
        }
    }

    /**
     * Check for any pending purchases that need processing.
     * Call this on app startup to handle purchases made while app was closed.
     */
    fun processPendingPurchases() {
        billingClient?.queryPurchasesAsync(
            QueryPurchasesParams.newBuilder()
                .setProductType(BillingClient.ProductType.INAPP)
                .build()
        ) { billingResult, purchasesList ->
            if (billingResult.responseCode == BillingClient.BillingResponseCode.OK) {
                purchasesList.forEach { purchase ->
                    if (purchase.purchaseState == Purchase.PurchaseState.PURCHASED &&
                        !purchase.isAcknowledged) {
                        Log.i(TAG, "Found unacknowledged purchase, processing...")
                        handlePurchase(purchase)
                    }
                }
            }
        }
    }

    /**
     * End connection to billing service.
     */
    fun endConnection() {
        billingClient?.endConnection()
        billingClient = null
        _isConnected.value = false
    }
}

/**
 * Result of a purchase attempt.
 */
sealed class PurchaseResult {
    data class Success(
        val creditsAdded: Int,
        val newBalance: Int,
        val alreadyProcessed: Boolean
    ) : PurchaseResult()

    data class Error(val message: String) : PurchaseResult()

    object Cancelled : PurchaseResult()
}
