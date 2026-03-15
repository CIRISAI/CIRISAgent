package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.api.SOPMetadataData
import ai.ciris.mobile.shared.api.TicketData
import ai.ciris.mobile.shared.api.TicketStatsData
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.TicketsFilter
import ai.ciris.mobile.shared.viewmodels.TicketsScreenState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog

/**
 * Tickets management screen for viewing and managing workflow tickets.
 *
 * Features:
 * - Ticket list with status, priority, and deadline
 * - Statistics summary (pending, in-progress, completed)
 * - Filtering by status and type
 * - Expandable ticket details
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TicketsScreen(
    state: TicketsScreenState,
    onRefresh: () -> Unit,
    onFilterChange: (TicketsFilter) -> Unit,
    onSelectTicket: (TicketData?) -> Unit,
    onNavigateBack: () -> Unit,
    onShowCreateDialog: (String) -> Unit = {},
    onHideCreateDialog: () -> Unit = {},
    onCreateTicket: (sop: String, email: String, userIdentifier: String?, notes: String?) -> Unit = { _, _, _, _ -> },
    modifier: Modifier = Modifier
) {
    var showFilters by remember { mutableStateOf(false) }
    var expandedTicketId by remember { mutableStateOf<String?>(null) }

    // Create ticket dialog
    if (state.showCreateDialog && state.selectedSopForCreate != null) {
        val sopMetadata = state.sopMetadata[state.selectedSopForCreate]
        CreateTicketDialog(
            sop = state.selectedSopForCreate,
            sopMetadata = sopMetadata,
            isCreating = state.isCreatingTicket,
            onDismiss = onHideCreateDialog,
            onConfirm = { email, userIdentifier, notes ->
                onCreateTicket(state.selectedSopForCreate, email, userIdentifier, notes)
            }
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Tickets & Privacy") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_tickets_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.ArrowBack,
                            contentDescription = "Back"
                        )
                    }
                },
                actions = {
                    TextButton(
                        onClick = { showFilters = !showFilters },
                        modifier = Modifier.testableClickable("btn_tickets_toggle_filters") { showFilters = !showFilters }
                    ) {
                        Text(
                            if (showFilters) "Hide Filters" else "Filters",
                            color = MaterialTheme.colorScheme.onPrimary
                        )
                    }
                    IconButton(
                        onClick = onRefresh,
                        enabled = !state.isLoading,
                        modifier = Modifier.testableClickable("btn_tickets_refresh") { onRefresh() }
                    ) {
                        Icon(
                            imageVector = Icons.Filled.Refresh,
                            contentDescription = "Refresh"
                        )
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        }
    ) { paddingValues ->
        Column(
            modifier = modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Stats cards
            state.stats?.let { stats ->
                TicketStatsRow(stats = stats)
            }

            // SOP Profiles section
            if (state.sopMetadata.isNotEmpty()) {
                SOPProfilesSection(
                    sopMetadata = state.sopMetadata,
                    onCreateTicket = onShowCreateDialog
                )
            }

            // Filters section
            if (showFilters) {
                TicketFiltersSection(
                    filter = state.filter,
                    supportedSops = state.supportedSops,
                    onFilterChange = onFilterChange
                )
            }

            // Error message
            state.error?.let { error ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.errorContainer
                    )
                ) {
                    Text(
                        text = error,
                        modifier = Modifier.padding(16.dp),
                        color = MaterialTheme.colorScheme.onErrorContainer
                    )
                }
            }

            // Tickets list
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = 8.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                if (state.isLoading && state.tickets.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            CircularProgressIndicator()
                        }
                    }
                } else if (state.tickets.isEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(32.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(
                                text = "No tickets found",
                                style = MaterialTheme.typography.bodyLarge,
                                color = MaterialTheme.colorScheme.onSurfaceVariant
                            )
                        }
                    }
                } else {
                    items(state.tickets, key = { it.ticketId }) { ticket ->
                        TicketCard(
                            ticket = ticket,
                            isExpanded = expandedTicketId == ticket.ticketId,
                            onToggleExpand = {
                                expandedTicketId = if (expandedTicketId == ticket.ticketId) null else ticket.ticketId
                            }
                        )
                    }
                }

                // Loading indicator at bottom
                if (state.isLoading && state.tickets.isNotEmpty()) {
                    item {
                        Box(
                            modifier = Modifier
                                .fillMaxWidth()
                                .padding(16.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            CircularProgressIndicator(modifier = Modifier.size(24.dp))
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun TicketStatsRow(stats: TicketStatsData) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        StatCard(
            label = "Pending",
            value = stats.pending.toString(),
            color = Color(0xFFFFA000),
            modifier = Modifier.weight(1f)
        )
        StatCard(
            label = "In Progress",
            value = stats.inProgress.toString(),
            color = Color(0xFF2196F3),
            modifier = Modifier.weight(1f)
        )
        StatCard(
            label = "Completed",
            value = stats.completed.toString(),
            color = Color(0xFF4CAF50),
            modifier = Modifier.weight(1f)
        )
        if (stats.urgent > 0) {
            StatCard(
                label = "Urgent",
                value = stats.urgent.toString(),
                color = Color(0xFFF44336),
                modifier = Modifier.weight(1f)
            )
        }
    }
}

@Composable
private fun StatCard(
    label: String,
    value: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier,
        colors = CardDefaults.cardColors(
            containerColor = color.copy(alpha = 0.1f)
        )
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(
                text = value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
                color = color
            )
            Text(
                text = label,
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TicketFiltersSection(
    filter: TicketsFilter,
    supportedSops: List<String>,
    onFilterChange: (TicketsFilter) -> Unit
) {
    var statusExpanded by remember { mutableStateOf(false) }
    var typeExpanded by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp)
    ) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            // Status filter
            ExposedDropdownMenuBox(
                expanded = statusExpanded,
                onExpandedChange = { statusExpanded = it },
                modifier = Modifier.weight(1f)
            ) {
                OutlinedTextField(
                    value = filter.status?.replaceFirstChar { it.uppercase() } ?: "All Status",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Status") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = statusExpanded) },
                    modifier = Modifier.menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = statusExpanded,
                    onDismissRequest = { statusExpanded = false }
                ) {
                    DropdownMenuItem(
                        text = { Text("All Status") },
                        onClick = {
                            onFilterChange(filter.copy(status = null))
                            statusExpanded = false
                        }
                    )
                    listOf("pending", "in_progress", "completed", "failed", "cancelled").forEach { status ->
                        DropdownMenuItem(
                            text = { Text(status.replace("_", " ").replaceFirstChar { it.uppercase() }) },
                            onClick = {
                                onFilterChange(filter.copy(status = status))
                                statusExpanded = false
                            }
                        )
                    }
                }
            }

            // Type filter
            ExposedDropdownMenuBox(
                expanded = typeExpanded,
                onExpandedChange = { typeExpanded = it },
                modifier = Modifier.weight(1f)
            ) {
                OutlinedTextField(
                    value = filter.ticketType?.uppercase() ?: "All Types",
                    onValueChange = {},
                    readOnly = true,
                    label = { Text("Type") },
                    trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded = typeExpanded) },
                    modifier = Modifier.menuAnchor()
                )
                ExposedDropdownMenu(
                    expanded = typeExpanded,
                    onDismissRequest = { typeExpanded = false }
                ) {
                    DropdownMenuItem(
                        text = { Text("All Types") },
                        onClick = {
                            onFilterChange(filter.copy(ticketType = null))
                            typeExpanded = false
                        }
                    )
                    listOf("dsar", "access", "delete", "export", "correct").forEach { type ->
                        DropdownMenuItem(
                            text = { Text(type.uppercase()) },
                            onClick = {
                                onFilterChange(filter.copy(ticketType = type))
                                typeExpanded = false
                            }
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun TicketCard(
    ticket: TicketData,
    isExpanded: Boolean,
    onToggleExpand: () -> Unit
) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onToggleExpand),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surface
        )
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Header row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Ticket ID
                    Text(
                        text = ticket.ticketId,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    // Urgent badge
                    if (ticket.isUrgent) {
                        Badge(
                            containerColor = Color(0xFFF44336)
                        ) {
                            Text("URGENT", fontSize = 10.sp)
                        }
                    }
                }
                // Expand/collapse icon
                Icon(
                    imageVector = if (isExpanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                    contentDescription = if (isExpanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Status and type row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                // Status badge
                StatusBadge(status = ticket.status)
                // Type badge
                Badge(
                    containerColor = MaterialTheme.colorScheme.secondaryContainer
                ) {
                    Text(
                        text = ticket.displayType,
                        color = MaterialTheme.colorScheme.onSecondaryContainer,
                        fontSize = 12.sp
                    )
                }
                // SOP badge
                Badge(
                    containerColor = MaterialTheme.colorScheme.tertiaryContainer
                ) {
                    Text(
                        text = ticket.sop,
                        color = MaterialTheme.colorScheme.onTertiaryContainer,
                        fontSize = 12.sp
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Email
            Text(
                text = ticket.email,
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            // Submitted time
            Text(
                text = "Submitted: ${formatTimestamp(ticket.submittedAt)}",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )

            // Expanded details
            if (isExpanded) {
                Spacer(modifier = Modifier.height(12.dp))
                HorizontalDivider()
                Spacer(modifier = Modifier.height(12.dp))

                // Priority
                DetailRow(label = "Priority", value = ticket.priority.toString())

                // Deadline
                ticket.deadline?.let {
                    DetailRow(label = "Deadline", value = formatTimestamp(it))
                }

                // User identifier
                ticket.userIdentifier?.let {
                    DetailRow(label = "User ID", value = it)
                }

                // Last updated
                DetailRow(label = "Last Updated", value = formatTimestamp(ticket.lastUpdated))

                // Completed at
                ticket.completedAt?.let {
                    DetailRow(label = "Completed", value = formatTimestamp(it))
                }

                // Notes
                ticket.notes?.let {
                    Spacer(modifier = Modifier.height(8.dp))
                    Text(
                        text = "Notes",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.primary
                    )
                    Text(
                        text = it,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                // Automated badge
                if (ticket.automated) {
                    Spacer(modifier = Modifier.height(8.dp))
                    Badge(
                        containerColor = MaterialTheme.colorScheme.primaryContainer
                    ) {
                        Text(
                            text = "Automated",
                            color = MaterialTheme.colorScheme.onPrimaryContainer,
                            fontSize = 12.sp
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusBadge(status: String) {
    val (color, text) = when (status) {
        "pending" -> Pair(Color(0xFFFFA000), "Pending")
        "in_progress" -> Pair(Color(0xFF2196F3), "In Progress")
        "completed" -> Pair(Color(0xFF4CAF50), "Completed")
        "failed" -> Pair(Color(0xFFF44336), "Failed")
        "cancelled" -> Pair(Color(0xFF9E9E9E), "Cancelled")
        else -> Pair(Color(0xFF9E9E9E), status.replaceFirstChar { it.uppercase() })
    }

    Badge(containerColor = color) {
        Text(text = text, fontSize = 12.sp)
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 2.dp),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodySmall,
            fontWeight = FontWeight.Medium
        )
    }
}

private fun formatTimestamp(timestamp: String): String {
    // Simple format for now - could use kotlinx-datetime for proper formatting
    return try {
        if (timestamp.contains("T")) {
            val parts = timestamp.split("T")
            val date = parts[0]
            val time = parts.getOrNull(1)?.substringBefore(".")?.take(5) ?: ""
            "$date $time"
        } else {
            timestamp
        }
    } catch (e: Exception) {
        timestamp
    }
}

// ===== SOP Profiles Section =====

@Composable
private fun SOPProfilesSection(
    sopMetadata: Map<String, SOPMetadataData>,
    onCreateTicket: (String) -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 16.dp, vertical = 8.dp)
    ) {
        Text(
            text = "Data Privacy Request Types",
            style = MaterialTheme.typography.titleSmall,
            fontWeight = FontWeight.Bold,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.padding(bottom = 8.dp)
        )

        LazyRow(
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(end = 8.dp)
        ) {
            items(sopMetadata.values.toList(), key = { it.sop }) { metadata ->
                SOPCard(
                    metadata = metadata,
                    onCreateTicket = { onCreateTicket(metadata.sop) }
                )
            }
        }
    }
}

@Composable
private fun SOPCard(
    metadata: SOPMetadataData,
    onCreateTicket: () -> Unit
) {
    Card(
        modifier = Modifier
            .width(200.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Column(
            modifier = Modifier.padding(12.dp)
        ) {
            // Header with GDPR badge
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = metadata.displayName,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
            }

            // GDPR Article badge
            metadata.gdprArticle?.let { article ->
                Badge(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    modifier = Modifier.padding(top = 4.dp)
                ) {
                    Text(
                        text = article,
                        fontSize = 10.sp,
                        color = MaterialTheme.colorScheme.onPrimaryContainer
                    )
                }
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Description
            Text(
                text = metadata.description.ifEmpty { "Process ${metadata.ticketType} requests" },
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )

            Spacer(modifier = Modifier.height(8.dp))

            // Info row
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween
            ) {
                // Deadline
                metadata.deadlineDays?.let { days ->
                    Text(
                        text = "${days}d deadline",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.tertiary
                    )
                }
                // Stages
                Text(
                    text = "${metadata.stageCount} stages",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            Spacer(modifier = Modifier.height(8.dp))

            // Create button
            Button(
                onClick = onCreateTicket,
                modifier = Modifier.fillMaxWidth(),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)
            ) {
                Icon(
                    imageVector = Icons.Filled.Add,
                    contentDescription = null,
                    modifier = Modifier.size(16.dp)
                )
                Spacer(modifier = Modifier.width(4.dp))
                Text("Create", fontSize = 12.sp)
            }
        }
    }
}

// ===== Create Ticket Dialog =====

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun CreateTicketDialog(
    sop: String,
    sopMetadata: SOPMetadataData?,
    isCreating: Boolean,
    onDismiss: () -> Unit,
    onConfirm: (email: String, userIdentifier: String?, notes: String?) -> Unit
) {
    var email by remember { mutableStateOf("") }
    var userIdentifier by remember { mutableStateOf("") }
    var notes by remember { mutableStateOf("") }
    var emailError by remember { mutableStateOf<String?>(null) }

    Dialog(onDismissRequest = { if (!isCreating) onDismiss() }) {
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier.padding(20.dp)
            ) {
                // Header
                Text(
                    text = "Create ${sopMetadata?.displayName ?: sop}",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )

                sopMetadata?.gdprArticle?.let { article ->
                    Text(
                        text = article,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.primary
                    )
                }

                Spacer(modifier = Modifier.height(16.dp))

                // Email field (required)
                OutlinedTextField(
                    value = email,
                    onValueChange = {
                        email = it
                        emailError = null
                    },
                    label = { Text("Email *") },
                    placeholder = { Text("user@example.com") },
                    isError = emailError != null,
                    supportingText = emailError?.let { { Text(it) } },
                    singleLine = true,
                    enabled = !isCreating,
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(12.dp))

                // User Identifier field (optional)
                OutlinedTextField(
                    value = userIdentifier,
                    onValueChange = { userIdentifier = it },
                    label = { Text("User Identifier") },
                    placeholder = { Text("Optional - account ID, username, etc.") },
                    singleLine = true,
                    enabled = !isCreating,
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(12.dp))

                // Notes field (optional)
                OutlinedTextField(
                    value = notes,
                    onValueChange = { notes = it },
                    label = { Text("Notes") },
                    placeholder = { Text("Optional - additional context") },
                    minLines = 2,
                    maxLines = 4,
                    enabled = !isCreating,
                    modifier = Modifier.fillMaxWidth()
                )

                Spacer(modifier = Modifier.height(8.dp))

                // Info about deadline
                sopMetadata?.deadlineDays?.let { days ->
                    Text(
                        text = "This request will have a $days day deadline",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                Spacer(modifier = Modifier.height(20.dp))

                // Buttons
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.End)
                ) {
                    OutlinedButton(
                        onClick = onDismiss,
                        enabled = !isCreating
                    ) {
                        Text("Cancel")
                    }

                    Button(
                        onClick = {
                            // Validate email
                            if (email.isBlank()) {
                                emailError = "Email is required"
                                return@Button
                            }
                            if (!email.contains("@") || !email.contains(".")) {
                                emailError = "Invalid email format"
                                return@Button
                            }
                            onConfirm(
                                email.trim(),
                                userIdentifier.trim().ifEmpty { null },
                                notes.trim().ifEmpty { null }
                            )
                        },
                        enabled = !isCreating
                    ) {
                        if (isCreating) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                        }
                        Text("Create Request")
                    }
                }
            }
        }
    }
}
