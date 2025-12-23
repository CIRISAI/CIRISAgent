package ai.ciris.mobile.shared.viewmodels

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PythonRuntime
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
 */
class FakePythonRuntime(
    var initSuccess: Boolean = true,
    var serverSuccess: Boolean = true,
    var healthy: Boolean = false,
    var servicesOnline: Int = 0,
    private val servicesTotal: Int = 22
) : PythonRuntime() {

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
}

/**
 * Fake Python runtime that simulates gradual service startup
 */
class FakePythonRuntimeGradual : PythonRuntime() {
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
}

/**
 * Fake API client for testing
 */
class FakeCIRISApiClient : CIRISApiClient("http://localhost:8080", "test-token")
