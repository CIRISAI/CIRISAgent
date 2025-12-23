package ai.ciris.mobile.shared

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.ui.screens.InteractScreen
import ai.ciris.mobile.shared.viewmodels.InteractViewModel
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.lifecycle.viewmodel.compose.viewModel

/**
 * Main CIRIS app entry point
 * Shared across Android and iOS
 */
@Composable
fun CIRISApp(
    accessToken: String,
    baseUrl: String = "http://localhost:8080"
) {
    MaterialTheme {
        val apiClient = CIRISApiClient(baseUrl, accessToken)
        val viewModel: InteractViewModel = viewModel {
            InteractViewModel(apiClient)
        }

        InteractScreen(
            viewModel = viewModel,
            onNavigateBack = { /* Handle navigation */ }
        )
    }
}
