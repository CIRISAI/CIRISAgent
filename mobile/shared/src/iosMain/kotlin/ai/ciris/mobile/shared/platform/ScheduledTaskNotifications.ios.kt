package ai.ciris.mobile.shared.platform

import kotlinx.cinterop.*
import platform.Foundation.*
import platform.UserNotifications.*
import platform.EventKit.*
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/**
 * iOS implementation of scheduled task notifications using:
 * - UNUserNotificationCenter for notifications
 * - EventKit for calendar events
 *
 * TODO: Test this implementation on actual iOS device/simulator
 */
@OptIn(ExperimentalForeignApi::class)
actual object ScheduledTaskNotifications {

    private val notificationCenter = UNUserNotificationCenter.currentNotificationCenter()
    private val eventStore = EKEventStore()
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

    actual suspend fun requestCalendarPermission(): Boolean = suspendCancellableCoroutine { cont ->
        eventStore.requestAccessToEntityType(EKEntityTypeEvent) { granted, error ->
            if (error != null) {
                PlatformLogger.e("ScheduledTaskNotifications", "Calendar permission error: ${error?.localizedDescription}")
            }
            cont.resume(granted)
        }
    }

    actual fun hasCalendarPermission(): Boolean {
        return EKEventStore.authorizationStatusForEntityType(EKEntityTypeEvent) == EKAuthorizationStatusAuthorized
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
        return try {
            if (!hasCalendarPermission()) {
                val granted = requestCalendarPermission()
                if (!granted) {
                    return ScheduleResult(success = false, error = "Calendar permission denied")
                }
            }

            val calendar = eventStore.defaultCalendarForNewEvents
            if (calendar == null) {
                return ScheduleResult(success = false, error = "No default calendar available")
            }

            val event = EKEvent.eventWithEventStore(eventStore).apply {
                setTitle("CIRIS: ${notification.title}")
                setNotes(notification.description)
                setCalendar(calendar)

                val startDate = NSDate.dateWithTimeIntervalSince1970(
                    notification.triggerTimeMillis / 1000.0
                )
                setStartDate(startDate)
                setEndDate(NSDate.dateWithTimeIntervalSince1970(
                    (notification.triggerTimeMillis + 3600000) / 1000.0 // 1 hour later
                ))

                // Add recurrence rule if recurring
                notification.cronExpression?.let { cron ->
                    createRecurrenceRule(cron)?.let { rule ->
                        setRecurrenceRules(listOf(rule))
                    }
                }

                // Add alarm/reminder
                if (reminderMinutes > 0) {
                    val alarm = EKAlarm.alarmWithRelativeOffset((-reminderMinutes * 60).toDouble())
                    setAlarms(listOf(alarm))
                }
            }

            var saveError: NSError? = null
            val success = eventStore.saveEvent(event, EKSpanThisEvent, saveError.ptr)

            if (success && saveError == null) {
                val eventId = event.eventIdentifier
                taskIdToEventId[notification.taskId] = eventId
                PlatformLogger.i("ScheduledTaskNotifications", "Created calendar event: $eventId")
                ScheduleResult(success = true, calendarEventId = eventId.hashCode().toLong())
            } else {
                ScheduleResult(success = false, error = saveError?.localizedDescription ?: "Failed to save event")
            }

        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Exception adding calendar event: ${e.message}")
            ScheduleResult(success = false, error = e.message)
        }
    }

    private fun createRecurrenceRule(cron: String): EKRecurrenceRule? {
        val parts = cron.split(" ")
        if (parts.size < 5) return null

        val minute = parts[0]
        val hour = parts[1]
        val dayOfMonth = parts[2]
        val month = parts[3]
        val dayOfWeek = parts[4]

        return when {
            // Daily
            dayOfMonth == "*" && month == "*" && dayOfWeek == "*" ->
                EKRecurrenceRule(
                    EKRecurrenceFrequencyDaily,
                    interval = 1,
                    end = null
                )

            // Weekly on specific day
            dayOfWeek != "*" && dayOfMonth == "*" -> {
                val dow = dayOfWeek.toIntOrNull() ?: return null
                // EKWeekday: 1=Sunday, 2=Monday... Cron: 0/7=Sunday, 1=Monday
                val ekDay = if (dow == 0 || dow == 7) EKWeekdaySunday else (dow + 1).toLong()
                val weekday = EKRecurrenceDayOfWeek.dayOfWeek(ekDay)
                EKRecurrenceRule(
                    EKRecurrenceFrequencyWeekly,
                    interval = 1,
                    daysOfTheWeek = listOf(weekday),
                    daysOfTheMonth = null,
                    monthsOfTheYear = null,
                    weeksOfTheYear = null,
                    daysOfTheYear = null,
                    setPositions = null,
                    end = null
                )
            }

            // Monthly on specific day
            dayOfMonth != "*" && month == "*" -> {
                val day = dayOfMonth.toIntOrNull() ?: return null
                EKRecurrenceRule(
                    EKRecurrenceFrequencyMonthly,
                    interval = 1,
                    daysOfTheWeek = null,
                    daysOfTheMonth = listOf(day),
                    monthsOfTheYear = null,
                    weeksOfTheYear = null,
                    daysOfTheYear = null,
                    setPositions = null,
                    end = null
                )
            }

            // Hourly
            minute == "0" && hour.startsWith("*/") -> {
                val interval = hour.removePrefix("*/").toIntOrNull() ?: return null
                EKRecurrenceRule(
                    EKRecurrenceFrequencyHourly,
                    interval = interval,
                    end = null
                )
            }

            else -> null
        }
    }

    actual suspend fun removeCalendarEvent(calendarEventId: Long): Boolean {
        return try {
            // Find event by searching through known events
            val eventIdentifier = taskIdToEventId.values.find {
                it.hashCode().toLong() == calendarEventId
            }

            if (eventIdentifier != null) {
                val event = eventStore.eventWithIdentifier(eventIdentifier)
                if (event != null) {
                    var error: NSError? = null
                    val success = eventStore.removeEvent(event, EKSpanThisEvent, error.ptr)
                    if (success) {
                        taskIdToEventId.entries.removeAll { it.value == eventIdentifier }
                    }
                    return success
                }
            }
            false
        } catch (e: Exception) {
            PlatformLogger.e("ScheduledTaskNotifications", "Exception removing calendar event: ${e.message}")
            false
        }
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
