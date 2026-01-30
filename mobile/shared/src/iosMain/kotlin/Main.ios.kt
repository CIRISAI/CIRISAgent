package ai.ciris.mobile.shared

import androidx.compose.ui.window.ComposeUIViewController
import platform.UIKit.UIViewController

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
): UIViewController = ComposeUIViewController {
    CIRISApp(
        accessToken = "",
        baseUrl = "http://localhost:8080",
        googleSignInCallback = object : NativeSignInCallback {
            override fun onGoogleSignInRequested(onResult: (NativeSignInResult) -> Unit) {
                onAppleSignInRequested { bridgeResult ->
                    onResult(bridgeResult.toNativeResult())
                }
            }

            override fun onSilentSignInRequested(onResult: (NativeSignInResult) -> Unit) {
                onSilentSignInRequested { bridgeResult ->
                    onResult(bridgeResult.toNativeResult())
                }
            }
        }
    )
}

/**
 * Bridge class for Apple Sign-In results from Swift.
 * This class is visible to Swift and provides a simple interface for passing results.
 */
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
