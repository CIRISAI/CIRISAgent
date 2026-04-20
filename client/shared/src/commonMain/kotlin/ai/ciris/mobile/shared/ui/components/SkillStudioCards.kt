package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import ai.ciris.mobile.shared.ui.icons.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Expandable card header component.
 */
@Composable
fun ExpandableCardHeader(
    icon: @Composable () -> Unit,
    title: String,
    count: Int? = null,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier
) {
    Row(
        modifier = modifier
            .fillMaxWidth()
            .clickable(onClick = onToggle)
            .padding(16.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Row(
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            icon()
            Text(
                text = if (count != null) "$title ($count)" else title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.Bold
            )
        }
        Icon(
            imageVector = if (isExpanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
            contentDescription = if (isExpanded) "Collapse" else "Expand"
        )
    }
}

/**
 * Metadata card - name, description, version, category, tags.
 */
@Composable
fun MetadataCard(
    draft: SkillDraft,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    onUpdateName: (String) -> Unit,
    onUpdateDescription: (String) -> Unit,
    onUpdateVersion: (String) -> Unit,
    onUpdateCategory: (SkillCategory) -> Unit,
    onShowAddTagDialog: () -> Unit,
    onRemoveTag: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var showCategoryMenu by remember { mutableStateOf(false) }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .testable("card_metadata")
    ) {
        Column {
            ExpandableCardHeader(
                icon = { Icon(CIRISIcons.info, contentDescription = null) },
                title = "Metadata",
                isExpanded = isExpanded,
                onToggle = onToggle
            )

            AnimatedVisibility(visible = isExpanded) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    HorizontalDivider()

                    // Name
                    OutlinedTextField(
                        value = draft.name,
                        onValueChange = onUpdateName,
                        label = { Text("Skill Name") },
                        placeholder = { Text("my-skill-name") },
                        singleLine = true,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testable("input_skill_name"),
                        supportingText = { Text("Lowercase, hyphens only") }
                    )

                    // Description
                    OutlinedTextField(
                        value = draft.description,
                        onValueChange = onUpdateDescription,
                        label = { Text("Description") },
                        placeholder = { Text("What does this skill do?") },
                        minLines = 2,
                        maxLines = 4,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testable("input_skill_description")
                    )

                    // Version and Category Row
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        // Version
                        OutlinedTextField(
                            value = draft.version,
                            onValueChange = onUpdateVersion,
                            label = { Text("Version") },
                            singleLine = true,
                            modifier = Modifier
                                .weight(1f)
                                .testable("input_skill_version")
                        )

                        // Category dropdown
                        Box(modifier = Modifier.weight(1f)) {
                            OutlinedTextField(
                                value = draft.category.displayName,
                                onValueChange = {},
                                label = { Text("Category") },
                                readOnly = true,
                                singleLine = true,
                                trailingIcon = {
                                    Icon(
                                        if (showCategoryMenu) CIRISIcons.arrowUp
                                        else CIRISIcons.arrowDown,
                                        contentDescription = null
                                    )
                                },
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .testableClickable("chip_category") { showCategoryMenu = true }
                            )
                            DropdownMenu(
                                expanded = showCategoryMenu,
                                onDismissRequest = { showCategoryMenu = false }
                            ) {
                                SkillCategory.entries.forEach { category ->
                                    DropdownMenuItem(
                                        text = { Text(category.displayName) },
                                        onClick = {
                                            onUpdateCategory(category)
                                            showCategoryMenu = false
                                        }
                                    )
                                }
                            }
                        }
                    }

                    // Tags
                    Column {
                        Text(
                            "Tags",
                            style = MaterialTheme.typography.labelMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(Modifier.height(4.dp))
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp),
                            modifier = Modifier.testable("chip_tags_container")
                        ) {
                            items(draft.tags) { tag ->
                                InputChip(
                                    selected = true,
                                    onClick = {},
                                    label = { Text(tag) },
                                    trailingIcon = {
                                        IconButton(
                                            onClick = { onRemoveTag(tag) },
                                            modifier = Modifier.size(18.dp)
                                        ) {
                                            Icon(
                                                CIRISIcons.close,
                                                contentDescription = "Remove tag",
                                                modifier = Modifier.size(14.dp)
                                            )
                                        }
                                    }
                                )
                            }
                            item {
                                AssistChip(
                                    onClick = onShowAddTagDialog,
                                    label = { Text("+ Add Tag") }
                                )
                            }
                        }
                    }

                    Spacer(Modifier.height(8.dp))
                }
            }
        }
    }
}

