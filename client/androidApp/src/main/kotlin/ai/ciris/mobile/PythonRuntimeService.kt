package ai.ciris.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.wifi.WifiManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Foreground service that runs the CIRIS Python runtime.
 * Keeps the FastAPI server alive when app is in background for OAuth/purchase callbacks.
 *
 * Background timeout behavior:
 * - When app goes to background, a 3-minute timeout starts
 * - If app returns to foreground before timeout, timer is cancelled
 * - If timeout expires while app is still in background, service stops to save battery
 * - This allows OAuth/purchase flows to complete while preventing indefinite background running
 */
class PythonRuntimeService : Service(), DefaultLifecycleObserver {

    companion object {
        private const val TAG = "PythonRuntimeService"
        private const val CHANNEL_ID = "ciris_runtime_channel"
        private const val NOTIFICATION_ID = 1001

        /** Background timeout for OAuth/purchase flows (3 minutes) */
        private const val BACKGROUND_TIMEOUT_MS = 180_000L

        var isRunning = false
            private set
    }

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var serverStarted = false

    private val mainHandler = Handler(Looper.getMainLooper())
    private var backgroundTimeoutRunnable: Runnable? = null
    private var isAppInForeground = true

    /**
     * Wi-Fi multicast lock held for the lifetime of the embedded backend.
     *
     * Chaquopy runs the Python runtime IN THIS PROCESS, so the backend's
     * mDNS/zeroconf sockets (LAN LLM + node discovery) and Reticulum
     * AutoInterface share this process's multicast filter. Android drops
     * inbound multicast (mDNS responses on 224.0.0.251:5353, RNS link-local
     * announces) unless a MulticastLock is held — which is why LAN discovery
     * returned nothing on physical devices. Held while the service runs so any
     * discovery/announce during that window can receive replies.
     */
    private var multicastLock: WifiManager.MulticastLock? = null

    override fun onCreate() {
        super<Service>.onCreate()
        Log.i(TAG, "Service created")
        createNotificationChannel()

        // Register for app lifecycle events on main thread
        mainHandler.post {
            ProcessLifecycleOwner.get().lifecycle.addObserver(this)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "Service starting")

        startForeground(NOTIFICATION_ID, createNotification("Starting CIRIS..."))
        isRunning = true
        acquireMulticastLock()

        serviceScope.launch {
            try {
                initializePython()
                startServer()
                updateNotification("CIRIS running")
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start Python runtime", e)
                updateNotification("Error: ${e.message}")
            }
        }

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        super<Service>.onDestroy()
        Log.i(TAG, "Service destroyed")
        isRunning = false
        serverStarted = false

        releaseMulticastLock()

        // Cancel timeout and remove lifecycle observer
        cancelBackgroundTimeout()
        mainHandler.post {
            ProcessLifecycleOwner.get().lifecycle.removeObserver(this)
        }

        serviceScope.cancel()
    }

    // ========================================================================
    // Lifecycle Observer - App Foreground/Background Detection
    // ========================================================================

    override fun onStart(owner: LifecycleOwner) {
        // App came to foreground
        isAppInForeground = true
        Log.i(TAG, "App entered foreground - cancelling background timeout")
        cancelBackgroundTimeout()
        updateNotification("CIRIS running")
    }

    override fun onStop(owner: LifecycleOwner) {
        // App went to background
        isAppInForeground = false
        Log.i(TAG, "App entered background - starting ${BACKGROUND_TIMEOUT_MS / 1000}s timeout for OAuth/purchase flows")
        startBackgroundTimeout()
        updateNotification("CIRIS running (background - ${BACKGROUND_TIMEOUT_MS / 1000}s timeout)")
    }

    // ========================================================================
    // Background Timeout Management
    // ========================================================================

    /**
     * Start the background timeout timer.
     * When expired, the service will stop if the app is still in background.
     */
    private fun startBackgroundTimeout() {
        cancelBackgroundTimeout()

        backgroundTimeoutRunnable = Runnable {
            if (isAppInForeground) {
                Log.i(TAG, "Background timeout expired but app is now in foreground - continuing")
            } else if (BuildConfig.TEST_MODE_ENABLED) {
                // QA/dev build: DON'T stop on the background timeout. The mobile
                // node must stay alive so the federation-delivery loop can
                // dispatch a sealed trace even while the app is backgrounded —
                // the emulator churns foreground/background under adb, and a
                // stop here strands the trace mid-delivery (the recurring
                // ship-unconfirmed / node-unreachable-after-run). Production
                // (release, TEST_MODE_ENABLED=false) still stops to save battery.
                Log.i(TAG, "Background timeout expired but TEST_MODE — keeping runtime alive for federation delivery")
            } else {
                Log.i(TAG, "Background timeout expired (${BACKGROUND_TIMEOUT_MS / 1000}s) - stopping service to save battery")
                stopSelf()
            }
        }

        mainHandler.postDelayed(backgroundTimeoutRunnable!!, BACKGROUND_TIMEOUT_MS)
        Log.i(TAG, "Background timeout timer started (${BACKGROUND_TIMEOUT_MS / 1000}s)")
    }

