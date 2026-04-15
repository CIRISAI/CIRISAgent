package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.LocalInferenceCapability
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.DiscoveredLlmServer
import ai.ciris.mobile.shared.viewmodels.StartLocalServerResult
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

private const val TAG = "LocalLlmDiscovery"

/**
 * State holder for Local LLM Server Discovery.
 * Can be used by any screen that needs to discover local inference servers.
 */
class LocalLlmDiscoveryState {
    var isDiscovering by mutableStateOf(false)
    var discoveredServers by mutableStateOf<List<DiscoveredLlmServer>>(emptyList())
    var selectedServer by mutableStateOf<DiscoveredLlmServer?>(null)
    var errorMessage by mutableStateOf<String?>(null)
    // Server start state
    var isStartingServer by mutableStateOf(false)
    var serverStartResult by mutableStateOf<StartLocalServerResult?>(null)
    var serverStartProgress by mutableStateOf<String?>(null)
}

@Composable
fun rememberLocalLlmDiscoveryState(): LocalLlmDiscoveryState {
    return remember { LocalLlmDiscoveryState() }
}

/**
 * Reusable composable for discovering and selecting local LLM inference servers.
 *
 * @param state The discovery state holder
 * @param apiClient The API client to use for discovery
 * @param onServerSelected Callback when a server is selected (provides URL and models)
 * @param onAddAsProvider Optional callback when "Add as Provider" is clicked (if null, button is hidden)
 * @param localInferenceCapability Optional device capability for showing "Start Server" option
 * @param primaryColor Primary theme color for buttons/highlights
 * @param surfaceColor Surface color for cards
 * @param textColor Primary text color
 * @param secondaryTextColor Secondary text color
 * @param modifier Modifier for the container
 */
