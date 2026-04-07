package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.LocalLocalization
import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.localization.currentLanguageInfo
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.viewmodels.SUPPORTED_LANGUAGES
import kotlinx.coroutines.delay
import ai.ciris.mobile.shared.platform.getDeviceDebugInfo
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.CIRISSignet
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.StartupPhase
import ai.ciris.mobile.shared.viewmodels.StartupViewModel
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * CIRIS startup screen with CIRIS signet, prep lights, and service lights
 * EXACTLY matches android/app/.../MainActivity.kt splash screen
 *
 * Shows:
 * - CIRIS signet logo (100dp, teal #419CA0)
 * - Phase indicator (10 phases: INITIALIZING -> READY)
 * - Elapsed time counter
 * - 6 prep lights for pydantic/native lib setup (12dp)
 * - Prep label showing progress (e.g., "Preparing Environment... 3/6")
 * - 22 service lights (2 rows of 11, 16dp each)
 * - Service count (e.g., "18/22 services online")
 * - Status messages during startup
 * - Error message with retry button (if any)
 *
 * Colors match Android exactly:
 * - Background: 0xFF1a1a2e (dark navy)
 * - Signet tint: 0xFF419CA0 (teal)
 * - Light off: 0xFF2a2a3e (dark gray)
 * - Light on: 0xFF00d4ff (cyan)
 * - Error: 0xFFff4444 (red)
 */
@Composable
fun StartupScreen(
    viewModel: StartupViewModel,
    modifier: Modifier = Modifier
) {
    val phase by viewModel.phase.collectAsState()
    val servicesOnline by viewModel.servicesOnline.collectAsState()
    val totalServices by viewModel.totalServices.collectAsState()
    val startedServiceSlots by viewModel.startedServiceSlots.collectAsState()
    val statusMessage by viewModel.statusMessage.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()
    val elapsedSeconds by viewModel.elapsedSeconds.collectAsState()
    val prepStepsCompleted by viewModel.prepStepsCompleted.collectAsState()
    val verifyStepsCompleted by viewModel.verifyStepsCompleted.collectAsState()
    val hasError by viewModel.hasError.collectAsState()
    val consolidatorStatus by viewModel.consolidatorStatus.collectAsState()

    // Language rotation for startup screen when no explicit language selection
    val localization = LocalLocalization.current
    val hasExplicitLanguage by localization?.hasExplicitLanguageSelection?.collectAsState()
        ?: remember { mutableStateOf(true) }
    var rotationLanguageIndex by remember { mutableStateOf(0) }

    // Get current language info (reactive - updates when language changes)
    val currentLangInfo = currentLanguageInfo()

    // Track if languages are preloaded for rotation
    var languagesPreloaded by remember { mutableStateOf(false) }

    // Preload all languages for smooth rotation on first launch
    LaunchedEffect(Unit) {
        localization?.preloadLanguages(SUPPORTED_LANGUAGES.map { it.code })
        languagesPreloaded = true
    }

    // Rotate through languages every 2.5 seconds during startup (visual effect)
    // Always rotate regardless of language selection - it's a startup animation
    // Stop rotation when startup completes (phase becomes READY or FIRST_RUN_SETUP)
    LaunchedEffect(languagesPreloaded, phase) {
        val shouldRotate = languagesPreloaded &&
            phase != StartupPhase.READY && phase != StartupPhase.FIRST_RUN_SETUP
        if (shouldRotate) {
            while (true) {
                delay(2500)
                rotationLanguageIndex = (rotationLanguageIndex + 1) % SUPPORTED_LANGUAGES.size
                val nextLang = SUPPORTED_LANGUAGES[rotationLanguageIndex]
                localization?.setTemporaryLanguage(nextLang.code)
            }
        }
    }

    // Reset to persisted language when startup completes (READY or going to interact)
    LaunchedEffect(phase) {
        if (phase == StartupPhase.READY || phase == StartupPhase.FIRST_RUN_SETUP) {
            localization?.resetToPersistedLanguage()
        }
    }

    // Auto-start CIRIS on mount
    LaunchedEffect(Unit) {
        if (phase == StartupPhase.INITIALIZING) {
            viewModel.startCIRIS()
        }
    }

    // Log light animation state changes
    LaunchedEffect(prepStepsCompleted) {
        PlatformLogger.i("StartupScreen", "[LIGHTS] Prep: $prepStepsCompleted/${StartupViewModel.TOTAL_PREP_STEPS}")
    }
    LaunchedEffect(verifyStepsCompleted) {
        PlatformLogger.i("StartupScreen", "[LIGHTS] Verify: $verifyStepsCompleted/${StartupViewModel.TOTAL_VERIFY_STEPS}")
    }
    LaunchedEffect(servicesOnline, startedServiceSlots) {
        PlatformLogger.i("StartupScreen", "[LIGHTS] Services: $servicesOnline/$totalServices, slots=${startedServiceSlots.sorted()}")
    }
    LaunchedEffect(phase) {
        PlatformLogger.i("StartupScreen", "[PHASE] $phase (${phase.displayName})")
    }

    Surface(
        modifier = modifier.fillMaxSize(),
        color = CIRISColors.BackgroundDark
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(24.dp),  // 24dp padding to match Android
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(0.dp, Alignment.CenterVertically)
        ) {
            // CIRIS Signet Logo (100dp like Android)
            CIRISSignet(
                modifier = Modifier
                    .size(100.dp)
                    .padding(bottom = 16.dp),
                tintColor = CIRISColors.SignetTeal
            )

            // Phase indicator
            Text(
                text = phase.displayName,
                fontSize = 12.sp,
                fontWeight = FontWeight.Normal,
                color = when (phase) {
                    StartupPhase.FIRST_RUN_SETUP -> CIRISColors.WarningYellow
                    StartupPhase.READY -> CIRISColors.SuccessGreen
                    StartupPhase.ERROR -> CIRISColors.ErrorRed
                    else -> CIRISColors.SignetTeal
                },
                letterSpacing = 0.15.sp,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            // Elapsed time (positioned right after phase like Android)
            Text(
                text = "${elapsedSeconds}.0s",
                fontSize = 10.sp,
                color = CIRISColors.TextDim,
                modifier = Modifier.padding(bottom = 24.dp)
            )

            // Prep lights row (6 lights for pydantic/native lib setup)
            PrepLightsRow(
                prepStepsCompleted = prepStepsCompleted,
                hasError = hasError,
                modifier = Modifier.padding(bottom = 8.dp)
            )

            // Prep label (above prep lights like Android)
            // Shows rotating languages if no explicit selection
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(bottom = 16.dp)
            ) {
                val prepText = if (prepStepsCompleted >= StartupViewModel.TOTAL_PREP_STEPS) {
                    localizedString("mobile.startup_environment_ready")
                } else if (prepStepsCompleted > 0) {
                    localizedString(
                        "mobile.startup_preparing_progress",
                        mapOf(
                            "current" to prepStepsCompleted.toString(),
                            "total" to StartupViewModel.TOTAL_PREP_STEPS.toString()
                        )
                    )
                } else {
                    localizedString("mobile.startup_preparing")
                }
                Text(
                    text = prepText,
                    fontSize = 10.sp,
                    color = if (prepStepsCompleted >= StartupViewModel.TOTAL_PREP_STEPS) {
                        CIRISColors.SuccessGreen
                    } else {
                        CIRISColors.TextDim
                    },
                    modifier = Modifier.padding(bottom = 4.dp)
                )

                // Show current language indicator during startup (always rotating)
                if (phase != StartupPhase.READY && phase != StartupPhase.FIRST_RUN_SETUP) {
                    Text(
                        text = currentLangInfo.nativeName,
                        fontSize = 9.sp,
                        color = CIRISColors.SignetTeal.copy(alpha = 0.7f),
                        modifier = Modifier.padding(top = 2.dp)
                    )
                }
            }

            // Verify lights row (11 steps: Phase 1 = 5, Phase 2 = 6)
            // Shown after prep completes, before services
            if (prepStepsCompleted >= StartupViewModel.TOTAL_PREP_STEPS) {
                VerifyLightsRow(
                    verifyStepsCompleted = verifyStepsCompleted,
                    hasError = hasError,
                    modifier = Modifier.padding(bottom = 8.dp)
                )

                // Verify label
                val verifyText = when {
                    verifyStepsCompleted >= StartupViewModel.TOTAL_VERIFY_STEPS ->
                        localizedString("mobile.startup_attestation_complete")
                    verifyStepsCompleted > 0 ->
                        localizedString(
                            "mobile.startup_attestation_progress",
                            mapOf(
                                "current" to verifyStepsCompleted.toString(),
                                "total" to StartupViewModel.TOTAL_VERIFY_STEPS.toString()
                            )
                        )
                    else -> localizedString("mobile.startup_attestation")
                }
                Text(
                    text = verifyText,
                    fontSize = 10.sp,
                    color = when {
                        verifyStepsCompleted >= StartupViewModel.TOTAL_VERIFY_STEPS -> CIRISColors.SuccessGreen
                        else -> CIRISColors.TextDim
                    },
                    modifier = Modifier.padding(bottom = 16.dp)
                )
            }

            // Services label (shown after verify completes or starts, above service lights)
            if (verifyStepsCompleted > 0 || servicesOnline > 0) {
                Text(
                    text = localizedString("mobile.startup_services"),
                    fontSize = 10.sp,
                    color = CIRISColors.TextDim,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            // Service lights grid (22 lights) - each light = specific service slot
            ServiceLightsGrid(
                startedServiceSlots = startedServiceSlots,
                totalServices = totalServices,
                hasError = hasError,
                modifier = Modifier.padding(bottom = 32.dp)
            )

            // Status message (main status text like Android) - selectable for debugging
            SelectionContainer {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = statusMessage,
                        fontSize = 14.sp,
                        color = CIRISColors.TextTertiary,
                        textAlign = TextAlign.Center,
                        modifier = Modifier.padding(bottom = 8.dp)
                    )

                    // Current service name (shown during startup, cyan colored)
                    if (servicesOnline > 0 && servicesOnline < totalServices) {
                        Text(
                            text = localizedString(
                                "mobile.startup_services_count",
                                mapOf("online" to servicesOnline.toString(), "total" to totalServices.toString())
                            ),
                            fontSize = 12.sp,
                            color = CIRISColors.AccentCyan
                        )
                    }

                    // Consolidator status indicator
                    consolidatorStatus?.let { status ->
                        Spacer(Modifier.height(8.dp))
                        Text(
                            text = "📊 $status",
                            fontSize = 10.sp,
                            color = CIRISColors.WarningYellow.copy(alpha = 0.9f)
                        )
                    }
                }
            }

            // Error section with debug info (appears on error)
            // Wrapped in SelectionContainer for easy copy/paste of error details
            errorMessage?.let { error ->
                Spacer(Modifier.height(16.dp))

                // Error message box - all text is selectable
                SelectionContainer {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .background(
                                color = CIRISColors.ErrorRed.copy(alpha = 0.1f),
                                shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)
                            )
                            .padding(16.dp),
                        horizontalAlignment = Alignment.Start
                    ) {
                        Text(
                            text = localizedString("mobile.startup_engine_failed"),
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = CIRISColors.ErrorRed,
                            modifier = Modifier.padding(bottom = 8.dp)
                        )

                        // Error message
                        Text(
                            text = error,
                            fontSize = 12.sp,
                            color = CIRISColors.TextSecondary,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        // Debug info section
                        Text(
                            text = localizedString("mobile.startup_debug_info"),
                            fontSize = 12.sp,
                            fontWeight = FontWeight.SemiBold,
                            color = CIRISColors.TextTertiary,
                            modifier = Modifier.padding(bottom = 4.dp)
                        )

                        // Platform-specific debug info will be provided by expect/actual
                        val debugInfo = getDeviceDebugInfo()
                        Text(
                            text = debugInfo,
                            fontSize = 10.sp,
                            color = CIRISColors.TextDim,
                            fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                            modifier = Modifier.padding(bottom = 12.dp)
                        )

                        // Help text
                        Text(
                            text = localizedString("mobile.startup_report_hint"),
                            fontSize = 10.sp,
                            color = CIRISColors.TextDim,
                            textAlign = TextAlign.Start
                        )
                    }
                }

                Spacer(Modifier.height(16.dp))

                // Retry button
                Button(
                    onClick = { viewModel.retry() },
                    modifier = Modifier.testableClickable("btn_startup_retry") { viewModel.retry() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = CIRISColors.SignetTeal
                    )
                ) {
                    Text(localizedString("mobile.startup_retry"), color = Color.White)
                }
            }
        }
    }
}

