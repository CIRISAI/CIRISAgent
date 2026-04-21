package ai.ciris.mobile.shared.ui.screens

import ai.ciris.mobile.shared.models.*
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.ui.components.*
import ai.ciris.mobile.shared.ui.theme.SemanticColors
import ai.ciris.mobile.shared.viewmodels.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * Skill Studio - Visual editor for OpenClaw SKILL.md files.
 *
 * Features:
 * - Card-based editing with progressive disclosure
 * - Tool and parameter management
 * - Environment variable configuration
 * - Real-time SKILL.md preview
 * - Security scanning before import
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SkillStudioScreen(
    state: SkillStudioScreenState,
    dialogState: SkillStudioDialogState,
    onNavigateBack: () -> Unit,
    onCreateNew: () -> Unit,
    onShowPreview: () -> Unit,
    onBackToEditing: () -> Unit,
    onImport: () -> Unit,
    onValidateAndImport: () -> Unit,
    // Metadata
    onUpdateName: (String) -> Unit,
    onUpdateDescription: (String) -> Unit,
    onUpdateVersion: (String) -> Unit,
    onUpdateCategory: (SkillCategory) -> Unit,
    onUpdateInstructions: (String) -> Unit,
    onShowAddTagDialog: () -> Unit,
    onAddTag: (String) -> Unit,
    onRemoveTag: (String) -> Unit,
    // Tools
    onShowAddToolDialog: () -> Unit,
    onShowEditToolDialog: (Int) -> Unit,
    onSaveTool: (ToolDefinition) -> Unit,
    onDeleteTool: (Int) -> Unit,
    // Parameters
    onShowAddParameterDialog: (Int) -> Unit,
    onSaveParameter: (ToolParameter) -> Unit,
    onDeleteParameter: (Int, Int) -> Unit,
    // Env Vars
    onShowAddEnvVarDialog: () -> Unit,
    onShowEditEnvVarDialog: (Int) -> Unit,
    onSaveEnvVar: (EnvVarRequirement) -> Unit,
    onDeleteEnvVar: (Int) -> Unit,
    // Binaries
    onAddBinary: (String) -> Unit,
    onRemoveBinary: (String) -> Unit,
    // Card expansion
    onToggleCard: (String) -> Unit,
    // Dialog
    onDismissDialog: () -> Unit,
    // Preview tabs
    onSetPreviewTab: (PreviewTab) -> Unit,
    modifier: Modifier = Modifier
) {
    // Handle dialogs
    when (dialogState) {
        is SkillStudioDialogState.EditTool -> {
            ToolEditDialog(
                tool = dialogState.tool,
                isNew = dialogState.isNew,
                onSave = onSaveTool,
                onDismiss = onDismissDialog,
                onAddParameter = { onShowAddParameterDialog(dialogState.index) }
            )
        }
        is SkillStudioDialogState.EditParameter -> {
            ParameterEditDialog(
                parameter = dialogState.parameter,
                isNew = dialogState.isNew,
                onSave = onSaveParameter,
                onDismiss = onDismissDialog
            )
        }
        is SkillStudioDialogState.EditEnvVar -> {
            EnvVarEditDialog(
                envVar = dialogState.envVar,
                isNew = dialogState.isNew,
                onSave = onSaveEnvVar,
                onDismiss = onDismissDialog
            )
        }
        is SkillStudioDialogState.AddTag -> {
            AddTagDialog(
                currentTags = dialogState.currentTags,
                onAdd = onAddTag,
                onDismiss = onDismissDialog
            )
        }
        is SkillStudioDialogState.ConfirmDelete -> {
            ConfirmDeleteDialog(
                itemType = dialogState.itemType,
                itemName = dialogState.itemName,
                onConfirm = {
                    dialogState.onConfirm()
                    onDismissDialog()
                },
                onDismiss = onDismissDialog
            )
        }
        SkillStudioDialogState.None -> { /* No dialog */ }
    }

    // Main content based on state
    when (state) {
        is SkillStudioScreenState.Loading -> {
            LoadingScreen(message = "Loading...")
        }

        is SkillStudioScreenState.Editing -> {
            EditingScreen(
                state = state,
                onNavigateBack = onNavigateBack,
                onShowPreview = onShowPreview,
                onUpdateName = onUpdateName,
                onUpdateDescription = onUpdateDescription,
                onUpdateVersion = onUpdateVersion,
                onUpdateCategory = onUpdateCategory,
                onUpdateInstructions = onUpdateInstructions,
                onShowAddTagDialog = onShowAddTagDialog,
                onRemoveTag = onRemoveTag,
                onShowAddToolDialog = onShowAddToolDialog,
                onShowEditToolDialog = onShowEditToolDialog,
                onDeleteTool = onDeleteTool,
                onShowAddEnvVarDialog = onShowAddEnvVarDialog,
                onShowEditEnvVarDialog = onShowEditEnvVarDialog,
                onDeleteEnvVar = onDeleteEnvVar,
                onAddBinary = onAddBinary,
                onRemoveBinary = onRemoveBinary,
                onToggleCard = onToggleCard
            )
        }

        is SkillStudioScreenState.Preview -> {
            PreviewScreen(
                state = state,
                onBack = onBackToEditing,
                onImport = onValidateAndImport,
                onSetTab = onSetPreviewTab
            )
        }

        is SkillStudioScreenState.SecurityReview -> {
            SecurityReviewScreen(
                state = state,
                onBack = onBackToEditing,
                onConfirmImport = onImport
            )
        }

        is SkillStudioScreenState.Importing -> {
            LoadingScreen(message = "Importing skill as adapter...")
        }

        is SkillStudioScreenState.ImportSuccess -> {
            ImportSuccessScreen(
                moduleName = state.moduleName,
                toolsCreated = state.toolsCreated,
                onDone = onNavigateBack
            )
        }

        is SkillStudioScreenState.Error -> {
            ErrorScreen(
                message = state.message,
                onBack = if (state.draft != null) onBackToEditing else onNavigateBack
            )
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun EditingScreen(
    state: SkillStudioScreenState.Editing,
    onNavigateBack: () -> Unit,
    onShowPreview: () -> Unit,
    onUpdateName: (String) -> Unit,
    onUpdateDescription: (String) -> Unit,
    onUpdateVersion: (String) -> Unit,
    onUpdateCategory: (SkillCategory) -> Unit,
    onUpdateInstructions: (String) -> Unit,
    onShowAddTagDialog: () -> Unit,
    onRemoveTag: (String) -> Unit,
    onShowAddToolDialog: () -> Unit,
    onShowEditToolDialog: (Int) -> Unit,
    onDeleteTool: (Int) -> Unit,
    onShowAddEnvVarDialog: () -> Unit,
    onShowEditEnvVarDialog: (Int) -> Unit,
    onDeleteEnvVar: (Int) -> Unit,
    onAddBinary: (String) -> Unit,
    onRemoveBinary: (String) -> Unit,
    onToggleCard: (String) -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Skill Studio") },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_skill_back") { onNavigateBack() }
                    ) {
                        Icon(CIRISIcons.arrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(
                        onClick = onShowPreview,
                        modifier = Modifier.testableClickable("btn_skill_preview") { onShowPreview() }
                    ) {
                        Icon(CIRISMaterialIcons.Filled.Visibility, contentDescription = "Preview")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        floatingActionButton = {
            FloatingActionButton(
                onClick = onShowAddToolDialog,
                modifier = Modifier.testable("fab_add_tool")
            ) {
                Icon(CIRISIcons.add, contentDescription = "Add Tool")
            }
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Validation errors
            if (state.validationErrors.isNotEmpty()) {
                item {
                    ValidationErrorsCard(errors = state.validationErrors)
                }
            }

            // Metadata Card
            item {
                MetadataCard(
                    draft = state.draft,
                    isExpanded = "metadata" in state.expandedCards,
                    onToggle = { onToggleCard("metadata") },
                    onUpdateName = onUpdateName,
                    onUpdateDescription = onUpdateDescription,
                    onUpdateVersion = onUpdateVersion,
                    onUpdateCategory = onUpdateCategory,
                    onShowAddTagDialog = onShowAddTagDialog,
                    onRemoveTag = onRemoveTag
                )
            }

            // Tools Card
            item {
                ToolsCard(
                    tools = state.draft.tools,
                    isExpanded = "tools" in state.expandedCards,
                    onToggle = { onToggleCard("tools") },
                    onAddTool = onShowAddToolDialog,
                    onEditTool = onShowEditToolDialog,
                    onDeleteTool = onDeleteTool
                )
            }

            // Environment Variables Card
            item {
                EnvVarsCard(
                    envVars = state.draft.environmentVariables,
                    isExpanded = "env_vars" in state.expandedCards,
                    onToggle = { onToggleCard("env_vars") },
                    onAddEnvVar = onShowAddEnvVarDialog,
                    onEditEnvVar = onShowEditEnvVarDialog,
                    onDeleteEnvVar = onDeleteEnvVar
                )
            }

            // Required Binaries Card
            item {
                BinariesCard(
                    binaries = state.draft.requiredBinaries,
                    isExpanded = "binaries" in state.expandedCards,
                    onToggle = { onToggleCard("binaries") },
                    onAddBinary = onAddBinary,
                    onRemoveBinary = onRemoveBinary
                )
            }

            // Instructions Card
            item {
                InstructionsCard(
                    instructions = state.draft.instructions,
                    isExpanded = "instructions" in state.expandedCards,
                    onToggle = { onToggleCard("instructions") },
                    onUpdateInstructions = onUpdateInstructions
                )
            }

            // Bottom spacing for FAB
            item {
                Spacer(modifier = Modifier.height(72.dp))
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun PreviewScreen(
    state: SkillStudioScreenState.Preview,
    onBack: () -> Unit,
    onImport: () -> Unit,
    onSetTab: (PreviewTab) -> Unit
) {
    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Preview") },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_preview_back") { onBack() }
                    ) {
                        Icon(CIRISIcons.arrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    IconButton(
                        onClick = { /* Copy to clipboard */ },
                        modifier = Modifier.testableClickable("btn_copy_md") { }
                    ) {
                        Icon(CIRISMaterialIcons.Filled.ContentCopy, contentDescription = "Copy")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary,
                    actionIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        bottomBar = {
            Surface(
                shadowElevation = 8.dp
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.End
                ) {
                    Button(
                        onClick = onImport,
                        modifier = Modifier.testable("btn_import_now")
                    ) {
                        Icon(CIRISMaterialIcons.Filled.Download, contentDescription = null)
                        Spacer(Modifier.width(8.dp))
                        Text("Import as Adapter")
                    }
                }
            }
        }
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
        ) {
            // Tabs
            TabRow(
                selectedTabIndex = if (state.activeTab == PreviewTab.SKILL_MD) 0 else 1
            ) {
                Tab(
                    selected = state.activeTab == PreviewTab.SKILL_MD,
                    onClick = { onSetTab(PreviewTab.SKILL_MD) },
                    modifier = Modifier.testable("tab_skill_md")
                ) {
                    Text("SKILL.md", modifier = Modifier.padding(16.dp))
                }
                Tab(
                    selected = state.activeTab == PreviewTab.SECURITY,
                    onClick = { onSetTab(PreviewTab.SECURITY) },
                    modifier = Modifier.testable("tab_security")
                ) {
                    Text("Security", modifier = Modifier.padding(16.dp))
                }
            }

            // Content
            when (state.activeTab) {
                PreviewTab.SKILL_MD -> {
                    SkillMdPreview(markdown = state.markdown)
                }
                PreviewTab.SECURITY -> {
                    SecurityPreviewPlaceholder()
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SecurityReviewScreen(
    state: SkillStudioScreenState.SecurityReview,
    onBack: () -> Unit,
    onConfirmImport: () -> Unit
) {
    val report = state.report

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Security Report") },
                navigationIcon = {
                    IconButton(
                        onClick = onBack,
                        modifier = Modifier.testableClickable("btn_security_back") { onBack() }
                    ) {
                        Icon(CIRISIcons.arrowBack, contentDescription = "Back")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primary,
                    titleContentColor = MaterialTheme.colorScheme.onPrimary,
                    navigationIconContentColor = MaterialTheme.colorScheme.onPrimary
                )
            )
        },
        bottomBar = {
            Surface(shadowElevation = 8.dp) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End)
                ) {
                    TextButton(
                        onClick = onBack,
                        modifier = Modifier.testable("btn_cancel_import")
                    ) {
                        Text("Cancel")
                    }
                    Button(
                        onClick = onConfirmImport,
                        enabled = report.safeToImport,
                        modifier = Modifier.testable("btn_confirm_import")
                    ) {
                        Text(if (report.safeToImport) "Import" else "Blocked")
                    }
                }
            }
        }
    ) { paddingValues ->
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            // Summary Card
            item {
                SecuritySummaryCard(report = report)
            }

            // Findings
            items(report.findings) { finding ->
                SecurityFindingCard(finding = finding)
            }
        }
    }
}

@Composable
private fun LoadingScreen(message: String) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator()
            Spacer(Modifier.height(16.dp))
            Text(message)
        }
    }
}

@Composable
private fun ErrorScreen(
    message: String,
    onBack: () -> Unit
) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp)
        ) {
            Icon(
                CIRISMaterialIcons.Filled.Error,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.error,
                modifier = Modifier.size(64.dp)
            )
            Spacer(Modifier.height(16.dp))
            Text(
                text = message,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.error
            )
            Spacer(Modifier.height(24.dp))
            Button(onClick = onBack) {
                Text("Go Back")
            }
        }
    }
}

