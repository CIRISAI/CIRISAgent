package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.testable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
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
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

/**
 * Dialog for editing a tool definition.
 */
@Composable
fun ToolEditDialog(
    tool: ToolDefinition,
    isNew: Boolean,
    onSave: (ToolDefinition) -> Unit,
    onDismiss: () -> Unit,
    onAddParameter: () -> Unit,
    modifier: Modifier = Modifier
) {
    var name by remember { mutableStateOf(tool.name) }
    var description by remember { mutableStateOf(tool.description) }
    var whenToUse by remember { mutableStateOf(tool.whenToUse) }
    var cost by remember { mutableStateOf(tool.cost.toString()) }
    var parameters by remember { mutableStateOf(tool.parameters) }

    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(
            usePlatformDefaultWidth = false
        )
    ) {
        Surface(
            modifier = modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.9f)
                .testable("dialog_edit_tool"),
            shape = RoundedCornerShape(16.dp)
        ) {
            Column(
                modifier = Modifier.padding(24.dp)
            ) {
                // Header
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = if (isNew) "Add Tool" else "Edit Tool",
                        style = MaterialTheme.typography.headlineSmall,
                        fontWeight = FontWeight.Bold
                    )
                    IconButton(onClick = onDismiss) {
                        Icon(Icons.Filled.Close, contentDescription = "Close")
                    }
                }

                Spacer(Modifier.height(16.dp))

                // Scrollable content
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    verticalArrangement = Arrangement.spacedBy(16.dp)
                ) {
                    item {
                        OutlinedTextField(
                            value = name,
                            onValueChange = { name = it.lowercase().replace(" ", "_") },
                            label = { Text("Tool Name") },
                            placeholder = { Text("get_weather") },
                            singleLine = true,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testable("input_tool_name"),
                            supportingText = { Text("Lowercase, underscores for spaces") }
                        )
                    }

                    item {
                        OutlinedTextField(
                            value = description,
                            onValueChange = { description = it },
                            label = { Text("Description") },
                            placeholder = { Text("What does this tool do?") },
                            minLines = 2,
                            maxLines = 4,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testable("input_tool_description")
                        )
                    }

                    item {
                        OutlinedTextField(
                            value = cost,
                            onValueChange = { cost = it.filter { c -> c.isDigit() } },
                            label = { Text("Cost (credits)") },
                            singleLine = true,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testable("input_tool_cost")
                        )
                    }

                    item {
                        OutlinedTextField(
                            value = whenToUse,
                            onValueChange = { whenToUse = it },
                            label = { Text("When to Use") },
                            placeholder = { Text("Describe when the agent should use this tool...") },
                            minLines = 3,
                            maxLines = 6,
                            modifier = Modifier
                                .fillMaxWidth()
                                .testable("input_tool_when_to_use")
                        )
                    }

                    // Parameters section
                    item {
                        Column {
                            Text(
                                text = "Parameters",
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold
                            )
                            Spacer(Modifier.height(8.dp))

                            if (parameters.isEmpty()) {
                                Text(
                                    "No parameters defined",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant
                                )
                            }
                        }
                    }

                    itemsIndexed(parameters) { index, param ->
                        ParameterListItem(
                            parameter = param,
                            index = index,
                            onDelete = {
                                parameters = parameters.toMutableList().apply { removeAt(index) }
                            }
                        )
                    }

                    item {
                        TextButton(
                            onClick = onAddParameter,
                            modifier = Modifier.testable("btn_add_parameter")
                        ) {
                            Icon(Icons.Filled.Add, contentDescription = null)
                            Spacer(Modifier.width(4.dp))
                            Text("Add Parameter")
                        }
                    }
                }

                Spacer(Modifier.height(16.dp))

                // Actions
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.End
                ) {
                    TextButton(
                        onClick = onDismiss,
                        modifier = Modifier.testable("btn_cancel_tool")
                    ) {
                        Text("Cancel")
                    }
                    Spacer(Modifier.width(8.dp))
                    Button(
                        onClick = {
                            onSave(
                                ToolDefinition(
                                    name = name,
                                    description = description,
                                    whenToUse = whenToUse,
                                    cost = cost.toIntOrNull() ?: 0,
                                    parameters = parameters
                                )
                            )
                        },
                        enabled = name.isNotBlank(),
                        modifier = Modifier.testable("btn_save_tool")
                    ) {
                        Text("Save Tool")
                    }
                }
            }
        }
    }
}

