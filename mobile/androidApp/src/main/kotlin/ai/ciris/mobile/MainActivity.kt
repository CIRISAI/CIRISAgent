package ai.ciris.mobile

import ai.ciris.mobile.shared.CIRISApp
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/**
 * Main Activity for CIRIS Android (KMP version)
 *
 * Responsibilities:
 * 1. Initialize Python runtime (Chaquopy)
 * 2. Start CIRIS engine (FastAPI server on localhost:8080)
 * 3. Show startup splash (22 service lights)
 * 4. Launch Compose UI when ready
 *
 * Based on original android/app/src/main/java/ai/ciris/mobile/MainActivity.kt
 */
class MainActivity : ComponentActivity() {

    private var serverStarted = false
    private val TAG = "MainActivity"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Initialize Python runtime (Chaquopy)
        if (!Python.isStarted()) {
            Log.i(TAG, "Initializing Python runtime...")
            Python.start(AndroidPlatform(this))
            Log.i(TAG, "Python runtime started")
        }

        setContent {
            var isReady by remember { mutableStateOf(false) }
            var statusMessage by remember { mutableStateOf("Initializing CIRIS...") }

            LaunchedEffect(Unit) {
                launch {
                    initializeCIRIS { status ->
                        statusMessage = status
                    }
                    isReady = true
                }
            }

            if (isReady) {
                // Launch main Compose UI
                CIRISApp(
                    accessToken = "temp_token", // TODO: Get from auth
                    baseUrl = "http://localhost:8080"
                )
            } else {
                // Show startup splash
                StartupSplashScreen(statusMessage)
            }
        }
    }

    /**
     * Initialize CIRIS runtime
     * TODO: Port full initialization logic from original MainActivity.kt:150-400
     */
    private suspend fun initializeCIRIS(onStatusUpdate: (String) -> Unit) {
        try {
            onStatusUpdate("Starting Python interpreter...")
            delay(500)

            onStatusUpdate("Loading CIRIS engine...")
            delay(500)

            // TODO: Call Python mobile_main.py
            // val py = Python.getInstance()
            // val module = py.getModule("mobile_main")
            // module.callAttr("start_ciris_runtime")

            onStatusUpdate("Starting FastAPI server...")
            delay(1000)

            onStatusUpdate("Checking service health...")
            delay(500)

            // TODO: Poll http://localhost:8080/v1/system/health
            // Wait for all 22 services to be online

            onStatusUpdate("CIRIS ready!")
            serverStarted = true

        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize CIRIS", e)
            onStatusUpdate("Error: ${e.message}")
        }
    }
}

@Composable
private fun StartupSplashScreen(status: String) {
    // TODO: Port splash screen with 22 service lights animation
    // from original MainActivity.kt:95-135

    androidx.compose.foundation.layout.Box(
        modifier = androidx.compose.ui.Modifier.fillMaxSize(),
        contentAlignment = androidx.compose.ui.Alignment.Center
    ) {
        androidx.compose.foundation.layout.Column(
            horizontalAlignment = androidx.compose.ui.Alignment.CenterHorizontally,
            verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(16.dp)
        ) {
            androidx.compose.material3.Text(
                text = "CIRIS",
                style = androidx.compose.material3.MaterialTheme.typography.displayLarge
            )
            androidx.compose.material3.CircularProgressIndicator()
            androidx.compose.material3.Text(
                text = status,
                style = androidx.compose.material3.MaterialTheme.typography.bodyMedium
            )
        }
    }
}
