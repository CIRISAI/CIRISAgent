package ai.ciris.mobile.shared.platform

/**
 * Data class representing a scheduled task notification.
 */
data class TaskNotification(
    val taskId: String,
    val title: String,
    val description: String,
    val triggerTimeMillis: Long,
    val isRecurring: Boolean,
    val cronExpression: String? = null
)

/**
 * Result of scheduling a notification/calendar event.
 */
data class ScheduleResult(
    val success: Boolean,
    val notificationId: Int? = null,
    val calendarEventId: Long? = null,
    val workerId: String? = null,
    val error: String? = null
)

/**
 * Platform-specific interface for scheduling task notifications and calendar events.
 *
 * Implementations:
 * - Android: NotificationManager + CalendarContract + WorkManager
 * - iOS: UNUserNotificationCenter + EventKit
 * - Desktop: System tray notifications (limited)
 */
expect object ScheduledTaskNotifications {
    /**
     * Request notification permissions from the user.
     * @return true if permissions granted
     */
    suspend fun requestNotificationPermission(): Boolean

    /**
     * Check if notification permissions are granted.
     */
    fun hasNotificationPermission(): Boolean

    /**
     * Request calendar permissions from the user.
     * @return true if permissions granted
     */
    suspend fun requestCalendarPermission(): Boolean

    /**
     * Check if calendar permissions are granted.
     */
    fun hasCalendarPermission(): Boolean

    /**
     * Schedule a notification for a task trigger.
     *
     * @param notification Task notification details
     * @return Result with notification ID or error
     */
    suspend fun scheduleNotification(notification: TaskNotification): ScheduleResult

    /**
     * Cancel a scheduled notification.
     *
     * @param taskId The task ID to cancel notification for
     */
    fun cancelNotification(taskId: String)

    /**
     * Add a calendar event for a scheduled task.
     *
     * @param notification Task notification details
     * @param reminderMinutes Minutes before event to show reminder (default 15)
     * @return Result with calendar event ID or error
     */
    suspend fun addCalendarEvent(
        notification: TaskNotification,
        reminderMinutes: Int = 15
    ): ScheduleResult

    /**
     * Remove a calendar event for a task.
     *
     * @param calendarEventId The calendar event ID to remove
     */
    suspend fun removeCalendarEvent(calendarEventId: Long): Boolean

    /**
     * Schedule background work to trigger a task (even if app is closed).
     *
     * @param notification Task notification details
     * @return Result with worker ID or error
     */
    suspend fun scheduleBackgroundWork(notification: TaskNotification): ScheduleResult

    /**
     * Cancel scheduled background work for a task.
     *
     * @param taskId The task ID to cancel work for
     */
    fun cancelBackgroundWork(taskId: String)

    /**
     * Show an immediate notification (for task completion, errors, etc.)
     *
     * @param title Notification title
     * @param message Notification message
     * @param taskId Optional task ID for deep linking
     */
    fun showImmediateNotification(title: String, message: String, taskId: String? = null)
}