/**
 * Tools list card with add/edit/delete.
 */
@Composable
fun ToolsCard(
    tools: List<ToolDefinition>,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    onAddTool: () -> Unit,
    onEditTool: (Int) -> Unit,
    onDeleteTool: (Int) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .testable("card_tools")
    ) {
        Column {
            ExpandableCardHeader(
                icon = { Icon(CIRISIcons.build, contentDescription = null) },
                title = "Tools",
                count = tools.size,
                isExpanded = isExpanded,
                onToggle = onToggle
            )

            AnimatedVisibility(visible = isExpanded) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    HorizontalDivider()

                    if (tools.isEmpty()) {
                        Text(
                            "No tools defined yet",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(vertical = 8.dp)
                        )
                    } else {
                        tools.forEachIndexed { index, tool ->
                            ToolListItem(
                                tool = tool,
                                index = index,
                                onEdit = { onEditTool(index) },
                                onDelete = { onDeleteTool(index) }
                            )
                        }
                    }

                    TextButton(
                        onClick = onAddTool,
                        modifier = Modifier.testable("btn_add_tool")
                    ) {
                        Icon(CIRISIcons.add, contentDescription = null)
                        Spacer(Modifier.width(4.dp))
                        Text("Add Tool")
                    }

                    Spacer(Modifier.height(8.dp))
                }
            }
        }
    }
}

@Composable
private fun ToolListItem(
    tool: ToolDefinition,
    index: Int,
    onEdit: () -> Unit,
    onDelete: () -> Unit
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .testable("item_tool_$index"),
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = tool.name.ifBlank { "(unnamed)" },
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
                if (tool.description.isNotBlank()) {
                    Text(
                        text = tool.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                if (tool.parameters.isNotEmpty()) {
                    Text(
                        text = "Params: ${tool.parameters.joinToString(", ") { it.name }}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.outline
                    )
                }
            }
            Row {
                IconButton(
                    onClick = onEdit,
                    modifier = Modifier.testable("btn_edit_tool_$index")
                ) {
                    Icon(CIRISIcons.edit, contentDescription = "Edit")
                }
                IconButton(
                    onClick = onDelete,
                    modifier = Modifier.testable("btn_delete_tool_$index")
                ) {
                    Icon(CIRISIcons.delete, contentDescription = "Delete")
                }
            }
        }
    }
}

/**
 * Environment variables card.
 */
@Composable
fun EnvVarsCard(
    envVars: List<EnvVarRequirement>,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    onAddEnvVar: () -> Unit,
    onEditEnvVar: (Int) -> Unit,
    onDeleteEnvVar: (Int) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .testable("card_env_vars")
    ) {
        Column {
            ExpandableCardHeader(
                icon = { Icon(CIRISIcons.settings, contentDescription = null) },
                title = "Environment Variables",
                count = envVars.size,
                isExpanded = isExpanded,
                onToggle = onToggle
            )

            AnimatedVisibility(visible = isExpanded) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    HorizontalDivider()

                    if (envVars.isEmpty()) {
                        Text(
                            "No environment variables required",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(vertical = 8.dp)
                        )
                    } else {
                        envVars.forEachIndexed { index, envVar ->
                            EnvVarListItem(
                                envVar = envVar,
                                index = index,
                                onEdit = { onEditEnvVar(index) },
                                onDelete = { onDeleteEnvVar(index) }
                            )
                        }
                    }

                    TextButton(
                        onClick = onAddEnvVar,
                        modifier = Modifier.testable("btn_add_env_var")
                    ) {
                        Icon(CIRISIcons.add, contentDescription = null)
                        Spacer(Modifier.width(4.dp))
                        Text("Add Variable")
                    }

                    Spacer(Modifier.height(8.dp))
                }
            }
        }
    }
}

