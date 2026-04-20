# CIRIS Mobile App - Help Index & User Guide

**Version 2.3.1** | Kotlin Multiplatform | Android/iOS/Windows/macOS/Linux

## Quick Reference

| Screen | Purpose | Access Path |
|--------|---------|-------------|
| **Login** | Sign in with Google/Apple/local account | App launch (if not authenticated) |
| **Setup** | First-run configuration wizard | After login (first time) |
| **Interact** | Main chat with CIRIS agent | Default after setup |
| **Settings** | Configure LLM, appearance, auth | Hamburger menu > Settings |
| **Billing** | Purchase CIRIS credits | Hamburger menu > Billing |

---

## Screens Reference

### 1. Startup Screen
**What it does**: Initializes the CIRIS agent engine with 22 services.

**Status Indicators**:
- **22 Service Lights**: Each light represents a backend service (memory, telemetry, audit, etc.)
- **8 Verify Steps**: CIRISVerify attestation progress (binary check, TPM, Ed25519, DNS, HTTPS, unified attestation)
- **6 Prep Lights**: Python library loading (pydantic, native libs, etc.)
- **Elapsed Timer**: Shows total startup time

**What to do if stuck**:
- Wait for up to 60 seconds on first run (libraries must compile)
- If error shows, tap "Retry" button
- Check network connectivity for LLM proxy mode

---

### 2. Login Screen
**What it does**: Authenticates you to use CIRIS services.

**Options**:
- **Sign in with Google** (Android/Web): Uses your Google account
- **Sign in with Apple** (iOS): Uses your Apple ID
- **Local Account**: Username/password for self-hosted instances

**Language Selector**: Tap globe icon (top-right) to change language (16 languages supported)

---

### 3. Setup Wizard
**What it does**: Configures your CIRIS agent on first run.

**Steps**:
1. **Welcome** - Introduction to CIRIS
2. **Authentication** - Confirm sign-in method
3. **Preferences** - Language, location sharing preferences
4. **LLM Configuration** - Choose CIRIS Proxy (recommended) or Bring Your Own Key (BYOK)
5. **Optional Features** - Enable weather, navigation, public API tools
6. **Adapters** - Select communication adapters (Discord, API, etc.)
7. **Confirmation** - Review and complete setup

**LLM Modes**:
- **CIRIS Proxy**: AI access included (credit-based)
- **BYOK**: Use your own OpenAI/Anthropic/other API key

---

### 4. Interact Screen (Main Chat)
**What it does**: Chat with your CIRIS agent.

**Elements**:
- **Message Input**: Type your message at bottom
- **Send Button**: Submit message (or press Enter)
- **Attach Files**: Add up to 3 files (images/documents, max 10MB each)
- **Processing Status**: Shows current pipeline step during response
- **Credit Indicator**: CIRIS credits remaining (if using proxy)
- **Wallet Indicator**: ETH balance (if wallet adapter enabled)
- **Trust Badge**: Attestation level (1-5 stars)

**Action Types** (shown in timeline):
| Icon | Action | Description |
|------|--------|-------------|
| Speech bubble | **Speak** | Agent sends a message |
| Tool icon | **Tool** | Agent uses an external tool |
| Lightbulb | **Ponder** | Agent deliberates (internal reasoning) |
| Hourglass | **Defer** | Agent escalates to Wise Authority |
| Checkmark | **Complete** | Task finished |

**Pipeline Visualization** (tap to expand):
- PDMA: Principled Decision Making
- CSDMA: Common Sense Checks
- IDMA: Intuition Analysis
- Conscience: Ethical evaluation

---

### 5. Settings Screen
**What it does**: Configure your CIRIS experience.

**Sections**:

**Display**
- Theme (light/dark)
- Color Palette
- Language selection

**AI Configuration** (BYOK mode only)
- LLM Provider (OpenAI, Anthropic, Groq, Together, LocalAI, Azure)
- Model selection
- API Key
- Base URL (for custom endpoints)

**Authentication**
- View current auth method
- Sign out
- Reset setup wizard

**Advanced**
- Device attestation status
- Token information
- Debug mode

---

### 6. Billing Screen
**What it does**: Manage CIRIS credits for AI access.

**Shows**:
- Current credit balance
- Available credit packages
- Purchase history

**Purchasing**:
- Select a credit package
- Complete purchase via Google Play/App Store
- Credits added immediately after purchase

---

### 7. Telemetry Screen
**What it does**: Monitor system health and resource usage.

