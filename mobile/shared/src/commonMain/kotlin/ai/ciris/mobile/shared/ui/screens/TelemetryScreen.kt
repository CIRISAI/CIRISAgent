package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.AuthType
import ai.ciris.mobile.shared.models.ExportDestination
import ai.ciris.mobile.shared.models.ExportDestinationCreate
import ai.ciris.mobile.shared.models.ExportFormat
import ai.ciris.mobile.shared.models.SignalType
import ai.ciris.mobile.shared.models.TestResult
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.Edit
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Telemetry screen for system metrics and service health
 * Based on TelemetryFragment.kt
 *
 * Features:
 * - Service status overview
 * - Resource usage (CPU, Memory, Disk)
 * - Cognitive state display
 * - Activity metrics (messages, tasks, errors)
 * - Export destinations CRUD
 * - Auto-refresh every 5 seconds
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TelemetryScreen(
    telemetryData: TelemetryData,
    isLoading: Boolean,
    onRefresh: () -> Unit,
    onNavigateBack: () -> Unit,
    // Export destinations
    exportDestinations: List<ExportDestination> = emptyList(),
    showDestinationDialog: Boolean = false,
    editingDestination: ExportDestination? = null,
    testResult: Pair<String, TestResult>? = null,
    onAddDestination: () -> Unit = {},
    onEditDestination: (ExportDestination) -> Unit = {},
    onDeleteDestination: (String) -> Unit = {},
    onToggleDestination: (String) -> Unit = {},
    onTestDestination: (String) -> Unit = {},
    onSaveDestination: (ExportDestinationCreate) -> Unit = {},
    onDismissDialog: () -> Unit = {},
    onClearTestResult: () -> Unit = {},
    modifier: Modifier = Modifier
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("System Telemetry") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_telemetry_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    IconButton(
                        onClick = onRefresh,
                        enabled = !isLoading,
                        modifier = Modifier.testableClickable("btn_telemetry_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Services overview
            item {
                ServicesOverviewCard(
                    healthyServices = telemetryData.healthyServices,
                    totalServices = telemetryData.totalServices,
                    cognitiveState = telemetryData.cognitiveState
                )
            }

            // Resource usage
            item {
                Text(
                    text = "Resource Usage",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
            }

            item {
                ResourceUsageCard(
                    cpuPercent = telemetryData.cpuPercent,
                    memoryMb = telemetryData.memoryMb,
                    diskUsedMb = telemetryData.diskUsedMb
                )
            }

            // Activity metrics
            item {
                Text(
                    text = "Activity (24h)",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
            }

            item {
                ActivityMetricsCard(
                    messagesProcessed = telemetryData.messagesProcessed24h,
                    tasksCompleted = telemetryData.tasksCompleted24h,
                    errors = telemetryData.errors24h
                )
            }

            // Service health list
            if (telemetryData.serviceHealthItems.isNotEmpty()) {
                item {
                    Text(
                        text = "Service Health",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                }

                items(telemetryData.serviceHealthItems) { item ->
                    ServiceHealthRow(item = item)
                }
            }

            // Export Destinations section
            item {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Export Destinations",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    IconButton(onClick = onAddDestination) {
                        Icon(
                            imageVector = Icons.Default.Add,
                            contentDescription = "Add Destination",
                            tint = MaterialTheme.colorScheme.primary
                        )
                    }
                }
            }

            if (exportDestinations.isEmpty()) {
                item {
                    Card(
                        modifier = Modifier.fillMaxWidth(),
                        colors = CardDefaults.cardColors(
                            containerColor = MaterialTheme.colorScheme.surfaceVariant
                        )
                    ) {
                        Text(
                            text = "No export destinations configured. Tap + to add one.",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(16.dp)
                        )
                    }
                }
            } else {
                items(exportDestinations, key = { it.id }) { destination ->
                    ExportDestinationCard(
                        destination = destination,
                        testResult = if (testResult?.first == destination.id) testResult.second else null,
                        onEdit = { onEditDestination(destination) },
                        onDelete = { onDeleteDestination(destination.id) },
                        onToggle = { onToggleDestination(destination.id) },
                        onTest = { onTestDestination(destination.id) },
                        onClearTestResult = onClearTestResult
                    )
                }
            }
        }
    }

    // Add/Edit Destination Dialog
    if (showDestinationDialog) {
        ExportDestinationDialog(
            destination = editingDestination,
            onDismiss = onDismissDialog,
            onSave = onSaveDestination
        )
    }
}

@Composable
private fun ServicesOverviewCard(
    healthyServices: Int,
    totalServices: Int,
    cognitiveState: String,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.primaryContainer
        )
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(24.dp),
            horizontalArrangement = Arrangement.SpaceEvenly
        ) {
            // Services online
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = "$healthyServices/$totalServices",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = if (healthyServices == totalServices)
                        SemanticColors.Default.success
                    else
                        SemanticColors.Default.warning
                )
                Text(
                    text = "Services Online",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }

            Divider(
                modifier = Modifier
                    .height(60.dp)
                    .width(1.dp)
            )

            // Cognitive state
            Column(
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(
                    text = cognitiveState,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = getCognitiveStateColor(cognitiveState)
                )
                Text(
                    text = "State",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer
                )
            }
        }
    }
}

