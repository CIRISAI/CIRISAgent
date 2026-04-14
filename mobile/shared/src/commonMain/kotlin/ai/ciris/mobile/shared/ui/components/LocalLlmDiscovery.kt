package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.api.CIRISApiClient
import ai.ciris.mobile.shared.platform.PlatformLogger
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.DiscoveredLlmServer
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.IO
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
            enabled = !state.isDiscovering,
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
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(12.dp),
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
                }
            }
        } else if (!state.isDiscovering && state.discoveredServers.isEmpty() && state.errorMessage == null) {
            Text(
                text = "No servers found. Ensure your LLM server is running on the network.",
                style = MaterialTheme.typography.bodySmall,
                color = secondaryTextColor
            )
        }
    }
}
