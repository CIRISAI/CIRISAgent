package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PythonRuntime
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.datetime.Clock

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

    private val _prepStepsCompleted = MutableStateFlow(0)
    val prepStepsCompleted: StateFlow<Int> = _prepStepsCompleted.asStateFlow()

    private val _hasError = MutableStateFlow(false)
    val hasError: StateFlow<Boolean> = _hasError.asStateFlow()

    private var startTime: Long = 0

    companion object {
        const val TOTAL_PREP_STEPS = 6  // pydantic/native lib setup steps
    }

    /**
     * Start CIRIS runtime
     * Call this once when app launches
     */
    fun startCIRIS() {
        startTime = Clock.System.now().toEpochMilliseconds()

        viewModelScope.launch {
            // Start elapsed time timer
            startElapsedTimer()

            // Start elapsed time counter
            launch {
                while (isActive && _phase.value != StartupPhase.READY && _phase.value != StartupPhase.ERROR) {
                    _elapsedSeconds.value = ((Clock.System.now().toEpochMilliseconds() - startTime) / 1000).toInt()
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
        _phase.value = StartupPhase.LOADING_RUNTIME
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
     * Step 3: Wait for services to be online
     * In first-run mode, only 10 minimal services start (ready for setup wizard)
     * In normal mode, all 22 services start
     */
    private suspend fun waitForServices() {
        _phase.value = StartupPhase.WAITING_SERVER
        _statusMessage.value = "Waiting for services..."

        var attempts = 0
        val maxAttempts = 60 // 2 minutes max (60 * 2s = 120s)
        var healthyCount = 0

        while (attempts < maxAttempts && currentCoroutineContext().isActive) {
            delay(2000) // Poll every 2 seconds

            // Check health
            val healthResult = pythonRuntime.checkHealth()
            if (healthResult.isSuccess && healthResult.getOrNull() == true) {
                healthyCount++

                // Get service count
                val statusResult = pythonRuntime.getServicesStatus()
                if (statusResult.isSuccess) {
                    val (online, total) = statusResult.getOrNull() ?: (0 to 22)
                    _servicesOnline.value = online
                    _totalServices.value = total
                    _statusMessage.value = "$online / $total services online"

                    // Ready conditions:
                    // 1. All 22 services online (normal mode)
                    // 2. 10+ services and health OK for 3+ checks (first-run mode)
                    // 3. Any services online and health OK for 5+ checks (fallback)
                    if (online == total && online > 0) {
                        _phase.value = StartupPhase.READY
                        _statusMessage.value = "CIRIS ready!"
                        return
                    }

                    if (online >= 10 && healthyCount >= 3) {
                        // First-run mode - 10 minimal services ready
                        _phase.value = StartupPhase.READY
                        _statusMessage.value = "Setup required"
                        return
                    }

                    if (online > 0 && healthyCount >= 5) {
                        // Fallback - server is responding, proceed anyway
                        _phase.value = StartupPhase.READY
                        _statusMessage.value = "CIRIS ready"
                        return
                    }
                }
            }

            attempts++
        }

        // Timeout - but if server was healthy, proceed anyway
        if (healthyCount > 0) {
            _phase.value = StartupPhase.READY
            _statusMessage.value = "Server ready (partial)"
            return
        }

        throw Exception("Timeout waiting for services (${_servicesOnline.value}/${_totalServices.value} online)")
    }

    /**
     * Update the current startup phase
     */
    fun setPhase(phase: StartupPhase) {
        _phase.value = phase
        _statusMessage.value = phase.displayName
    }

    /**
     * Called when a prep step completes (pydantic/native lib setup)
     */
    fun onPrepStepCompleted(step: Int) {
        if (step < 1 || step > TOTAL_PREP_STEPS) return

        // Set phase to PREPARING on first prep step
        if (_prepStepsCompleted.value == 0) {
            setPhase(StartupPhase.PREPARING)
        }

        _prepStepsCompleted.value = step
        _statusMessage.value = "Preparing environment... $step/$TOTAL_PREP_STEPS"

        // When all prep steps complete
        if (step >= TOTAL_PREP_STEPS) {
            setPhase(StartupPhase.STARTING_SERVER)
            _statusMessage.value = "Environment ready"
        }
    }

    /**
     * Called when a service starts
     */
    fun onServiceStarted(serviceNum: Int) {
        if (serviceNum < 1 || serviceNum > _totalServices.value) return

        // Set phase to LOADING_SERVICES on first service
        if (_servicesOnline.value == 0) {
            setPhase(StartupPhase.LOADING_SERVICES)
        }

        _servicesOnline.value = serviceNum
        _statusMessage.value = "Starting services... $serviceNum/${_totalServices.value}"

        // When all services are ready
        if (serviceNum >= _totalServices.value) {
            setPhase(StartupPhase.READY)
            _statusMessage.value = "All ${_totalServices.value} services ready"
        }
    }

    /**
     * Called when an error is detected
     */
    fun onErrorDetected(error: String) {
        if (_hasError.value) return // Already in error state

        _hasError.value = true
        _errorMessage.value = error
        setPhase(StartupPhase.ERROR)
    }

    /**
     * Start elapsed time timer
     */
    fun startElapsedTimer() {
        startTime = Clock.System.now().toEpochMilliseconds()
    }

    /**
     * Stop elapsed time timer
     */
    fun stopElapsedTimer() {
        // Timer stops automatically when phase becomes READY or ERROR
    }

    /**
     * Retry startup after error
     */
    fun retry() {
        _errorMessage.value = null
        _servicesOnline.value = 0
        _elapsedSeconds.value = 0
        _prepStepsCompleted.value = 0
        _hasError.value = false
        startCIRIS()
    }

    /**
     * Reset for resume after setup completion
     * Python server is still running, just need to watch for remaining services
     * Called when setup wizard completes and we need to show remaining 12 services starting
     */
    fun resetForResume() {
        _phase.value = StartupPhase.LOADING_SERVICES
        _statusMessage.value = "Resuming services..."
        _errorMessage.value = null
        _hasError.value = false
        // Don't reset service count - it will be updated as remaining services start
        // Don't reset elapsed time - continues from startup

        // Start watching for service updates
        viewModelScope.launch {
            waitForServices()
        }
    }

    override fun onCleared() {
        super.onCleared()
        // Don't shutdown Python - it persists for app lifetime
    }
}

/**
 * Startup phases for UI display
 * Matches android/app/.../MainActivity.kt StartupPhase enum
 */
enum class StartupPhase(val displayName: String) {
    INITIALIZING("INITIALIZING"),
    LOADING_RUNTIME("LOADING RUNTIME"),
    PREPARING("PREPARING ENVIRONMENT"),
    STARTING_SERVER("STARTING SERVER"),
    WAITING_SERVER("WAITING FOR SERVER"),
    LOADING_SERVICES("LOADING SERVICES"),
    CHECKING_CONFIG("CHECKING CONFIG"),
    FIRST_RUN_SETUP("FIRST-TIME SETUP"),
    AUTHENTICATING("AUTHENTICATING"),
    READY("READY"),
    ERROR("ERROR")
}
