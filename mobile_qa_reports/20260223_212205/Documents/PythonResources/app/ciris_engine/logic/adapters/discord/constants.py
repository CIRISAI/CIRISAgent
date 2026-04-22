"""
Constants for Discord adapter to eliminate duplicate literals.
"""

# Error Messages
ERROR_TIME_SERVICE_NOT_INITIALIZED = "Time service not initialized"
ERROR_DISCORD_CLIENT_NOT_INITIALIZED = "Discord client not initialized"
ERROR_GUILD_ID_AND_USER_ID_REQUIRED = "guild_id and user_id are required"
ERROR_GUILD_ID_USER_ID_ROLE_NAME_REQUIRED = "guild_id, user_id, and role_name are required"
ERROR_CHANNEL_ID_REQUIRED = "channel_id is required"
ERROR_CHANNEL_ID_AND_CONTENT_REQUIRED = "channel_id and content are required"
ERROR_CHANNEL_ID_AND_MESSAGE_ID_REQUIRED = "channel_id and message_id are required"
ERROR_USER_ID_REQUIRED = "user_id is required"
ERROR_GUIDANCE_CHANNEL_NOT_CONFIGURED = "DiscordAdapter: Guidance channel not configured."
ERROR_DEFERRAL_CHANNEL_NOT_CONFIGURED = "DiscordAdapter: Deferral channel not configured."
ERROR_DISCORD_CLIENT_NOT_AVAILABLE = "Discord client not available"
ERROR_DEFERRAL_CHANNEL_NOT_FOUND = "Deferral channel {} not found"
ERROR_ROLE_NOT_FOUND = "Role '{}' not found"
ERROR_CHANNEL_DOES_NOT_SUPPORT_MESSAGES = "Channel {} does not support sending messages"
ERROR_GUILD_NOT_FOUND = "Guild {} not found"

# Field Descriptions
FIELD_DESC_DISCORD_CHANNEL_ID = "Discord channel ID"
FIELD_DESC_DISCORD_GUILD_ID = "Discord guild ID"
FIELD_DESC_USER_ID = "User ID"
FIELD_DESC_MESSAGE_CONTENT = "Message content to send"
FIELD_DESC_MESSAGE_ID = "Message ID to delete"
FIELD_DESC_TIMEOUT_DURATION = "Timeout duration in seconds"
FIELD_DESC_TIMEOUT_REASON = "Reason for timeout"
FIELD_DESC_BAN_REASON = "Reason for ban"
FIELD_DESC_KICK_REASON = "Reason for kick"
FIELD_DESC_ROLE_NAME = "Name of role to add"
FIELD_DESC_ROLE_NAME_REMOVE = "Name of role to remove"
FIELD_DESC_USER_ID_TO_TIMEOUT = "User ID to timeout"
FIELD_DESC_USER_ID_TO_BAN = "User ID to ban"
FIELD_DESC_USER_ID_TO_KICK = "User ID to kick"
FIELD_DESC_DELETE_MESSAGE_DAYS = "Days of messages to delete"
FIELD_DESC_GUILD_ID_OPTIONAL = "Optional guild ID for guild-specific info"
FIELD_DESC_CHANNEL_ID_GET_INFO = "Channel ID to get info for"
FIELD_DESC_USER_ID_GET_INFO = "User ID to get info for"
FIELD_DESC_EMBED_TITLE = "Embed title"
FIELD_DESC_EMBED_DESCRIPTION = "Embed description"
FIELD_DESC_EMBED_COLOR = "Embed color (hex)"

# Field Names for Embeds
FIELD_NAME_TASK_ID = "Task ID"
FIELD_NAME_THOUGHT_ID = "Thought ID"
FIELD_NAME_DEFERRAL_ID = "Deferral ID"
FIELD_NAME_DEFER_UNTIL = "Defer Until"
FIELD_NAME_CONTEXT = "Context"
FIELD_NAME_REQUESTER = "Requester"
FIELD_NAME_ACTION_TYPE = "Action Type"
FIELD_NAME_PARAMETERS = "Parameters"
FIELD_NAME_OUTPUT = "Output"
FIELD_NAME_ERROR = "Error"
FIELD_NAME_EXECUTION_TIME = "Execution Time"
FIELD_NAME_PRIORITY = "Priority"
FIELD_NAME_PROGRESS = "Progress"
FIELD_NAME_CREATED = "Created"
FIELD_NAME_SUBTASKS = "Subtasks"
FIELD_NAME_ACTOR = "Actor"
FIELD_NAME_SERVICE = "Service"
FIELD_NAME_TIME = "Time"
FIELD_NAME_RESULT = "Result"
FIELD_NAME_OPERATION = "Operation"
FIELD_NAME_SEVERITY = "Severity"
FIELD_NAME_RETRYABLE = "Retryable"
FIELD_NAME_SUGGESTED_FIX = "Suggested Fix"

# Status Messages
STATUS_MESSAGE_EXECUTING = "Executing..."
STATUS_MESSAGE_COMPLETED = "Completed"
STATUS_MESSAGE_FAILED = "Failed"
STATUS_MESSAGE_SUCCESS = "✅ Success"
STATUS_MESSAGE_FAILED_WITH_ICON = "❌ Failed"

# Permissions
PERMISSION_AUTHORITY = "AUTHORITY"
PERMISSION_OBSERVER = "OBSERVER"