@Composable
private fun ImportSuccessScreen(
    moduleName: String,
    toolsCreated: List<String>,
    onDone: () -> Unit
) {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            modifier = Modifier.padding(32.dp)
        ) {
            Icon(
                CIRISIcons.checkCircle,
                contentDescription = null,
                tint = SemanticColors.Default.success,
                modifier = Modifier.size(64.dp)
            )
            Spacer(Modifier.height(16.dp))
            Text(
                text = "Skill Imported Successfully!",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold
            )
            Spacer(Modifier.height(8.dp))
            Text(
                text = "Module: $moduleName",
                style = MaterialTheme.typography.bodyLarge
            )
            if (toolsCreated.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Tools created: ${toolsCreated.joinToString(", ")}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Spacer(Modifier.height(24.dp))
            Button(
                onClick = onDone,
                modifier = Modifier.testable("btn_import_done")
            ) {
                Text("Done")
            }
        }
    }
}

@Composable
private fun ValidationErrorsCard(errors: List<String>) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    CIRISIcons.warning,
                    contentDescription = null,
                    tint = MaterialTheme.colorScheme.error
                )
                Spacer(Modifier.width(8.dp))
                Text(
                    "Please fix these issues:",
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onErrorContainer
                )
            }
            Spacer(Modifier.height(8.dp))
            errors.forEach { error ->
                Text(
                    text = "- $error",
                    color = MaterialTheme.colorScheme.onErrorContainer,
                    style = MaterialTheme.typography.bodyMedium
                )
            }
        }
    }
}

