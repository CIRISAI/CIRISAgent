package ai.ciris.mobile.shared.platform

actual object ScheduledTaskNotifications {
    actual fun scheduleNotification(taskId: String, title: String, message: String, triggerTimeMs: Long) {
        // TODO: Use Web Notifications API with user permission
    }
    actual fun cancelNotification(taskId: String) {}
    actual fun cancelAllNotifications() {}
}