/**
 * Row of 6 prep lights for pydantic/native lib setup
 * Matches android/app/.../MainActivity.kt prep lights
 */
@Composable
private fun PrepLightsRow(
    prepStepsCompleted: Int,
    hasError: Boolean,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(6.dp)
    ) {
        repeat(StartupViewModel.TOTAL_PREP_STEPS) { index ->
            PrepLight(
                isOn = (index + 1) <= prepStepsCompleted,
                hasError = hasError && (index + 1) <= prepStepsCompleted
            )
        }
    }
}

/**
 * Verify lights row (11 lights for CIRISVerify attestation)
 * Phase 1: 5 steps (parallel manifest fetch + validation)
 * Phase 2: 6 steps (sequential integrity checks)
 *
 * Visual grouping: [5 lights] | [6 lights] with small gap
 */
@Composable
private fun VerifyLightsRow(
    verifyStepsCompleted: Int,
    hasError: Boolean,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.spacedBy(4.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Phase 1 lights (5 steps)
        repeat(5) { index ->
            VerifyLight(
                isOn = (index + 1) <= verifyStepsCompleted,
                hasError = hasError && (index + 1) <= verifyStepsCompleted
            )
        }

        // Small separator between phases
        Spacer(modifier = Modifier.width(8.dp))

        // Phase 2 lights (6 steps, offset by 5)
        repeat(6) { index ->
            val stepNum = 5 + index + 1
            VerifyLight(
                isOn = stepNum <= verifyStepsCompleted,
                hasError = hasError && stepNum <= verifyStepsCompleted
            )
        }
    }
}

