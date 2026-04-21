package ai.ciris.mobile.shared.ui.components

import ai.ciris.mobile.shared.localization.localizedString
import ai.ciris.mobile.shared.models.ImportedSkillData
import ai.ciris.mobile.shared.models.SkillImportResult
import ai.ciris.mobile.shared.models.SkillPreviewData
import ai.ciris.mobile.shared.platform.TestAutomation
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.viewmodels.SkillImportViewModel.ImportPhase
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Build
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material.icons.filled.KeyboardArrowDown
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import ai.ciris.mobile.shared.ui.components.emojiToIconOrDefault
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

// ============================================================================
// Skill Workshop Dialog - HyperCard-style card editor
// Simple first, complex underneath. Every field has plain English.
// ============================================================================

/**
 * The Skill Workshop: create or import skills through a card-based editor.
 *
 * Design philosophy (HyperCard meets the polyglot accord):
 * - Simple mode: plain English labels, one thing at a time
 * - Advanced mode: shows all fields, parameters, guidance
 * - JSON mode: raw schema editing for power users
 *
 * "Keep the song singable for every voice not yet heard."
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
    // Observe text input requests for test automation
    val textInputRequest by TestAutomation.textInputRequests.collectAsState()

    // Handle incoming text input requests
    LaunchedEffect(textInputRequest) {
        textInputRequest?.let { request ->
            when (request.testTag) {
                "input_skill_md" -> {
                    if (request.clearFirst) {
                        onContentChanged(request.text)
                    } else {
                        onContentChanged(skillMdContent + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
                "input_skill_source_url" -> {
                    if (request.clearFirst) {
                        onSourceUrlChanged(request.text)
                    } else {
                        onSourceUrlChanged(sourceUrl + request.text)
                    }
                    TestAutomation.clearTextInputRequest()
                }
            }
        }
    }

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
                                    ImportPhase.PASTE -> localizedString("mobile.skill_import")
                                    ImportPhase.PREVIEW -> localizedString("mobile.skill_import_review")
                                    ImportPhase.RESULT -> localizedString("mobile.skill_build_success")
                                }
                            )
                        },
                        navigationIcon = {
                            if (phase != ImportPhase.PASTE) {
                                IconButton(onClick = onDismiss) {
                                    Icon(CIRISIcons.arrowBack, localizedString("mobile.common_back"))
                                }
                            }
                        },
                        actions = {
                            IconButton(
                                onClick = onDismiss,
                                modifier = Modifier.testableClickable("btn_skill_import_close") { onDismiss() }
                            ) {
                                Icon(CIRISIcons.close, localizedString("mobile.common_close"))
                            }
                        }
                    )
                }
            ) { paddingValues ->
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(paddingValues)
                        .padding(16.dp)
                        .verticalScroll(rememberScrollState()),
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
                        ImportPhase.PREVIEW -> PreviewAsCards(
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

// ============================================================================
// Phase 1: Paste - Simple import flow
// ============================================================================

@Composable
private fun PasteContent(
    content: String,
    sourceUrl: String,
    isLoading: Boolean,
    onContentChanged: (String) -> Unit,
    onSourceUrlChanged: (String) -> Unit,
    onPreview: () -> Unit
) {
    // Friendly intro
    Text(
        text = localizedString("mobile.skill_import_paste_hint"),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )

    // Warning card
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.tertiaryContainer
        )
    ) {
        Text(
            text = localizedString("mobile.skill_import_warning_untrusted"),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onTertiaryContainer,
            modifier = Modifier.padding(12.dp)
        )
    }

    // SKILL.md content input
    OutlinedTextField(
        value = content,
        onValueChange = onContentChanged,
        label = { Text(localizedString("mobile.skill_import_paste")) },
        placeholder = {
            Text(
                "---\nname: my-skill\ndescription: Does something useful\n---\n\nTell the agent what to do...",
                fontFamily = FontFamily.Monospace,
                style = MaterialTheme.typography.bodySmall
            )
        },
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(min = 200.dp, max = 400.dp)
            .testable("input_skill_md"),
        textStyle = MaterialTheme.typography.bodySmall.copy(fontFamily = FontFamily.Monospace),
        minLines = 8
    )

    // Optional source URL - collapsible for simplicity
    var showSource by remember { mutableStateOf(sourceUrl.isNotBlank()) }

    if (!showSource) {
        TextButton(
            onClick = { showSource = true },
            modifier = Modifier.testable("btn_show_source_url")
        ) {
            Text(localizedString("mobile.skill_import_source"))
        }
    }

    AnimatedVisibility(visible = showSource) {
        OutlinedTextField(
            value = sourceUrl,
            onValueChange = onSourceUrlChanged,
            label = { Text(localizedString("mobile.skill_import_source")) },
            placeholder = { Text(localizedString("mobile.skill_import_source_hint")) },
            modifier = Modifier
                .fillMaxWidth()
                .testable("input_skill_source_url"),
            singleLine = true
        )
    }

    // Analyze button
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
            Text(localizedString("mobile.skill_import_analyzing"))
        } else {
            Text(localizedString("mobile.skill_import_analyze"))
        }
    }
}

// ============================================================================
// Phase 2: Preview as Cards - Show what we found, simple first
// ============================================================================

@Composable
private fun PreviewAsCards(
    preview: SkillPreviewData?,
    isLoading: Boolean,
    onImport: () -> Unit,
    onDismiss: () -> Unit
) {
    if (preview == null) {
        Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
            CircularProgressIndicator()
        }
        return
    }

    // Review hint
    Text(
        text = localizedString("mobile.skill_import_review_hint"),
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant
    )

    // Card 1: Identity (always visible)
    WorkshopCard(
        title = localizedString("mobile.skill_card_identity"),
        hint = localizedString("mobile.skill_card_identity_hint"),
        emoji = "\u2756",  // ❖ identity
        initiallyExpanded = true
    ) {
        SimpleField(localizedString("mobile.skill_field_name"), preview.name)
        SimpleField(localizedString("mobile.skill_field_desc"), preview.description)
        SimpleField(localizedString("mobile.skill_field_version"), "v${preview.version}")
        SimpleField(localizedString("mobile.skill_field_name_hint"), preview.moduleName)
    }

    // Card 2: Tools (always visible)
    WorkshopCard(
        title = localizedString("mobile.skill_card_tools"),
        hint = localizedString("mobile.skill_card_tools_hint"),
        emoji = "\u2692",  // ⚒ tools
        initiallyExpanded = true
    ) {
        if (preview.tools.isNotEmpty()) {
            preview.tools.forEach { tool ->
                SuggestionChip(
                    onClick = {},
                    label = { Text(tool, style = MaterialTheme.typography.labelSmall) },
                    modifier = Modifier.padding(end = 4.dp)
                )
            }
        } else {
            Text(
                "No tools defined",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant
            )
        }
    }

    // Card 3: Requirements (collapsed by default - only if present)
    if (preview.requiredEnvVars.isNotEmpty() || preview.requiredBinaries.isNotEmpty()) {
        WorkshopCard(
            title = localizedString("mobile.skill_card_requires"),
            hint = localizedString("mobile.skill_card_requires_hint"),
            emoji = "\u25A0",  // ■ requirements
            initiallyExpanded = false
        ) {
            if (preview.requiredEnvVars.isNotEmpty()) {
                Text(
                    localizedString("mobile.skill_req_env"),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )
                preview.requiredEnvVars.forEach { env ->
                    Text(
                        text = env,
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.padding(start = 8.dp)
                    )
                }
            }
            if (preview.requiredBinaries.isNotEmpty()) {
                Spacer(Modifier.height(4.dp))
                Text(
                    localizedString("mobile.skill_req_bins"),
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Bold
                )
                preview.requiredBinaries.forEach { bin ->
                    Text(
                        text = bin,
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                        modifier = Modifier.padding(start = 8.dp)
                    )
                }
            }
        }
    }

    // Card 4: Instructions preview (collapsed - for review)
    if (preview.instructionsPreview.isNotBlank()) {
        WorkshopCard(
            title = localizedString("mobile.skill_card_instruct"),
            hint = localizedString("mobile.skill_card_instruct_hint"),
            emoji = "\u2261",  // ≡ instructions
            initiallyExpanded = false
        ) {
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
                    maxLines = 15,
                    overflow = TextOverflow.Ellipsis
                )
            }
        }
    }

    // Card 5: Safety (collapsed - auto-set for imports)
    WorkshopCard(
        title = localizedString("mobile.skill_card_behavior"),
        hint = localizedString("mobile.skill_card_behavior_hint"),
        emoji = "\u25C6",  // ◆ safety
        initiallyExpanded = false
    ) {
        SimpleField(
            localizedString("mobile.skill_behavior_approval"),
            "Yes — imported skills always ask permission first"
        )
        SimpleField(
            localizedString("mobile.skill_behavior_confidence"),
            "70% — agent needs to be fairly sure"
        )
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
            Text(localizedString("mobile.skill_import_edit_first"))
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
                Text(localizedString("mobile.skill_building"))
            } else {
                Text(localizedString("mobile.skill_import_approve"))
            }
        }
    }
}

// ============================================================================
// Phase 3: Result
// ============================================================================

@Composable
private fun ResultContent(
    result: SkillImportResult?,
    onDismiss: () -> Unit
) {
    if (result == null) return

    Spacer(Modifier.height(16.dp))

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
                text = if (result.success)
                    localizedString("mobile.skill_import_success")
                else
                    localizedString("mobile.skill_build_failed"),
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = result.message,
                style = MaterialTheme.typography.bodyMedium
            )
        }
    }

    if (result.success && result.toolsCreated.isNotEmpty()) {
        WorkshopCard(
            title = localizedString("mobile.skill_card_tools"),
            hint = localizedString("mobile.skill_build_success_hint"),
            emoji = "\u2692",  // ⚒ tools
            initiallyExpanded = true
        ) {
            result.toolsCreated.forEach { tool ->
                SuggestionChip(
                    onClick = {},
                    label = { Text(tool) }
                )
            }
        }
    }

    Spacer(Modifier.height(24.dp))

    Button(
        onClick = onDismiss,
        modifier = Modifier
            .fillMaxWidth()
            .testable("btn_skill_import_done")
    ) {
        Text(localizedString("mobile.common_close"))
    }
}

// ============================================================================
// Workshop Card - The core UI component (HyperCard inspired)
// Collapsible card with title, hint, emoji. Shows content on expand.
// ============================================================================

@Composable
fun WorkshopCard(
    title: String,
    hint: String,
    emoji: String,
    initiallyExpanded: Boolean = false,
    content: @Composable ColumnScope.() -> Unit
) {
    var expanded by remember { mutableStateOf(initiallyExpanded) }

    Card(
        modifier = Modifier.fillMaxWidth(),
        elevation = CardDefaults.cardElevation(defaultElevation = 1.dp)
    ) {
        Column(modifier = Modifier.fillMaxWidth()) {
            // Header - always visible, clickable to expand/collapse
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .testableClickable("card_${title.lowercase().replace(" ", "_")}") {
                        expanded = !expanded
                    }
                    .padding(16.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Icon(
                    imageVector = emojiToIconOrDefault(emoji),
                    contentDescription = null,
                    modifier = Modifier.padding(end = 12.dp).size(24.dp),
                    tint = MaterialTheme.colorScheme.primary
                )
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = title,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = hint,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = if (expanded) Int.MAX_VALUE else 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
                Icon(
                    CIRISIcons.arrowDown,
                    contentDescription = if (expanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Content - animated expand/collapse
            AnimatedVisibility(
                visible = expanded,
                enter = expandVertically(),
                exit = shrinkVertically()
            ) {
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(start = 16.dp, end = 16.dp, bottom = 16.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                    content = content
                )
            }
        }
    }
}

// ============================================================================
// Simple field - Label: Value display
// ============================================================================

@Composable
private fun SimpleField(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween
    ) {
        Text(
            text = label,
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.weight(0.4f)
        )
        Text(
            text = value,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(0.6f)
        )
    }
}

// ============================================================================
// Imported Skill Card - for the "My Skills" list
// ============================================================================

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
                }
            }

            IconButton(
                onClick = onDelete,
                modifier = Modifier.testableClickable("btn_delete_skill_${skill.moduleName}") { onDelete() }
            ) {
                Icon(
                    CIRISIcons.delete,
                    contentDescription = localizedString("mobile.skill_delete_title"),
                    tint = MaterialTheme.colorScheme.error
                )
            }
        }
    }
}