@Composable
private fun SkillMdPreview(markdown: String) {
    Surface(
        modifier = Modifier.fillMaxSize(),
        color = MaterialTheme.colorScheme.surfaceVariant
    ) {
        LazyColumn(
            modifier = Modifier.padding(16.dp)
        ) {
            item {
                Text(
                    text = markdown,
                    style = MaterialTheme.typography.bodySmall,
                    fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace
                )
            }
        }
    }
}

@Composable
private fun SecurityPreviewPlaceholder() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center
    ) {
        Text("Security scan will run before import")
    }
}

@Composable
private fun SecuritySummaryCard(report: SecurityReport) {
    val backgroundColor = if (report.safeToImport) {
        SemanticColors.Default.success.copy(alpha = 0.1f)
    } else {
        MaterialTheme.colorScheme.errorContainer
    }

    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(containerColor = backgroundColor)
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    imageVector = if (report.safeToImport) CIRISIcons.checkCircle else CIRISIcons.warning,
                    contentDescription = null,
                    tint = if (report.safeToImport) SemanticColors.Default.success else MaterialTheme.colorScheme.error,
                    modifier = Modifier.size(32.dp)
                )
                Spacer(Modifier.width(12.dp))
                Text(
                    text = if (report.safeToImport) "SAFE TO IMPORT" else "ISSUES FOUND",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.Bold
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(report.summary, style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(12.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceEvenly
            ) {
                SeverityCount("Critical", report.criticalCount, MaterialTheme.colorScheme.error)
                SeverityCount("High", report.highCount, SemanticColors.Default.warning)
                SeverityCount("Medium", report.mediumCount, SemanticColors.Default.info)
                SeverityCount("Low", report.lowCount, MaterialTheme.colorScheme.outline)
            }
        }
    }
}