/**
 * Single verify light indicator (same size as prep lights)
 */
@Composable
private fun VerifyLight(
    isOn: Boolean,
    hasError: Boolean,
    modifier: Modifier = Modifier
) {
    val targetColor = when {
        hasError -> CIRISColors.ErrorRed
        isOn -> CIRISColors.AccentCyan
        else -> CIRISColors.LightOff
    }

    val animatedColor by animateColorAsState(
        targetValue = targetColor,
        animationSpec = tween(durationMillis = 200, easing = LinearEasing),
        label = "verifyLightColor"
    )

    Box(
        modifier = modifier
            .size(10.dp)
            .background(
                color = animatedColor,
                shape = CircleShape
            )
    )
}

/**
 * Single prep light indicator (smaller than service lights)
 */
@Composable
private fun PrepLight(
    isOn: Boolean,
    hasError: Boolean,
    modifier: Modifier = Modifier
) {
    val targetColor = when {
        hasError -> CIRISColors.ErrorRed
        isOn -> CIRISColors.LightOn
        else -> CIRISColors.LightOff
    }

    val animatedColor by animateColorAsState(
        targetValue = targetColor,
        animationSpec = tween(
            durationMillis = 200,
            easing = LinearEasing
        ),
        label = "PrepLightColor"
    )

    Box(
        modifier = modifier
            .size(12.dp)  // Smaller than service lights (12dp vs 16dp)
            .background(
                color = animatedColor,
                shape = CircleShape
            )
    )
}