@Composable
private fun ResourceUsageCard(
    cpuPercent: Int,
    memoryMb: Int,
    diskUsedMb: Double,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // CPU
            ResourceUsageRow(
                label = "CPU",
                value = "$cpuPercent%",
                progress = cpuPercent / 100f,
                color = getUsageColor(cpuPercent)
            )

            // Memory (assume 4GB max)
            val memoryPercent = (memoryMb * 100 / 4096).coerceIn(0, 100)
            ResourceUsageRow(
                label = "Memory",
                value = "$memoryMb MB",
                progress = memoryPercent / 100f,
                color = getUsageColor(memoryPercent)
            )

            // Disk
            val diskGb = diskUsedMb / 1024.0
            val diskPercent = ((diskUsedMb / 10240.0) * 100).toInt().coerceIn(0, 100)
            ResourceUsageRow(
                label = "Disk",
                value = if (diskGb >= 1.0) "${((diskGb * 10).toInt() / 10.0)} GB" else "${diskUsedMb.toInt()} MB",
                progress = diskPercent / 100f,
                color = getUsageColor(diskPercent)
            )
        }
    }
}

@Composable
private fun ResourceUsageRow(
    label: String,
    value: String,
    progress: Float,
    color: Color,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Text(
                text = label,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium
            )
            Text(
                text = value,
                style = MaterialTheme.typography.bodyMedium,
                color = color
            )
        }
        LinearProgressIndicator(
            progress = progress.coerceIn(0f, 1f),
            modifier = Modifier
                .fillMaxWidth()
                .height(8.dp),
            color = color,
            trackColor = MaterialTheme.colorScheme.surfaceVariant
        )
    }
}

@Composable
private fun ActivityMetricsCard(
    messagesProcessed: Int,
    tasksCompleted: Int,
    errors: Int,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            MetricRow("Messages Processed", messagesProcessed.toString())
            MetricRow("Tasks Completed", tasksCompleted.toString())
            MetricRow(
                "Errors",
                errors.toString(),
                valueColor = if (errors > 0) SemanticColors.Default.error else Color.Unspecified
            )
        }
    }
}

@Composable
private fun MetricRow(
    label: String,
    value: String,
    valueColor: Color = Color.Unspecified,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
            color = valueColor
        )
    }
}

@Composable
private fun ServiceHealthRow(
    item: ServiceHealthItem,
    modifier: Modifier = Modifier
) {
    Card(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Status dot
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(
                        if (item.healthy) SemanticColors.Default.success else SemanticColors.Default.error
                    )
            )

            // Service name
            Text(
                text = item.name,
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.Medium,
                modifier = Modifier.weight(1f)
            )

            // Status
            Text(
                text = item.status,
                style = MaterialTheme.typography.bodyMedium,
                color = if (item.healthy)
                    SemanticColors.Default.success
                else
                    SemanticColors.Default.error
            )
        }
    }
}

// Export Destination Composables

