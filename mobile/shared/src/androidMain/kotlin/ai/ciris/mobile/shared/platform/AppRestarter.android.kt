package ai.ciris.mobile.shared.platform

import android.app.AlarmManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.util.Log
import kotlin.system.exitProcess

/**
 * Android implementation of AppRestarter.
 *
 * Uses AlarmManager to schedule a restart, then kills the current process.
 * This ensures the entire app (including embedded Python) restarts fresh.
 */
actual object AppRestarter {
    private const val TAG = "AppRestarter"

    private var appContext: Context? = null
    private var launchActivityClass: Class<*>? = null

    /**
     * Initialize the AppRestarter with application context and launch activity.
     *
     * Call this from your Application.onCreate() or MainActivity.onCreate()
     *
     * @param context Application context
     * @param launchActivity The main activity class to restart to
     */
    fun init(context: Context, launchActivity: Class<*>) {
        appContext = context.applicationContext
        launchActivityClass = launchActivity
        Log.d(TAG, "AppRestarter initialized with ${launchActivity.simpleName}")
    }

    /**
     * Restart the app completely.
     *
     * This will:
     * 1. Create an intent to launch the main activity
     * 2. Schedule it via AlarmManager
     * 3. Kill the current process
     */
    actual fun restartApp() {
        val context = appContext
        val activityClass = launchActivityClass

        if (context == null || activityClass == null) {
            Log.e(TAG, "AppRestarter not initialized! Call init() first.")
            return
        }

        Log.i(TAG, "Restarting app...")

        try {
            // Create intent to launch main activity
            val intent = Intent(context, activityClass).apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP)
            }

            // Create a pending intent
            val pendingIntent = PendingIntent.getActivity(
                context,
                0,
                intent,
                PendingIntent.FLAG_CANCEL_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )

            // Schedule restart in 100ms
            val alarmManager = context.getSystemService(Context.ALARM_SERVICE) as AlarmManager
            alarmManager.setExact(
                AlarmManager.RTC,
                System.currentTimeMillis() + 100,
                pendingIntent
            )

            Log.i(TAG, "Restart scheduled, killing process...")

            // Kill the current process
            android.os.Process.killProcess(android.os.Process.myPid())
            exitProcess(0)

        } catch (e: Exception) {
            Log.e(TAG, "Failed to restart app: ${e.message}", e)

            // Fallback: just try to start the activity directly
            try {
                val fallbackIntent = Intent(context, activityClass).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    addFlags(Intent.FLAG_ACTIVITY_CLEAR_TASK)
                }
                context.startActivity(fallbackIntent)

                // Still kill the process to ensure Python restarts
                android.os.Process.killProcess(android.os.Process.myPid())
                exitProcess(0)
            } catch (e2: Exception) {
                Log.e(TAG, "Fallback restart also failed: ${e2.message}", e2)
            }
        }
    }
}