/**
 * Grid of 22 service lights (2 rows of 11)
 * Each light represents a specific service SLOT (1-22)
 * Lights turn on based on which slots have started, not sequentially
 */
@Composable
private fun ServiceLightsGrid(
    startedServiceSlots: Set<Int>,
    totalServices: Int,
    hasError: Boolean,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // Row 1: Service slots 1-11
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            repeat(11) { index ->
                val slot = index + 1  // Slots are 1-indexed
                ServiceLight(
                    isOn = slot in startedServiceSlots,
                    hasError = hasError && slot in startedServiceSlots
                )
            }
        }

        // Row 2: Service slots 12-22
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            repeat(11) { index ->
                val slot = index + 12  // Slots 12-22
                ServiceLight(
                    isOn = slot in startedServiceSlots,
                    hasError = hasError && slot in startedServiceSlots
                )
            }
        }
    }
}

/**
 * Single service light indicator
 * Matches android/app/.../MainActivity.kt light animation
 */
@Composable
private fun ServiceLight(
    isOn: Boolean,
    hasError: Boolean,
    modifier: Modifier = Modifier
) {
    val targetColor = when {
        hasError -> CIRISColors.ErrorRed
        isOn -> CIRISColors.LightOn
        else -> CIRISColors.LightOff
    }

    val animatedColor by animateColorAsState(
        targetValue = targetColor,
        animationSpec = tween(
            durationMillis = 200,
            easing = LinearEasing
        ),
        label = "ServiceLightColor"
    )

    Box(
        modifier = modifier
            .size(16.dp)  // 16dp for service lights (matches Android)
            .background(
                color = animatedColor,
                shape = CircleShape
            )
    )
}
