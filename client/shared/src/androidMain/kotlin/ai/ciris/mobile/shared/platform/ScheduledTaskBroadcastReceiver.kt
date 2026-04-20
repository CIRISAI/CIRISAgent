package ai.ciris.mobile.shared.platform

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import androidx.core.content.ContextCompat

/**
 * BroadcastReceiver for scheduled task events from the Python backend.
 *
 * The Python code can trigger task execution or status updates by sending
 * broadcasts with specific actions and extras.
 *
 * Actions:
 * - ai.ciris.mobile.EXECUTE_SCHEDULED_TASK - Execute a scheduled task
 * - ai.ciris.mobile.TASK_COMPLETED - Task completed successfully
 * - ai.ciris.mobile.TASK_FAILED - Task execution failed
 *
 * Extras:
 * - task_id: String - The task ID
 * - task_name: String - Human-readable task name
 * - message: String - Status message or error description
 */
class ScheduledTaskBroadcastReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "ScheduledTaskReceiver"

        const val ACTION_EXECUTE_TASK = "ai.ciris.mobile.EXECUTE_SCHEDULED_TASK"
        const val ACTION_TASK_COMPLETED = "ai.ciris.mobile.TASK_COMPLETED"
        const val ACTION_TASK_FAILED = "ai.ciris.mobile.TASK_FAILED"
        const val ACTION_TASK_STARTED = "ai.ciris.mobile.TASK_STARTED"

        const val EXTRA_TASK_ID = "task_id"
        const val EXTRA_TASK_NAME = "task_name"
        const val EXTRA_MESSAGE = "message"
        const val EXTRA_TRIGGER_PROMPT = "trigger_prompt"

        private var listener: ScheduledTaskListener? = null

        /**
         * Register a listener for task events.
         */
        fun setListener(listener: ScheduledTaskListener?) {
            this.listener = listener
        }

        /**
         * Create an IntentFilter for all task-related actions.
         */
        fun createIntentFilter(): IntentFilter {
            return IntentFilter().apply {
                addAction(ACTION_EXECUTE_TASK)
                addAction(ACTION_TASK_COMPLETED)
                addAction(ACTION_TASK_FAILED)
                addAction(ACTION_TASK_STARTED)
            }
        }

        /**
         * Register this receiver with a context.
         */
        fun register(context: Context, receiver: ScheduledTaskBroadcastReceiver) {
            ContextCompat.registerReceiver(
                context,
                receiver,
                createIntentFilter(),
                ContextCompat.RECEIVER_NOT_EXPORTED
            )
            PlatformLogger.i(TAG, "ScheduledTaskBroadcastReceiver registered")
        }

        /**
         * Send a broadcast to execute a task (called from Python via JNI or reflection).
         */
        fun sendExecuteTaskBroadcast(
            context: Context,
            taskId: String,
            taskName: String,
            triggerPrompt: String
        ) {
            val intent = Intent(ACTION_EXECUTE_TASK).apply {
                putExtra(EXTRA_TASK_ID, taskId)
                putExtra(EXTRA_TASK_NAME, taskName)
                putExtra(EXTRA_TRIGGER_PROMPT, triggerPrompt)
                setPackage(context.packageName)
            }
            context.sendBroadcast(intent)
            PlatformLogger.i(TAG, "Sent execute task broadcast: $taskId")
        }

        /**
         * Send a task completion broadcast.
         */
        fun sendTaskCompletedBroadcast(
            context: Context,
            taskId: String,
            taskName: String,
            message: String
        ) {
            val intent = Intent(ACTION_TASK_COMPLETED).apply {
                putExtra(EXTRA_TASK_ID, taskId)
                putExtra(EXTRA_TASK_NAME, taskName)
                putExtra(EXTRA_MESSAGE, message)
                setPackage(context.packageName)
            }
            context.sendBroadcast(intent)
            PlatformLogger.i(TAG, "Sent task completed broadcast: $taskId")
        }

        /**
         * Send a task failure broadcast.
         */
        fun sendTaskFailedBroadcast(
            context: Context,
            taskId: String,
            taskName: String,
            errorMessage: String
        ) {
            val intent = Intent(ACTION_TASK_FAILED).apply {
                putExtra(EXTRA_TASK_ID, taskId)
                putExtra(EXTRA_TASK_NAME, taskName)
                putExtra(EXTRA_MESSAGE, errorMessage)
                setPackage(context.packageName)
            }
            context.sendBroadcast(intent)
            PlatformLogger.e(TAG, "Sent task failed broadcast: $taskId - $errorMessage")
        }
    }

    override fun onReceive(context: Context, intent: Intent) {
        val taskId = intent.getStringExtra(EXTRA_TASK_ID) ?: return
        val taskName = intent.getStringExtra(EXTRA_TASK_NAME) ?: "Unknown Task"
        val message = intent.getStringExtra(EXTRA_MESSAGE)
        val triggerPrompt = intent.getStringExtra(EXTRA_TRIGGER_PROMPT)

        PlatformLogger.i(TAG, "Received broadcast: ${intent.action} for task: $taskId")

        when (intent.action) {
            ACTION_EXECUTE_TASK -> {
                PlatformLogger.i(TAG, "Execute task requested: $taskName ($taskId)")

                // Show notification that task is starting
                ScheduledTaskNotifications.showImmediateNotification(
                    title = "Running: $taskName",
                    message = "Task is being executed...",
                    taskId = taskId
                )

                // Notify listener
                listener?.onTaskExecutionRequested(taskId, taskName, triggerPrompt ?: "")
            }

            ACTION_TASK_STARTED -> {
                PlatformLogger.i(TAG, "Task started: $taskName ($taskId)")
                listener?.onTaskStarted(taskId, taskName)
            }

            ACTION_TASK_COMPLETED -> {
                PlatformLogger.i(TAG, "Task completed: $taskName ($taskId)")

                // Show completion notification
                ScheduledTaskNotifications.showImmediateNotification(
                    title = "Completed: $taskName",
                    message = message ?: "Task completed successfully",
                    taskId = taskId
                )

                // Notify listener
                listener?.onTaskCompleted(taskId, taskName, message)
            }

            ACTION_TASK_FAILED -> {
                PlatformLogger.e(TAG, "Task failed: $taskName ($taskId) - $message")

                // Show failure notification
                ScheduledTaskNotifications.showImmediateNotification(
                    title = "Failed: $taskName",
                    message = message ?: "Task execution failed",
                    taskId = taskId
                )

                // Notify listener
                listener?.onTaskFailed(taskId, taskName, message ?: "Unknown error")
            }
        }
    }
}

/**
 * Listener interface for scheduled task events.
 */
interface ScheduledTaskListener {
    /**
     * Called when a task execution is requested (e.g., from alarm/notification trigger).
     */
    fun onTaskExecutionRequested(taskId: String, taskName: String, triggerPrompt: String)

    /**
     * Called when a task has started executing.
     */
    fun onTaskStarted(taskId: String, taskName: String)

    /**
     * Called when a task completes successfully.
     */
    fun onTaskCompleted(taskId: String, taskName: String, result: String?)

    /**
     * Called when a task execution fails.
     */
    fun onTaskFailed(taskId: String, taskName: String, error: String)
}
