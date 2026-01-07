package ai.ciris.mobile.shared.ui.screens

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
 * CIRIS startup screen with 22 service lights
 * Based on android/app/.../MainActivity.kt splash screen
 *
 * Shows:
 * - CIRIS logo
 * - 22 service lights (2 rows of 11)
 * - Current phase
 * - Service count (e.g., "18/22 services online")
 * - Elapsed time
 * - Error message (if any)
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

    // Auto-start CIRIS on mount
    LaunchedEffect(Unit) {
        if (phase == StartupPhase.INITIALIZING) {
            viewModel.startCIRIS()
        }
    }

    Surface(
        modifier = modifier.fillMaxSize(),
        color = Color(0xFF1a1a2e)  // Dark background from Android app
    ) {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center
        ) {
            // CIRIS Logo/Text
            Text(
                text = "CIRIS",
                fontSize = 64.sp,
                fontWeight = FontWeight.Bold,
                color = Color(0xFF00d4ff),  // Cyan from Android app
                modifier = Modifier.padding(bottom = 48.dp)
            )

            // Service lights grid (22 lights)
            ServiceLightsGrid(
                servicesOnline = servicesOnline,
                totalServices = totalServices,
                hasError = errorMessage != null
            )

            Spacer(Modifier.height(32.dp))

            // Status message
            Text(
                text = statusMessage,
                fontSize = 16.sp,
                color = Color.White,
                textAlign = TextAlign.Center,
                modifier = Modifier.padding(horizontal = 16.dp)
            )

            Spacer(Modifier.height(8.dp))

            // Service count
            Text(
                text = "$servicesOnline / $totalServices services online",
                fontSize = 14.sp,
                color = Color(0xFFaaaaaa),
                fontWeight = FontWeight.Medium
            )

            Spacer(Modifier.height(8.dp))

            // Elapsed time
            Text(
                text = "Elapsed: ${elapsedSeconds}s",
                fontSize = 12.sp,
                color = Color(0xFF888888)
            )

            // Error message (if any)
            errorMessage?.let { error ->
                Spacer(Modifier.height(24.dp))

                Card(
                    colors = CardDefaults.cardColors(
                        containerColor = Color(0xFF332222)
                    ),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(16.dp)
                    ) {
                        Text(
                            text = "Error",
                            fontSize = 16.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color(0xFFff4444)
                        )

                        Spacer(Modifier.height(8.dp))

                        Text(
                            text = error,
                            fontSize = 14.sp,
                            color = Color.White
                        )

                        Spacer(Modifier.height(16.dp))

                        Button(
                            onClick = { viewModel.retry() },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = Color(0xFF00d4ff)
                            )
                        ) {
                            Text("Retry")
                        }
                    }
                }
            }
        }
    }
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
        hasError -> Color(0xFFff4444)  // Red for error
        isOn -> Color(0xFF00d4ff)      // Cyan for online
        else -> Color(0xFF2a2a3e)      // Dark gray for offline
    }

    val animatedColor by animateColorAsState(
        targetValue = targetColor,
        animationSpec = tween(
            durationMillis = 300,
            easing = LinearEasing
        ),
        label = "ServiceLightColor"
    )

    Box(
        modifier = modifier
            .size(12.dp)
            .background(
                color = animatedColor,
                shape = CircleShape
            )
    )
}
