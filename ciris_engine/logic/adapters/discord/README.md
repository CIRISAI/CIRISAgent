# Discord Adapter

Production-ready Discord bot adapter providing community moderation, Wise Authority integration, and comprehensive Discord API support.

## Overview

The Discord Adapter is CIRIS's most mature adapter, currently powering community moderation at agents.ciris.ai. It provides full Discord bot functionality while maintaining CIRIS's ethical framework and audit trail requirements.

## Core Components

### Primary Services

**DiscordAdapter** - Main service implementing both `CommunicationService` and `WiseAuthorityService` protocols:
- Message handling and response generation
- Community moderation capabilities
- Wise Authority deferral and approval workflow
- Multi-channel monitoring and management
- Rate limiting and connection management

**DiscordToolService** - Discord-specific moderation tools:
- User management (timeouts, kicks, bans)
- Channel management and permissions
- Message moderation and content filtering
- Moderator identification and role management
- Real-time community monitoring

**DiscordObserver** - Event monitoring and telemetry:
- Message event tracking
- User behavior analysis
- Performance monitoring
- Audit trail generation

### Supporting Components

**DiscordConnectionManager** - Connection lifecycle and resilience:
- Automatic reconnection handling
- Connection state monitoring
- Graceful shutdown coordination
- Error recovery and failover

**DiscordChannelManager** - Multi-channel operations:
- Channel discovery and configuration
- Permission validation
- Message routing and context management
- Channel-specific behavior adaptation

**DiscordMessageHandler** - Message processing pipeline:
- Message parsing and validation
- Content filtering and moderation
- Response formatting and delivery
- Thread and reply management

**DiscordRateLimiter** - Discord API compliance:
- Automatic rate limit detection and handling
- Request queuing and prioritization
- Burst limit management
- API quota monitoring

**DiscordReactionHandler** - Reaction-based interactions:
- Approval/rejection reactions for WA workflows
- Interactive command interfaces
- User feedback collection
- Emoji-based navigation

## Discord-Specific Features

### Community Moderation
- **Automatic content filtering** with configurable sensitivity
- **User behavior analysis** and trust scoring
- **Escalation workflows** for problematic users
- **Moderator alerts** and notification system
- **Audit logging** of all moderation actions

### Wise Authority Integration
- **Deferral workflow** - Uncertain decisions escalated to designated Wise Authorities
- **Reaction-based approval** - WAs approve/reject through Discord reactions
- **Context preservation** - Full conversation context provided to WAs
- **Audit trail** - All WA interactions logged and traceable
- **Permission validation** - Ensures only authorized users can act as WAs

### Multi-Channel Support
- **Channel-specific behavior** - Different personalities/rules per channel
- **Permission inheritance** - Respects Discord's role-based permissions
- **Cross-channel context** - Maintains user context across channels
- **Channel discovery** - Automatic detection of accessible channels

### Error Handling & Resilience
- **Graceful degradation** - Continues operating with limited functionality
- **Automatic reconnection** - Handles Discord API outages
- **Message delivery guarantees** - Retry logic for critical messages
- **Fallback responses** - Generic responses when services unavailable

## Configuration

### Required Environment Variables
```bash
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_GUILD_ID=your_server_id_here
DISCORD_CHANNEL_ID=primary_channel_id  # Optional, discovers all accessible channels
```

### Optional Configuration
```bash
DISCORD_MONITORED_CHANNELS=channel1,channel2,channel3  # Specific channels to monitor
DISCORD_MAX_MESSAGE_LENGTH=2000  # Discord message limit
DISCORD_RATE_LIMIT_PER_SECOND=5  # Custom rate limiting
```

### Wise Authority Setup
Wise Authorities are configured through Discord roles and permissions. Users with appropriate permissions can:
- Receive deferral notifications via DM
- Approve/reject decisions through reactions
- Access detailed context and reasoning
- Override agent decisions when necessary

## Usage Examples

### Basic Discord Bot
```bash
python main.py --adapter discord --guild-id 123456789012345678
```

### Multi-Channel Moderation
```bash
python main.py --adapter discord --guild-id 123456789012345678 --template ubuntu
```

### Development with Mock LLM
```bash
python main.py --adapter discord --guild-id 123456789012345678 --mock-llm
```

## Available Tools

The DiscordToolService provides comprehensive moderation tools:

### User Management
- **`timeout_user`** - Temporary user timeout with duration
- **`kick_user`** - Remove user from server
- **`ban_user`** - Permanently ban user with reason
- **`get_user_info`** - Retrieve user profile and history

### Channel Management
- **`get_channel_info`** - Channel details and permissions
- **`list_channels`** - Available channels and access levels
- **`get_moderators`** - Identify users with moderation permissions

### Message Management
- **`delete_message`** - Remove problematic content
- **`edit_message`** - Correct or update agent messages
- **`send_dm`** - Direct message to users
- **`get_message_history`** - Retrieve channel message history

### Monitoring & Analysis
- **`get_server_info`** - Server statistics and member count
- **`analyze_user_behavior`** - User interaction patterns
- **`get_moderation_log`** - Recent moderation actions

## Architecture Integration

### Message Bus Integration
- **CommunicationBus** - Provides Discord communication implementation
- **WiseBus** - Enables distributed wisdom through Discord WAs
- **ToolBus** - Adds Discord-specific moderation tools
- **RuntimeControlBus** - Remote management through Discord commands

### Service Dependencies
- **TimeService** - For message timestamps and timeout durations
- **AuditService** - Complete logging of Discord interactions
- **MemoryService** - User context and behavior history storage
- **LLMService** - Response generation and content analysis

### Graph Memory Integration
- Stores Discord-specific nodes: `DiscordDeferralNode`, `DiscordApprovalNode`, `DiscordWANode`
- Maintains user interaction history in graph memory
- Tracks moderation decisions and outcomes
- Preserves Wise Authority approval chains

## Production Deployment

### Currently Running
The Discord Adapter is production-ready and currently deployed at:
- **agents.ciris.ai** - Community moderation and support
- **Multiple Discord servers** - Various community management roles
- **24/7 operation** - Continuous monitoring and moderation

### Performance Characteristics
- **Low latency** - <200ms average response time
- **High reliability** - 99.9%+ uptime with automatic recovery
- **Scalable** - Handles 1000+ member servers efficiently
- **Resource efficient** - ~100MB RAM per server deployment

### Monitoring & Observability
- **Real-time metrics** - Message rates, response times, error rates
- **Health checks** - Connection status, API quota usage
- **Audit trails** - Complete interaction logging for compliance
- **Performance alerts** - Proactive issue detection

## Development & Testing

### Testing Infrastructure
- **Mock Discord client** - Offline testing without Discord API
- **Integration tests** - Full workflow validation
- **Load testing** - High-volume message handling
- **Permission testing** - Role and permission validation

### Debugging Tools
- **Connection diagnostics** - Discord API connectivity testing
- **Message tracing** - End-to-end message flow tracking
- **Performance profiling** - Latency and throughput analysis
- **Error simulation** - Fault injection for resilience testing

---

*The Discord Adapter demonstrates CIRIS's production readiness, providing ethical AI moderation to Discord communities while maintaining complete transparency and human oversight through the Wise Authority system.*
