package ai.ciris.mobile.shared.platform

/**
 * WASM implementation of ScheduledTaskNotifications.
 * Browser APIs for notifications are limited; stubs for now.
 */
actual object ScheduledTaskNotifications {
    actual suspend fun requestNotificationPermission(): Boolean {
        // Would use Notification.requestPermission() in JS
        return false
    }

    actual fun hasNotificationPermission(): Boolean {
        // Would check Notification.permission in JS
        return false
    }

    actual suspend fun requestCalendarPermission(): Boolean {
        // No calendar API in browsers
        return false
    }

    actual fun hasCalendarPermission(): Boolean {
        return false
    }

    actual suspend fun scheduleNotification(notification: TaskNotification): ScheduleResult {
        // Web Notifications API doesn't support scheduling
        return ScheduleResult(success = false, error = "Scheduled notifications not supported in browser")
    }

    actual fun cancelNotification(taskId: String) {
        // No-op for browser
    }

    actual suspend fun addCalendarEvent(
        notification: TaskNotification,
        reminderMinutes: Int
    ): ScheduleResult {
        // No calendar API in browsers
        return ScheduleResult(success = false, error = "Calendar events not supported in browser")
    }

    actual suspend fun removeCalendarEvent(calendarEventId: Long): Boolean {
        return false
    }

    actual suspend fun scheduleBackgroundWork(notification: TaskNotification): ScheduleResult {
        // No background work API in browsers
        return ScheduleResult(success = false, error = "Background work not supported in browser")
    }

    actual fun cancelBackgroundWork(taskId: String) {
        // No-op for browser
    }

    actual fun showImmediateNotification(title: String, message: String, taskId: String?) {
        // Would use Notification API in JS if permission granted
        // For now, just log
        console.log("Notification: $title - $message")
    }
}

private external object console {
    fun log(message: String)
}
