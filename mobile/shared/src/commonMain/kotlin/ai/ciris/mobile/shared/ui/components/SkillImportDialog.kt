package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.models.ImportedSkillData
import ai.ciris.mobile.shared.models.SkillImportResult
import ai.ciris.mobile.shared.models.SkillPreviewData
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.SkillImportViewModel.ImportPhase
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

/**
 * Dialog for importing OpenClaw skills as CIRIS adapters.
 *
 * Three-phase flow:
 * 1. PASTE: User pastes SKILL.md content + optional source URL
 * 2. PREVIEW: Shows parsed skill details for confirmation
 * 3. RESULT: Shows import success/failure
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SkillImportDialog(
    phase: ImportPhase,
    skillMdContent: String,
    sourceUrl: String,
    preview: SkillPreviewData?,
    importResult: SkillImportResult?,
    isLoading: Boolean,
    error: String?,
    onContentChanged: (String) -> Unit,
    onSourceUrlChanged: (String) -> Unit,
    onPreview: () -> Unit,
    onImport: () -> Unit,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier
) {
    Dialog(
        onDismissRequest = onDismiss,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = modifier
                .fillMaxWidth(0.95f)
                .fillMaxHeight(0.9f),
            shape = RoundedCornerShape(16.dp),
            color = MaterialTheme.colorScheme.surface,
            tonalElevation = 6.dp
        ) {
            Scaffold(
                topBar = {
                    TopAppBar(
                        title = {
                            Text(
                                when (phase) {
                                    ImportPhase.PASTE -> "Import Skill"
                                    ImportPhase.PREVIEW -> "Preview Import"
                                    ImportPhase.RESULT -> "Import Result"
                                }
                            )
                        },
                        navigationIcon = {
                            if (phase == ImportPhase.PREVIEW) {
                                IconButton(onClick = { /* go back to paste handled by VM */ }) {
                                    Icon(Icons.Filled.ArrowBack, "Back")
                                }
                            }
                        },
                        actions = {
                            IconButton(
                                onClick = onDismiss,
                                modifier = Modifier.testableClickable("btn_skill_import_close") { onDismiss() }
                            ) {
                                Icon(Icons.Filled.Close, "Close")
                            }
                        }
                    )
                }
            ) { paddingValues ->
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    // Error display
                    if (error != null) {
                        Card(
                            colors = CardDefaults.cardColors(
                                containerColor = MaterialTheme.colorScheme.errorContainer
                            )
                        ) {
                            Text(
                                text = error,
                                color = MaterialTheme.colorScheme.onErrorContainer,
                                style = MaterialTheme.typography.bodyMedium,
                                modifier = Modifier.padding(12.dp)
                            )
                        }
                    }

                    when (phase) {
                        ImportPhase.PASTE -> PasteContent(
                            content = skillMdContent,
                            sourceUrl = sourceUrl,
                            isLoading = isLoading,
                            onContentChanged = onContentChanged,
                            onSourceUrlChanged = onSourceUrlChanged,
                            onPreview = onPreview
                        )
                        ImportPhase.PREVIEW -> PreviewContent(
                            preview = preview,
                            isLoading = isLoading,
                            onImport = onImport,
                            onDismiss = onDismiss
                        )
                        ImportPhase.RESULT -> ResultContent(
                            result = importResult,
                            onDismiss = onDismiss
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun PasteContent(
    content: String,
    sourceUrl: String,
    isLoading: Boolean,
    onContentChanged: (String) -> Unit,
    onSourceUrlChanged: (String) -> Unit,
    onPreview: () -> Unit
) {
    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text(
            text = "Paste an OpenClaw SKILL.md to import it as a CIRIS adapter.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        // SKILL.md content input
        OutlinedTextField(
            value = content,
            onValueChange = onContentChanged,
            label = { Text("SKILL.md Content") },
            placeholder = {
                Text(
                    "---\nname: my-skill\ndescription: Does something\n---\n\nInstructions here...",
                    fontFamily = FontFamily.Monospace,
                    style = MaterialTheme.typography.bodySmall
                )
            },
            modifier = Modifier
                .fillMaxWidth()
                .weight(1f)
                .testable("input_skill_md"),
            textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
            minLines = 10
        )

        // Optional source URL
        OutlinedTextField(
            value = sourceUrl,
            onValueChange = onSourceUrlChanged,
            label = { Text("Source URL (optional)") },
            placeholder = { Text("https://clawhub.com/skills/my-skill") },
            modifier = Modifier
                .fillMaxWidth()
                .testable("input_skill_source_url"),
            singleLine = true
        )

        // Preview button
        Button(
            onClick = onPreview,
            enabled = content.isNotBlank() && !isLoading,
            modifier = Modifier
                .fillMaxWidth()
                .testable("btn_skill_preview")
        ) {
            if (isLoading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(16.dp),
                    strokeWidth = 2.dp,
                    color = MaterialTheme.colorScheme.onPrimary
                )
                Spacer(Modifier.width(8.dp))
            }
            Text("Preview Import")
        }
    }
}

@Composable
private fun PreviewContent(
    preview: SkillPreviewData?,
    isLoading: Boolean,
    onImport: () -> Unit,
    onDismiss: () -> Unit
) {
    if (preview == null) {
        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState()),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        // Skill info card
        Card(
            modifier = Modifier.fillMaxWidth(),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.primaryContainer
            )
        ) {
            Column(modifier = Modifier.padding(16.dp)) {
                Text(
                    text = preview.name,
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "v${preview.version}",
                    style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onPrimaryContainer.copy(alpha = 0.7f)
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = preview.description,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }

        // Module name
        DetailRow("Adapter Module", preview.moduleName)

        // Tools
        if (preview.tools.isNotEmpty()) {
            Text("Tools", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            preview.tools.forEach { tool ->
                SuggestionChip(
                    onClick = {},
                    label = { Text(tool, style = MaterialTheme.typography.labelSmall) }
                )
            }
        }

        // Requirements
        if (preview.requiredEnvVars.isNotEmpty()) {
            Text("Required Environment Variables", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            preview.requiredEnvVars.forEach { env ->
                Text(
                    text = env,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace
                )
            }
        }

        if (preview.requiredBinaries.isNotEmpty()) {
            Text("Required Binaries", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            preview.requiredBinaries.forEach { bin ->
                Text(
                    text = bin,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace
                )
            }
        }

        // Instructions preview
        if (preview.instructionsPreview.isNotBlank()) {
            Text("Instructions Preview", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
            Card(
                colors = CardDefaults.cardColors(
                    containerColor = MaterialTheme.colorScheme.surfaceVariant
                )
            ) {
                Text(
                    text = preview.instructionsPreview,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = FontFamily.Monospace,
                    modifier = Modifier.padding(12.dp),
                    maxLines = 10,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }

        Spacer(Modifier.height(8.dp))

        // Action buttons
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            OutlinedButton(
                onClick = onDismiss,
                modifier = Modifier.weight(1f)
            ) {
                Text("Cancel")
            }
            Button(
                onClick = onImport,
                enabled = !isLoading,
                modifier = Modifier
                    .weight(1f)
                    .testable("btn_skill_import_confirm")
            ) {
                if (isLoading) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(16.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary
                    )
                    Spacer(Modifier.width(8.dp))
                }
                Text("Import Skill")
            }
        }
    }
}

@Composable
private fun ResultContent(
    result: SkillImportResult?,
    onDismiss: () -> Unit
) {
    if (result == null) return

    Column(
        modifier = Modifier.fillMaxSize(),
        verticalArrangement = Arrangement.spacedBy(12.dp),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        Spacer(Modifier.height(32.dp))

        // Success/failure icon
        Card(
            colors = CardDefaults.cardColors(
                containerColor = if (result.success)
                    MaterialTheme.colorScheme.primaryContainer
                else
                    MaterialTheme.colorScheme.errorContainer
            ),
            modifier = Modifier.fillMaxWidth()
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = if (result.success) "Import Successful" else "Import Failed",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.Bold
                )
                Spacer(Modifier.height(8.dp))
                Text(
                    text = result.message,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (result.success)
                        MaterialTheme.colorScheme.onPrimaryContainer
                    else
                        MaterialTheme.colorScheme.onErrorContainer
                )
            }
        }

        if (result.success) {
            DetailRow("Module", result.moduleName)
            DetailRow("Auto-loaded", if (result.autoLoaded) "Yes" else "No (restart to activate)")

            if (result.toolsCreated.isNotEmpty()) {
                Text("Tools Created", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.Bold)
                result.toolsCreated.forEach { tool ->
                    SuggestionChip(
                        onClick = {},
                        label = { Text(tool) }
                    )
                }
            }
        }

        Spacer(Modifier.weight(1f))

        Button(
            onClick = onDismiss,
            modifier = Modifier
                .fillMaxWidth()
                .testable("btn_skill_import_done")
        ) {
            Text("Done")
        }
    }
}

@Composable
private fun DetailRow(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            fontFamily = FontFamily.Monospace
        )
    }
}

/**
 * Card for displaying an imported skill in the list.
 */
@Composable
fun ImportedSkillCard(
    skill: ImportedSkillData,
    onDelete: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 2.dp)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = skill.originalSkillName,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = skill.description,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
                Spacer(Modifier.height(4.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    SuggestionChip(
                        onClick = {},
                        label = { Text("v${skill.version}", style = MaterialTheme.typography.labelSmall) }
                    )
                    SuggestionChip(
                        onClick = {},
                        label = { Text(skill.moduleName, style = MaterialTheme.typography.labelSmall) }
                    )
                }
            }

            IconButton(
                onClick = onDelete,
                modifier = Modifier.testableClickable("btn_delete_skill_${skill.moduleName}") { onDelete() }
            ) {
                Icon(
                    Icons.Filled.Delete,
                    contentDescription = "Remove skill",
                    tint = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}
