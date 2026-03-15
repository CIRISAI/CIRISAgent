package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.api.ScheduledTaskData
import ai.ciris.mobile.shared.api.SchedulerStatsData as ApiSchedulerStatsData
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.ScheduledTaskNotifications
import ai.ciris.mobile.shared.platform.TaskNotification
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.datetime.Instant

/**
 * Options for local notifications/calendar when creating tasks.
 */
data class TaskNotificationOptions(
    val enableNotification: Boolean = true,
    val addToCalendar: Boolean = false,
    val calendarReminderMinutes: Int = 15
)

/**
 * Scheduler overview data combining telemetry and scheduler API data.
 */
data class SchedulerOverviewData(
    val cognitiveState: String = "UNKNOWN",
    val activeCount: Int = 0,
    val recurringCount: Int = 0,
    val pendingCount: Int = 0,
    val completedTotal: Int = 0,
    val failedTotal: Int = 0,
    val uptimeSeconds: Double = 0.0,
    val hasNotificationPermission: Boolean = false,
    val hasCalendarPermission: Boolean = false
)

/**
 * State for the Scheduler screen.
 */
data class SchedulerScreenState(
    val overview: SchedulerOverviewData = SchedulerOverviewData(),
    val tasks: List<ScheduledTaskData> = emptyList(),
    val isLoading: Boolean = false,
    val isRefreshing: Boolean = false,
    val error: String? = null,
    // Create task dialog state
    val showCreateDialog: Boolean = false,
    val isCreatingTask: Boolean = false,
    val createTaskError: String? = null,
    val createTaskSuccess: Boolean = false,
    // Notification options
    val notificationOptions: TaskNotificationOptions = TaskNotificationOptions()
)

/**
 * ViewModel for the Scheduler screen.
 *
 * Features:
 * - Shows scheduled tasks list with status
 * - Displays scheduler statistics
 * - Allows creating one-time and recurring tasks
 * - Allows cancelling scheduled tasks
 * - Shows current cognitive state
 */
