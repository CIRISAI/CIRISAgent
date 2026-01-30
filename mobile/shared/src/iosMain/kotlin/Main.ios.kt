package ai.ciris.mobile.shared

import androidx.compose.ui.window.ComposeUIViewController
import platform.Foundation.NSLog
import platform.UIKit.UIViewController

// StoreKit bridge imports
import ai.ciris.mobile.shared.platform.StoreKitCallback
import ai.ciris.mobile.shared.platform.StoreKitProduct
import ai.ciris.mobile.shared.platform.StoreKitPurchaseResult
import ai.ciris.mobile.shared.platform.StoreKitProductBridge
import ai.ciris.mobile.shared.platform.StoreKitPurchaseResultBridge

/**
 * iOS entry point for the CIRIS app.
 * Creates a UIViewController that hosts the Compose Multiplatform UI.
 *
 * This function is called from SwiftUI via UIViewControllerRepresentable.
 */
fun MainViewController(): UIViewController = ComposeUIViewController {
    CIRISApp(
        accessToken = "",  // Empty initially, will be populated after login
        baseUrl = "http://localhost:8080"  // Local Python server
    )
}

/**
 * iOS entry point with Apple Sign-In callback.
 * This version accepts a callback for Apple Sign-In integration.
 *
 * @param onAppleSignInRequested Callback triggered when user taps "Sign in with Apple"
 * @param onSilentSignInRequested Callback triggered for silent sign-in attempt
 */
fun MainViewControllerWithAuth(
    onAppleSignInRequested: (callback: (AppleSignInResultBridge) -> Unit) -> Unit,
    onSilentSignInRequested: (callback: (AppleSignInResultBridge) -> Unit) -> Unit
): UIViewController {
    NSLog("[Main.ios][INFO] MainViewControllerWithAuth called, creating NativeSignInCallback")

    val callback = object : NativeSignInCallback {
        override fun onGoogleSignInRequested(onResult: (NativeSignInResult) -> Unit) {
            NSLog("[Main.ios][INFO] onGoogleSignInRequested called - invoking Swift onAppleSignInRequested")
            onAppleSignInRequested { bridgeResult ->
                NSLog("[Main.ios][INFO] Got bridgeResult from Swift: type=${bridgeResult.type}")
                onResult(bridgeResult.toNativeResult())
            }
        }

        override fun onSilentSignInRequested(onResult: (NativeSignInResult) -> Unit) {
            NSLog("[Main.ios][INFO] onSilentSignInRequested called - invoking Swift onSilentSignInRequested")
            onSilentSignInRequested { bridgeResult ->
                NSLog("[Main.ios][INFO] Got silent bridgeResult from Swift: type=${bridgeResult.type}")
                onResult(bridgeResult.toNativeResult())
            }
        }
    }

    NSLog("[Main.ios][INFO] NativeSignInCallback created successfully")

    return ComposeUIViewController {
        NSLog("[Main.ios][INFO] ComposeUIViewController content lambda executing, passing callback to CIRISApp")
        CIRISApp(
            accessToken = "",
            baseUrl = "http://localhost:8080",
            googleSignInCallback = callback
        )
    }
}

/**
 * iOS entry point with Apple Sign-In and StoreKit callbacks.
 * This is the full-featured entry point for production use.
 *
 * @param onAppleSignInRequested Callback triggered when user taps "Sign in with Apple"
 * @param onSilentSignInRequested Callback triggered for silent sign-in attempt
 * @param onLoadProducts Callback to load StoreKit products
 * @param onPurchase Callback to purchase a product
 * @param isStoreLoading Callback to check if store is loading
 * @param getStoreError Callback to get store error message
 */
