package ai.ciris.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.Log
import androidx.core.app.NotificationCompat

/**
 * Foreground service to keep the Python CIRIS runtime alive when the app is backgrounded.
 *
 * This is critical for OAuth flows where the user switches to Chrome browser:
 * - Without foreground service: Android may kill the Python process
 * - With foreground service: Python server stays running, OAuth callback works
 *
 * The service shows a persistent notification while CIRIS is running.
 *
 * AUTO-SLEEP FEATURE:
 * The service automatically stops itself after 5 minutes of background activity.
 * This saves battery and resources when OAuth is complete. The timer resets each
 * time the app comes to foreground (via resetSleepTimer).
 *
 * Uses START_NOT_STICKY so the service doesn't auto-restart after sleeping.
 * MainActivity has smart startup logic to detect and gracefully shutdown any
 * stale server sessions before starting a new one (prevents "port already bound" errors).
 */
class CirisBackgroundService : Service() {

    companion object {
        private const val TAG = "CirisBackgroundService"
        private const val CHANNEL_ID = "ciris_background_channel"
        private const val NOTIFICATION_ID = 1001

        // Auto-sleep after 5 minutes of background activity
        private const val SLEEP_TIMEOUT_MS = 5 * 60 * 1000L  // 5 minutes

        private var instance: CirisBackgroundService? = null

        fun start(context: Context) {
            val intent = Intent(context, CirisBackgroundService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
            Log.i(TAG, "Foreground service start requested")
        }

        fun stop(context: Context) {
            val intent = Intent(context, CirisBackgroundService::class.java)
            context.stopService(intent)
            Log.i(TAG, "Foreground service stop requested")
        }

        /**
         * Reset the sleep timer when app comes to foreground.
         * Call this from MainActivity.onResume().
         */
        fun resetSleepTimer() {
            instance?.resetTimer()
        }

        /**
         * Start the sleep timer when app goes to background.
         * Call this from MainActivity.onPause().
         */
        fun startSleepTimer() {
            instance?.startTimer()
        }
    }

    private val handler = Handler(Looper.getMainLooper())
    private var sleepTimerRunning = false

    private val sleepRunnable = Runnable {
        Log.i(TAG, "Sleep timeout reached (${SLEEP_TIMEOUT_MS / 1000}s) - stopping service to save resources")
        stopSelf()
    }

    override fun onCreate() {
        super.onCreate()
        instance = this
        Log.i(TAG, "Service created")
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "Service started with startId: $startId")

        val notification = createNotification()
        startForeground(NOTIFICATION_ID, notification)

        Log.i(TAG, "Foreground service is now running - Python runtime protected from background kill")
        Log.i(TAG, "Service will auto-sleep after ${SLEEP_TIMEOUT_MS / 1000}s of background activity")

        // START_NOT_STICKY: Don't restart after auto-sleep - user will restart app if needed
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null // Not a bound service
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
        handler.removeCallbacks(sleepRunnable)
        Log.i(TAG, "Service destroyed - Python runtime no longer protected")
    }

    /**
     * Start the sleep timer. Called when app goes to background.
     */
    private fun startTimer() {
        if (!sleepTimerRunning) {
            sleepTimerRunning = true
            handler.postDelayed(sleepRunnable, SLEEP_TIMEOUT_MS)
            Log.i(TAG, "Sleep timer started - service will stop in ${SLEEP_TIMEOUT_MS / 1000}s if app stays in background")
        }
    }

    /**
     * Reset/cancel the sleep timer. Called when app comes to foreground.
     */
    private fun resetTimer() {
        if (sleepTimerRunning) {
            handler.removeCallbacks(sleepRunnable)
            sleepTimerRunning = false
            Log.i(TAG, "Sleep timer cancelled - app is in foreground")
        }
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "CIRIS Background Service",
                NotificationManager.IMPORTANCE_LOW // Low importance = no sound, minimal UI
            ).apply {
                description = "Keeps CIRIS AI running in the background"
                setShowBadge(false)
            }

            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
            Log.i(TAG, "Notification channel created")
        }
    }

    private fun createNotification(): Notification {
        // Intent to return to the app when tapping notification
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java).apply {
                flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
            },
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("CIRIS is running")
            .setContentText("Local AI server active")
            .setSmallIcon(R.drawable.ic_launcher_foreground) // Use app icon
            .setContentIntent(pendingIntent)
            .setOngoing(true) // Can't be swiped away
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setCategory(NotificationCompat.CATEGORY_SERVICE)
            .build()
    }
}