@Composable
private fun EnvVarListItem(
    envVar: EnvVarRequirement,
    index: Int,
    onEdit: () -> Unit,
    onDelete: () -> Unit
) {
    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .testable("item_env_var_$index"),
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = envVar.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    if (envVar.required) {
                        Spacer(Modifier.width(4.dp))
                        Text(
                            text = "*required",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                }
                if (envVar.description.isNotBlank()) {
                    Text(
                        text = envVar.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
            Row {
                IconButton(onClick = onEdit) {
                    Icon(CIRISIcons.edit, contentDescription = "Edit")
                }
                IconButton(onClick = onDelete) {
                    Icon(CIRISIcons.delete, contentDescription = "Delete")
                }
            }
        }
    }
}

/**
 * Required binaries card.
 */
@Composable
fun BinariesCard(
    binaries: List<String>,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    onAddBinary: (String) -> Unit,
    onRemoveBinary: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    var newBinary by remember { mutableStateOf("") }

    Card(
        modifier = modifier
            .fillMaxWidth()
            .testable("card_binaries")
    ) {
        Column {
            ExpandableCardHeader(
                icon = { Icon(CIRISMaterialIcons.Filled.Terminal, contentDescription = null) },
                title = "Required Binaries",
                count = binaries.size,
                isExpanded = isExpanded,
                onToggle = onToggle
            )

            AnimatedVisibility(visible = isExpanded) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    HorizontalDivider()

                    if (binaries.isEmpty()) {
                        Text(
                            "No CLI binaries required",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.padding(vertical = 8.dp)
                        )
                    } else {
                        LazyRow(
                            horizontalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            items(binaries) { binary ->
                                InputChip(
                                    selected = true,
                                    onClick = {},
                                    label = { Text(binary) },
                                    trailingIcon = {
                                        IconButton(
                                            onClick = { onRemoveBinary(binary) },
                                            modifier = Modifier.size(18.dp)
                                        ) {
                                            Icon(
                                                CIRISIcons.close,
                                                contentDescription = "Remove",
                                                modifier = Modifier.size(14.dp)
                                            )
                                        }
                                    }
                                )
                            }
                        }
                    }

                    Row(
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        OutlinedTextField(
                            value = newBinary,
                            onValueChange = { newBinary = it },
                            label = { Text("Binary name") },
                            placeholder = { Text("curl, jq, etc.") },
                            singleLine = true,
                            modifier = Modifier.weight(1f)
                        )
                        IconButton(
                            onClick = {
                                if (newBinary.isNotBlank()) {
                                    onAddBinary(newBinary)
                                    newBinary = ""
                                }
                            }
                        ) {
                            Icon(CIRISIcons.add, contentDescription = "Add")
                        }
                    }

                    Spacer(Modifier.height(8.dp))
                }
            }
        }
    }
}

/**
 * Instructions (markdown) card.
 */
@Composable
fun InstructionsCard(
    instructions: String,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    onUpdateInstructions: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier
            .fillMaxWidth()
            .testable("card_instructions")
    ) {
        Column {
            ExpandableCardHeader(
                icon = { Icon(CIRISMaterialIcons.Filled.Description, contentDescription = null) },
                title = "Instructions",
                isExpanded = isExpanded,
                onToggle = onToggle
            )

            AnimatedVisibility(visible = isExpanded) {
                Column(
                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)
                ) {
                    HorizontalDivider()
                    Spacer(Modifier.height(8.dp))

                    Text(
                        "Write the AI instructions in Markdown format:",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    Spacer(Modifier.height(8.dp))

                    OutlinedTextField(
                        value = instructions,
                        onValueChange = onUpdateInstructions,
                        placeholder = { Text("# My Skill\n\nDescribe how the agent should use this skill...") },
                        minLines = 10,
                        maxLines = 20,
                        modifier = Modifier
                            .fillMaxWidth()
                            .testable("input_instructions_md")
                    )

                    Spacer(Modifier.height(8.dp))
                }
            }
        }
    }
}
