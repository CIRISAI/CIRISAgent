package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.ConnectionStatus
import ai.ciris.mobile.shared.viewmodels.ServerConnectionViewModel
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Server Connection Manager screen.
 *
 * Allows users to:
 * - View current connection status
 * - Restart local server (desktop only)
 * - Connect to remote agents
 * - Manage recent connections
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ServerConnectionScreen(
    viewModel: ServerConnectionViewModel,
    onBack: () -> Unit
) {
    val connectionStatus by viewModel.connectionStatus.collectAsState()
    val currentUrl by viewModel.currentUrl.collectAsState()
    val isLocalServer by viewModel.isLocalServer.collectAsState()
    val recentConnections by viewModel.recentConnections.collectAsState()
    val isLoading by viewModel.isLoading.collectAsState()
    val errorMessage by viewModel.errorMessage.collectAsState()
    val statusMessage by viewModel.statusMessage.collectAsState()
    val isDesktop by viewModel.isDesktop.collectAsState()

    var remoteUrlInput by remember { mutableStateOf("") }

    // Start polling when screen is visible
    LaunchedEffect(Unit) {
        viewModel.startPolling()
    }

    DisposableEffect(Unit) {
        onDispose {
            viewModel.stopPolling()
        }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.server_connection_title")) },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testable("btn_server_back")
                    ) {
                        Icon(
                            imageVector = CIRISIcons.arrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Status messages
            item {
                Spacer(modifier = Modifier.height(8.dp))

                if (errorMessage != null) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.errorContainer
                        )
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Icon(
                                imageVector = CIRISIcons.close,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.onErrorContainer
                            )
                            Text(
                                text = errorMessage ?: "",
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                modifier = Modifier.weight(1f)
                            )
                            IconButton(onClick = { viewModel.clearError() }) {
                                Icon(
                                    imageVector = CIRISIcons.close,
                                    contentDescription = "Dismiss",
                                    tint = MaterialTheme.colorScheme.onErrorContainer
                                )
                            }
                        }
                    }
                }

                if (statusMessage != null) {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = Color(0xFFE8F5E9)
                        )
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Icon(
                                imageVector = CIRISIcons.checkCircle,
                                contentDescription = null,
                                tint = Color(0xFF388E3C)
                            )
                            Text(
                                text = statusMessage ?: "",
                                color = Color(0xFF388E3C),
                                modifier = Modifier.weight(1f)
                            )
                            IconButton(onClick = { viewModel.clearStatus() }) {
                                Icon(
                                    imageVector = CIRISIcons.close,
                                    contentDescription = "Dismiss",
                                    tint = Color(0xFF388E3C)
                                )
                            }
                        }
                    }
                }
            }

            // Section 1: Connection Status Card
            item {
                ConnectionStatusCard(
                    connectionStatus = connectionStatus,
                    currentUrl = currentUrl,
                    isLocalServer = isLocalServer
                )
            }

            // Section 2: Local Server Controls (desktop only)
            if (isDesktop) {
                item {
                    LocalServerControlsCard(
                        isLocalServer = isLocalServer,
                        connectionStatus = connectionStatus,
                        isLoading = isLoading,
                        onRestart = { viewModel.restartLocalServer() },
                        onStop = { viewModel.stopLocalServer() }
                    )
                }
            }

            // Section 3: Remote Connection
            item {
                RemoteConnectionCard(
                    urlInput = remoteUrlInput,
                    onUrlChange = { remoteUrlInput = it },
                    isLocalServer = isLocalServer,
                    isLoading = isLoading,
                    onConnect = {
                        viewModel.connectToUrl(remoteUrlInput)
                        remoteUrlInput = ""
                    },
                    onDisconnect = { viewModel.disconnectFromRemote() }
                )
            }

            // Section 4: Recent Connections
            if (recentConnections.isNotEmpty()) {
                item {
                    Text(
                        text = localizedString("mobile.server_recent_connections"),
                        style = MaterialTheme.typography.titleMedium,
                        color = MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.padding(top = 8.dp)
                    )
                }

                items(recentConnections) { url ->
                    RecentConnectionItem(
                        url = url,
                        isCurrentUrl = url == currentUrl,
                        onConnect = { viewModel.connectToUrl(url) },
                        onRemove = { viewModel.removeRecentConnection(url) }
                    )
                }
            }

            // Bottom padding
            item {
                Spacer(modifier = Modifier.height(32.dp))
            }
        }

        // Loading overlay
        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = 0.3f)),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator(color = MaterialTheme.colorScheme.primary)
            }
        }
    }
}

