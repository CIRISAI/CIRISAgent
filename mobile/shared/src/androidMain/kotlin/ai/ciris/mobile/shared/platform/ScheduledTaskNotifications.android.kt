package ai.ciris.mobile.shared.platform

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.CalendarContract
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import androidx.work.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.TimeZone
import java.util.concurrent.TimeUnit

/**
 * Android implementation of scheduled task notifications using:
 * - NotificationManager for notifications
 * - CalendarContract for calendar events
 * - WorkManager for background scheduling
 */
actual object ScheduledTaskNotifications {

    private const val CHANNEL_ID = "ciris_scheduled_tasks"
    private const val CHANNEL_NAME = "Scheduled Tasks"
    private const val CHANNEL_DESCRIPTION = "Notifications for CIRIS scheduled task triggers"

    private const val IMMEDIATE_CHANNEL_ID = "ciris_task_updates"
    private const val IMMEDIATE_CHANNEL_NAME = "Task Updates"

    private var applicationContext: Context? = null
    private val taskIdToNotificationId = mutableMapOf<String, Int>()
    private var nextNotificationId = 1000

    /**
     * Initialize with application context. Call from Application.onCreate().
     */
    fun initialize(context: Context) {
        applicationContext = context.applicationContext
        createNotificationChannels()
    }

    private fun getContext(): Context {
        return applicationContext
            ?: throw IllegalStateException("ScheduledTaskNotifications not initialized. Call initialize() first.")
    }

    private fun createNotificationChannels() {
        val context = applicationContext ?: return

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val notificationManager = context.getSystemService(NotificationManager::class.java)

            // Scheduled tasks channel
            val scheduledChannel = NotificationChannel(
                CHANNEL_ID,
                CHANNEL_NAME,
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = CHANNEL_DESCRIPTION
                enableVibration(true)
            }
            notificationManager.createNotificationChannel(scheduledChannel)

            // Immediate updates channel
            val immediateChannel = NotificationChannel(
                IMMEDIATE_CHANNEL_ID,
                IMMEDIATE_CHANNEL_NAME,
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Immediate notifications for task completions and updates"
                enableVibration(true)
            }
            notificationManager.createNotificationChannel(immediateChannel)
        }
    }

    actual suspend fun requestNotificationPermission(): Boolean {
        // On Android 13+, POST_NOTIFICATIONS permission is required
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            // Permission must be requested via Activity - return current state
            return hasNotificationPermission()
        }
        return true
    }

    actual fun hasNotificationPermission(): Boolean {
        val context = applicationContext ?: return false

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(
                context,
                Manifest.permission.POST_NOTIFICATIONS
            ) == PackageManager.PERMISSION_GRANTED
        } else {
            NotificationManagerCompat.from(context).areNotificationsEnabled()
        }
    }

    actual suspend fun requestCalendarPermission(): Boolean {
        // Calendar permissions must be requested via Activity
        return hasCalendarPermission()
    }

    actual fun hasCalendarPermission(): Boolean {
        val context = applicationContext ?: return false

        val readPermission = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.READ_CALENDAR
        ) == PackageManager.PERMISSION_GRANTED

        val writePermission = ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.WRITE_CALENDAR
        ) == PackageManager.PERMISSION_GRANTED

        return readPermission && writePermission
    }

    actual suspend fun scheduleNotification(notification: TaskNotification): ScheduleResult {
        val context = getContext()

        if (!hasNotificationPermission()) {
            return ScheduleResult(
                success = false,
                error = "Notification permission not granted"
            )
        }

        return try {
            val notificationId = getOrCreateNotificationId(notification.taskId)
            val delayMillis = notification.triggerTimeMillis - System.currentTimeMillis()

            if (delayMillis <= 0) {
                // Trigger immediately
                showTaskNotification(notification, notificationId)
            } else {
                // Schedule via WorkManager
                scheduleNotificationWork(notification, delayMillis)
            }

            ScheduleResult(
                success = true,
                notificationId = notificationId
            )
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Failed to schedule notification: ${e.message}")
            ScheduleResult(success = false, error = e.message)
        }
    }

    private fun showTaskNotification(notification: TaskNotification, notificationId: Int) {
        val context = getContext()

        // Create intent for notification tap (deep link to scheduler screen)
        val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra("navigate_to", "scheduler")
            putExtra("task_id", notification.taskId)
        }

        val pendingIntent = intent?.let {
            PendingIntent.getActivity(
                context,
                notificationId,
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        }

        val builder = NotificationCompat.Builder(context, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_agenda)
            .setContentTitle("CIRIS Task: ${notification.title}")
            .setContentText(notification.description)
            .setStyle(NotificationCompat.BigTextStyle().bigText(notification.description))
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)

        if (notification.isRecurring) {
            builder.setSubText("Recurring task")
        }

        try {
            NotificationManagerCompat.from(context).notify(notificationId, builder.build())
        } catch (e: SecurityException) {
            PlatformLogger.e("ScheduledTaskNotifications", "SecurityException showing notification: ${e.message}")
        }
    }

    private fun scheduleNotificationWork(notification: TaskNotification, delayMillis: Long) {
        val context = getContext()

        val inputData = workDataOf(
            "task_id" to notification.taskId,
            "title" to notification.title,
            "description" to notification.description,
            "is_recurring" to notification.isRecurring,
            "cron_expression" to (notification.cronExpression ?: "")
        )

        val workRequest = OneTimeWorkRequestBuilder<TaskNotificationWorker>()
            .setInitialDelay(delayMillis, TimeUnit.MILLISECONDS)
            .setInputData(inputData)
            .addTag("ciris_task_${notification.taskId}")
            .build()

        WorkManager.getInstance(context)
            .enqueueUniqueWork(
                "ciris_notify_${notification.taskId}",
                ExistingWorkPolicy.REPLACE,
                workRequest
            )
    }

    actual fun cancelNotification(taskId: String) {
        val context = applicationContext ?: return

        // Cancel any pending WorkManager work
        WorkManager.getInstance(context).cancelUniqueWork("ciris_notify_$taskId")

        // Cancel displayed notification
        taskIdToNotificationId[taskId]?.let { notificationId ->
            NotificationManagerCompat.from(context).cancel(notificationId)
            taskIdToNotificationId.remove(taskId)
        }
    }

    actual suspend fun addCalendarEvent(
        notification: TaskNotification,
        reminderMinutes: Int
    ): ScheduleResult = withContext(Dispatchers.IO) {
        val context = getContext()

        if (!hasCalendarPermission()) {
            return@withContext ScheduleResult(
                success = false,
                error = "Calendar permission not granted"
            )
        }

        try {
            val calendarId = getPrimaryCalendarId(context)
            if (calendarId == null) {
                return@withContext ScheduleResult(
                    success = false,
                    error = "No calendar found on device"
                )
            }

            // Create event
            val eventValues = ContentValues().apply {
                put(CalendarContract.Events.CALENDAR_ID, calendarId)
                put(CalendarContract.Events.TITLE, "CIRIS: ${notification.title}")
                put(CalendarContract.Events.DESCRIPTION, notification.description)
                put(CalendarContract.Events.DTSTART, notification.triggerTimeMillis)
                put(CalendarContract.Events.DTEND, notification.triggerTimeMillis + 3600000) // 1 hour
                put(CalendarContract.Events.EVENT_TIMEZONE, TimeZone.getDefault().id)

                // Add recurrence rule if recurring
                notification.cronExpression?.let { cron ->
                    cronToRRule(cron)?.let { rrule ->
                        put(CalendarContract.Events.RRULE, rrule)
                    }
                }
            }

            val eventUri = context.contentResolver.insert(
                CalendarContract.Events.CONTENT_URI,
                eventValues
            )

            val eventId = eventUri?.lastPathSegment?.toLongOrNull()

            if (eventId != null && reminderMinutes > 0) {
                // Add reminder
                val reminderValues = ContentValues().apply {
                    put(CalendarContract.Reminders.EVENT_ID, eventId)
                    put(CalendarContract.Reminders.MINUTES, reminderMinutes)
                    put(CalendarContract.Reminders.METHOD, CalendarContract.Reminders.METHOD_ALERT)
                }
                context.contentResolver.insert(
                    CalendarContract.Reminders.CONTENT_URI,
                    reminderValues
                )
            }

            ScheduleResult(
                success = eventId != null,
                calendarEventId = eventId,
                error = if (eventId == null) "Failed to create calendar event" else null
            )
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Failed to add calendar event: ${e.message}")
            ScheduleResult(success = false, error = e.message)
        }
    }

    private fun getPrimaryCalendarId(context: Context): Long? {
        val projection = arrayOf(
            CalendarContract.Calendars._ID,
            CalendarContract.Calendars.IS_PRIMARY
        )

        context.contentResolver.query(
            CalendarContract.Calendars.CONTENT_URI,
            projection,
            null,
            null,
            null
        )?.use { cursor ->
            while (cursor.moveToNext()) {
                val id = cursor.getLong(0)
                val isPrimary = cursor.getInt(1) == 1
                if (isPrimary) return id
            }
            // If no primary, return first calendar
            if (cursor.moveToFirst()) {
                return cursor.getLong(0)
            }
        }
        return null
    }

    /**
     * Convert cron expression to iCalendar RRULE format.
     * Supports common patterns.
     */
    private fun cronToRRule(cron: String): String? {
        val parts = cron.split(" ")
        if (parts.size < 5) return null

        val minute = parts[0]
        val hour = parts[1]
        val dayOfMonth = parts[2]
        val month = parts[3]
        val dayOfWeek = parts[4]

        return when {
            // Daily at specific time: "0 9 * * *"
            minute != "*" && hour != "*" && dayOfMonth == "*" && month == "*" && dayOfWeek == "*" ->
                "FREQ=DAILY"

            // Weekly on specific day: "0 9 * * 1"
            minute != "*" && hour != "*" && dayOfWeek != "*" && dayOfMonth == "*" ->
                "FREQ=WEEKLY;BYDAY=${cronDayToRRule(dayOfWeek)}"

            // Monthly on specific day: "0 9 15 * *"
            minute != "*" && hour != "*" && dayOfMonth != "*" && dayOfMonth != "*" && month == "*" ->
                "FREQ=MONTHLY;BYMONTHDAY=$dayOfMonth"

            // Every N hours: "0 */2 * * *"
            minute == "0" && hour.startsWith("*/") -> {
                val interval = hour.removePrefix("*/").toIntOrNull() ?: return null
                "FREQ=HOURLY;INTERVAL=$interval"
            }

            // Every N minutes: "*/15 * * * *"
            minute.startsWith("*/") && hour == "*" -> {
                val interval = minute.removePrefix("*/").toIntOrNull() ?: return null
                "FREQ=MINUTELY;INTERVAL=$interval"
            }

            else -> null // Unsupported pattern
        }
    }

    private fun cronDayToRRule(cronDay: String): String {
        return when (cronDay) {
            "0", "7" -> "SU"
            "1" -> "MO"
            "2" -> "TU"
            "3" -> "WE"
            "4" -> "TH"
            "5" -> "FR"
            "6" -> "SA"
            else -> "MO" // Default
        }
    }

    actual suspend fun removeCalendarEvent(calendarEventId: Long): Boolean = withContext(Dispatchers.IO) {
        val context = getContext()

        if (!hasCalendarPermission()) return@withContext false

        try {
            val uri = CalendarContract.Events.CONTENT_URI.buildUpon()
                .appendPath(calendarEventId.toString())
                .build()

            val deleted = context.contentResolver.delete(uri, null, null)
            deleted > 0
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Failed to remove calendar event: ${e.message}")
            false
        }
    }

    actual suspend fun scheduleBackgroundWork(notification: TaskNotification): ScheduleResult {
        val context = getContext()

        return try {
            val delayMillis = notification.triggerTimeMillis - System.currentTimeMillis()

            if (delayMillis <= 0) {
                return ScheduleResult(success = false, error = "Trigger time is in the past")
            }

            val inputData = workDataOf(
                "task_id" to notification.taskId,
                "title" to notification.title,
                "description" to notification.description,
                "trigger_prompt" to notification.description, // Use description as prompt
                "is_recurring" to notification.isRecurring,
                "cron_expression" to (notification.cronExpression ?: "")
            )

            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.NOT_REQUIRED)
                .build()

            val workRequest = OneTimeWorkRequestBuilder<TaskExecutionWorker>()
                .setInitialDelay(delayMillis, TimeUnit.MILLISECONDS)
                .setInputData(inputData)
                .setConstraints(constraints)
                .addTag("ciris_task_exec_${notification.taskId}")
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 1, TimeUnit.MINUTES)
                .build()

            WorkManager.getInstance(context)
                .enqueueUniqueWork(
                    "ciris_exec_${notification.taskId}",
                    ExistingWorkPolicy.REPLACE,
                    workRequest
                )

            ScheduleResult(
                success = true,
                workerId = workRequest.id.toString()
            )
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Failed to schedule background work: ${e.message}")
            ScheduleResult(success = false, error = e.message)
        }
    }

    actual fun cancelBackgroundWork(taskId: String) {
        val context = applicationContext ?: return

        WorkManager.getInstance(context).apply {
            cancelUniqueWork("ciris_exec_$taskId")
            cancelUniqueWork("ciris_notify_$taskId")
        }
    }

    actual fun showImmediateNotification(title: String, message: String, taskId: String?) {
        val context = applicationContext ?: return

        if (!hasNotificationPermission()) return

        val notificationId = taskId?.let { getOrCreateNotificationId(it) } ?: nextNotificationId++

        val intent = context.packageManager.getLaunchIntentForPackage(context.packageName)?.apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
            taskId?.let {
                putExtra("navigate_to", "scheduler")
                putExtra("task_id", it)
            }
        }

        val pendingIntent = intent?.let {
            PendingIntent.getActivity(
                context,
                notificationId,
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        }

        val builder = NotificationCompat.Builder(context, IMMEDIATE_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_menu_info_details)
            .setContentTitle(title)
            .setContentText(message)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)
            .setContentIntent(pendingIntent)

        try {
            NotificationManagerCompat.from(context).notify(notificationId, builder.build())
        } catch (e: SecurityException) {
            PlatformLogger.e("ScheduledTaskNotifications", "SecurityException: ${e.message}")
        }
    }

    private fun getOrCreateNotificationId(taskId: String): Int {
        return taskIdToNotificationId.getOrPut(taskId) { nextNotificationId++ }
    }
}

