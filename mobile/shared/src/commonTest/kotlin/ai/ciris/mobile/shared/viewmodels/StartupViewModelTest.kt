package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClientProtocol
import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.PythonRuntimeProtocol
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.*
import kotlin.test.*

@OptIn(ExperimentalCoroutinesApi::class)
class StartupViewModelTest {

    private val testDispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setup() {
        Dispatchers.setMain(testDispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    @Test
    fun startCIRIS_successfulStartup_phasesCorrectOrder() = runTest {
        val mockRuntime = FakePythonRuntime(
            initSuccess = true,
            serverSuccess = true,
            healthy = true,
            servicesOnline = 22
        )
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient, "/test/python")

        viewModel.startCIRIS()
        advanceUntilIdle()

        // Should reach READY state
        assertEquals(StartupPhase.READY, viewModel.phase.value)
        assertEquals(22, viewModel.servicesOnline.value)
        assertEquals(22, viewModel.totalServices.value)
        assertNull(viewModel.errorMessage.value)
        assertTrue(viewModel.statusMessage.value.contains("ready", ignoreCase = true))
    }

    @Test
    fun startCIRIS_pythonInitFails_showsError() = runTest {
        val mockRuntime = FakePythonRuntime(initSuccess = false)
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        viewModel.startCIRIS()
        advanceUntilIdle()

        assertEquals(StartupPhase.ERROR, viewModel.phase.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("Python", ignoreCase = true))
    }

    @Test
    fun startCIRIS_serverStartFails_showsError() = runTest {
        val mockRuntime = FakePythonRuntime(
            initSuccess = true,
            serverSuccess = false
        )
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        viewModel.startCIRIS()
        advanceUntilIdle()

        assertEquals(StartupPhase.ERROR, viewModel.phase.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("server", ignoreCase = true))
    }

    @Test
    fun startCIRIS_servicesNeverReady_showsTimeoutError() = runTest {
        val mockRuntime = FakePythonRuntime(
            initSuccess = true,
            serverSuccess = true,
            healthy = true,
            servicesOnline = 15 // Never reaches 22
        )
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        viewModel.startCIRIS()
        advanceUntilIdle()

        assertEquals(StartupPhase.ERROR, viewModel.phase.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("Timeout", ignoreCase = true))
        assertEquals(15, viewModel.servicesOnline.value)
    }

    @Test
    fun startCIRIS_servicesGraduallyOnline_updatesCount() = runTest {
        val mockRuntime = FakePythonRuntimeGradual()
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        viewModel.startCIRIS()

        // Let it run for a few iterations
        repeat(5) {
            advanceTimeBy(2000)
            runCurrent()
        }

        // Services should be increasing
        assertTrue(viewModel.servicesOnline.value > 0)
        assertTrue(viewModel.servicesOnline.value <= 22)
    }

    @Test
    fun retry_afterError_resetsState() = runTest {
        val mockRuntime = FakePythonRuntime(initSuccess = false)
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        // First attempt fails
        viewModel.startCIRIS()
        advanceUntilIdle()
        assertEquals(StartupPhase.ERROR, viewModel.phase.value)

        // Make runtime succeed this time
        mockRuntime.initSuccess = true
        mockRuntime.serverSuccess = true
        mockRuntime.healthy = true
        mockRuntime.servicesOnline = 22

        // Retry
        viewModel.retry()
        advanceUntilIdle()

        // Should succeed now
        assertEquals(StartupPhase.READY, viewModel.phase.value)
        assertNull(viewModel.errorMessage.value)
    }

    @Test
    fun startCIRIS_elapsedTimeIncreases() = runTest {
        val mockRuntime = FakePythonRuntime(
            initSuccess = true,
            serverSuccess = true,
            healthy = true,
            servicesOnline = 22
        )
        val mockApiClient = FakeCIRISApiClient()
        val viewModel = StartupViewModel(mockRuntime, mockApiClient)

        viewModel.startCIRIS()

        // Advance time
        repeat(3) {
            advanceTimeBy(1000)
            runCurrent()
        }

        // Elapsed time should have increased
        assertTrue(viewModel.elapsedSeconds.value > 0)
    }
}

/**
 * Fake Python runtime for testing
 * Implements PythonRuntimeProtocol interface for testability
 */
class FakePythonRuntime(
    var initSuccess: Boolean = true,
    var serverSuccess: Boolean = true,
    var healthy: Boolean = false,
    var servicesOnline: Int = 0,
    private val servicesTotal: Int = 22
) : PythonRuntimeProtocol {

    private var initialized = false
    private var started = false

    override suspend fun initialize(pythonHome: String): Result<Unit> {
        delay(100) // Simulate initialization time
        return if (initSuccess) {
            initialized = true
            Result.success(Unit)
        } else {
            Result.failure(Exception("Failed to initialize Python"))
        }
    }

    override suspend fun startServer(): Result<String> {
        delay(100) // Simulate server startup
        return if (serverSuccess && initialized) {
            started = true
            Result.success("http://localhost:8080")
        } else {
            Result.failure(Exception("Failed to start server"))
        }
    }

    override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> {
        onStatus?.invoke("Starting server...")
        return startServer()
    }

    override fun injectPythonConfig(config: Map<String, String>) {
        // No-op for testing
    }

    override suspend fun checkHealth(): Result<Boolean> {
        delay(50) // Simulate network delay
        return Result.success(healthy && started)
    }

    override suspend fun getServicesStatus(): Result<Pair<Int, Int>> {
        delay(50)
        return Result.success(servicesOnline to servicesTotal)
    }

    override fun shutdown() {
        started = false
    }

    override fun isInitialized(): Boolean = initialized

    override fun isServerStarted(): Boolean = started

    override val serverUrl: String = "http://localhost:8080"
}

/**
 * Fake Python runtime that simulates gradual service startup
 * Implements PythonRuntimeProtocol interface for testability
 */
class FakePythonRuntimeGradual : PythonRuntimeProtocol {
    private var initialized = false
    private var started = false
    private var checkCount = 0

