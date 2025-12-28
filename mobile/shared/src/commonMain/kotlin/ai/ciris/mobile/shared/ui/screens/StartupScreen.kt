package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.ui.components.CIRISSignet
import ai.ciris.mobile.shared.ui.theme.CIRISColors
import ai.ciris.mobile.shared.viewmodels.StartupPhase
import ai.ciris.mobile.shared.viewmodels.StartupViewModel
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
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
    val statusMessage by viewModel.statusMessage.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()
    val elapsedSeconds by viewModel.elapsedSeconds.collectAsState()
    val prepStepsCompleted by viewModel.prepStepsCompleted.collectAsState()
    val hasError by viewModel.hasError.collectAsState()

    // Auto-start CIRIS on mount
    LaunchedEffect(Unit) {
        if (phase == StartupPhase.INITIALIZING) {
            viewModel.startCIRIS()
        }
    }

    Surface(
        modifier = modifier.fillMaxSize(),
        color = CIRISColors.BackgroundDark
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp),  // 24dp padding to match Android
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
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
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                modifier = Modifier.padding(bottom = 16.dp)
            ) {
                Text(
                    text = if (prepStepsCompleted >= StartupViewModel.TOTAL_PREP_STEPS) {
                        "Environment Ready"
                    } else if (prepStepsCompleted > 0) {
                        "Preparing Environment... $prepStepsCompleted/${StartupViewModel.TOTAL_PREP_STEPS}"
                    } else {
                        "Preparing Environment"
                    },
                    fontSize = 10.sp,
                    color = if (prepStepsCompleted >= StartupViewModel.TOTAL_PREP_STEPS) {
                        CIRISColors.SuccessGreen
                    } else {
                        CIRISColors.TextDim
                    },
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            // Services label (shown after prep completes, above service lights)
            if (prepStepsCompleted >= StartupViewModel.TOTAL_PREP_STEPS) {
                Text(
                    text = "Starting Services",
                    fontSize = 10.sp,
                    color = CIRISColors.TextDim,
                    modifier = Modifier.padding(bottom = 4.dp)
                )
            }

            // Service lights grid (22 lights)
            ServiceLightsGrid(
                servicesOnline = servicesOnline,
                totalServices = totalServices,
                hasError = hasError,
                modifier = Modifier.padding(bottom = 32.dp)
            )

            // Status message (main status text like Android)
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
                    text = "Service $servicesOnline/$totalServices",
                    fontSize = 12.sp,
                    color = CIRISColors.AccentCyan
                )
            }

            // Show Logs button (appears on error, matches Android)
            errorMessage?.let { _ ->
                Spacer(Modifier.height(24.dp))

                // Simple text button like Android
                Text(
                    text = "Show Logs",
                    fontSize = 14.sp,
                    color = CIRISColors.AccentCyan,
                    modifier = Modifier.padding(12.dp)
                )
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
 * Animates as services come online
 */
@Composable
private fun ServiceLightsGrid(
    servicesOnline: Int,
    totalServices: Int,
    hasError: Boolean,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        // Row 1 (11 lights)
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            repeat(11) { index ->
                ServiceLight(
                    isOn = index < servicesOnline,
                    hasError = hasError && index < servicesOnline
                )
            }
        }

        // Row 2 (11 lights)
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            repeat(11) { index ->
                val lightIndex = index + 11
                ServiceLight(
                    isOn = lightIndex < servicesOnline,
                    hasError = hasError && lightIndex < servicesOnline
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