**Metrics**:
- **Services Online**: X/22 services healthy
- **CPU Usage**: Current processor load
- **Memory Usage**: RAM consumption
- **Disk Usage**: Storage utilization
- **Activity** (24h): Messages, tasks, errors

**Export Destinations**: Configure where telemetry data is sent.

---

### 8. Sessions Screen
**What it does**: Manage cognitive states.

**States**:
| State | Purpose | Typical Use |
|-------|---------|-------------|
| **WAKEUP** | Identity confirmation | App startup |
| **WORK** | Normal task processing | Default operation |
| **PLAY** | Creative mode | Brainstorming, games |
| **SOLITUDE** | Self-reflection | Maintenance, learning |
| **DREAM** | Deep introspection | Complex reasoning |
| **SHUTDOWN** | Graceful termination | End session |

**Actions**:
- **Initiate State Change**: Request transition to different state
- **Return to WORK**: Resume normal operation

---

### 9. Memory Screen
**What it does**: Explore the agent's knowledge graph.

**Features**:
- **Search**: Find memories by keyword
- **Timeline**: Browse recent memories
- **Filters**: By scope (IDENTITY, USER, SERVICE), by type (Observation, Decision, Task)
- **Node Details**: Tap any memory to see full content

**Statistics**:
- Total nodes
- Nodes by type
- Recent 24h activity

---

### 10. Graph Memory Screen
**What it does**: Visualize the knowledge graph in 3D.

**Controls**:
- **Pan**: Drag to move view
- **Zoom**: Pinch to zoom in/out
- **Select**: Tap a node for details
- **Layout**: Force-directed or hierarchical
- **Filters**: Show/hide by scope or type

---

### 11. Services Screen
**What it does**: Monitor individual service health.

**Service Categories**:
- **Graph Services**: memory, consent, config, telemetry, audit, incident, tsdb
- **Infrastructure**: authentication, resource_monitor, database, secrets
- **Lifecycle**: initialization, shutdown, time, scheduler
- **Governance**: wise_authority, adaptive_filter, visibility, self_observation
- **Runtime**: llm, runtime_control

**Actions**:
- **Reset Circuit Breaker**: Restart failed service
- **Run Diagnostics**: Check service health

---

### 12. Wise Authority Screen
**What it does**: Handle ethical deferrals requiring human input.

**What is a deferral?**
When CIRIS encounters a decision requiring human judgment (ethical uncertainty, high risk, policy questions), it defers to the Wise Authority.

**Actions**:
- **Review**: Read the deferral context
- **Approve/Reject**: Provide guidance
- **Add Reasoning**: Explain your decision

---

### 13. Adapters Screen
**What it does**: Manage communication adapters.

**Default Adapter**: `api` (always enabled)

**Available Adapters**:
- **Discord**: Connect to Discord server
- **Home Assistant**: Smart home integration
- **Wallet**: Cryptocurrency operations
- **Weather**: Weather forecasts (NOAA)
- **Navigation**: Directions (OSM Nominatim)

**Configuration**: Each adapter has a wizard for setup.

---

### 14. Audit Screen
**What it does**: View system audit trail.

**Entry Details**:
- Timestamp
- Service name
- Action type
- Outcome (success/failure)
- Hash chain verification
- Digital signature

**Filters**: By service, action type, or outcome.

---

### 15. Logs Screen
**What it does**: View real-time system logs.

**Log Levels**:
- **DEBUG**: Detailed diagnostic info
- **INFO**: Normal operations
- **WARN**: Potential issues
- **ERROR**: Failures requiring attention

**Features**:
- Search by keyword
- Filter by level
- Auto-refresh toggle
- Export logs

---

### 16. Trust Screen
**What it does**: Display device attestation status.

**Attestation Levels**:
| Level | Name | Requirements |
|-------|------|--------------|
| 1 | Binary Loaded | CIRISVerify library present |
| 2 | Environment | Secure environment detected |
| 3 | Registry Cross-Validation | Network validation passed |
| 4 | File Integrity | Binary hash verified |
| 5 | Full Trust | Complete attestation (TPM/hardware) |

**Platform-Specific**:
- **Android**: Google Play Integrity API
- **iOS**: App Attest
- **Desktop**: Software-based (level 3 max)

---

### 17. Wallet Screen
**What it does**: Manage cryptocurrency for AI-to-AI payments.

**Features**:
- **Balance**: Current ETH balance
- **Send**: Transfer funds
- **Limits**: Daily/session spending caps
- **History**: Transaction log