class SchedulerViewModel(
    private val apiClient: CIRISApiClient
) : ViewModel() {

    companion object {
        private const val TAG = "SchedulerViewModel"
    }

    private fun log(level: String, method: String, message: String) {
        val fullMessage = "[$method] $message"
        when (level) {
            "DEBUG" -> PlatformLogger.d(TAG, fullMessage)
            "INFO" -> PlatformLogger.i(TAG, fullMessage)
            "WARN" -> PlatformLogger.w(TAG, fullMessage)
            "ERROR" -> PlatformLogger.e(TAG, fullMessage)
            else -> PlatformLogger.i(TAG, fullMessage)
        }
    }

    private fun logDebug(method: String, message: String) = log("DEBUG", method, message)
    private fun logInfo(method: String, message: String) = log("INFO", method, message)
    private fun logError(method: String, message: String) = log("ERROR", method, message)

    // State
    private val _state = MutableStateFlow(SchedulerScreenState())
    val state: StateFlow<SchedulerScreenState> = _state.asStateFlow()
    private var dataLoadStarted = false

    init {
        logInfo("init", "SchedulerViewModel initialized")
    }

    /**
     * Start scheduler data loading.
     */
    fun startPolling() {
        val method = "startPolling"
        if (dataLoadStarted) {
            logDebug(method, "Data load already started, skipping")
            return
        }
        dataLoadStarted = true
        logInfo(method, "Starting scheduler data loading")
        refresh()
    }

    /**
     * Stop polling.
     */
    fun stopPolling() {
        val method = "stopPolling"
        logInfo(method, "Stopping scheduler polling")
        dataLoadStarted = false
    }

    /**
     * Refresh scheduler data.
     */
    fun refresh() {
        val method = "refresh"
        logInfo(method, "Refreshing scheduler data")

        viewModelScope.launch {
            _state.update { it.copy(isRefreshing = true, error = null) }

            try {
                // Fetch cognitive state from telemetry
                var cognitiveState = "UNKNOWN"
                try {
                    val telemetry = apiClient.getUnifiedTelemetry()
                    cognitiveState = telemetry.cognitiveState
                } catch (e: Exception) {
                    logDebug(method, "Telemetry not available: ${e.message}")
                }

                // Fetch scheduler stats
                var statsData: ApiSchedulerStatsData? = null
                try {
                    statsData = apiClient.getSchedulerStats()
                } catch (e: Exception) {
                    logDebug(method, "Scheduler stats not available: ${e.message}")
                }

                // Fetch scheduled tasks
                var tasks: List<ScheduledTaskData> = emptyList()
                try {
                    val tasksResult = apiClient.getScheduledTasks()
                    tasks = tasksResult.tasks
                } catch (e: Exception) {
                    logDebug(method, "Scheduled tasks not available: ${e.message}")
                }

                val overview = SchedulerOverviewData(
                    cognitiveState = cognitiveState,
                    activeCount = statsData?.tasksPending ?: tasks.count { it.status == "PENDING" || it.status == "ACTIVE" },
                    recurringCount = statsData?.recurringTasks ?: tasks.count { it.isRecurring },
                    pendingCount = statsData?.tasksPending ?: tasks.count { it.status == "PENDING" },
                    completedTotal = statsData?.tasksCompletedTotal ?: 0,
                    failedTotal = statsData?.tasksFailedTotal ?: 0,
                    uptimeSeconds = statsData?.schedulerUptimeSeconds ?: 0.0
                )

                _state.update {
                    it.copy(
                        overview = overview,
                        tasks = tasks,
                        isRefreshing = false,
                        error = null
                    )
                }

                logInfo(method, "Scheduler data: cognitiveState=$cognitiveState, tasks=${tasks.size}, pending=${overview.pendingCount}")

            } catch (e: Exception) {
                logError(method, "Failed to refresh: ${e.message}")
                _state.update {
                    it.copy(
                        isRefreshing = false,
                        error = "Failed to refresh: ${e.message}"
                    )
                }
            }
        }
    }

    /**
     * Show the create task dialog.
     */
    fun showCreateTaskDialog() {
        _state.update { it.copy(showCreateDialog = true, createTaskError = null, createTaskSuccess = false) }
    }

    /**
     * Hide the create task dialog.
     */
    fun hideCreateTaskDialog() {
        _state.update { it.copy(showCreateDialog = false, createTaskError = null, createTaskSuccess = false) }
    }

    /**
     * Create a new scheduled task.
     *
     * @param name Task name
     * @param goalDescription What the task aims to achieve
     * @param triggerPrompt Prompt to execute when triggered
     * @param deferUntil ISO timestamp for one-time task (mutually exclusive with scheduleCron)
     * @param scheduleCron Cron expression for recurring task (e.g., "0 9 * * *" for daily at 9am)
     * @param options Notification and calendar options
     */
    fun createTask(
        name: String,
        goalDescription: String,
        triggerPrompt: String,
        deferUntil: String? = null,
        scheduleCron: String? = null,
        options: TaskNotificationOptions = _state.value.notificationOptions
    ) {
        val method = "createTask"
        logInfo(method, "Creating task: $name (notify=${options.enableNotification}, calendar=${options.addToCalendar})")

        viewModelScope.launch {
            _state.update { it.copy(isCreatingTask = true, createTaskError = null) }

            try {
                // Create task in backend
                val createdTask = apiClient.createScheduledTask(
                    name = name,
                    goalDescription = goalDescription,
                    triggerPrompt = triggerPrompt,
                    deferUntil = deferUntil,
                    scheduleCron = scheduleCron
                )

                logInfo(method, "Task created in backend: ${createdTask.taskId}")

                // Calculate trigger time
                val triggerTimeMillis = when {
                    deferUntil != null -> {
                        try {
                            Instant.parse(deferUntil).toEpochMilliseconds()
                        } catch (e: Exception) {
                            logError(method, "Failed to parse deferUntil: $deferUntil")
                            System.currentTimeMillis() + 3600000 // Default 1 hour
                        }
                    }
                    scheduleCron != null -> calculateNextCronTrigger(scheduleCron)
                    else -> System.currentTimeMillis() + 3600000 // Default 1 hour
                }

                val taskNotification = TaskNotification(
                    taskId = createdTask.taskId,
                    title = name,
                    description = goalDescription,
                    triggerTimeMillis = triggerTimeMillis,
                    isRecurring = scheduleCron != null,
                    cronExpression = scheduleCron
                )

                // Schedule local notification if enabled
                if (options.enableNotification) {
                    val notifyResult = ScheduledTaskNotifications.scheduleNotification(taskNotification)
                    if (notifyResult.success) {
                        logInfo(method, "Scheduled notification: ${notifyResult.notificationId}")
                    } else {
                        logError(method, "Failed to schedule notification: ${notifyResult.error}")
                    }

                    // Also schedule background work to ensure task triggers even if app is closed
                    val workResult = ScheduledTaskNotifications.scheduleBackgroundWork(taskNotification)
                    if (workResult.success) {
                        logInfo(method, "Scheduled background work: ${workResult.workerId}")
                    }
                }

                // Add to calendar if enabled
                if (options.addToCalendar) {
                    val calendarResult = ScheduledTaskNotifications.addCalendarEvent(
                        taskNotification,
                        options.calendarReminderMinutes
                    )
                    if (calendarResult.success) {
                        logInfo(method, "Added calendar event: ${calendarResult.calendarEventId}")
                    } else {
                        logError(method, "Failed to add calendar event: ${calendarResult.error}")
                    }
                }

                _state.update {
                    it.copy(
                        isCreatingTask = false,
                        createTaskSuccess = true,
                        showCreateDialog = false
                    )
                }

                // Refresh the task list
                refresh()

            } catch (e: Exception) {
                logError(method, "Failed to create task: ${e.message}")
                _state.update {
                    it.copy(
                        isCreatingTask = false,
                        createTaskError = e.message ?: "Failed to create task"
                    )
                }
            }
        }
    }

    /**
     * Calculate the next trigger time for a cron expression.
     * Simple implementation for common patterns.
     */
    private fun calculateNextCronTrigger(cron: String): Long {
        val parts = cron.split(" ")
        if (parts.size < 5) return System.currentTimeMillis() + 3600000

        val minute = parts[0].toIntOrNull() ?: 0
        val hour = parts[1].toIntOrNull() ?: 9

        // Calculate next occurrence (simplified - daily at specified time)
        val now = System.currentTimeMillis()
        val calendar = java.util.Calendar.getInstance()
        calendar.timeInMillis = now
        calendar.set(java.util.Calendar.HOUR_OF_DAY, hour)
        calendar.set(java.util.Calendar.MINUTE, minute)
        calendar.set(java.util.Calendar.SECOND, 0)
        calendar.set(java.util.Calendar.MILLISECOND, 0)

        // If time already passed today, schedule for tomorrow
        if (calendar.timeInMillis <= now) {
            calendar.add(java.util.Calendar.DAY_OF_YEAR, 1)
        }

        return calendar.timeInMillis
    }

    /**
     * Cancel a scheduled task.
     */
    fun cancelTask(taskId: String) {
        val method = "cancelTask"
        logInfo(method, "Cancelling task: $taskId")

        viewModelScope.launch {
            try {
                val success = apiClient.cancelScheduledTask(taskId)
                if (success) {
                    logInfo(method, "Task cancelled successfully")

                    // Cancel local notification
                    ScheduledTaskNotifications.cancelNotification(taskId)
                    logDebug(method, "Cancelled notification for task: $taskId")

                    // Cancel background work
                    ScheduledTaskNotifications.cancelBackgroundWork(taskId)
                    logDebug(method, "Cancelled background work for task: $taskId")

                    // Refresh the task list
                    refresh()
                } else {
                    logError(method, "Failed to cancel task")
                    _state.update { it.copy(error = "Failed to cancel task") }
                }
            } catch (e: Exception) {
                logError(method, "Failed to cancel task: ${e.message}")
                _state.update { it.copy(error = "Failed to cancel task: ${e.message}") }
            }
        }
    }

    /**
     * Clear any error message.
     */
    fun clearError() {
        _state.update { it.copy(error = null, createTaskError = null) }
    }

    override fun onCleared() {
        logInfo("onCleared", "ViewModel cleared")
        super.onCleared()
    }
}
