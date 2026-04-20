package ai.ciris.mobile.shared.viewmodels

import ai.ciris.api.models.DocumentPayload
import ai.ciris.api.models.ImagePayload
import ai.ciris.mobile.shared.PurchaseError
import ai.ciris.mobile.shared.PurchaseResultType
import ai.ciris.mobile.shared.api.*
import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.ui.screens.CreditProduct
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.*
import kotlin.test.*

@OptIn(ExperimentalCoroutinesApi::class)
class BillingViewModelTest {

    private val testDispatcher = StandardTestDispatcher()

    @BeforeTest
    fun setup() {
        Dispatchers.setMain(testDispatcher)
    }

    @AfterTest
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun createViewModel(
        apiClient: FakeCIRISApiClientForBilling = FakeCIRISApiClientForBilling()
    ): BillingViewModel {
        return BillingViewModel(apiClient)
    }

    // --- loadBalance tests ---

    @Test
    fun loadBalance_success_updatesBalance() = runTest {
        val apiClient = FakeCIRISApiClientForBilling(
            creditStatus = CreditStatusData(
                hasCredit = true,
                creditsRemaining = 50,
                freeUsesRemaining = 10,
                dailyFreeUsesRemaining = 5,
                totalUses = 100,
                planName = "basic",
                purchaseRequired = false
            )
        )
        val viewModel = createViewModel(apiClient)

        viewModel.loadBalance()
        advanceUntilIdle()

        assertEquals(65, viewModel.currentBalance.value) // 50 + 10 + 5
        assertNull(viewModel.errorMessage.value)
        assertFalse(viewModel.isByokMode.value)
    }

    @Test
    fun loadBalance_byokMode_showsUnlimited() = runTest {
        val apiClient = FakeCIRISApiClientForBilling(
            creditStatus = CreditStatusData(
                hasCredit = true,
                creditsRemaining = 0,
                freeUsesRemaining = 0,
                dailyFreeUsesRemaining = 0,
                totalUses = 0,
                planName = "unlimited",
                purchaseRequired = false
            )
        )
        val viewModel = createViewModel(apiClient)

        viewModel.loadBalance()
        advanceUntilIdle()

        assertTrue(viewModel.isByokMode.value)
        assertEquals(-1, viewModel.currentBalance.value) // -1 means unlimited
        assertNull(viewModel.errorMessage.value)
    }

