package ai.ciris.mobile

import android.content.Intent
import android.os.Bundle
import android.util.Log
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/**
 * MainActivity for CIRIS Android.
 *
 * Launches the Python FastAPI server on-device and displays the web UI
 * in a WebView. All LLM calls are routed to a remote OpenAI-compatible endpoint.
 *
 * Architecture:
 * - Python runtime: On-device (Chaquopy)
 * - FastAPI server: localhost:8000
 * - Web UI: Bundled assets in WebView
 * - LLM: Remote endpoint only
 * - Database: On-device SQLite
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private var serverStarted = false

    companion object {
        private const val TAG = "CIRISMobile"
        private const val SERVER_URL = "http://127.0.0.1:8000"
        private const val UI_PATH = "/index.html"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Initialize Python runtime
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
            Log.i(TAG, "Python runtime initialized")
        }

        // Setup WebView for bundled UI
        setupWebView()

        // Start Python server in background
        startPythonServer()
    }

    private fun setupWebView() {
        webView = findViewById(R.id.webView)

        webView.apply {
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                allowFileAccess = true
                allowContentAccess = true
            }

            webViewClient = object : WebViewClient() {
                override fun onReceivedError(
                    view: WebView?,
                    errorCode: Int,
                    description: String?,
                    failingUrl: String?
                ) {
                    Log.e(TAG, "WebView error: $description at $failingUrl")
                    if (!serverStarted) {
                        // Server might not be ready yet, retry
                        retryLoadUI()
                    }
                }

                override fun shouldOverrideUrlLoading(
                    view: WebView?,
                    url: String?
                ): Boolean {
                    // Keep navigation within WebView
                    return false
                }
            }

            webChromeClient = WebChromeClient()
        }

        Log.i(TAG, "WebView configured")
    }

    private fun startPythonServer() {
        CoroutineScope(Dispatchers.IO).launch {
            try {
                Log.i(TAG, "Starting Python server...")

                val python = Python.getInstance()
                val mobileMain = python.getModule("mobile_main")

                // Start server in background thread
                launch(Dispatchers.IO) {
                    try {
                        mobileMain.callAttr("main")
                    } catch (e: Exception) {
                        Log.e(TAG, "Server error: ${e.message}", e)
                    }
                }

                // Wait for server to be ready
                delay(2000) // Give server time to start

                withContext(Dispatchers.Main) {
                    serverStarted = true
                    loadUI()
                }

            } catch (e: Exception) {
                Log.e(TAG, "Failed to start server: ${e.message}", e)
                withContext(Dispatchers.Main) {
                    // Show error to user
                    webView.loadData(
                        """
                        <html>
                        <body>
                        <h1>Server Error</h1>
                        <p>Failed to start CIRIS server: ${e.message}</p>
                        <p>Check Settings to configure your LLM endpoint.</p>
                        </body>
                        </html>
                        """.trimIndent(),
                        "text/html",
                        "UTF-8"
                    )
                }
            }
        }
    }

    private fun loadUI() {
        val url = "$SERVER_URL$UI_PATH"
        Log.i(TAG, "Loading UI from $url")
        webView.loadUrl(url)
    }

    private fun retryLoadUI() {
        CoroutineScope(Dispatchers.Main).launch {
            delay(1000)
            if (serverStarted) {
                loadUI()
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu?): Boolean {
        menuInflater.inflate(R.menu.main_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        return when (item.itemId) {
            R.id.action_settings -> {
                startActivity(Intent(this, SettingsActivity::class.java))
                true
            }
            R.id.action_refresh -> {
                webView.reload()
                true
            }
            else -> super.onOptionsItemSelected(item)
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) {
            webView.goBack()
        } else {
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // Note: Python server continues running
        // In production, implement proper shutdown
    }
}