@Composable
private fun ParameterListItem(
    parameter: ToolParameter,
    index: Int,
    onDelete: () -> Unit
) {
    Surface(
        shape = RoundedCornerShape(8.dp),
        color = MaterialTheme.colorScheme.surfaceVariant,
        modifier = Modifier
            .fillMaxWidth()
            .testable("item_param_$index")
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.Top
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(
                        text = parameter.name,
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = " (${parameter.type.value})",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                    if (parameter.required) {
                        Text(
                            text = " *required",
                            style = MaterialTheme.typography.labelSmall,
                            color = MaterialTheme.colorScheme.error
                        )
                    }
                }
                if (parameter.description.isNotBlank()) {
                    Text(
                        text = parameter.description,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
                parameter.default?.let { default ->
                    Text(
                        text = "Default: $default",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.outline
                    )
                }
            }
            IconButton(onClick = onDelete) {
                Icon(Icons.Filled.Delete, contentDescription = "Delete")
            }
        }
    }
}

/**
 * Dialog for editing a tool parameter.
 */
@Composable
fun ParameterEditDialog(
    parameter: ToolParameter,
    isNew: Boolean,
    onSave: (ToolParameter) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    var name by remember { mutableStateOf(parameter.name) }
    var type by remember { mutableStateOf(parameter.type) }
    var description by remember { mutableStateOf(parameter.description) }
    var required by remember { mutableStateOf(parameter.required) }
    var default by remember { mutableStateOf(parameter.default ?: "") }
    var showTypeMenu by remember { mutableStateOf(false) }

    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = modifier.testable("dialog_edit_parameter"),
        title = {
            Text(if (isNew) "Add Parameter" else "Edit Parameter")
        },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.lowercase().replace(" ", "_") },
                    label = { Text("Parameter Name") },
                    placeholder = { Text("location") },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_param_name")
                )

                // Type dropdown
                Box {
                    OutlinedTextField(
                        value = type.displayName,
                        onValueChange = {},
                        label = { Text("Type") },
                        readOnly = true,
                        singleLine = true,
                        trailingIcon = {
                            Icon(
                                if (showTypeMenu) Icons.Filled.KeyboardArrowUp
                                else Icons.Filled.KeyboardArrowDown,
                                contentDescription = null
                            )
                        },
                        modifier = Modifier
                            .fillMaxWidth()
                            .testable("input_param_type")
                    )
                    DropdownMenu(
                        expanded = showTypeMenu,
                        onDismissRequest = { showTypeMenu = false }
                    ) {
                        ParameterType.entries.forEach { t ->
                            DropdownMenuItem(
                                text = { Text(t.displayName) },
                                onClick = {
                                    type = t
                                    showTypeMenu = false
                                }
                            )
                        }
                    }
                }

                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Description") },
                    placeholder = { Text("What is this parameter for?") },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_param_description")
                )

                Row(
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Checkbox(
                        checked = required,
                        onCheckedChange = { required = it },
                        modifier = Modifier.testable("checkbox_param_required")
                    )
                    Text("Required")
                }

                OutlinedTextField(
                    value = default,
                    onValueChange = { default = it },
                    label = { Text("Default Value (optional)") },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_param_default")
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSave(
                        ToolParameter(
                            name = name,
                            type = type,
                            description = description,
                            required = required,
                            default = default.ifBlank { null }
                        )
                    )
                },
                enabled = name.isNotBlank(),
                modifier = Modifier.testable("btn_save_param")
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testable("btn_cancel_param")
            ) {
                Text("Cancel")
            }
        }
    )
}