    @Test
    fun loadBalance_networkError_showsErrorMessage() = runTest {
        val apiClient = FakeCIRISApiClientForBilling(
            getCreditsException = Exception("Connection refused")
        )
        val viewModel = createViewModel(apiClient)

        viewModel.loadBalance()
        advanceUntilIdle()

        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("Connection refused"))
        assertEquals(-1, viewModel.currentBalance.value)
    }

    @Test
    fun loadBalance_401Error_triggersRetry() = runTest {
        // First call throws 401, second succeeds
        val apiClient = FakeCIRISApiClientForBilling(
            getCreditsException = Exception("HTTP 401 Unauthorized")
        )
        val viewModel = createViewModel(apiClient)

        viewModel.loadBalance()
        // Advance past the initial call
        advanceTimeBy(100)
        runCurrent()

        // After 401, it should trigger retry after delay
        // Change the mock to succeed on retry
        apiClient.getCreditsException = null
        apiClient.creditStatus = CreditStatusData(
            hasCredit = true,
            creditsRemaining = 100,
            freeUsesRemaining = 0,
            dailyFreeUsesRemaining = 0,
            totalUses = 10,
            planName = "basic",
            purchaseRequired = false
        )

        // Advance past the 2000ms delay
        advanceTimeBy(3000)
        advanceUntilIdle()

        // Should have retried and succeeded
        assertEquals(100, viewModel.currentBalance.value)
        assertNull(viewModel.errorMessage.value)
    }

    @Test
    fun loadBalance_401Error_retryAlsoFails_showsError() = runTest {
        // Both calls throw 401 — should show error after retry exhausted
        val apiClient = FakeCIRISApiClientForBilling(
            getCreditsException = Exception("HTTP 401 Unauthorized")
        )
        val viewModel = createViewModel(apiClient)

        viewModel.loadBalance()
        advanceTimeBy(5000) // Past both attempt + retry delay
        advanceUntilIdle()

        // Should show error after retry fails
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("401"))
    }

    // --- Purchase flow tests ---

    @Test
    fun onProductSelected_byokMode_showsError() = runTest {
        val apiClient = FakeCIRISApiClientForBilling(
            creditStatus = CreditStatusData(
                hasCredit = true, creditsRemaining = 0, freeUsesRemaining = 0,
                dailyFreeUsesRemaining = 0, totalUses = 0,
                planName = "unlimited", purchaseRequired = false
            )
        )
        val viewModel = createViewModel(apiClient)
        viewModel.loadBalance()
        advanceUntilIdle()

        var callbackInvoked = false
        val product = CreditProduct("test", 100, "$9.99", "Test product")
        viewModel.onProductSelected(product) { callbackInvoked = true }

        assertFalse(callbackInvoked)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("BYOK", ignoreCase = true))
    }

    @Test
    fun onProductSelected_alreadyPurchasing_ignores() = runTest {
        val viewModel = createViewModel()
        val product = CreditProduct("test", 100, "$9.99", "Test product")

        // Simulate purchase in progress
        viewModel.onPurchaseStarted("test")

        var callbackCount = 0
        viewModel.onProductSelected(product) { callbackCount++ }

        assertEquals(0, callbackCount)
    }

    @Test
    fun onProductSelected_normal_callsOnPurchaseReady() = runTest {
        val viewModel = createViewModel()
        val product = CreditProduct("test", 100, "$9.99", "Test product")

        var readyProduct: CreditProduct? = null
        viewModel.onProductSelected(product) { readyProduct = it }

        assertNotNull(readyProduct)
        assertEquals("test", readyProduct!!.productId)
    }

    // --- handlePurchaseResult tests ---

    @Test
    fun handlePurchaseResult_success_updatesBalance() = runTest {
        // Set fake to return 200 credits so background refresh matches
        val apiClient = FakeCIRISApiClientForBilling(
            creditStatus = CreditStatusData(
                hasCredit = true, creditsRemaining = 200, freeUsesRemaining = 0,
                dailyFreeUsesRemaining = 0, totalUses = 10,
                planName = "basic", purchaseRequired = false
            )
        )
        val viewModel = createViewModel(apiClient)
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(
            PurchaseResultType.Success(creditsAdded = 100, newBalance = 200)
        )
        advanceUntilIdle()

        assertEquals(200, viewModel.currentBalance.value)
        assertFalse(viewModel.isPurchasing.value)
        assertNotNull(viewModel.successMessage.value)
        assertTrue(viewModel.successMessage.value!!.contains("100"))
    }

    @Test
    fun handlePurchaseResult_cancelled_clearsState() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(PurchaseResultType.Cancelled)

        assertFalse(viewModel.isPurchasing.value)
        assertNull(viewModel.errorMessage.value)
    }

    @Test
    fun handlePurchaseResult_authExpired_showsRetryMessage() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(
            PurchaseResultType.Error("auth_expired", PurchaseError.TokenExpired())
        )

        assertFalse(viewModel.isPurchasing.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("expired", ignoreCase = true))
    }

    @Test
    fun handlePurchaseResult_authRequired_showsSignInMessage() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(
            PurchaseResultType.Error("No auth", PurchaseError.AuthRequired())
        )

        assertFalse(viewModel.isPurchasing.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("sign in", ignoreCase = true))
    }

    @Test
    fun handlePurchaseResult_serverError_showsServerMessage() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(
            PurchaseResultType.Error("Server error: 500", PurchaseError.ServerError(500, "Internal error"))
        )

        assertFalse(viewModel.isPurchasing.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("500"))
    }

    @Test
    fun handlePurchaseResult_networkError_showsNetworkMessage() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(
            PurchaseResultType.Error("timed out", PurchaseError.NetworkError("Connection timed out"))
        )

        assertFalse(viewModel.isPurchasing.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("network", ignoreCase = true) ||
            viewModel.errorMessage.value!!.contains("connection", ignoreCase = true))
    }

    @Test
    fun handlePurchaseResult_storeError_showsStoreMessage() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(
            PurchaseResultType.Error("Product not found", PurchaseError.StoreError("Product not found"))
        )

        assertFalse(viewModel.isPurchasing.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("Product not found"))
    }

    @Test
    fun handlePurchaseResult_untypedError_fallsBackToGeneric() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseStarted("test")

        viewModel.handlePurchaseResult(
            PurchaseResultType.Error("Something went wrong", errorType = null)
        )

        assertFalse(viewModel.isPurchasing.value)
        assertNotNull(viewModel.errorMessage.value)
        assertTrue(viewModel.errorMessage.value!!.contains("Something went wrong"))
    }

    // --- Formatting tests ---

    @Test
    fun getFormattedBalance_byok_showsUnlimited() = runTest {
        val apiClient = FakeCIRISApiClientForBilling(
            creditStatus = CreditStatusData(
                hasCredit = true, creditsRemaining = 0, freeUsesRemaining = 0,
                dailyFreeUsesRemaining = 0, totalUses = 0,
                planName = "unlimited", purchaseRequired = false
            )
        )
        val viewModel = createViewModel(apiClient)
        viewModel.loadBalance()
        advanceUntilIdle()

        val formatted = viewModel.getFormattedBalance()
        assertTrue(formatted.contains("Unlimited", ignoreCase = true))
    }

    @Test
    fun getFormattedBalance_negative_showsSignIn() = runTest {
        val viewModel = createViewModel()
        // Default balance is -1 (not loaded)

        val formatted = viewModel.getFormattedBalance()
        assertTrue(formatted.contains("Sign in", ignoreCase = true))
    }

    @Test
    fun getFormattedBalance_positive_showsCredits() = runTest {
        val apiClient = FakeCIRISApiClientForBilling(
            creditStatus = CreditStatusData(
                hasCredit = true, creditsRemaining = 42, freeUsesRemaining = 0,
                dailyFreeUsesRemaining = 0, totalUses = 10,
                planName = "basic", purchaseRequired = false
            )
        )
        val viewModel = createViewModel(apiClient)
        viewModel.loadBalance()
        advanceUntilIdle()

        val formatted = viewModel.getFormattedBalance()
        assertTrue(formatted.contains("42"))
        assertTrue(formatted.contains("credits", ignoreCase = true))
    }

    // --- Clear tests ---

    @Test
    fun clearError_removesErrorMessage() = runTest {
        val viewModel = createViewModel()
        viewModel.onPurchaseError("test error")
        assertNotNull(viewModel.errorMessage.value)

        viewModel.clearError()
        assertNull(viewModel.errorMessage.value)
    }

    @Test
    fun clearSuccess_removesSuccessMessage() = runTest {
        val viewModel = createViewModel()
        viewModel.handlePurchaseResult(
            PurchaseResultType.Success(creditsAdded = 10, newBalance = 20)
        )
        advanceUntilIdle()
        assertNotNull(viewModel.successMessage.value)

        viewModel.clearSuccess()
        assertNull(viewModel.successMessage.value)
    }

    // --- Credit breakdown test ---

    @Test
    fun getCreditBreakdown_returnsCorrectValues() = runTest {
        val apiClient = FakeCIRISApiClientForBilling(
            creditStatus = CreditStatusData(
                hasCredit = true, creditsRemaining = 50, freeUsesRemaining = 10,
                dailyFreeUsesRemaining = 5, totalUses = 200,
                planName = "premium", purchaseRequired = false
            )
        )
        val viewModel = createViewModel(apiClient)
        viewModel.loadBalance()
        advanceUntilIdle()

        val breakdown = viewModel.getCreditBreakdown()
        assertEquals(50, breakdown.paidCredits)
        assertEquals(10, breakdown.freeUses)
        assertEquals(5, breakdown.dailyFreeUses)
        assertEquals(200, breakdown.totalUses)
        assertEquals("premium", breakdown.planName)
        assertEquals(65, breakdown.total)
    }
}