@Composable
private fun ExportDestinationCard(
    destination: ExportDestination,
    testResult: TestResult?,
    onEdit: () -> Unit,
    onDelete: () -> Unit,
    onToggle: () -> Unit,
    onTest: () -> Unit,
    onClearTestResult: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (destination.enabled)
                MaterialTheme.colorScheme.surface
            else
                MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.5f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Header row with toggle and name
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Switch(
                        checked = destination.enabled,
                        onCheckedChange = { onToggle() },
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = SemanticColors.Default.success,
                            checkedTrackColor = SemanticColors.Default.success.copy(alpha = 0.5f)
                        )
                    )
                    Column {
                        Text(
                            text = destination.name,
                            style = MaterialTheme.typography.titleSmall,
                            fontWeight = FontWeight.Bold,
                            color = if (destination.enabled)
                                MaterialTheme.colorScheme.onSurface
                            else
                                MaterialTheme.colorScheme.onSurface.copy(alpha = 0.6f)
                        )
                        Text(
                            text = destination.endpoint,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }
            }

            // Signal chips and format badge
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                destination.signals.forEach { signal ->
                    SuggestionChip(
                        onClick = {},
                        label = {
                            Text(
                                text = signal.name,
                                style = MaterialTheme.typography.labelSmall
                            )
                        },
                        modifier = Modifier.height(28.dp)
                    )
                }
                Spacer(modifier = Modifier.width(8.dp))
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = MaterialTheme.colorScheme.secondaryContainer
                ) {
                    Text(
                        text = destination.format.name,
                        style = MaterialTheme.typography.labelSmall,
                        modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
                    )
                }
            }

            // Test result (if any)
            testResult?.let { result ->
                Surface(
                    shape = RoundedCornerShape(4.dp),
                    color = if (result.success)
                        SemanticColors.Default.success.copy(alpha = 0.1f)
                    else
                        SemanticColors.Default.error.copy(alpha = 0.1f),
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onClearTestResult() }
                ) {
                    Row(
                        modifier = Modifier.padding(8.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Box(
                            modifier = Modifier
                                .size(8.dp)
                                .clip(CircleShape)
                                .background(
                                    if (result.success) SemanticColors.Default.success
                                    else SemanticColors.Default.error
                                )
                        )
                        Text(
                            text = result.message,
                            style = MaterialTheme.typography.bodySmall,
                            color = if (result.success)
                                SemanticColors.Default.success
                            else
                                SemanticColors.Default.error
                        )
                        result.latencyMs?.let { latency ->
                            Text(
                                text = "(${latency.toInt()}ms)",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                }
            }

            // Actions row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.End,
                verticalAlignment = Alignment.CenterVertically
            ) {
                IconButton(onClick = onTest) {
                    Icon(
                        imageVector = Icons.Default.PlayArrow,
                        contentDescription = "Test",
                        tint = MaterialTheme.colorScheme.primary
                    )
                }
                IconButton(onClick = onEdit) {
                    Icon(
                        imageVector = Icons.Default.Edit,
                        contentDescription = "Edit",
                        tint = MaterialTheme.colorScheme.primary
                    )
                }
                IconButton(onClick = onDelete) {
                    Icon(
                        imageVector = Icons.Default.Delete,
                        contentDescription = "Delete",
                        tint = SemanticColors.Default.error
                    )
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ExportDestinationDialog(
    destination: ExportDestination?,
    onDismiss: () -> Unit,
    onSave: (ExportDestinationCreate) -> Unit
) {
    var name by remember { mutableStateOf(destination?.name ?: "") }
    var endpoint by remember { mutableStateOf(destination?.endpoint ?: "") }
    var format by remember { mutableStateOf(destination?.format ?: ExportFormat.OTLP) }
    var signals by remember { mutableStateOf(destination?.signals ?: listOf(SignalType.METRICS)) }
    var authType by remember { mutableStateOf(destination?.authType ?: AuthType.NONE) }
    var authValue by remember { mutableStateOf("") } // Don't pre-fill auth values
    var authHeader by remember { mutableStateOf(destination?.authHeader ?: "") }
    var intervalSeconds by remember { mutableStateOf(destination?.intervalSeconds?.toString() ?: "60") }
    var enabled by remember { mutableStateOf(destination?.enabled ?: true) }

    var formatExpanded by remember { mutableStateOf(false) }
    var authTypeExpanded by remember { mutableStateOf(false) }

    val isValid = name.isNotBlank() && endpoint.isNotBlank() && signals.isNotEmpty()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(if (destination == null) "Add Export Destination" else "Edit Destination")
        },
        text = {
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                // Name field
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it },
                    label = { Text("Name") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                // Endpoint field
                OutlinedTextField(
                    value = endpoint,
                    onValueChange = { endpoint = it },
                    label = { Text("Endpoint URL") },
                    placeholder = { Text("https://otlp.example.com/v1") },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth()
                )

                // Format dropdown
                ExposedDropdownMenuBox(
                    expanded = formatExpanded,
                    onExpandedChange = { formatExpanded = it }
                ) {
                    OutlinedTextField(
                        value = format.name,
                        onValueChange = {},
                        label = { Text("Format") },
                        readOnly = true,
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = formatExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor()
                    )
                    ExposedDropdownMenu(
                        expanded = formatExpanded,
                        onDismissRequest = { formatExpanded = false }
                    ) {
                        ExportFormat.entries.forEach { f ->
                            DropdownMenuItem(
                                text = { Text(f.name) },
                                onClick = {
                                    format = f
                                    formatExpanded = false
                                }
                            )
                        }
                    }
                }

                // Signals checkboxes
                Text(
                    text = "Signals",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                SignalType.entries.forEach { signal ->
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Checkbox(
                            checked = signal in signals,
                            onCheckedChange = { checked ->
                                signals = if (checked) signals + signal else signals - signal
                            }
                        )
                        Text(signal.name)
                    }
                }

                // Auth type dropdown
                ExposedDropdownMenuBox(
                    expanded = authTypeExpanded,
                    onExpandedChange = { authTypeExpanded = it }
                ) {
                    OutlinedTextField(
                        value = authType.name,
                        onValueChange = {},
                        label = { Text("Auth Type") },
                        readOnly = true,
                        trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = authTypeExpanded) },
                        modifier = Modifier
                            .fillMaxWidth()
                            .menuAnchor()
                    )
                    ExposedDropdownMenu(
                        expanded = authTypeExpanded,
                        onDismissRequest = { authTypeExpanded = false }
                    ) {
                        AuthType.entries.forEach { a ->
                            DropdownMenuItem(
                                text = { Text(a.name) },
                                onClick = {
                                    authType = a
                                    authTypeExpanded = false
                                }
                            )
                        }
                    }
                }

                // Auth fields (conditional)
                when (authType) {
                    AuthType.BEARER -> {
                        OutlinedTextField(
                            value = authValue,
                            onValueChange = { authValue = it },
                            label = { Text("Bearer Token") },
                            singleLine = true,
                            visualTransformation = PasswordVisualTransformation(),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    AuthType.BASIC -> {
                        OutlinedTextField(
                            value = authValue,
                            onValueChange = { authValue = it },
                            label = { Text("Credentials (user:password)") },
                            singleLine = true,
                            visualTransformation = PasswordVisualTransformation(),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    AuthType.HEADER -> {
                        OutlinedTextField(
                            value = authHeader,
                            onValueChange = { authHeader = it },
                            label = { Text("Header Name") },
                            placeholder = { Text("X-API-Key") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth()
                        )
                        OutlinedTextField(
                            value = authValue,
                            onValueChange = { authValue = it },
                            label = { Text("Header Value") },
                            singleLine = true,
                            visualTransformation = PasswordVisualTransformation(),
                            modifier = Modifier.fillMaxWidth()
                        )
                    }
                    AuthType.NONE -> {}
                }

                // Interval field
                OutlinedTextField(
                    value = intervalSeconds,
                    onValueChange = { intervalSeconds = it.filter { c -> c.isDigit() } },
                    label = { Text("Push Interval (seconds)") },
                    singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth()
                )

                // Enabled switch
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("Enabled")
                    Switch(
                        checked = enabled,
                        onCheckedChange = { enabled = it }
                    )
                }
            }
        },
        confirmButton = {
            TextButton(
                onClick = {
                    onSave(
                        ExportDestinationCreate(
                            name = name,
                            endpoint = endpoint,
                            format = format,
                            signals = signals,
                            authType = authType,
                            authValue = authValue.takeIf { it.isNotBlank() },
                            authHeader = authHeader.takeIf { it.isNotBlank() },
                            intervalSeconds = intervalSeconds.toIntOrNull() ?: 60,
                            enabled = enabled
                        )
                    )
                },
                enabled = isValid
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) {
                Text("Cancel")
            }
        }
    )
}

// Helper functions

private fun getCognitiveStateColor(state: String): Color {
    val semantic = SemanticColors.Default
    return when (state.uppercase()) {
        "WORK" -> semantic.success
        "PLAY" -> semantic.info
        "SOLITUDE", "DREAM" -> semantic.warning
        "WAKEUP", "SHUTDOWN" -> Color(0xFFF97316) // Orange for transitional states
        else -> Color.Gray
    }
}

private fun getUsageColor(percent: Int): Color {
    val semantic = SemanticColors.Default
    return when {
        percent < 50 -> semantic.success
        percent < 80 -> semantic.warning
        else -> semantic.error
    }
}

// Data classes

/**
 * Telemetry data model
 * Matches SystemOverviewData from TelemetryFragment.kt
 */
data class TelemetryData(
    val healthyServices: Int = 0,
    val totalServices: Int = 0,
    val cognitiveState: String = "WORK",
    val cpuPercent: Int = 0,
    val memoryMb: Int = 0,
    val diskUsedMb: Double = 0.0,
    val messagesProcessed24h: Int = 0,
    val tasksCompleted24h: Int = 0,
    val errors24h: Int = 0,
    val serviceHealthItems: List<ServiceHealthItem> = emptyList()
)

data class ServiceHealthItem(
    val name: String,
    val healthy: Boolean,
    val status: String
)