@Composable
private fun SeverityCount(label: String, count: Int, color: androidx.compose.ui.graphics.Color) {
    Column(horizontalAlignment = Alignment.CenterHorizontally) {
        Text(
            text = count.toString(),
            style = MaterialTheme.typography.titleLarge,
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

@Composable
private fun SecurityFindingCard(finding: SecurityFinding) {
    val (icon, color) = when (finding.severity.lowercase()) {
        "critical" -> CIRISMaterialIcons.Filled.Error to MaterialTheme.colorScheme.error
        "high" -> CIRISIcons.warning to SemanticColors.Default.warning
        "medium" -> CIRISIcons.info to SemanticColors.Default.info
        else -> CIRISIcons.info to MaterialTheme.colorScheme.outline
    }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(icon, contentDescription = null, tint = color)
                Spacer(Modifier.width(8.dp))
                Text(
                    text = "${finding.severity.uppercase()}: ${finding.title}",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold
                )
            }
            Spacer(Modifier.height(8.dp))
            Text(finding.description, style = MaterialTheme.typography.bodyMedium)
            finding.evidence?.let { evidence ->
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "Evidence: $evidence",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            if (finding.recommendation.isNotBlank()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "Recommendation: ${finding.recommendation}",
                    style = MaterialTheme.typography.bodySmall,
                    fontWeight = FontWeight.Medium
                )
            }
        }
    }
}
