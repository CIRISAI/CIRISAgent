package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.platform.DebugLogBuffer
import ai.ciris.mobile.shared.platform.DebugLogEntry
import androidx.compose.animation.*
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Floating debug indicator button that shows error count
 * and expands to full debug console when tapped.
 */
@Composable
fun DebugIndicator(
    onTap: () -> Unit,
    modifier: Modifier = Modifier
) {
    val errorCount by DebugLogBuffer.errorCount.collectAsState()
    val entries by DebugLogBuffer.entries.collectAsState()

    Surface(
        onClick = onTap,
        shape = RoundedCornerShape(20.dp),
        color = when {
            errorCount > 0 -> Color(0xFFFEE2E2)
            else -> Color(0xFFF3F4F6)
        },
        modifier = modifier.height(36.dp)
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp)
        ) {
            Text(
                text = if (errorCount > 0) "🐛" else "📋",
                fontSize = 14.sp
            )
            Text(
                text = "${entries.size}",
                fontSize = 12.sp,
                color = if (errorCount > 0) Color(0xFFDC2626) else Color(0xFF6B7280)
            )
            if (errorCount > 0) {
                Surface(
                    shape = CircleShape,
                    color = Color(0xFFDC2626)
                ) {
                    Text(
                        text = "$errorCount",
                        fontSize = 10.sp,
                        color = Color.White,
                        modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                    )
                }
            }
        }
    }
}

/**
 * Error toast that appears when a new error is logged
 */
@Composable
fun ErrorToast(
    modifier: Modifier = Modifier
) {
    val latestError by DebugLogBuffer.latestError.collectAsState()

    AnimatedVisibility(
        visible = latestError != null,
        enter = slideInVertically(initialOffsetY = { -it }) + fadeIn(),
        exit = slideOutVertically(targetOffsetY = { -it }) + fadeOut(),
        modifier = modifier
    ) {
        Surface(
            shape = RoundedCornerShape(8.dp),
            color = Color(0xFFFEE2E2),
            shadowElevation = 4.dp,
            modifier = Modifier
                .fillMaxWidth()
                .padding(8.dp)
                .clickable { DebugLogBuffer.dismissLatestError() }
        ) {
            Row(
                modifier = Modifier.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text(text = "❌", fontSize = 16.sp)
                Text(
                    text = latestError ?: "",
                    fontSize = 12.sp,
                    color = Color(0xFFDC2626),
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    modifier = Modifier.weight(1f)
                )
                Icon(
                    imageVector = Icons.Default.Close,
                    contentDescription = "Dismiss",
                    tint = Color(0xFFDC2626),
                    modifier = Modifier.size(16.dp)
                )
            }
        }
    }
}

/**
 * Full debug console panel - shows all log entries
 * with filtering and clear functionality.
 */