fun MainViewControllerWithAuthAndStore(
    onAppleSignInRequested: (callback: (AppleSignInResultBridge) -> Unit) -> Unit,
    onSilentSignInRequested: (callback: (AppleSignInResultBridge) -> Unit) -> Unit,
    onLoadProducts: (callback: (List<StoreKitProductBridge>) -> Unit) -> Unit,
    onPurchase: (productId: String, appleIDToken: String, callback: (StoreKitPurchaseResultBridge) -> Unit) -> Unit,
    isStoreLoading: () -> Boolean,
    getStoreError: () -> String?
): UIViewController {
    NSLog("[Main.ios][INFO] MainViewControllerWithAuthAndStore called")

    val signInCallback = object : NativeSignInCallback {
        override fun onGoogleSignInRequested(onResult: (NativeSignInResult) -> Unit) {
            NSLog("[Main.ios][INFO] onGoogleSignInRequested called - invoking Swift onAppleSignInRequested")
            onAppleSignInRequested { bridgeResult ->
                NSLog("[Main.ios][INFO] Got bridgeResult from Swift: type=${bridgeResult.type}")
                onResult(bridgeResult.toNativeResult())
            }
        }

        override fun onSilentSignInRequested(onResult: (NativeSignInResult) -> Unit) {
            NSLog("[Main.ios][INFO] onSilentSignInRequested called - invoking Swift onSilentSignInRequested")
            onSilentSignInRequested { bridgeResult ->
                NSLog("[Main.ios][INFO] Got silent bridgeResult from Swift: type=${bridgeResult.type}")
                onResult(bridgeResult.toNativeResult())
            }
        }
    }

    // Create a PurchaseLauncher that wraps the StoreKit callbacks
    // Store the purchase result callback to be invoked when Swift returns results
    var purchaseResultCallback: PurchaseResultCallback? = null
    var currentAuthToken: String? = null

    val purchaseLauncher = object : PurchaseLauncher {
        override fun launchPurchase(productId: String) {
            NSLog("[Main.ios][INFO] launchPurchase called for $productId (no auth token)")
            // Cannot purchase without auth token on iOS - need to use launchPurchaseWithAuth
            purchaseResultCallback?.onResult(PurchaseResultType.Error("Authentication required for purchase"))
        }

        override fun launchPurchaseWithAuth(productId: String, authToken: String) {
            NSLog("[Main.ios][INFO] launchPurchaseWithAuth called for $productId")
            currentAuthToken = authToken
            onPurchase(productId, authToken) { bridgeResult ->
                NSLog("[Main.ios][INFO] Got purchase result from Swift: type=${bridgeResult.type}")
                val result = when (val storeKitResult = bridgeResult.toResult()) {
                    is StoreKitPurchaseResult.Success -> PurchaseResultType.Success(
                        creditsAdded = storeKitResult.creditsAdded,
                        newBalance = storeKitResult.newBalance
                    )
                    is StoreKitPurchaseResult.Cancelled -> PurchaseResultType.Cancelled
                    is StoreKitPurchaseResult.Pending -> PurchaseResultType.Error("Purchase pending approval")
                    is StoreKitPurchaseResult.Failed -> PurchaseResultType.Error(storeKitResult.error)
                }
                purchaseResultCallback?.onResult(result)
            }
        }

        override fun loadProducts(onResult: (List<ProductInfo>) -> Unit) {
            NSLog("[Main.ios][INFO] loadProducts called")
            onLoadProducts { bridgeProducts ->
                NSLog("[Main.ios][INFO] Got ${bridgeProducts.size} products from Swift")
                val products = bridgeProducts.map { bp ->
                    ProductInfo(
                        id = bp.id,
                        displayName = bp.displayName,
                        description = bp.description,
                        displayPrice = bp.displayPrice,
                        price = bp.price
                    )
                }
                onResult(products)
            }
        }

        override fun isLoading(): Boolean = isStoreLoading()
        override fun getErrorMessage(): String? = getStoreError()

        override fun setOnPurchaseResult(callback: PurchaseResultCallback) {
            purchaseResultCallback = callback
        }
    }

    NSLog("[Main.ios][INFO] Callbacks created successfully")

    return ComposeUIViewController {
        NSLog("[Main.ios][INFO] ComposeUIViewController content lambda executing with auth and store callbacks")
        CIRISApp(
            accessToken = "",
            baseUrl = "http://localhost:8080",
            googleSignInCallback = signInCallback,
            purchaseLauncher = purchaseLauncher
        )
    }
}

class AppleSignInResultBridge private constructor(
    val type: String,  // "success", "error", "cancelled"
    val idToken: String? = null,
    val userId: String? = null,
    val email: String? = null,
    val displayName: String? = null,
    val errorMessage: String? = null
) {
    companion object {
        fun success(idToken: String, userId: String, email: String?, displayName: String?): AppleSignInResultBridge {
            return AppleSignInResultBridge(
                type = "success",
                idToken = idToken,
                userId = userId,
                email = email,
                displayName = displayName
            )
        }

        fun error(message: String): AppleSignInResultBridge {
            return AppleSignInResultBridge(type = "error", errorMessage = message)
        }

        fun cancelled(): AppleSignInResultBridge {
            return AppleSignInResultBridge(type = "cancelled")
        }
    }

    fun toNativeResult(): NativeSignInResult {
        return when (type) {
            "success" -> NativeSignInResult.Success(
                idToken = idToken ?: "",
                userId = userId ?: "",
                email = email,
                displayName = displayName,
                provider = "apple"
            )
            "cancelled" -> NativeSignInResult.Cancelled
            else -> NativeSignInResult.Error(errorMessage ?: "Unknown error")
        }
    }
}