/**
 * Connection status card showing current connection state.
 */
@Composable
private fun ConnectionStatusCard(
    connectionStatus: ConnectionStatus,
    currentUrl: String,
    isLocalServer: Boolean
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = when (connectionStatus) {
                        ConnectionStatus.CONNECTED_LOCAL,
                        ConnectionStatus.CONNECTED_REMOTE -> CIRISIcons.checkCircle
                        ConnectionStatus.CONNECTING -> CIRISIcons.refresh
                        else -> CIRISIcons.close
                    },
                    contentDescription = null,
                    tint = getStatusColor(connectionStatus),
                    modifier = Modifier.size(28.dp)
                )
                Text(
                    text = localizedString("mobile.server_connection_title"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }

            // Status indicator
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Box(
                    modifier = Modifier
                        .size(12.dp)
                        .background(getStatusColor(connectionStatus), CircleShape)
                )
                Text(
                    text = getStatusText(connectionStatus),
                    color = getStatusColor(connectionStatus),
                    fontWeight = FontWeight.Medium
                )
            }

            // Current URL
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = CIRISIcons.play,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.size(16.dp)
                )
                Text(
                    text = currentUrl,
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Connection type badge
            Surface(
                shape = RoundedCornerShape(4.dp),
                color = if (isLocalServer) Color(0xFF10B981).copy(alpha = 0.15f)
                       else MaterialTheme.colorScheme.primary.copy(alpha = 0.15f)
            ) {
                Text(
                    text = if (isLocalServer) localizedString("mobile.interact_local")
                           else localizedString("mobile.interact_remote"),
                    modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold,
                    color = if (isLocalServer) Color(0xFF10B981) else MaterialTheme.colorScheme.primary
                )
            }
        }
    }
}

/**
 * Local server controls card (desktop only).
 */
@Composable
private fun LocalServerControlsCard(
    isLocalServer: Boolean,
    connectionStatus: ConnectionStatus,
    isLoading: Boolean,
    onRestart: () -> Unit,
    onStop: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = CIRISIcons.refresh,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary
                )
                Text(
                    text = localizedString("mobile.server_local_controls"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }

            Text(
                text = "Manage the local CIRIS backend server running on this device.",
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Restart button
                Button(
                    onClick = onRestart,
                    enabled = !isLoading && isLocalServer,
                    modifier = Modifier
                        .weight(1f)
                        .testableClickable("btn_restart_server") { onRestart() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary
                    )
                ) {
                    Icon(
                        imageVector = CIRISIcons.refresh,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(localizedString("mobile.server_restart_button"))
                }

                // Stop button
                OutlinedButton(
                    onClick = onStop,
                    enabled = !isLoading && isLocalServer &&
                              connectionStatus != ConnectionStatus.DISCONNECTED,
                    modifier = Modifier
                        .weight(1f)
                        .testableClickable("btn_stop_server") { onStop() }
                ) {
                    Icon(
                        imageVector = CIRISIcons.close,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(localizedString("mobile.server_stop_button"))
                }
            }
        }
    }
}

/**
 * Remote connection card.
 */