# Action Types for Authorization
ACTION_READ = "read"
ACTION_OBSERVE = "observe"
ACTION_FETCH = "fetch"

# Service Names and Types
SERVICE_NAME_DISCORD_ADAPTER = "DiscordAdapter"
SERVICE_NAME_DISCORD_TOOL_SERVICE = "DiscordToolService"
SERVICE_TYPE_DISCORD = "discord"
SERVICE_TYPE_ADAPTER = "adapter"
SERVICE_TYPE_TOOL = "TOOL"

# Telemetry Metric Names
METRIC_DISCORD_MESSAGE_SENT = "discord.message.sent"
METRIC_DISCORD_MESSAGE_RECEIVED = "discord.message.received"
METRIC_DISCORD_TOOL_EXECUTED = "discord.tool.executed"
METRIC_DISCORD_ADAPTER_STARTING = "discord.adapter.starting"
METRIC_DISCORD_ADAPTER_STARTED = "discord.adapter.started"
METRIC_DISCORD_ADAPTER_STOPPING = "discord.adapter.stopping"
METRIC_DISCORD_ADAPTER_STOPPED = "discord.adapter.stopped"
METRIC_DISCORD_CONNECTION_ESTABLISHED = "discord.connection.established"
METRIC_DISCORD_CONNECTION_LOST = "discord.connection.lost"
METRIC_DISCORD_CONNECTION_RECONNECTING = "discord.connection.reconnecting"
METRIC_DISCORD_CONNECTION_FAILED = "discord.connection.failed"

# Default Values
DEFAULT_TIMEOUT_DURATION_SECONDS = 300
DEFAULT_DELETE_MESSAGE_DAYS = 0
DEFAULT_EMBED_COLOR = 0x3498DB
DEFAULT_MESSAGE_LIMIT = 50
DEFAULT_PAGE_SIZE = 10
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BASE_DELAY = 2.0
DEFAULT_RETRY_MAX_DELAY = 30.0
DEFAULT_TOOL_TIMEOUT = 30.0
DEFAULT_READY_TIMEOUT = 30.0
DEFAULT_APPROVAL_TIMEOUT_SECONDS = 300

# Operation Names
OPERATION_SEND_MESSAGE = "send_message"
OPERATION_FETCH_MESSAGES = "fetch_messages"
OPERATION_FETCH_GUIDANCE = "fetch_guidance"
OPERATION_SEND_OUTPUT = "send_output"

# Config Keys
CONFIG_KEY_DISCORD_API = "discord_api"
CONFIG_KEY_RETRY = "retry"
CONFIG_KEY_GLOBAL = "global"

# Node Types
NODE_TYPE_DISCORD_DEFERRAL = "DISCORD_DEFERRAL"
NODE_TYPE_DISCORD_APPROVAL = "DISCORD_APPROVAL"

# Action Names
ACTION_SPEAK = "speak"
ACTION_OBSERVE = "observe"
ACTION_SEND_DEFERRAL = "send_deferral"
ACTION_FETCH_GUIDANCE = "fetch_guidance"

# Scope Values
SCOPE_LOCAL = "local"

# Handler Names
HANDLER_NAME_DISCORD_ADAPTER = "discord_adapter"
HANDLER_NAME_ADAPTER_DISCORD = "adapter.discord"

# Approval Status
APPROVAL_STATUS_PENDING = "pending"

# Embed Field Names
EMBED_HOW_TO_RESPOND = "How to Respond"
EMBED_RESPOND_INSTRUCTIONS = "React with ✅ to approve or ❌ to deny"

# Reaction Emojis
REACTION_APPROVE = "✅"
REACTION_DENY = "❌"
REACTION_REQUEST_INFO = "🔄"

# Status Emojis
STATUS_EMOJI_PENDING = "⏳"
STATUS_EMOJI_IN_PROGRESS = "🔄"
STATUS_EMOJI_COMPLETED = "✅"
STATUS_EMOJI_FAILED = "❌"
STATUS_EMOJI_DEFERRED = "⏸️"
STATUS_EMOJI_UNKNOWN = "❓"

# Adapter Type
ADAPTER_TYPE_DISCORD = "discord"

# Channel Type
CHANNEL_TYPE_DISCORD = "discord"

# Message Formatting
MESSAGE_PREFIX_DEFERRAL_REQUEST = "**DEFERRAL REQUEST (ID: {})**"
MESSAGE_PREFIX_DEFERRAL_RESOLVED = "**DEFERRAL RESOLVED**"
MESSAGE_CONTINUED_FROM_DEFERRAL = "*(Continued from deferral {})*"
MESSAGE_DEFERRAL_CONTENT_TOO_LONG = "**DEFERRAL REQUEST** (content too long)"

# Logging Messages
LOG_DISCORD_ADAPTER_ATTACHED = "DiscordAdapter.attach_to_client: Attaching to Discord client"
LOG_ALL_HANDLERS_ATTACHED = "DiscordAdapter.attach_to_client: All handlers attached"
LOG_DISCORD_ADAPTER_STARTED = "Discord adapter started successfully"
LOG_DISCORD_ADAPTER_STOPPED = "Discord adapter stopped successfully"
LOG_DISCORD_TOOL_SERVICE_STARTED = "Discord tool service started"
LOG_DISCORD_TOOL_SERVICE_STOPPED = "Discord tool service stopped"