**Gas Management**: Shows required ETH for transactions.

---

### 18. Scheduler Screen
**What it does**: Schedule recurring tasks.

**Task Types**:
- **One-time**: Run once at specified time
- **Recurring**: Run on schedule (daily, hourly, weekly)

**Schedule Options**:
- Custom cron expression
- Presets: Daily 9am, Every 2 hours, Weekly Monday

**Cognitive State Triggers**: Tasks can trigger state changes.

---

### 19. Config Screen
**What it does**: Advanced configuration management.

**Sections**: Grouped by prefix (adapter.*, service.*, security.*, etc.)

**Actions**:
- Search configurations
- Edit values
- Delete unused configs
- Filter by category

---

### 20. Consent Screen
**What it does**: Manage GDPR privacy preferences.

**Consent Streams**:
- **TEMPORARY**: Data deleted after session
- **PARTNERED**: Data shared with trusted partners
- **ANONYMOUS**: Aggregated data only

**Partnership Requests**: Review and approve data sharing requests.

---

### 21. Users Screen
**What it does**: Manage user accounts (admin only).

**Features**:
- User list with search
- Role management (API user, WA admin)
- Authentication type filtering
- Status filtering (active, disabled)

---

### 22. Tickets Screen
**What it does**: Track workflow tickets.

**Ticket Status**:
- Pending
- In Progress
- Completed
- Blocked

**Features**:
- Priority levels
- Deadline tracking
- Stage progression

---

### 23. Data Management Screen
**What it does**: GDPR data controls.

**Options**:
- **Delete Local Account**: Factory reset (removes all data)
- **Delete Opt-in Traces**: Remove telemetry data (GDPR Art. 17)
- **DSAR Request**: Download your data (self-service)

---

### 24. Runtime Screen (Advanced)
**What it does**: Step-by-step debugging of the H3ERE pipeline.

**Controls**:
- **Pause**: Stop processing
- **Resume**: Continue processing
- **Single Step**: Execute one pipeline step

**Pipeline Steps**:
1. Thought classification
2. DMA orchestration
3. PDMA (Principled)
4. CSDMA (Common Sense)
5. IDMA (Intuition)
6. Action selection
7. Handler dispatch
8. Tool execution
9. Memory update
10. Response generation
11. Output delivery

---

### 25. System Screen
**What it does**: System overview and controls.

**Features**:
- Health overview
- Resource usage graphs
- Environmental metrics (carbon, energy, cost)
- Service grid visualization
- Pause/Resume processor

---

### 26. Tools Screen
**What it does**: Browse available tools catalog.

**Tool Information**:
- Name and provider (which adapter)
- Description
- Parameters
- When to use
- DMA guidance (ethical considerations)

---

## Localization

CIRIS supports 16 languages:
- Amharic (am), Arabic (ar), German (de), English (en)
- Spanish (es), French (fr), Hindi (hi), Italian (it)
- Japanese (ja), Korean (ko), Portuguese (pt), Russian (ru)
- Swahili (sw), Turkish (tr), Urdu (ur), Chinese (zh)

**Change Language**: Settings > Display > Language

---

## Troubleshooting

### App won't start
1. Check network connection
2. Wait for full startup (can take 60s on first run)
3. Try "Retry" if error appears
4. Clear app data and restart

### Messages not sending
1. Check credit balance (if using CIRIS Proxy)
2. Verify API key (if using BYOK)
3. Check service health in Telemetry screen

### Login issues
1. Ensure Google/Apple account is active
2. Try signing out and back in
3. Check network connectivity

### Slow responses
1. Normal for complex questions
2. Watch pipeline visualization for progress
3. Consider using faster LLM model

### Attestation failing
1. Check Trust screen for details
2. Ensure device isn't rooted/jailbroken
3. Update to latest app version

---

## Keyboard Shortcuts (Desktop)

| Shortcut | Action |
|----------|--------|
| Enter | Send message |
| Shift+Enter | New line in message |
| Escape | Close dialogs |
| Ctrl/Cmd+K | Quick search |

---

## Getting Help

- **In-App**: Hamburger menu > Help
- **GitHub Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **Documentation**: See `/mobile/CLAUDE.md` for developer docs

---

## Version History

- **2.3.1**: Added location search, version display on billing screen
- **2.3.0**: Full localization (16 languages)
- **2.2.x**: iOS App Store release, Desktop support
- **2.1.x**: Wallet integration, Trust verification
- **2.0.0**: Kotlin Multiplatform rewrite

---

*CIRIS - Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude*
