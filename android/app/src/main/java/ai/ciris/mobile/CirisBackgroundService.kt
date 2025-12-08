package ai.ciris.mobile

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
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
 */
class CirisBackgroundService : Service() {

    companion object {
        private const val TAG = "CirisBackgroundService"
        private const val CHANNEL_ID = "ciris_background_channel"
        private const val NOTIFICATION_ID = 1001

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
    }

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "Service created")
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "Service started with startId: $startId")

        val notification = createNotification()
        startForeground(NOTIFICATION_ID, notification)

        Log.i(TAG, "Foreground service is now running - Python runtime protected from background kill")

        // START_STICKY: restart service if killed by system
        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? {
        return null // Not a bound service
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.i(TAG, "Service destroyed")
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