/**
 * WorkManager worker for showing scheduled notifications.
 */
class TaskNotificationWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val taskId = inputData.getString("task_id") ?: return Result.failure()
        val title = inputData.getString("title") ?: "Scheduled Task"
        val description = inputData.getString("description") ?: ""
        val isRecurring = inputData.getBoolean("is_recurring", false)

        ScheduledTaskNotifications.showImmediateNotification(
            title = "CIRIS Task: $title",
            message = description,
            taskId = taskId
        )

        return Result.success()
    }
}

/**
 * WorkManager worker for executing scheduled tasks in background.
 * This worker starts the Python runtime and triggers the task.
 */
class TaskExecutionWorker(
    context: Context,
    params: WorkerParameters
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val taskId = inputData.getString("task_id") ?: return Result.failure()
        val title = inputData.getString("title") ?: "Scheduled Task"

        PlatformLogger.i("TaskExecutionWorker", "Executing scheduled task: $taskId - $title")

        // Show notification that task is starting
        ScheduledTaskNotifications.showImmediateNotification(
            title = "Running: $title",
            message = "CIRIS is executing your scheduled task...",
            taskId = taskId
        )

        // The actual task execution happens via the Python runtime
        // This worker's job is to ensure the app/runtime is woken up
        // The Python TaskSchedulerService handles the actual execution

        // Broadcast to wake up Python runtime if needed
        try {
            val intent = Intent("ai.ciris.mobile.EXECUTE_SCHEDULED_TASK").apply {
                putExtra("task_id", taskId)
                setPackage(applicationContext.packageName)
            }
            applicationContext.sendBroadcast(intent)
        } catch (e: Exception) {
            PlatformLogger.e("TaskExecutionWorker", "Failed to broadcast: ${e.message}")
        }

        return Result.success()
    }
}