/**
 * Fake API client for billing tests.
 * Implements CIRISApiClientProtocol with configurable getCredits() behavior.
 * Only getCredits() is meaningfully implemented since BillingViewModel only uses that.
 */
class FakeCIRISApiClientForBilling(
    var creditStatus: CreditStatusData = CreditStatusData(
        hasCredit = true,
        creditsRemaining = 100,
        freeUsesRemaining = 10,
        dailyFreeUsesRemaining = 5,
        totalUses = 50,
        planName = "Test Plan",
        purchaseRequired = false
    ),
    var getCreditsException: Exception? = null
) : CIRISApiClientProtocol {

    var getCreditsCallCount = 0
        private set

    override suspend fun getCredits(): CreditStatusData {
        getCreditsCallCount++
        getCreditsException?.let { throw it }
        return creditStatus
    }

    // Stub implementations — not used by BillingViewModel
    override fun setAccessToken(token: String) {}
    override suspend fun sendMessage(message: String, channelId: String, images: List<ImagePayload>?, documents: List<DocumentPayload>?): InteractResponse =
        InteractResponse(response = "", message_id = "")
    override suspend fun getMessages(limit: Int): List<ChatMessage> = emptyList()
    override suspend fun getSystemStatus(): SystemStatus =
        SystemStatus(status = "healthy", cognitive_state = "WORK", services_online = 22, services_total = 22)
    override suspend fun getTelemetry(): TelemetryResponse =
        TelemetryResponse(data = TelemetryData(agent_id = "", uptime_seconds = 0.0, cognitive_state = "WORK", services_online = 0, services_total = 0, services = emptyMap()))
    override suspend fun login(username: String, password: String): AuthResponse =
        AuthResponse(access_token = "test", token_type = "bearer", user = UserInfo(user_id = "test", email = "test@test.com"))
    override suspend fun googleAuth(idToken: String, userId: String?): AuthResponse =
        AuthResponse(access_token = "test", token_type = "bearer", user = UserInfo(user_id = "test", email = "test@test.com"))
    override suspend fun appleAuth(idToken: String, userId: String?): AuthResponse =
        AuthResponse(access_token = "test", token_type = "bearer", user = UserInfo(user_id = "test", email = "test@test.com"))
    override suspend fun logout() {}
    override suspend fun initiateShutdown() {}
    override suspend fun emergencyShutdown() {}
    override suspend fun getSetupStatus(): SetupStatusResponse =
        SetupStatusResponse(data = SetupStatusData(setup_required = false, has_env_file = true, has_admin_user = true))
    override suspend fun completeSetup(request: CompleteSetupRequest): SetupCompletionResult =
        SetupCompletionResult(success = true, message = "ok")
    override suspend fun nativeAuth(idToken: String, userId: String?, provider: String): AuthResponse =
        AuthResponse(access_token = "test", token_type = "bearer", user = UserInfo(user_id = "test", email = "test@test.com"))
    override suspend fun transitionCognitiveState(targetState: String, reason: String?): StateTransitionResult =
        StateTransitionResult(success = true, message = "ok", currentState = targetState, previousState = "WORK")
    override suspend fun getLlmConfig(): LlmConfigData =
        LlmConfigData(provider = "mock", baseUrl = null, model = "mock", apiKeySet = false, isCirisProxy = true, backupBaseUrl = null, backupModel = null, backupApiKeySet = false)
    override suspend fun listAdapters(): AdaptersListData =
        AdaptersListData(adapters = emptyList(), totalCount = 0, runningCount = 0)
    override suspend fun reloadAdapter(adapterId: String): AdapterActionData =
        AdapterActionData(adapterId = adapterId, success = true, message = "ok")
    override suspend fun removeAdapter(adapterId: String): AdapterActionData =
        AdapterActionData(adapterId = adapterId, success = true, message = "ok")
    override suspend fun getServices(): ServicesResponse =
        ServicesResponse(globalServices = emptyMap(), handlers = emptyMap())
    override suspend fun getRuntimeState(): RuntimeStateResponse =
        RuntimeStateResponse(processorState = "RUNNING", cognitiveState = "WORK", queueDepth = 0, activeTasks = emptyList())
    override suspend fun pauseRuntime(): RuntimeControlResponse =
        RuntimeControlResponse(processorState = "PAUSED", message = "ok")
    override suspend fun resumeRuntime(): RuntimeControlResponse =
        RuntimeControlResponse(processorState = "RUNNING", message = "ok")
    override suspend fun singleStepProcessor(): SingleStepResponse =
        SingleStepResponse(stepPoint = "test", message = "ok", processingTimeMs = 0L, tokensUsed = 0)
    override suspend fun getContextEnrichment(): ContextEnrichmentResponse =
        ContextEnrichmentResponse(
            entries = emptyMap(),
            stats = EnrichmentCacheStatsData(
                entries = 0, hits = 0, misses = 0,
                hitRatePct = 0.0, startupPopulated = false,
            ),
        )
    override suspend fun queryEnvironmentItems(): List<EnvironmentGraphNodeData> = emptyList()
    override suspend fun createEnvironmentItem(
        name: String,
        category: String,
        quantity: Int,
        condition: String,
        notes: String?,
    ): EnvironmentGraphNodeData = EnvironmentGraphNodeData(
        id = "stub",
        type = "environment",
        attributes = emptyMap(),
        createdAt = null,
        communityShared = false,
    )
    override suspend fun deleteEnvironmentItem(nodeId: String): Boolean = true
    override suspend fun getCountries(): CountriesResponse =
        CountriesResponse(countries = emptyList(), count = 0)
    override suspend fun searchLocations(
        query: String, countryCode: String?, limit: Int,
    ): LocationSearchResponse =
        LocationSearchResponse(results = emptyList(), query = query, count = 0)
    override suspend fun updateUserLocation(location: LocationResultData): UpdateLocationResult =
        UpdateLocationResult(success = true, message = "ok", locationDisplay = "")
    override suspend fun getCurrentLocation(): CurrentLocationData =
        CurrentLocationData(configured = false)
    override fun close() {}
}
