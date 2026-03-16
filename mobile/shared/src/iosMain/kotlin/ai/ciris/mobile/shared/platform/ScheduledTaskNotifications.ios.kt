package ai.ciris.mobile.shared.platform

import platform.Foundation.*
import platform.UserNotifications.*
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * iOS implementation of scheduled task notifications using:
 * - UNUserNotificationCenter for notifications
 * - EventKit for calendar events (stubbed - requires EventKit cinterop fixes)
 *
 * TODO: Fix EventKit cinterop bindings for calendar integration
 */
@OptIn(kotlinx.cinterop.ExperimentalForeignApi::class)
actual object ScheduledTaskNotifications {

    private val notificationCenter = UNUserNotificationCenter.currentNotificationCenter()
    private val taskIdToNotificationId = mutableMapOf<String, String>()
    private val taskIdToEventId = mutableMapOf<String, String>()

    actual suspend fun requestNotificationPermission(): Boolean = suspendCancellableCoroutine { cont ->
        notificationCenter.requestAuthorizationWithOptions(
            UNAuthorizationOptionAlert or UNAuthorizationOptionSound or UNAuthorizationOptionBadge
        ) { granted, error ->
            if (error != null) {
                PlatformLogger.e("ScheduledTaskNotifications", "Notification permission error: ${error.localizedDescription}")
            }
            cont.resume(granted)
        }
    }

    actual fun hasNotificationPermission(): Boolean {
        var hasPermission = false
        notificationCenter.getNotificationSettingsWithCompletionHandler { settings ->
            hasPermission = settings?.authorizationStatus == UNAuthorizationStatusAuthorized
        }
        // Note: This is synchronous check - may need async handling in production
        return hasPermission
    }

    actual suspend fun requestCalendarPermission(): Boolean {
        // TODO: Implement with EventKit once cinterop bindings are fixed
        PlatformLogger.w("ScheduledTaskNotifications", "Calendar permission not yet implemented on iOS")
        return false
    }

    actual fun hasCalendarPermission(): Boolean {
        // TODO: Implement with EventKit once cinterop bindings are fixed
        return false
    }

    actual suspend fun scheduleNotification(notification: TaskNotification): ScheduleResult {
        return try {
            if (!hasNotificationPermission()) {
                val granted = requestNotificationPermission()
                if (!granted) {
                    return ScheduleResult(success = false, error = "Notification permission denied")
                }
            }

            val content = UNMutableNotificationContent().apply {
                setTitle("CIRIS Task: ${notification.title}")
                setBody(notification.description)
                setSound(UNNotificationSound.defaultSound())
                if (notification.isRecurring) {
                    setSubtitle("Recurring task")
                }
                // Add task ID for deep linking
                setUserInfo(mapOf("task_id" to notification.taskId, "navigate_to" to "scheduler"))
            }

            val triggerDate = NSDate.dateWithTimeIntervalSince1970(
                notification.triggerTimeMillis / 1000.0
            )
            val dateComponents = NSCalendar.currentCalendar.components(
                NSCalendarUnitYear or NSCalendarUnitMonth or NSCalendarUnitDay or
                    NSCalendarUnitHour or NSCalendarUnitMinute or NSCalendarUnitSecond,
                fromDate = triggerDate
            )

            val trigger = if (notification.isRecurring && notification.cronExpression != null) {
                // For recurring, create repeating trigger based on cron
                createRecurringTrigger(notification.cronExpression, dateComponents)
            } else {
                UNCalendarNotificationTrigger.triggerWithDateMatchingComponents(
                    dateComponents,
                    repeats = false
                )
            }

            val identifier = "ciris_task_${notification.taskId}"
            val request = UNNotificationRequest.requestWithIdentifier(
                identifier,
                content,
                trigger
            )

            var result: ScheduleResult? = null

            notificationCenter.addNotificationRequest(request) { error ->
                result = if (error != null) {
                    PlatformLogger.e("ScheduledTaskNotifications", "Failed to schedule: ${error.localizedDescription}")
                    ScheduleResult(success = false, error = error.localizedDescription)
                } else {
                    taskIdToNotificationId[notification.taskId] = identifier
                    ScheduleResult(success = true, notificationId = identifier.hashCode())
                }
            }

            // Wait briefly for callback
            NSThread.sleepForTimeInterval(0.1)
            result ?: ScheduleResult(success = true, notificationId = identifier.hashCode())

        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Exception scheduling notification: ${e.message}")
            ScheduleResult(success = false, error = e.message)
        }
    }

    private fun createRecurringTrigger(
        cronExpression: String,
        baseComponents: NSDateComponents
    ): UNNotificationTrigger {
        val parts = cronExpression.split(" ")
        if (parts.size < 5) {
            return UNCalendarNotificationTrigger.triggerWithDateMatchingComponents(
                baseComponents,
                repeats = true
            )
        }

        val minute = parts[0]
        val hour = parts[1]
        val dayOfMonth = parts[2]
        val month = parts[3]
        val dayOfWeek = parts[4]

        val components = NSDateComponents()

        // Set time
        if (minute != "*") {
            minute.toIntOrNull()?.let { components.setMinute(it.toLong()) }
        }
        if (hour != "*") {
            hour.toIntOrNull()?.let { components.setHour(it.toLong()) }
        }

        // Daily at specific time - only set hour/minute
        if (dayOfMonth == "*" && month == "*" && dayOfWeek == "*") {
            // Already set hour/minute above
        }
        // Weekly on specific day
        else if (dayOfWeek != "*" && dayOfMonth == "*") {
            dayOfWeek.toIntOrNull()?.let { dow ->
                // iOS: 1=Sunday, 2=Monday, etc. Cron: 0/7=Sunday, 1=Monday
                val iosDay = if (dow == 0 || dow == 7) 1 else dow + 1
                components.setWeekday(iosDay.toLong())
            }
        }
        // Monthly on specific day
        else if (dayOfMonth != "*" && month == "*") {
            dayOfMonth.toIntOrNull()?.let { components.setDay(it.toLong()) }
        }

        return UNCalendarNotificationTrigger.triggerWithDateMatchingComponents(
            components,
            repeats = true
        )
    }

    actual fun cancelNotification(taskId: String) {
        val identifier = taskIdToNotificationId[taskId] ?: "ciris_task_$taskId"
        notificationCenter.removePendingNotificationRequestsWithIdentifiers(listOf(identifier))
        notificationCenter.removeDeliveredNotificationsWithIdentifiers(listOf(identifier))
        taskIdToNotificationId.remove(taskId)
    }

    actual suspend fun addCalendarEvent(
        notification: TaskNotification,
        reminderMinutes: Int
    ): ScheduleResult {
        // TODO: Implement with EventKit once cinterop bindings are fixed
        // EventKit constants (EKEntityTypeEvent, EKSpanThisEvent, EKRecurrenceFrequency*)
        // are not resolving properly in Kotlin/Native cinterop
        PlatformLogger.w("ScheduledTaskNotifications", "Calendar events not yet implemented on iOS (EventKit cinterop pending)")
        return ScheduleResult(success = false, error = "Calendar integration not yet available on iOS")
    }

    actual suspend fun removeCalendarEvent(calendarEventId: Long): Boolean {
        // TODO: Implement with EventKit once cinterop bindings are fixed
        PlatformLogger.w("ScheduledTaskNotifications", "Calendar event removal not yet implemented on iOS")
        return false
    }

    actual suspend fun scheduleBackgroundWork(notification: TaskNotification): ScheduleResult {
        // iOS uses BGTaskScheduler for background work
        // For now, rely on notification triggers which can wake the app
        // TODO: Implement BGTaskScheduler integration for iOS 13+

        // Schedule notification which will wake app when triggered
        val notificationResult = scheduleNotification(notification)

        return if (notificationResult.success) {
            ScheduleResult(
                success = true,
                workerId = "ios_notification_${notification.taskId}"
            )
        } else {
            notificationResult
        }
    }

    actual fun cancelBackgroundWork(taskId: String) {
        // Cancel notification-based background trigger
        cancelNotification(taskId)
        // TODO: Cancel BGTaskScheduler task when implemented
    }

    actual fun showImmediateNotification(title: String, message: String, taskId: String?) {
        val content = UNMutableNotificationContent().apply {
            setTitle(title)
            setBody(message)
            setSound(UNNotificationSound.defaultSound())
            taskId?.let {
                setUserInfo(mapOf("task_id" to it, "navigate_to" to "scheduler"))
            }
        }

        // Trigger immediately (in 1 second)
        val trigger = UNTimeIntervalNotificationTrigger.triggerWithTimeInterval(1.0, repeats = false)

        val identifier = taskId?.let { "ciris_immediate_$it" } ?: "ciris_immediate_${NSDate().timeIntervalSince1970}"
        val request = UNNotificationRequest.requestWithIdentifier(identifier, content, trigger)

        notificationCenter.addNotificationRequest(request) { error ->
            if (error != null) {
                PlatformLogger.e("ScheduledTaskNotifications", "Failed to show notification: ${error.localizedDescription}")
            }
        }
    }
}