@Composable
private fun RemoteConnectionCard(
    urlInput: String,
    onUrlChange: (String) -> Unit,
    isLocalServer: Boolean,
    isLoading: Boolean,
    onConnect: () -> Unit,
    onDisconnect: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Icon(
                    imageVector = CIRISIcons.play,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.primary
                )
                Text(
                    text = localizedString("mobile.server_remote_connection"),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
            }

            Text(
                text = "Connect to a CIRIS agent running on a remote server.",
                fontSize = 13.sp,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            // URL input field
            OutlinedTextField(
                value = urlInput,
                onValueChange = onUrlChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .testable("input_server_url"),
                label = { Text("Server URL") },
                placeholder = { Text(localizedString("mobile.server_url_placeholder")) },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Uri,
                    imeAction = ImeAction.Go
                ),
                keyboardActions = KeyboardActions(
                    onGo = { if (urlInput.isNotBlank()) onConnect() }
                ),
                leadingIcon = {
                    Icon(CIRISIcons.play, contentDescription = null)
                }
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Connect button
                Button(
                    onClick = onConnect,
                    enabled = !isLoading && urlInput.isNotBlank(),
                    modifier = Modifier
                        .weight(1f)
                        .testableClickable("btn_connect") { onConnect() },
                    colors = ButtonDefaults.buttonColors(
                        containerColor = MaterialTheme.colorScheme.primary
                    )
                ) {
                    Icon(
                        imageVector = CIRISIcons.play,
                        contentDescription = null,
                        modifier = Modifier.size(18.dp)
                    )
                    Spacer(modifier = Modifier.width(8.dp))
                    Text(localizedString("mobile.server_connect_button"))
                }

                // Disconnect button (only if connected to remote)
                if (!isLocalServer) {
                    OutlinedButton(
                        onClick = onDisconnect,
                        enabled = !isLoading,
                        modifier = Modifier
                            .weight(1f)
                            .testableClickable("btn_disconnect") { onDisconnect() }
                    ) {
                        Icon(
                            imageVector = CIRISIcons.close,
                            contentDescription = null,
                            modifier = Modifier.size(18.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(localizedString("mobile.server_disconnect_button"))
                    }
                }
            }
        }
    }
}

/**
 * Recent connection list item.
 */
@Composable
private fun RecentConnectionItem(
    url: String,
    isCurrentUrl: Boolean,
    onConnect: () -> Unit,
    onRemove: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (isCurrentUrl)
                MaterialTheme.colorScheme.primary.copy(alpha = 0.1f)
                else MaterialTheme.colorScheme.surface
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(12.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Icon(
                imageVector = CIRISIcons.play,
                contentDescription = null,
                tint = if (isCurrentUrl) MaterialTheme.colorScheme.primary
                       else MaterialTheme.colorScheme.onSurfaceVariant
            )

            Text(
                text = url,
                modifier = Modifier.weight(1f),
                fontSize = 13.sp,
                color = if (isCurrentUrl) MaterialTheme.colorScheme.primary
                        else MaterialTheme.colorScheme.onSurface
            )

            if (isCurrentUrl) {
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = Color(0xFF10B981).copy(alpha = 0.15f)
                ) {
                    Text(
                        text = "Current",
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
                        fontSize = 11.sp,
                        color = Color(0xFF10B981)
                    )
                }
            } else {
                IconButton(
                    onClick = onConnect,
                    modifier = Modifier.testable("btn_connect_recent")
                ) {
                    Icon(
                        imageVector = CIRISIcons.play,
                        contentDescription = "Connect",
                        tint = MaterialTheme.colorScheme.primary
                    )
                }
            }

            IconButton(
                onClick = onRemove,
                modifier = Modifier.testable("btn_remove_recent")
            ) {
                Icon(
                    imageVector = CIRISIcons.close,
                    contentDescription = "Remove",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
        }
    }
}

/**
 * Get color for connection status.
 */
@Composable
private fun getStatusColor(status: ConnectionStatus): Color {
    return when (status) {
        ConnectionStatus.CONNECTED_LOCAL -> Color(0xFF10B981) // Green
        ConnectionStatus.CONNECTED_REMOTE -> Color(0xFF3B82F6) // Blue
        ConnectionStatus.CONNECTING -> Color(0xFFF59E0B) // Amber
        ConnectionStatus.DISCONNECTED -> Color(0xFFEF4444) // Red
        ConnectionStatus.ERROR -> Color(0xFFEF4444) // Red
    }
}

/**
 * Get text for connection status.
 */
@Composable
private fun getStatusText(status: ConnectionStatus): String {
    return when (status) {
        ConnectionStatus.CONNECTED_LOCAL,
        ConnectionStatus.CONNECTED_REMOTE -> localizedString("mobile.server_status_connected")
        ConnectionStatus.CONNECTING -> localizedString("mobile.server_status_connecting")
        ConnectionStatus.DISCONNECTED,
        ConnectionStatus.ERROR -> localizedString("mobile.server_status_disconnected")
    }
}
