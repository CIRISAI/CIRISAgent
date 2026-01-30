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
