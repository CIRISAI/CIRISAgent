package ai.ciris.mobile.shared.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import ai.ciris.mobile.shared.ui.icons.*
import ai.ciris.mobile.shared.ui.components.CIRISIcons
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import ai.ciris.mobile.shared.platform.testable
import ai.ciris.mobile.shared.platform.testableClickable
import ai.ciris.mobile.shared.platform.getAppVersion
import ai.ciris.mobile.shared.platform.getAppBuildNumber
import ai.ciris.mobile.shared.platform.openUrlInBrowser
import ai.ciris.mobile.shared.localization.localizedString

/**
 * Help screen providing user documentation and support resources.
 *
 * Features:
 * - Expandable FAQ sections
 * - Quick start guide
 * - Links to documentation and support
 * - Version information
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HelpScreen(
    onNavigateBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    val helpSections = remember { getHelpSections() }
    var expandedSections by remember { mutableStateOf(setOf<String>()) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(localizedString("mobile.screen_help")) },
                navigationIcon = {
                    IconButton(
                        onClick = onNavigateBack,
                        modifier = Modifier.testableClickable("btn_help_back") { onNavigateBack() }
                    ) {
                        Icon(
                            imageVector = CIRISIcons.arrowBack,
                            contentDescription = localizedString("mobile.common_back")
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
                .padding(horizontal = 16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(vertical = 16.dp)
        ) {
            // Welcome header
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.primaryContainer
                    )
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(20.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        Text(
                            text = localizedString("mobile.help_welcome_title"),
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                        Text(
                            text = localizedString("mobile.help_welcome_desc"),
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onPrimaryContainer
                        )
                    }
                }
            }

            // Help sections
            items(helpSections) { section ->
                HelpSectionCard(
                    section = section,
                    isExpanded = section.id in expandedSections,
                    onToggle = {
                        expandedSections = if (section.id in expandedSections) {
                            expandedSections - section.id
                        } else {
                            expandedSections + section.id
                        }
                    }
                )
            }

            // Support links
            item {
                Card(
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp)
                    ) {
                        Text(
                            text = localizedString("mobile.help_support_title"),
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )

                        OutlinedButton(
                            onClick = { openUrlInBrowser("https://github.com/CIRISAI/CIRISAgent/issues") },
                            modifier = Modifier
                                .fillMaxWidth()
                                .testableClickable("btn_help_github") {
                                    openUrlInBrowser("https://github.com/CIRISAI/CIRISAgent/issues")
                                }
                        ) {
                            Text(localizedString("mobile.help_report_issue"))
                        }

                        OutlinedButton(
                            onClick = { openUrlInBrowser("https://ciris.ai/docs") },
                            modifier = Modifier
                                .fillMaxWidth()
                                .testableClickable("btn_help_docs") {
                                    openUrlInBrowser("https://ciris.ai/docs")
                                }
                        ) {
                            Text(localizedString("mobile.help_documentation"))
                        }
                    }
                }
            }

            // Version info
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    colors = CardDefaults.cardColors(
                        containerColor = MaterialTheme.colorScheme.surfaceVariant
                    )
                ) {
                    Column(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(16.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Text(
                            text = "CIRIS Agent",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "v${getAppVersion()} (${getAppBuildNumber()})",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Text(
                            text = localizedString("mobile.help_copyright"),
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.7f)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun HelpSectionCard(
    section: HelpSection,
    isExpanded: Boolean,
    onToggle: () -> Unit,
    modifier: Modifier = Modifier
) {
    Card(
        modifier = modifier.fillMaxWidth(),
        onClick = onToggle
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .testableClickable("item_help_${section.id}") { onToggle() }
        ) {
            // Header
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(16.dp),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = localizedString(section.titleKey),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f)
                )
                Icon(
                    imageVector = if (isExpanded) CIRISIcons.arrowUp else CIRISIcons.arrowDown,
                    contentDescription = if (isExpanded) "Collapse" else "Expand",
                    tint = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }

            // Content (when expanded)
            if (isExpanded) {
                HorizontalDivider()
                Column(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    section.items.forEach { item ->
                        HelpItem(item)
                    }
                }
            }
        }
    }
}

@Composable
private fun HelpItem(
    item: HelpItem,
    modifier: Modifier = Modifier
) {
    Column(
        modifier = modifier.fillMaxWidth(),
        verticalArrangement = Arrangement.spacedBy(4.dp)
    ) {
        Text(
            text = localizedString(item.questionKey),
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.Medium,
            color = MaterialTheme.colorScheme.primary
        )
        Text(
            text = localizedString(item.answerKey),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )
    }
}

// Data classes
private data class HelpSection(
    val id: String,
    val titleKey: String,
    val items: List<HelpItem>
)

private data class HelpItem(
    val questionKey: String,
    val answerKey: String
)

// Help content
private fun getHelpSections(): List<HelpSection> = listOf(
    HelpSection(
        id = "getting_started",
        titleKey = "mobile.help_section_getting_started",
        items = listOf(
            HelpItem("mobile.help_q_what_is_ciris", "mobile.help_a_what_is_ciris"),
            HelpItem("mobile.help_q_how_to_chat", "mobile.help_a_how_to_chat"),
            HelpItem("mobile.help_q_credits", "mobile.help_a_credits")
        )
    ),
    HelpSection(
        id = "features",
        titleKey = "mobile.help_section_features",
        items = listOf(
            HelpItem("mobile.help_q_cognitive_states", "mobile.help_a_cognitive_states"),
            HelpItem("mobile.help_q_memory", "mobile.help_a_memory"),
            HelpItem("mobile.help_q_tools", "mobile.help_a_tools")
        )
    ),
    HelpSection(
        id = "settings",
        titleKey = "mobile.help_section_settings",
        items = listOf(
            HelpItem("mobile.help_q_llm_config", "mobile.help_a_llm_config"),
            HelpItem("mobile.help_q_byok", "mobile.help_a_byok"),
            HelpItem("mobile.help_q_language", "mobile.help_a_language")
        )
    ),
    HelpSection(
        id = "privacy",
        titleKey = "mobile.help_section_privacy",
        items = listOf(
            HelpItem("mobile.help_q_data_stored", "mobile.help_a_data_stored"),
            HelpItem("mobile.help_q_delete_data", "mobile.help_a_delete_data"),
            HelpItem("mobile.help_q_attestation", "mobile.help_a_attestation")
        )
    ),
    HelpSection(
        id = "troubleshooting",
        titleKey = "mobile.help_section_troubleshooting",
        items = listOf(
            HelpItem("mobile.help_q_app_slow", "mobile.help_a_app_slow"),
            HelpItem("mobile.help_q_no_response", "mobile.help_a_no_response"),
            HelpItem("mobile.help_q_credits_gone", "mobile.help_a_credits_gone")
        )
    )
)