/**
 * Dialog for editing an environment variable requirement.
 */
@Composable
fun EnvVarEditDialog(
    envVar: EnvVarRequirement,
    isNew: Boolean,
    onSave: (EnvVarRequirement) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    var name by remember { mutableStateOf(envVar.name) }
    var description by remember { mutableStateOf(envVar.description) }
    var required by remember { mutableStateOf(envVar.required) }
    var defaultValue by remember { mutableStateOf(envVar.defaultValue ?: "") }

    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = modifier.testable("dialog_edit_env_var"),
        title = {
            Text(if (isNew) "Add Environment Variable" else "Edit Environment Variable")
        },
        text = {
            Column(
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                OutlinedTextField(
                    value = name,
                    onValueChange = { name = it.uppercase().replace(" ", "_").replace("-", "_") },
                    label = { Text("Variable Name") },
                    placeholder = { Text("API_KEY") },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_env_name"),
                    supportingText = { Text("UPPER_SNAKE_CASE") }
                )

                OutlinedTextField(
                    value = description,
                    onValueChange = { description = it },
                    label = { Text("Description") },
                    placeholder = { Text("What is this variable used for?") },
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_env_description")
                )

                Row(
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Checkbox(
                        checked = required,
                        onCheckedChange = { required = it },
                        modifier = Modifier.testable("checkbox_env_required")
                    )
                    Text("Required")
                }

                OutlinedTextField(
                    value = defaultValue,
                    onValueChange = { defaultValue = it },
                    label = { Text("Default Value (optional)") },
                    singleLine = true,
                    modifier = Modifier
                        .fillMaxWidth()
                        .testable("input_env_default")
                )
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    onSave(
                        EnvVarRequirement(
                            name = name,
                            description = description,
                            required = required,
                            defaultValue = defaultValue.ifBlank { null }
                        )
                    )
                },
                enabled = name.isNotBlank(),
                modifier = Modifier.testable("btn_save_env")
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testable("btn_cancel_env")
            ) {
                Text("Cancel")
            }
        }
    )
}

/**
 * Dialog for adding a tag.
 */
@Composable
fun AddTagDialog(
    currentTags: List<String>,
    onAdd: (String) -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    var tag by remember { mutableStateOf("") }

    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = modifier.testable("dialog_add_tag"),
        title = { Text("Add Tag") },
        text = {
            OutlinedTextField(
                value = tag,
                onValueChange = { tag = it.lowercase().trim() },
                label = { Text("Tag") },
                placeholder = { Text("weather, api, automation...") },
                singleLine = true,
                modifier = Modifier
                    .fillMaxWidth()
                    .testable("input_tag")
            )
        },
        confirmButton = {
            Button(
                onClick = { onAdd(tag) },
                enabled = tag.isNotBlank() && tag !in currentTags,
                modifier = Modifier.testable("btn_add_tag")
            ) {
                Text("Add")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testable("btn_cancel_tag")
            ) {
                Text("Cancel")
            }
        }
    )
}

/**
 * Confirmation dialog for deleting an item.
 */
@Composable
fun ConfirmDeleteDialog(
    itemType: String,
    itemName: String,
    onConfirm: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        modifier = modifier.testable("dialog_confirm_delete"),
        icon = {
            Icon(
                Icons.Filled.Warning,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.error
            )
        },
        title = { Text("Delete $itemType?") },
        text = {
            Text("Are you sure you want to delete \"$itemName\"? This action cannot be undone.")
        },
        confirmButton = {
            Button(
                onClick = onConfirm,
                colors = ButtonDefaults.buttonColors(
                    containerColor = MaterialTheme.colorScheme.error
                ),
                modifier = Modifier.testable("btn_confirm_delete")
            ) {
                Text("Delete")
            }
        },
        dismissButton = {
            TextButton(
                onClick = onDismiss,
                modifier = Modifier.testable("btn_cancel_delete")
            ) {
                Text("Cancel")
            }
        }
    )
}