@Composable
fun LocalLlmServerDiscovery(
    state: LocalLlmDiscoveryState,
    apiClient: CIRISApiClient,
    onServerSelected: (server: DiscoveredLlmServer) -> Unit,
    onAddAsProvider: ((server: DiscoveredLlmServer) -> Unit)? = null,
    localInferenceCapability: LocalInferenceCapability? = null,
    primaryColor: Color = MaterialTheme.colorScheme.primary,
    surfaceColor: Color = MaterialTheme.colorScheme.surfaceVariant,
    textColor: Color = MaterialTheme.colorScheme.onSurface,
    secondaryTextColor: Color = MaterialTheme.colorScheme.onSurfaceVariant,
    modifier: Modifier = Modifier
) {
    val coroutineScope = rememberCoroutineScope()

    fun discoverServers() {
        if (state.isDiscovering) return

        state.isDiscovering = true
        state.errorMessage = null
        state.discoveredServers = emptyList()

        coroutineScope.launch(Dispatchers.IO) {
            try {
                PlatformLogger.i(TAG, "Starting local LLM server discovery...")
                val servers = apiClient.discoverLocalLlmServers(
                    timeoutSeconds = 5.0f,
                    includeLocalhost = true
                )

                withContext(Dispatchers.Main) {
                    state.discoveredServers = servers
                    state.isDiscovering = false
                    PlatformLogger.i(TAG, "Discovered ${servers.size} servers")

                    // Auto-select if only one server found
                    if (servers.size == 1) {
                        state.selectedServer = servers.first()
                        onServerSelected(servers.first())
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    state.errorMessage = e.message ?: "Discovery failed"
                    state.isDiscovering = false
                    PlatformLogger.e(TAG, "Discovery failed: ${e.message}")
                }
            }
        }
    }

    fun startLocalServer() {
        if (state.isStartingServer) return

        state.isStartingServer = true
        state.serverStartResult = null
        state.serverStartProgress = "Starting local inference server..."
        state.errorMessage = null

        coroutineScope.launch(Dispatchers.IO) {
            try {
                PlatformLogger.i(TAG, "Starting local LLM server...")

                val result = apiClient.startLocalLlmServer(
                    serverType = "llama_cpp",
                    model = "gemma-4-e2b",
                    port = 8080
                )

                withContext(Dispatchers.Main) {
                    state.serverStartResult = result
                    state.isStartingServer = false

                    if (result.success) {
                        state.serverStartProgress = "Server started! Loading model (this may take ${result.estimatedReadySeconds}s)..."
                        PlatformLogger.i(TAG, "Server started successfully, waiting for readiness...")

                        // Wait for the server to be ready, then re-discover
                        coroutineScope.launch(Dispatchers.IO) {
                            // Wait for estimated ready time (in chunks so we can update UI)
                            val waitSeconds = result.estimatedReadySeconds.coerceIn(10, 120)
                            repeat(waitSeconds / 5) {
                                delay(5000)
                                withContext(Dispatchers.Main) {
                                    val remaining = waitSeconds - ((it + 1) * 5)
                                    state.serverStartProgress = "Loading model (~${remaining}s remaining)..."
                                }
                            }

                            // Re-discover to find the new server
                            withContext(Dispatchers.Main) {
                                state.serverStartProgress = null
                                discoverServers()
                            }
                        }
                    } else {
                        state.serverStartProgress = null
                        state.errorMessage = result.message
                        PlatformLogger.e(TAG, "Failed to start server: ${result.message}")
                    }
                }
            } catch (e: Exception) {
                withContext(Dispatchers.Main) {
                    state.isStartingServer = false
                    state.serverStartProgress = null
                    state.errorMessage = "Failed to start server: ${e.message}"
                    PlatformLogger.e(TAG, "Server start failed: ${e.message}")
                }
            }
        }
    }

    // Auto-discover on first composition
    LaunchedEffect(Unit) {
        if (state.discoveredServers.isEmpty() && !state.isDiscovering) {
            discoverServers()
        }
    }

    Column(
        modifier = modifier,
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Discover button
        OutlinedButton(
            onClick = { discoverServers() },
            enabled = !state.isDiscovering && !state.isStartingServer,
            modifier = Modifier
                .fillMaxWidth()
                .testableClickable("btn_discover_servers") { discoverServers() },
            colors = ButtonDefaults.outlinedButtonColors(
                contentColor = primaryColor
            )
        ) {
            if (state.isDiscovering) {
                CircularProgressIndicator(
                    modifier = Modifier.size(16.dp),
                    strokeWidth = 2.dp,
                    color = primaryColor
                )
                Spacer(Modifier.width(8.dp))
                Text("Discovering...", color = primaryColor)
            } else {
                Icon(
                    imageVector = Icons.Filled.Refresh,
                    contentDescription = null,
                    modifier = Modifier.size(18.dp)
                )
                Spacer(Modifier.width(8.dp))
                Text("Discover Servers", color = primaryColor)
            }
        }

        // Error message
        state.errorMessage?.let { error ->
            Text(
                text = error,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.error
            )
        }

        // Discovered servers list
        if (state.discoveredServers.isNotEmpty()) {
            Text(
                text = "Found ${state.discoveredServers.size} server(s):",
                style = MaterialTheme.typography.labelMedium,
                color = secondaryTextColor
            )

            state.discoveredServers.forEach { server ->
                val isSelected = state.selectedServer?.id == server.id

                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable {
                            state.selectedServer = server
                            onServerSelected(server)
                        }
                        .testableClickable("server_${server.id}") {
                            state.selectedServer = server
                            onServerSelected(server)
                        },
                    colors = CardDefaults.cardColors(
                        containerColor = if (isSelected) primaryColor.copy(alpha = 0.15f) else surfaceColor
                    ),
                    border = if (isSelected) BorderStroke(2.dp, primaryColor) else null
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = server.label,
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = textColor
                                )
                                Text(
                                    text = server.url,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = secondaryTextColor.copy(alpha = 0.7f)
                                )
                                if (server.models.isNotEmpty()) {
                                    Text(
                                        text = "${server.modelCount} model(s): ${server.models.take(2).joinToString()}${if (server.models.size > 2) "..." else ""}",
                                        style = MaterialTheme.typography.bodySmall,
                                        color = secondaryTextColor.copy(alpha = 0.7f)
                                    )
                                }
                            }
                            // Server type badge
                            Surface(
                                color = MaterialTheme.colorScheme.tertiaryContainer,
                                shape = RoundedCornerShape(4.dp)
                            ) {
                                Text(
                                    text = server.serverType.uppercase(),
                                    style = MaterialTheme.typography.labelSmall,
                                    color = MaterialTheme.colorScheme.onTertiaryContainer,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                            }
                        }

                        // Add as Provider button (only shown if callback is provided)
                        if (onAddAsProvider != null) {
                            Spacer(Modifier.height(8.dp))
                            OutlinedButton(
                                onClick = { onAddAsProvider(server) },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .testableClickable("btn_add_provider_${server.id}") { onAddAsProvider(server) },
                                colors = ButtonDefaults.outlinedButtonColors(
                                    contentColor = primaryColor
                                ),
                                border = BorderStroke(1.dp, primaryColor.copy(alpha = 0.5f))
                            ) {
                                Text("Add as Provider", color = primaryColor)
                            }
                        }
                    }
                }
            }
        } else if (!state.isDiscovering && state.discoveredServers.isEmpty() && state.errorMessage == null) {
            // No servers found - show "Start Local Server" option if device is capable
            val isCapable = localInferenceCapability?.isReady == true

            if (isCapable && !state.isStartingServer && state.serverStartProgress == null) {
                // Show start server card
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .testableClickable("card_start_local_server") { startLocalServer() },
                    colors = CardDefaults.cardColors(
                        containerColor = primaryColor.copy(alpha = 0.1f)
                    ),
                    border = BorderStroke(1.dp, primaryColor.copy(alpha = 0.3f))
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            Icon(
                                imageVector = Icons.Filled.PlayArrow,
                                contentDescription = null,
                                tint = primaryColor,
                                modifier = Modifier.size(24.dp)
                            )
                            Spacer(Modifier.width(12.dp))
                            Column(modifier = Modifier.weight(1f)) {
                                Text(
                                    text = "Start Local Inference",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.SemiBold,
                                    color = textColor
                                )
                                Text(
                                    text = "Your device can run local AI inference",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = secondaryTextColor
                                )
                            }
                        }

                        Spacer(Modifier.height(12.dp))

                        Text(
                            text = "No LLM server detected, but this device has enough resources to run one. " +
                                    "Click below to start a local llama.cpp server with Gemma 4. " +
                                    "This may take 30-60 seconds to load the model.",
                            style = MaterialTheme.typography.bodySmall,
                            color = secondaryTextColor,
                            fontSize = 12.sp
                        )

                        Spacer(Modifier.height(12.dp))

                        Button(
                            onClick = { startLocalServer() },
                            modifier = Modifier
                                .fillMaxWidth()
                                .testableClickable("btn_start_local_server") { startLocalServer() },
                            colors = ButtonDefaults.buttonColors(
                                containerColor = primaryColor
                            )
                        ) {
                            Icon(
                                imageVector = Icons.Filled.PlayArrow,
                                contentDescription = null,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(Modifier.width(8.dp))
                            Text("Start Local Server")
                        }
                    }
                }
            } else if (state.isStartingServer || state.serverStartProgress != null) {
                // Show starting progress
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = surfaceColor
                    )
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(32.dp),
                            strokeWidth = 3.dp,
                            color = primaryColor
                        )
                        Spacer(Modifier.height(12.dp))
                        Text(
                            text = state.serverStartProgress ?: "Starting server...",
                            style = MaterialTheme.typography.bodyMedium,
                            color = textColor
                        )
                        Text(
                            text = "Please wait while the model loads",
                            style = MaterialTheme.typography.bodySmall,
                            color = secondaryTextColor
                        )
                    }
                }
            } else {
                // Device not capable or hasn't probed capability yet
                Text(
                    text = "No servers found. Ensure your LLM server is running on the network.",
                    style = MaterialTheme.typography.bodySmall,
                    color = secondaryTextColor
                )
            }
        }
    }
}
