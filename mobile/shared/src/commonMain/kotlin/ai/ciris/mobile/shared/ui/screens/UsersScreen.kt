package ai.ciris.mobile.shared.ui.screens

import ai.ciris.api.models.APIRole
import ai.ciris.api.models.UserDetail
import ai.ciris.api.models.UserSummary
import ai.ciris.api.models.WARole
import ai.ciris.mobile.shared.viewmodels.UsersFilter
import ai.ciris.mobile.shared.viewmodels.UsersPagination
import ai.ciris.mobile.shared.viewmodels.UsersScreenState
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Clear
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp

/**
 * Users management screen.
 *
 * Features:
 * - User list with pagination
 * - Search and filters (role, auth type, status)
 * - User details panel
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun UsersScreen(
    state: UsersScreenState,
    onRefresh: () -> Unit,
    onSearch: (String) -> Unit,
    onFilterChange: (UsersFilter) -> Unit,
    onSelectUser: (String) -> Unit,
    onClearSelection: () -> Unit,
    onNextPage: () -> Unit,
    onPreviousPage: () -> Unit,
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showFilters by remember { mutableStateOf(false) }
    var searchQuery by remember { mutableStateOf(state.filter.search) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Users") },
                navigationIcon = {
                    IconButton(onClick = onNavigateBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(onClick = { showFilters = !showFilters }) {
                        Icon(
                            Icons.Filled.Search,
                            contentDescription = "Filters",
                            tint = if (hasActiveFilters(state.filter))
                                MaterialTheme.colorScheme.primary
                            else
                                MaterialTheme.colorScheme.onSurface
                        )
                    }
                    IconButton(onClick = onRefresh, enabled = !state.isLoading) {
                        Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
                )
            )
        },
        modifier = modifier
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Search bar
            SearchBar(
                query = searchQuery,
                onQueryChange = { searchQuery = it },
                onSearch = { onSearch(searchQuery) },
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(horizontal = 16.dp, vertical = 8.dp)
            )

            // Filter chips (when expanded)
            if (showFilters) {
                FilterChipsRow(
                    filter = state.filter,
                    onFilterChange = onFilterChange,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp)
                )
            }

            // Loading indicator
            if (state.isLoading) {
                LinearProgressIndicator(
                    modifier = Modifier.fillMaxWidth()
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

            // Stats row
            if (state.pagination.totalItems > 0) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "${state.pagination.totalItems} users",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Text(
                        text = "Page ${state.pagination.page} of ${state.pagination.totalPages}",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }

            // User list
            Box(modifier = Modifier.weight(1f)) {
                if (state.users.isEmpty() && !state.isLoading) {
                    // Empty state
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .padding(32.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Icon(
                            Icons.Filled.Person,
                            contentDescription = null,
                            modifier = Modifier.size(64.dp),
                            tint = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(16.dp))
                        Text(
                            text = if (hasActiveFilters(state.filter)) "No users match your filters"
                            else "No users found",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(16.dp),
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        items(state.users, key = { it.userId }) { user ->
                            UserListItem(
                                user = user,
                                isSelected = state.selectedUser?.userId == user.userId,
                                onClick = { onSelectUser(user.userId) }
                            )
                        }
                    }
                }
            }

            // Pagination controls
            if (state.pagination.totalPages > 1) {
                PaginationControls(
                    pagination = state.pagination,
                    onPrevious = onPreviousPage,
                    onNext = onNextPage,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp)
                )
            }
        }

        // User details bottom sheet
        state.selectedUser?.let { user ->
            ModalBottomSheet(
                onDismissRequest = onClearSelection,
                sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
            ) {
                UserDetailsPanel(
                    user = user,
                    isLoading = state.isLoadingDetails,
                    onClose = onClearSelection
                )
            }
        }
    }
}

@Composable
private fun SearchBar(
    query: String,
    onQueryChange: (String) -> Unit,
    onSearch: () -> Unit,
    modifier: Modifier = Modifier
) {
    OutlinedTextField(
        value = query,
        onValueChange = onQueryChange,
        placeholder = { Text("Search users...") },
        leadingIcon = {
            Icon(Icons.Filled.Search, contentDescription = "Search")
        },
        trailingIcon = {
            if (query.isNotEmpty()) {
                IconButton(onClick = { onQueryChange(""); onSearch() }) {
                    Icon(Icons.Filled.Clear, contentDescription = "Clear")
                }
            }
        },
        singleLine = true,
        modifier = modifier,
        keyboardActions = androidx.compose.foundation.text.KeyboardActions(
            onSearch = { onSearch() }
        )
    )
}

@Composable
private fun FilterChipsRow(
    filter: UsersFilter,
    onFilterChange: (UsersFilter) -> Unit,
    modifier: Modifier = Modifier
) {
    Column(modifier = modifier) {
        // API Role filter
        Text(
            text = "API Role",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 4.dp)
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            FilterChip(
                selected = filter.apiRole == null,
                onClick = { onFilterChange(filter.copy(apiRole = null)) },
                label = { Text("All") }
            )
            APIRole.entries.forEach { role ->
                FilterChip(
                    selected = filter.apiRole == role,
                    onClick = { onFilterChange(filter.copy(apiRole = role)) },
                    label = { Text(role.value) }
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Auth type filter
        Text(
            text = "Auth Type",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 4.dp)
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            FilterChip(
                selected = filter.authType == null,
                onClick = { onFilterChange(filter.copy(authType = null)) },
                label = { Text("All") }
            )
            listOf("password", "oauth", "api_key").forEach { authType ->
                FilterChip(
                    selected = filter.authType == authType,
                    onClick = { onFilterChange(filter.copy(authType = authType)) },
                    label = { Text(authType.replace("_", " ").replaceFirstChar { it.uppercase() }) }
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Status filter
        Text(
            text = "Status",
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 4.dp)
        )
        Row(
            modifier = Modifier.horizontalScroll(rememberScrollState()),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            FilterChip(
                selected = filter.isActive == null,
                onClick = { onFilterChange(filter.copy(isActive = null)) },
                label = { Text("All") }
            )
            FilterChip(
                selected = filter.isActive == true,
                onClick = { onFilterChange(filter.copy(isActive = true)) },
                label = { Text("Active") }
            )
            FilterChip(
                selected = filter.isActive == false,
                onClick = { onFilterChange(filter.copy(isActive = false)) },
                label = { Text("Inactive") }
            )
        }
    }
}

@Composable
private fun UserListItem(
    user: UserSummary,
    isSelected: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        colors = CardDefaults.cardColors(
            containerColor = if (isSelected)
                MaterialTheme.colorScheme.primaryContainer
            else
                MaterialTheme.colorScheme.surface
        ),
        elevation = CardDefaults.cardElevation(defaultElevation = if (isSelected) 4.dp else 1.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            // Avatar
            UserAvatar(
                username = user.username,
                photoUrl = user.oauthPicture,
                isActive = user.isActive ?: true
            )

            // User info
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = user.username,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )
                user.oauthEmail?.let { email ->
                    Text(
                        text = email,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // Auth type badge
                    RoleBadge(
                        text = user.authType,
                        color = getAuthTypeColor(user.authType)
                    )
                    // API Role badge
                    RoleBadge(
                        text = user.apiRole.value,
                        color = getApiRoleColor(user.apiRole)
                    )
                    // WA Role badge (if present)
                    user.waRole?.let { waRole ->
                        RoleBadge(
                            text = "WA:${waRole.value}",
                            color = getWaRoleColor(waRole)
                        )
                    }
                }
            }

            // Status indicator
            Box(
                modifier = Modifier
                    .size(12.dp)
                    .clip(CircleShape)
                    .background(
                        if (user.isActive == true) Color(0xFF10B981)
                        else Color(0xFFEF4444)
                    )
            )
        }
    }
}

@Composable
private fun UserAvatar(
    username: String,
    photoUrl: String?,
    isActive: Boolean,
    modifier: Modifier = Modifier
) {
    Box(
        modifier = modifier
            .size(48.dp)
            .clip(CircleShape)
            .background(
                if (isActive) MaterialTheme.colorScheme.primaryContainer
                else MaterialTheme.colorScheme.surfaceVariant
            ),
        contentAlignment = Alignment.Center
    ) {
        // TODO: Load photo from URL if available
        Text(
            text = username.take(2).uppercase(),
            style = MaterialTheme.typography.titleMedium,
            color = if (isActive) MaterialTheme.colorScheme.onPrimaryContainer
            else MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

@Composable
private fun RoleBadge(
    text: String,
    color: Color,
    modifier: Modifier = Modifier
) {
    Surface(
        modifier = modifier,
        shape = RoundedCornerShape(4.dp),
        color = color.copy(alpha = 0.15f)
    ) {
        Text(
            text = text.uppercase(),
            modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp),
            style = MaterialTheme.typography.labelSmall,
            color = color,
            fontWeight = FontWeight.Bold
        )
    }
}

@Composable
private fun UserDetailsPanel(
    user: UserDetail,
    isLoading: Boolean,
    onClose: () -> Unit,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier
            .fillMaxWidth()
            .padding(16.dp)
    ) {
        // Header
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                text = "User Details",
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
            IconButton(onClick = onClose) {
                Icon(Icons.Filled.Close, contentDescription = "Close")
            }
        }

        if (isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp),
                contentAlignment = Alignment.Center
            ) {
                CircularProgressIndicator()
            }
        } else {
            Spacer(modifier = Modifier.height(16.dp))

            // User header
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                UserAvatar(
                    username = user.username,
                    photoUrl = user.oauthPicture,
                    isActive = user.isActive ?: true,
                    modifier = Modifier.size(64.dp)
                )
                Column {
                    Text(
                        text = user.username,
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    user.oauthEmail?.let { email ->
                        Text(
                            text = email,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(24.dp))

            // Details grid
            DetailRow(label = "User ID", value = user.userId)
            DetailRow(label = "Auth Type", value = user.authType)
            DetailRow(label = "API Role", value = user.apiRole.value)
            user.waRole?.let {
                DetailRow(label = "WA Role", value = it.value)
            }
            user.waId?.let {
                DetailRow(label = "WA ID", value = it)
            }
            DetailRow(label = "Status", value = if (user.isActive == true) "Active" else "Inactive")
            DetailRow(label = "Created", value = formatTimestamp(user.createdAt.toString()))
            user.lastLogin?.let {
                DetailRow(label = "Last Login", value = formatTimestamp(it.toString()))
            }

            // Permissions
            if (user.permissions.isNotEmpty()) {
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "Permissions",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(8.dp))
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    user.permissions.forEach { permission ->
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = MaterialTheme.colorScheme.secondaryContainer
                        ) {
                            Text(
                                text = permission,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onSecondaryContainer
                            )
                        }
                    }
                }
            }

            // Custom permissions
            user.customPermissions?.takeIf { it.isNotEmpty() }?.let { customPerms ->
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "Custom Permissions",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(8.dp))
                FlowRow(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(4.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp)
                ) {
                    customPerms.forEach { permission ->
                        Surface(
                            shape = RoundedCornerShape(4.dp),
                            color = MaterialTheme.colorScheme.tertiaryContainer
                        ) {
                            Text(
                                text = permission,
                                modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
                                style = MaterialTheme.typography.labelSmall,
                                color = MaterialTheme.colorScheme.onTertiaryContainer
                            )
                        }
                    }
                }
            }

            // Linked OAuth accounts
            user.linkedOauthAccounts?.takeIf { it.isNotEmpty() }?.let { accounts ->
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "Linked OAuth Accounts",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(8.dp))
                accounts.forEach { account ->
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        shape = RoundedCornerShape(8.dp),
                        color = MaterialTheme.colorScheme.surfaceVariant
                    ) {
                        Row(
                            modifier = Modifier.padding(12.dp),
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = account.provider.uppercase(),
                                style = MaterialTheme.typography.labelMedium,
                                fontWeight = FontWeight.Bold
                            )
                            account.accountName?.let { name ->
                                Text(
                                    text = name,
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }
                }
            }

            Spacer(modifier = Modifier.height(32.dp))
        }
    }
}

@Composable
private fun DetailRow(
    label: String,
    value: String,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 4.dp),
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
            fontWeight = FontWeight.Medium
        )
    }
}

@Composable
private fun PaginationControls(
    pagination: UsersPagination,
    onPrevious: () -> Unit,
    onNext: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier,
        horizontalArrangement = Arrangement.Center,
        verticalAlignment = Alignment.CenterVertically
    ) {
        IconButton(
            onClick = onPrevious,
            enabled = pagination.page > 1
        ) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, contentDescription = "Previous")
        }

        Text(
            text = "${pagination.page} / ${pagination.totalPages}",
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(horizontal = 16.dp)
        )

        IconButton(
            onClick = onNext,
            enabled = pagination.page < pagination.totalPages
        ) {
            Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, contentDescription = "Next")
        }
    }
}

// Helper functions

private fun hasActiveFilters(filter: UsersFilter): Boolean {
    return filter.search.isNotBlank() ||
            filter.authType != null ||
            filter.apiRole != null ||
            filter.waRole != null ||
            filter.isActive != null
}

private fun getAuthTypeColor(authType: String): Color {
    return when (authType) {
        "oauth" -> Color(0xFF3B82F6) // Blue
        "password" -> Color(0xFF10B981) // Green
        "api_key" -> Color(0xFFF59E0B) // Amber
        else -> Color(0xFF6B7280) // Gray
    }
}

private fun getApiRoleColor(role: APIRole): Color {
    return when (role) {
        APIRole.SYSTEM_ADMIN -> Color(0xFFEF4444) // Red
        APIRole.AUTHORITY -> Color(0xFF8B5CF6) // Purple
        APIRole.ADMIN -> Color(0xFFF59E0B) // Amber
        APIRole.OBSERVER -> Color(0xFF10B981) // Green
        APIRole.SERVICE_ACCOUNT -> Color(0xFF6B7280) // Gray
    }
}

private fun getWaRoleColor(role: WARole): Color {
    return when (role) {
        WARole.ROOT -> Color(0xFFEF4444) // Red
        WARole.AUTHORITY -> Color(0xFF8B5CF6) // Purple
        WARole.OBSERVER -> Color(0xFF10B981) // Green
    }
}

private fun formatTimestamp(timestamp: String): String {
    return try {
        val date = timestamp.substringBefore("T")
        val time = timestamp.substringAfter("T").substringBefore(".").substringBefore("Z")
        "$date $time"
    } catch (e: Exception) {
        timestamp
    }
}

@Composable
private fun FlowRow(
    modifier: Modifier = Modifier,
    horizontalArrangement: Arrangement.Horizontal = Arrangement.Start,
    verticalArrangement: Arrangement.Vertical = Arrangement.Top,
    content: @Composable () -> Unit
) {
    // Simple implementation using Row with wrap
    // In production, use the FlowRow from Compose Foundation 1.4+
    Row(
        modifier = modifier.horizontalScroll(rememberScrollState()),
        horizontalArrangement = horizontalArrangement
    ) {
        content()
    }
}
