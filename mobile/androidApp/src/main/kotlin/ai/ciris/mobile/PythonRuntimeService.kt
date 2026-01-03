package ai.ciris.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch

/**
 * Foreground service that runs the CIRIS Python runtime
 * Keeps the FastAPI server alive when app is in background
 *
 * Based on original android/app/.../PythonRuntimeService.kt
 */
class PythonRuntimeService : Service() {

    companion object {
        private const val TAG = "PythonRuntimeService"
        private const val CHANNEL_ID = "ciris_runtime_channel"
        private const val NOTIFICATION_ID = 1001

        var isRunning = false
            private set
    }

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Default)
    private var serverStarted = false

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "Service created")
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "Service starting")

        startForeground(NOTIFICATION_ID, createNotification("Starting CIRIS..."))
        isRunning = true

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
        super.onDestroy()
        Log.i(TAG, "Service destroyed")
        isRunning = false
        serverStarted = false
        serviceScope.cancel()
    }

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

        try {
            val py = Python.getInstance()
            val mobileMain = py.getModule("mobile_main")
            mobileMain.callAttr("start_ciris_runtime")
            serverStarted = true
            Log.i(TAG, "CIRIS server started on localhost:8080")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start CIRIS server", e)
            throw e
        }
    }

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