@Composable
fun DebugConsole(
    isExpanded: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier
) {
    val entries by DebugLogBuffer.entries.collectAsState()
    val errorCount by DebugLogBuffer.errorCount.collectAsState()
    var selectedFilter by remember { mutableStateOf<String?>(null) }
    var searchTag by remember { mutableStateOf("") }

    val filteredEntries = remember(entries, selectedFilter, searchTag) {
        entries.filter { entry ->
            (selectedFilter == null || entry.level == selectedFilter) &&
            (searchTag.isEmpty() || entry.tag.contains(searchTag, ignoreCase = true) ||
             entry.message.contains(searchTag, ignoreCase = true))
        }.reversed() // Most recent first
    }

    AnimatedVisibility(
        visible = isExpanded,
        enter = slideInVertically(initialOffsetY = { it }) + fadeIn(),
        exit = slideOutVertically(targetOffsetY = { it }) + fadeOut(),
        modifier = modifier
    ) {
        Surface(
            shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp),
            color = Color(0xFF1F2937),
            shadowElevation = 8.dp,
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(
                modifier = Modifier.fillMaxWidth()
            ) {
                // Header bar
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Row(
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = "🐛 Debug Console",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Bold,
                            color = Color.White
                        )
                        Text(
                            text = "(${filteredEntries.size}/${entries.size})",
                            fontSize = 12.sp,
                            color = Color(0xFF9CA3AF)
                        )
                        if (errorCount > 0) {
                            Surface(
                                shape = CircleShape,
                                color = Color(0xFFDC2626)
                            ) {
                                Text(
                                    text = "$errorCount errors",
                                    fontSize = 10.sp,
                                    color = Color.White,
                                    modifier = Modifier.padding(horizontal = 6.dp, vertical = 2.dp)
                                )
                            }
                        }
                    }

                    Row(
                        horizontalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        // Clear button
                        IconButton(
                            onClick = {
                                DebugLogBuffer.clear()
                            },
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Delete,
                                contentDescription = "Clear logs",
                                tint = Color(0xFF9CA3AF),
                                modifier = Modifier.size(18.dp)
                            )
                        }
                        // Close button
                        IconButton(
                            onClick = onToggle,
                            modifier = Modifier.size(32.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.KeyboardArrowDown,
                                contentDescription = "Close",
                                tint = Color.White,
                                modifier = Modifier.size(24.dp)
                            )
                        }
                    }
                }

                // Filter chips
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 12.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    FilterChip(
                        selected = selectedFilter == null,
                        onClick = { selectedFilter = null },
                        label = "All"
                    )
                    FilterChip(
                        selected = selectedFilter == "ERROR",
                        onClick = { selectedFilter = if (selectedFilter == "ERROR") null else "ERROR" },
                        label = "❌ Errors"
                    )
                    FilterChip(
                        selected = selectedFilter == "WARN",
                        onClick = { selectedFilter = if (selectedFilter == "WARN") null else "WARN" },
                        label = "⚠️ Warnings"
                    )
                    FilterChip(
                        selected = selectedFilter == "INFO",
                        onClick = { selectedFilter = if (selectedFilter == "INFO") null else "INFO" },
                        label = "ℹ️ Info"
                    )
                    FilterChip(
                        selected = selectedFilter == "DEBUG",
                        onClick = { selectedFilter = if (selectedFilter == "DEBUG") null else "DEBUG" },
                        label = "🔍 Debug"
                    )
                }

                // Search/filter input
                OutlinedTextField(
                    value = searchTag,
                    onValueChange = { searchTag = it },
                    placeholder = {
                        Text(
                            "Filter by tag or message...",
                            color = Color(0xFF6B7280),
                            fontSize = 12.sp
                        )
                    },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 12.dp, vertical = 4.dp)
                        .height(40.dp),
                    textStyle = LocalTextStyle.current.copy(
                        fontSize = 12.sp,
                        color = Color.White
                    ),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = Color(0xFF419CA0),
                        unfocusedBorderColor = Color(0xFF374151),
                        cursorColor = Color.White
                    )
                )

                // Log entries
                val listState = rememberLazyListState()
                LazyColumn(
                    state = listState,
                    modifier = Modifier
                        .fillMaxWidth()
                        .heightIn(max = 300.dp)
                        .padding(horizontal = 8.dp, vertical = 4.dp)
                ) {
                    items(filteredEntries, key = { it.id }) { entry ->
                        LogEntryRow(entry = entry)
                    }

                    if (filteredEntries.isEmpty()) {
                        item {
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .padding(32.dp),
                                contentAlignment = Alignment.Center
                            ) {
                                Text(
                                    text = if (entries.isEmpty()) "No logs yet" else "No matching logs",
                                    fontSize = 12.sp,
                                    color = Color(0xFF6B7280)
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun FilterChip(
    selected: Boolean,
    onClick: () -> Unit,
    label: String,
    modifier: Modifier = Modifier
) {
    Surface(
        onClick = onClick,
        shape = RoundedCornerShape(16.dp),
        color = if (selected) Color(0xFF419CA0) else Color(0xFF374151),
        modifier = modifier
    ) {
        Text(
            text = label,
            fontSize = 11.sp,
            color = Color.White,
            modifier = Modifier.padding(horizontal = 10.dp, vertical = 4.dp)
        )
    }
}

@Composable
private fun LogEntryRow(
    entry: DebugLogEntry,
    modifier: Modifier = Modifier
) {
    var expanded by remember { mutableStateOf(false) }

    Surface(
        onClick = { expanded = !expanded },
        color = when (entry.level) {
            "ERROR" -> Color(0xFF450A0A).copy(alpha = 0.5f)
            "WARN" -> Color(0xFF422006).copy(alpha = 0.5f)
            else -> Color.Transparent
        },
        shape = RoundedCornerShape(4.dp),
        modifier = modifier
            .fillMaxWidth()
            .padding(vertical = 1.dp)
    ) {
        Column(
            modifier = Modifier.padding(horizontal = 8.dp, vertical = 4.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                // Time
                Text(
                    text = entry.formattedTime,
                    fontSize = 10.sp,
                    color = Color(0xFF6B7280),
                    fontFamily = FontFamily.Monospace
                )
                // Emoji
                Text(
                    text = entry.emoji,
                    fontSize = 12.sp
                )
                // Tag
                Text(
                    text = entry.tag,
                    fontSize = 10.sp,
                    fontWeight = FontWeight.Medium,
                    color = when (entry.level) {
                        "ERROR" -> Color(0xFFFCA5A5)
                        "WARN" -> Color(0xFFFCD34D)
                        "INFO" -> Color(0xFF93C5FD)
                        else -> Color(0xFF9CA3AF)
                    },
                    maxLines = 1
                )
                // Expand icon
                Icon(
                    imageVector = if (expanded) Icons.Default.KeyboardArrowUp else Icons.Default.KeyboardArrowDown,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    tint = Color(0xFF6B7280),
                    modifier = Modifier.size(14.dp)
                )
            }

            // Message - truncated unless expanded
            Text(
                text = entry.message,
                fontSize = 11.sp,
                color = Color(0xFFE5E7EB),
                fontFamily = FontFamily.Monospace,
                maxLines = if (expanded) Int.MAX_VALUE else 2,
                overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(start = 64.dp, top = 2.dp)
            )
        }
    }
}
