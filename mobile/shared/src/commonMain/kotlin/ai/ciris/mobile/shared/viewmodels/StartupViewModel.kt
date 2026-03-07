package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClientProtocol
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.PythonRuntimeProtocol
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
    private val pythonRuntime: PythonRuntimeProtocol,
    private val apiClient: CIRISApiClientProtocol,
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

    private val _verifyStepsCompleted = MutableStateFlow(0)
    val verifyStepsCompleted: StateFlow<Int> = _verifyStepsCompleted.asStateFlow()

    private val _hasError = MutableStateFlow(false)
    val hasError: StateFlow<Boolean> = _hasError.asStateFlow()

    private var startTime: Long = 0

    companion object {
        private const val TAG = "StartupViewModel"
        const val TOTAL_PREP_STEPS = 6  // pydantic/native lib setup steps
        const val TOTAL_VERIFY_STEPS = 11  // CIRISVerify attestation: Phase 1 (5) + Phase 2 (6)

        // VERIFY log patterns from ciris-verify v1.1.5
        // Format: VERIFY STEP {n}/{total} COMPLETE: {OK|FAILED|SKIP} ({details})
        private val VERIFY_STEP_PATTERN = Regex(
            """VERIFY STEP (\d+)/(\d+) (STARTING|COMPLETE): (.+)"""
        )
        private val VERIFY_PHASE_PATTERN = Regex(
            """VERIFY PHASE (\d+)/(\d+) (STARTING|COMPLETE): (.+)"""
        )
        private val VERIFY_COMPLETE_PATTERN = Regex(
            """VERIFY ATTESTATION COMPLETE: level=(\d+), valid=(true|false), checks=(\d+)/(\d+)"""
        )
    }

    /**
     * Start CIRIS runtime
     * Call this once when app launches
     */
    fun startCIRIS() {
        PlatformLogger.i(TAG, "[STARTUP] startCIRIS() called - beginning startup sequence")
        PlatformLogger.i(TAG, "[STARTUP] TOTAL_PREP_STEPS=$TOTAL_PREP_STEPS, TOTAL_VERIFY_STEPS=$TOTAL_VERIFY_STEPS")
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
     * On desktop, this waits for the server to become healthy.
     * While waiting, polls startup-status to drive service light animations.
     */
    private suspend fun startFastAPIServer() {
        _phase.value = StartupPhase.STARTING_SERVER
        _statusMessage.value = "Connecting to CIRIS..."

        // Wire output callback to parse service startup lines
        val servicePattern = Regex("""\[SERVICE (\d+)/(\d+)\] (\S+) STARTED""")
        pythonRuntime.setOutputLineCallback { line ->
            // Check for service startup
            servicePattern.find(line)?.let { match ->
                val num = match.groupValues[1].toIntOrNull() ?: return@let
                val total = match.groupValues[2].toIntOrNull() ?: return@let
                _totalServices.value = total
                onServiceStarted(num)
            }
            // Forward verify messages
            if (line.contains("VERIFY")) {
                onVerifyLogMessage(line)
            }
        }

        // Poll for server to become healthy (Python may still be starting)
        val result = pythonRuntime.startServer()

        // Clean up callback
        pythonRuntime.setOutputLineCallback(null)

        if (result.isFailure) {
            throw result.exceptionOrNull() ?: Exception("Failed to connect to server")
        }

        // Server is healthy — verify/prep completed before server was available
        // Mark them done only if they weren't already driven by console output
        if (_verifyStepsCompleted.value == 0) {
            _verifyStepsCompleted.value = TOTAL_VERIFY_STEPS
        }
        if (_prepStepsCompleted.value == 0) {
            _prepStepsCompleted.value = TOTAL_PREP_STEPS
        }
        PlatformLogger.i(TAG, "[STARTUP] Server healthy - verify=${_verifyStepsCompleted.value}, prep=${_prepStepsCompleted.value}, services=${_servicesOnline.value}")
        _statusMessage.value = "Connected to CIRIS"
    }

    /**
     * Step 3: Wait for services to be online
     * In first-run mode, only 10 minimal services start (ready for setup wizard)
     * In normal mode, all 22 services start
     */
    private suspend fun waitForServices() {
        // If services were already fully loaded during startFastAPIServer() polling, skip waiting
        if (_servicesOnline.value >= _totalServices.value && _servicesOnline.value > 0) {
            PlatformLogger.i(TAG, "[STARTUP] All ${_servicesOnline.value} services already loaded, skipping wait")
            showReadyAndComplete()
            return
        }

        _phase.value = StartupPhase.LOADING_SERVICES
        _statusMessage.value = "Loading services..."

        var attempts = 0
        val maxAttempts = 300 // 60 seconds max (300 * 200ms)
        var healthyCount = 0
        var lastOnline = 0

        while (attempts < maxAttempts && currentCoroutineContext().isActive) {
            // Fast polling (200ms) to catch rapid service startup
            delay(200)

            // Get service count - on Android this reads from logcat-updated PythonRuntime.servicesOnline
            val statusResult = pythonRuntime.getServicesStatus()
            if (statusResult.isSuccess) {
                val (online, total) = statusResult.getOrNull() ?: (0 to 22)

                // Only log when count changes
                if (online != lastOnline) {
                    PlatformLogger.i(TAG, "[STARTUP][SERVICE] Service $online/$total started")
                    lastOnline = online
                }

                _servicesOnline.value = online
                _totalServices.value = total
                _statusMessage.value = "$online / $total services"

                // All services online - we're done!
                if (online == total && online > 0) {
                    PlatformLogger.i(TAG, "[STARTUP][SERVICE] All $total services started")
                    showReadyAndComplete()
                    return
                }
            }

            // Check health every 10 polls (2 seconds)
            if (attempts % 10 == 0) {
                val healthResult = pythonRuntime.checkHealth()
                if (healthResult.isSuccess && healthResult.getOrNull() == true) {
                    healthyCount++

                    val (online, total) = statusResult.getOrNull() ?: (0 to 22)

                    // First-run mode - 10 minimal services ready
                    if (online >= 10 && healthyCount >= 3) {
                        _phase.value = StartupPhase.READY
                        _statusMessage.value = "Setup required"
                        return
                    }

                    // Fallback - server healthy for a while
                    if (healthyCount >= 5) {
                        showReadyAndComplete()
                        return
                    }
                }
            }

            attempts++
        }

        // Timeout - but if server was healthy, proceed anyway
        if (healthyCount > 0) {
            showReadyAndComplete()
            return
        }

        throw Exception("Timeout waiting for services (${_servicesOnline.value}/${_totalServices.value} online)")
    }

    /**
     * Show "Agent Runtime Ready!" briefly before completing startup
     * Populates all lights to show successful connection
     */
    private suspend fun showReadyAndComplete() {
        // Ensure all lights are populated for visual feedback
        _prepStepsCompleted.value = TOTAL_PREP_STEPS
        _verifyStepsCompleted.value = TOTAL_VERIFY_STEPS
        if (_servicesOnline.value == 0) {
            // If telemetry not available (requires auth), show all services as ready
            _servicesOnline.value = _totalServices.value
        }

        _statusMessage.value = "Agent Runtime Ready!"
        PlatformLogger.i(TAG, "[STARTUP] Agent Runtime Ready! - displaying for 1.2s")
        delay(1200) // Brief pause to show ready state BEFORE transitioning
        _phase.value = StartupPhase.READY
    }

    /**
     * Update the current startup phase
     */
    fun setPhase(phase: StartupPhase) {
        val oldPhase = _phase.value
        _phase.value = phase
        _statusMessage.value = phase.displayName
        PlatformLogger.i(TAG, "[STARTUP][PHASE] $oldPhase -> $phase (${phase.displayName})")
    }

    /**
     * Update status message for debugging (visible on startup screen).
     * Use this to show token validation/exchange progress.
     */
    fun setStatus(message: String) {
        PlatformLogger.i(TAG, "[STARTUP][STATUS] $message")
        _statusMessage.value = message
    }

    /**
     * Called when a prep step completes (pydantic/native lib setup)
     */
    fun onPrepStepCompleted(step: Int) {
        if (step < 1 || step > TOTAL_PREP_STEPS) {
            PlatformLogger.w(TAG, "[STARTUP][PREP] Invalid step: $step (expected 1-$TOTAL_PREP_STEPS)")
            return
        }

        // Set phase to PREPARING on first prep step
        if (_prepStepsCompleted.value == 0) {
            setPhase(StartupPhase.PREPARING)
        }

        _prepStepsCompleted.value = step
        _statusMessage.value = "Preparing environment... $step/$TOTAL_PREP_STEPS"
        PlatformLogger.i(TAG, "[STARTUP][PREP] Step $step/$TOTAL_PREP_STEPS complete")

        // When all prep steps complete
        if (step >= TOTAL_PREP_STEPS) {
            PlatformLogger.i(TAG, "[STARTUP][PREP] All prep steps complete, transitioning to STARTING_SERVER")
            setPhase(StartupPhase.STARTING_SERVER)
            _statusMessage.value = "Environment ready"
        }
    }

    // Track verify phase (1 or 2) for calculating total steps
    private var _currentVerifyPhase = 1
    private var _phase1StepsCompleted = 0
    private var _phase2StepsCompleted = 0

    /**
     * Called when a CIRISVerify phase completes
     * Phase 1: 5 steps (parallel manifest fetch + validation)
     * Phase 2: 6 steps (sequential integrity checks)
     */
    fun onVerifyStepCompleted(step: Int) {
        if (step < 1 || step > TOTAL_VERIFY_STEPS) {
            PlatformLogger.w(TAG, "[STARTUP][VERIFY] Invalid step: $step (expected 1-$TOTAL_VERIFY_STEPS)")
            return
        }

        // Set phase to VERIFYING on first verify step
        if (_verifyStepsCompleted.value == 0) {
            PlatformLogger.i(TAG, "[STARTUP][VERIFY] Starting verification phase")
            setPhase(StartupPhase.VERIFYING)
        }

        _verifyStepsCompleted.value = step
        _statusMessage.value = "Verifying integrity... $step/$TOTAL_VERIFY_STEPS"
        PlatformLogger.i(TAG, "[STARTUP][VERIFY] Step $step/$TOTAL_VERIFY_STEPS complete")

        // When all verify steps complete
        if (step >= TOTAL_VERIFY_STEPS) {
            PlatformLogger.i(TAG, "[STARTUP][VERIFY] All verify steps complete - integrity verified")
            _statusMessage.value = "Integrity verified"
        }
    }

    /**
     * Parse VERIFY log messages from ciris-verify v1.1.5+
     * Call this for each log line from Python stdout/logcat
     *
     * Log format:
     *   VERIFY STEP {n}/{total} COMPLETE: {OK|FAILED|SKIP} ({details})
     *   VERIFY PHASE {n}/{total} COMPLETE: {description}
     *   VERIFY ATTESTATION COMPLETE: level={0-5}, valid={bool}, checks={n}/{m}
     */
    fun onVerifyLogMessage(message: String) {
        // Log all VERIFY messages for debugging
        if (message.contains("VERIFY", ignoreCase = true)) {
            PlatformLogger.d(TAG, "[STARTUP][VERIFY_LOG] $message")
        }

        // Check for step completion
        VERIFY_STEP_PATTERN.find(message)?.let { match ->
            val (stepNum, total, status) = match.destructured
            if (status == "COMPLETE") {
                // Phase 1 has 5 steps, Phase 2 has 6 steps
                val stepInt = stepNum.toIntOrNull() ?: return
                val totalInt = total.toIntOrNull() ?: return

                if (totalInt == 5) {
                    // Phase 1 step completed
                    _phase1StepsCompleted = maxOf(_phase1StepsCompleted, stepInt)
                    _verifyStepsCompleted.value = _phase1StepsCompleted
                } else if (totalInt == 6) {
                    // Phase 2 step completed
                    _phase2StepsCompleted = maxOf(_phase2StepsCompleted, stepInt)
                    _verifyStepsCompleted.value = 5 + _phase2StepsCompleted
                }

                _statusMessage.value = "Verifying... ${_verifyStepsCompleted.value}/$TOTAL_VERIFY_STEPS"
                PlatformLogger.d(TAG, "Verify step: ${_verifyStepsCompleted.value}/$TOTAL_VERIFY_STEPS")
            } else if (status == "STARTING" && _verifyStepsCompleted.value == 0) {
                // First step starting - enter VERIFYING phase
                setPhase(StartupPhase.VERIFYING)
            }
            return
        }

        // Check for phase completion
        VERIFY_PHASE_PATTERN.find(message)?.let { match ->
            val (phaseNum, _, status) = match.destructured
            if (status == "COMPLETE") {
                _currentVerifyPhase = (phaseNum.toIntOrNull() ?: 1) + 1
                PlatformLogger.d(TAG, "Verify phase $phaseNum complete, moving to phase $_currentVerifyPhase")
            }
            return
        }

        // Check for attestation complete
        VERIFY_COMPLETE_PATTERN.find(message)?.let { match ->
            val (level, valid, passed, total) = match.destructured
            _verifyStepsCompleted.value = TOTAL_VERIFY_STEPS
            _statusMessage.value = "Attestation: Level $level ($passed/$total checks)"
            PlatformLogger.i(TAG, "Attestation complete: level=$level, valid=$valid, checks=$passed/$total")
        }
    }

    /**
     * Called when a service starts
     */
    fun onServiceStarted(serviceNum: Int) {
        if (serviceNum < 1 || serviceNum > _totalServices.value) {
            PlatformLogger.w(TAG, "[STARTUP][SERVICE] Invalid service num: $serviceNum (expected 1-${_totalServices.value})")
            return
        }

        // Set phase to LOADING_SERVICES on first service
        if (_servicesOnline.value == 0) {
            PlatformLogger.i(TAG, "[STARTUP][SERVICE] Starting services phase")
            setPhase(StartupPhase.LOADING_SERVICES)
        }

        _servicesOnline.value = serviceNum
        _statusMessage.value = "Starting services... $serviceNum/${_totalServices.value}"
        PlatformLogger.i(TAG, "[STARTUP][SERVICE] Service $serviceNum/${_totalServices.value} started")

        // When all services are ready, update status but don't set READY phase directly.
        // waitForServices() handles the READY transition with proper delay.
        if (serviceNum >= _totalServices.value) {
            PlatformLogger.i(TAG, "[STARTUP][SERVICE] All ${_totalServices.value} services started")
            _statusMessage.value = "All ${_totalServices.value} services ready"
        }
    }

    /**
     * Called when an error is detected
     */
    fun onErrorDetected(error: String) {
        if (_hasError.value) return // Already in error state

        PlatformLogger.e(TAG, "[STARTUP][ERROR] Error detected: $error")
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
        _verifyStepsCompleted.value = 0
        _currentVerifyPhase = 1
        _phase1StepsCompleted = 0
        _phase2StepsCompleted = 0
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
    VERIFYING("VERIFYING INTEGRITY"),
    STARTING_SERVER("STARTING BACKEND"),
    WAITING_SERVER("WAITING FOR BACKEND"),
    LOADING_SERVICES("LOADING SERVICES"),
    CHECKING_CONFIG("CHECKING CONFIG"),
    FIRST_RUN_SETUP("FIRST-TIME SETUP"),
    AUTHENTICATING("AUTHENTICATING"),
    READY("READY"),
    ERROR("ERROR")
}
