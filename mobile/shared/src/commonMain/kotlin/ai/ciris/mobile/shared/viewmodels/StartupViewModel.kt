package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PythonRuntime
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/**
 * Manages CIRIS startup sequence
 * Initializes Python runtime, starts FastAPI server, waits for all 22 services
 *
 * Based on android/app/.../MainActivity.kt startup logic
 */
class StartupViewModel(
    private val pythonRuntime: PythonRuntime,
    private val apiClient: CIRISApiClient,
    private val pythonHomePath: String = "/default/python/path"
) : ViewModel() {

    private val _phase = MutableStateFlow(StartupPhase.INITIALIZING)
    val phase: StateFlow<StartupPhase> = _phase.asStateFlow()

    private val _servicesOnline = MutableStateFlow(0)
    val servicesOnline: StateFlow<Int> = _servicesOnline.asStateFlow()

    private val _totalServices = MutableStateFlow(22)
    val totalServices: StateFlow<Int> = _totalServices.asStateFlow()

    private val _statusMessage = MutableStateFlow("Initializing...")
    val statusMessage: StateFlow<String> = _statusMessage.asStateFlow()

    private val _errorMessage = MutableStateFlow<String?>(null)
    val errorMessage: StateFlow<String?> = _errorMessage.asStateFlow()

    private val _elapsedSeconds = MutableStateFlow(0)
    val elapsedSeconds: StateFlow<Int> = _elapsedSeconds.asStateFlow()

    private var startTime: Long = 0

    /**
     * Start CIRIS runtime
     * Call this once when app launches
     */
    fun startCIRIS() {
        startTime = System.currentTimeMillis()

        viewModelScope.launch {
            // Start elapsed time counter
            launch {
                while (isActive && _phase.value != StartupPhase.READY && _phase.value != StartupPhase.ERROR) {
                    _elapsedSeconds.value = ((System.currentTimeMillis() - startTime) / 1000).toInt()
                    delay(1000)
                }
            }

            // Execute startup sequence
            try {
                initializePython()
                startFastAPIServer()
                waitForServices()
            } catch (e: Exception) {
                _errorMessage.value = e.message ?: "Unknown error during startup"
                _phase.value = StartupPhase.ERROR
            }
        }
    }

    /**
     * Step 1: Initialize Python interpreter
     */
    private suspend fun initializePython() {
        _phase.value = StartupPhase.INITIALIZING_PYTHON
        _statusMessage.value = "Starting Python interpreter..."

        val result = pythonRuntime.initialize(pythonHomePath)
        if (result.isFailure) {
            throw result.exceptionOrNull() ?: Exception("Failed to initialize Python")
        }

        _statusMessage.value = "Python ready"
    }

    /**
     * Step 2: Start FastAPI server
     */
    private suspend fun startFastAPIServer() {
        _phase.value = StartupPhase.STARTING_SERVER
        _statusMessage.value = "Starting CIRIS engine..."

        val result = pythonRuntime.startServer()
        if (result.isFailure) {
            throw result.exceptionOrNull() ?: Exception("Failed to start server")
        }

        _statusMessage.value = "Server started at ${result.getOrNull()}"
    }

    /**
     * Step 3: Wait for all 22 services to be online
     */
    private suspend fun waitForServices() {
        _phase.value = StartupPhase.WAITING_FOR_SERVICES
        _statusMessage.value = "Waiting for services..."

        var attempts = 0
        val maxAttempts = 60 // 2 minutes max (60 * 2s = 120s)

        while (attempts < maxAttempts && isActive) {
            delay(2000) // Poll every 2 seconds

            // Check health
            val healthResult = pythonRuntime.checkHealth()
            if (healthResult.isSuccess && healthResult.getOrNull() == true) {
                // Get service count
                val statusResult = pythonRuntime.getServicesStatus()
                if (statusResult.isSuccess) {
                    val (online, total) = statusResult.getOrNull() ?: (0 to 22)
                    _servicesOnline.value = online
                    _totalServices.value = total
                    _statusMessage.value = "$online / $total services online"

                    if (online == total && online > 0) {
                        // All services ready!
                        _phase.value = StartupPhase.READY
                        _statusMessage.value = "CIRIS ready!"
                        return
                    }
                }
            }

            attempts++
        }

        // Timeout
        throw Exception("Timeout waiting for services (${_servicesOnline.value}/${_totalServices.value} online)")
    }

    /**
     * Retry startup after error
     */
    fun retry() {
        _errorMessage.value = null
        _servicesOnline.value = 0
        _elapsedSeconds.value = 0
        startCIRIS()
    }

    override fun onCleared() {
        super.onCleared()
        // Don't shutdown Python - it persists for app lifetime
    }
}

/**
 * Startup phases for UI display
 */
enum class StartupPhase {
    INITIALIZING,              // Initial state
    INITIALIZING_PYTHON,       // Py_Initialize() or Python.start()
    STARTING_SERVER,           // mobile_main.py execution
    WAITING_FOR_SERVICES,      // Polling for 22/22 services
    READY,                     // All services online, ready to use
    ERROR                      // Fatal error occurred
}