    override suspend fun initialize(pythonHome: String): Result<Unit> {
        initialized = true
        return Result.success(Unit)
    }

    override suspend fun startServer(): Result<String> {
        started = true
        return Result.success("http://localhost:8080")
    }

    override suspend fun startPythonServer(onStatus: ((String) -> Unit)?): Result<String> {
        onStatus?.invoke("Starting server...")
        return startServer()
    }

    override fun injectPythonConfig(config: Map<String, String>) {
        // No-op for testing
    }

    override suspend fun checkHealth(): Result<Boolean> {
        return Result.success(started)
    }

    override suspend fun getServicesStatus(): Result<Pair<Int, Int>> {
        // Simulate gradual service startup
        // 0 → 5 → 10 → 15 → 20 → 22
        checkCount++
        val online = minOf(checkCount * 5, 22)
        return Result.success(online to 22)
    }

    override fun shutdown() {
        started = false
    }

    override fun isInitialized(): Boolean = initialized
    override fun isServerStarted(): Boolean = started
    override val serverUrl: String = "http://localhost:8080"
}

/**
 * Fake API client for testing
 * Implements CIRISApiClientProtocol interface for testability
 */
class FakeCIRISApiClient : CIRISApiClientProtocol {
    private var token: String? = null

    override fun setAccessToken(token: String) {
        this.token = token
    }

    override suspend fun sendMessage(message: String, channelId: String): InteractResponse {
        return InteractResponse(response = "Test response", message_id = "test-id")
    }

    override suspend fun getMessages(limit: Int): List<ChatMessage> {
        return emptyList()
    }

    override suspend fun getSystemStatus(): SystemStatus {
        return SystemStatus(
            status = "healthy",
            cognitive_state = "WORK",
            services_online = 22,
            services_total = 22
        )
    }

    override suspend fun getTelemetry(): TelemetryResponse {
        return TelemetryResponse(
            agent_id = "test-agent",
            uptime_seconds = 100.0,
            cognitive_state = "WORK",
            services_online = 22,
            services_total = 22,
            services = emptyMap()
        )
    }

    override suspend fun login(username: String, password: String): AuthResponse {
        return AuthResponse(
            access_token = "test-token",
            token_type = "bearer",
            user = UserInfo(user_id = "test-user", email = "test@example.com")
        )
    }

    override suspend fun googleAuth(idToken: String, userId: String?): AuthResponse {
        return AuthResponse(
            access_token = "test-token",
            token_type = "bearer",
            user = UserInfo(user_id = "test-user", email = "test@example.com")
        )
    }

    override suspend fun logout() {
        token = null
    }

    override suspend fun initiateShutdown() {
        // No-op for testing
    }

    override suspend fun emergencyShutdown() {
        // No-op for testing
    }

    override suspend fun getSetupStatus(): SetupStatusResponse {
        return SetupStatusResponse(
            data = SetupStatusData(setup_required = false, has_env_file = true, has_admin_user = true)
        )
    }

    override suspend fun completeSetup(request: CompleteSetupRequest): SetupCompletionResult {
        return SetupCompletionResult(success = true, message = "Setup complete")
    }

    override fun close() {
        // No-op for testing
    }
}