    /**
     * Cancel the background timeout timer.
     */
    private fun cancelBackgroundTimeout() {
        backgroundTimeoutRunnable?.let {
            mainHandler.removeCallbacks(it)
            backgroundTimeoutRunnable = null
            Log.d(TAG, "Background timeout timer cancelled")
        }
    }

    // ========================================================================
    // Python Runtime Management
    // ========================================================================

    private fun initializePython() {
        if (!Python.isStarted()) {
            Log.i(TAG, "Initializing Python runtime...")
            Python.start(AndroidPlatform(this))
            Log.i(TAG, "Python runtime started")
        }
    }

    private fun startServer() {
        if (serverStarted) {
            Log.i(TAG, "Server already started")
            return
        }

        // SmartStartup: Check for existing server from previous instance
        if (isOrphanServerRunning()) {
            Log.i(TAG, "[SmartStartup] Detected existing server on :8080 - attaching to it")
            serverStarted = true
            return
        }

        try {
            val py = Python.getInstance()
            val mobileMain = py.getModule("mobile_main")
            // Call main() which starts the full CIRIS runtime
            mobileMain.callAttr("main")
            serverStarted = true
            Log.i(TAG, "CIRIS server started on localhost:8080")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start CIRIS server", e)
            throw e
        }
    }

    /**
     * Check if an orphan server from a previous instance is running.
     */
    private fun isOrphanServerRunning(): Boolean {
        return try {
            val url = java.net.URL("http://localhost:8080/v1/system/health")
            val connection = url.openConnection() as java.net.HttpURLConnection
            connection.connectTimeout = 1000
            connection.readTimeout = 1000
            connection.requestMethod = "GET"
            val responseCode = connection.responseCode
            connection.disconnect()
            responseCode == 200
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Send shutdown signal to orphan server via local-shutdown endpoint.
     */
    private fun shutdownOrphanServer() {
        try {
            val url = java.net.URL("http://localhost:8080/v1/system/local-shutdown")
            val connection = url.openConnection() as java.net.HttpURLConnection
            connection.connectTimeout = 3000
            connection.readTimeout = 5000
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.outputStream.bufferedWriter().use { it.write("{}") }
            val responseCode = connection.responseCode
            connection.disconnect()
            Log.i(TAG, "[SmartStartup] local-shutdown response: $responseCode")
        } catch (e: Exception) {
            Log.w(TAG, "[SmartStartup] Failed to send shutdown: ${e.message}")
        }
    }

    // ========================================================================
    // Wi-Fi Multicast Lock (LAN discovery: mDNS + Reticulum AutoInterface)
    // ========================================================================

    /**
     * Acquire the multicast lock so the in-process Python backend can RECEIVE
     * multicast on Wi-Fi. Idempotent: a no-op if already held. Failures are
     * logged and swallowed — discovery degrades gracefully rather than crashing
     * the runtime service.
     */
    private fun acquireMulticastLock() {
        if (multicastLock?.isHeld == true) return
        try {
            val wifi = applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
            if (wifi == null) {
                Log.w(TAG, "WifiManager unavailable - LAN discovery multicast will be filtered")
                return
            }
            val lock = wifi.createMulticastLock("ciris-lan-discovery").apply {
                setReferenceCounted(false)
                acquire()
            }
            multicastLock = lock
            Log.i(TAG, "Multicast lock acquired (held=${lock.isHeld}) - mDNS/RNS LAN discovery enabled")
        } catch (e: Exception) {
            Log.w(TAG, "Failed to acquire multicast lock: ${e.message}")
        }
    }

    /** Release the multicast lock if held. Safe to call multiple times. */
    private fun releaseMulticastLock() {
        try {
            multicastLock?.let {
                if (it.isHeld) {
                    it.release()
                    Log.i(TAG, "Multicast lock released")
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "Failed to release multicast lock: ${e.message}")
        } finally {
            multicastLock = null
        }
    }

    // ========================================================================
    // Notification Management
    // ========================================================================

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "CIRIS Runtime",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "CIRIS Python runtime service"
                setShowBadge(false)
            }

            val notificationManager = getSystemService(NotificationManager::class.java)
            notificationManager.createNotificationChannel(channel)
        }
    }

    private fun createNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("CIRIS")
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_manage)
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val notificationManager = getSystemService(NotificationManager::class.java)
        notificationManager.notify(NOTIFICATION_ID, createNotification(text))
    }
}
