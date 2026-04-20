package ai.ciris.mobile.shared.platform

import kotlinx.coroutines.*
import java.awt.SystemTray
import java.awt.TrayIcon
import java.awt.Toolkit
import java.util.Timer
import java.util.TimerTask
import java.util.concurrent.ConcurrentHashMap

/**
 * Desktop implementation of scheduled task notifications.
 *
 * Uses:
 * - Java AWT SystemTray for notifications (where supported)
 * - Timer for scheduling (since no WorkManager on desktop)
 * - No calendar integration (would require platform-specific APIs)
 */
actual object ScheduledTaskNotifications {

    private var trayIcon: TrayIcon? = null
    private val scheduledTimers = ConcurrentHashMap<String, Timer>()
    private var isInitialized = false

    /**
     * Initialize system tray icon for desktop notifications.
     */
    fun initialize() {
        if (isInitialized) return
        isInitialized = true

        if (!SystemTray.isSupported()) {
            PlatformLogger.w("ScheduledTaskNotifications", "System tray not supported on this platform")
            return
        }

        try {
            val image = Toolkit.getDefaultToolkit().createImage(
                javaClass.getResource("/ciris_icon.png")
            ) ?: Toolkit.getDefaultToolkit().createImage(ByteArray(0))

            trayIcon = TrayIcon(image, "CIRIS").apply {
                isImageAutoSize = true
            }
            SystemTray.getSystemTray().add(trayIcon)
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Failed to initialize system tray: ${e.message}")
        }
    }

    actual suspend fun requestNotificationPermission(): Boolean {
        // Desktop doesn't require explicit permission
        return SystemTray.isSupported()
    }

    actual fun hasNotificationPermission(): Boolean {
        return SystemTray.isSupported()
    }

    actual suspend fun requestCalendarPermission(): Boolean {
        // Calendar integration not supported on desktop
        return false
    }

    actual fun hasCalendarPermission(): Boolean {
        // Calendar integration not supported on desktop
        return false
    }

    actual suspend fun scheduleNotification(notification: TaskNotification): ScheduleResult {
        if (!isInitialized) initialize()

        return try {
            val delayMillis = notification.triggerTimeMillis - System.currentTimeMillis()

            if (delayMillis <= 0) {
                // Show immediately
                showImmediateNotification(
                    "CIRIS Task: ${notification.title}",
                    notification.description,
                    notification.taskId
                )
            } else {
                // Schedule for later
                val timer = Timer("ciris_notify_${notification.taskId}", true)
                timer.schedule(object : TimerTask() {
                    override fun run() {
                        showImmediateNotification(
                            "CIRIS Task: ${notification.title}",
                            notification.description,
                            notification.taskId
                        )
                        scheduledTimers.remove(notification.taskId)

                        // For recurring tasks, reschedule
                        if (notification.isRecurring && notification.cronExpression != null) {
                            val nextTrigger = calculateNextTrigger(notification.cronExpression)
                            if (nextTrigger != null) {
                                GlobalScope.launch {
                                    scheduleNotification(notification.copy(triggerTimeMillis = nextTrigger))
                                }
                            }
                        }
                    }
                }, delayMillis)

                scheduledTimers[notification.taskId] = timer
            }

            ScheduleResult(
                success = true,
                notificationId = notification.taskId.hashCode()
            )
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Failed to schedule notification: ${e.message}")
            ScheduleResult(success = false, error = e.message)
        }
    }

    private fun calculateNextTrigger(cronExpression: String): Long? {
        // Simple next trigger calculation for common patterns
        val parts = cronExpression.split(" ")
        if (parts.size < 5) return null

        val minute = parts[0].toIntOrNull() ?: 0
        val hour = parts[1].toIntOrNull() ?: 0

        val now = System.currentTimeMillis()
        val calendar = java.util.Calendar.getInstance()

        return when {
            // Daily: add 24 hours
            parts[2] == "*" && parts[3] == "*" && parts[4] == "*" -> {
                calendar.timeInMillis = now
                calendar.add(java.util.Calendar.DAY_OF_YEAR, 1)
                calendar.set(java.util.Calendar.HOUR_OF_DAY, hour)
                calendar.set(java.util.Calendar.MINUTE, minute)
                calendar.set(java.util.Calendar.SECOND, 0)
                calendar.timeInMillis
            }
            // Weekly: add 7 days
            parts[4] != "*" -> {
                calendar.timeInMillis = now
                calendar.add(java.util.Calendar.WEEK_OF_YEAR, 1)
                calendar.set(java.util.Calendar.HOUR_OF_DAY, hour)
                calendar.set(java.util.Calendar.MINUTE, minute)
                calendar.set(java.util.Calendar.SECOND, 0)
                calendar.timeInMillis
            }
            else -> null
        }
    }

    actual fun cancelNotification(taskId: String) {
        scheduledTimers[taskId]?.cancel()
        scheduledTimers.remove(taskId)
    }

    actual suspend fun addCalendarEvent(
        notification: TaskNotification,
        reminderMinutes: Int
    ): ScheduleResult {
        // Calendar integration not supported on desktop
        // Could potentially integrate with system calendar via ICS files or platform-specific APIs
        PlatformLogger.w("ScheduledTaskNotifications", "Calendar integration not supported on desktop")
        return ScheduleResult(
            success = false,
            error = "Calendar integration not supported on desktop. Use system calendar manually."
        )
    }

    actual suspend fun removeCalendarEvent(calendarEventId: Long): Boolean {
        // Not supported on desktop
        return false
    }

    actual suspend fun scheduleBackgroundWork(notification: TaskNotification): ScheduleResult {
        // On desktop, we use the same Timer-based approach
        // The JVM process stays running, so this works reliably
        return scheduleNotification(notification)
    }

    actual fun cancelBackgroundWork(taskId: String) {
        cancelNotification(taskId)
    }

    actual fun showImmediateNotification(title: String, message: String, taskId: String?) {
        if (!isInitialized) initialize()

        try {
            if (trayIcon != null) {
                trayIcon?.displayMessage(
                    title,
                    message,
                    TrayIcon.MessageType.INFO
                )
            } else {
                // Fallback: print to console
                PlatformLogger.i("ScheduledTaskNotifications", "[$title] $message")
            }
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Failed to show notification: ${e.message}")
            // Fallback
            PlatformLogger.i("ScheduledTaskNotifications", "[$title] $message")
        }
    }
}
