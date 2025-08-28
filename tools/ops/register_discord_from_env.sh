#!/bin/bash
# Register Discord adapter using environment variables

# Load .env file
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Set defaults
API_URL="${CIRIS_API_URL:-http://localhost:8080}"
API_USER="${CIRIS_API_USER:-admin}"
API_PASSWORD="${CIRIS_API_PASSWORD:-ciris_admin_password}"

# Check if required variables are set
if [ -z "$DISCORD_BOT_TOKEN" ]; then
    echo "Error: DISCORD_BOT_TOKEN not set in .env"
    exit 1
fi

echo "Registering Discord adapter..."
echo "  Bot Token: ***${DISCORD_BOT_TOKEN: -10}"
echo "  Home Channel: $DISCORD_CHANNEL_ID"
echo "  Deferral Channel: $DISCORD_DEFERRAL_CHANNEL_ID"

# Login to get token
TOKEN=$(curl -s -X POST "$API_URL/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"username\": \"$API_USER\", \"password\": \"$API_PASSWORD\"}" | \
    jq -r '.access_token')

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
    echo "Error: Failed to login"
    exit 1
fi

echo "Logged in successfully"

# Build monitored channels array
MONITORED_CHANNELS="[\"$DISCORD_CHANNEL_ID\""
if [ ! -z "$SNORE_CHANNEL_ID" ] && [ "$SNORE_CHANNEL_ID" != "$DISCORD_CHANNEL_ID" ]; then
    MONITORED_CHANNELS="$MONITORED_CHANNELS, \"$SNORE_CHANNEL_ID\""
fi
MONITORED_CHANNELS="$MONITORED_CHANNELS]"

# Build admin users array
ADMIN_USERS="[]"
if [ ! -z "$WA_USER_ID" ]; then
    ADMIN_USERS="[\"$WA_USER_ID\"]"
fi

# Register adapter
RESPONSE=$(curl -s -X POST "$API_URL/v1/system/adapters/discord" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"config\": {
            \"bot_token\": \"$DISCORD_BOT_TOKEN\",
            \"home_channel_id\": \"$DISCORD_CHANNEL_ID\",
            \"deferral_channel_id\": \"$DISCORD_DEFERRAL_CHANNEL_ID\",
            \"monitored_channel_ids\": $MONITORED_CHANNELS,
            \"admin_user_ids\": $ADMIN_USERS,
            \"enabled\": true
        }
    }")

# Check if successful
SUCCESS=$(echo "$RESPONSE" | jq -r '.data.success')
if [ "$SUCCESS" = "true" ]; then
    ADAPTER_ID=$(echo "$RESPONSE" | jq -r '.data.adapter_id')
    echo "✅ Discord adapter registered successfully!"
    echo "   Adapter ID: $ADAPTER_ID"
    echo ""
    echo "Check status with:"
    echo "  curl -H \"Authorization: Bearer $TOKEN\" $API_URL/v1/system/adapters"
else
    echo "❌ Failed to register adapter:"
    echo "$RESPONSE" | jq
    exit 1
fi
