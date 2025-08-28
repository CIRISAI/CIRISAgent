#!/bin/bash
# CIRIS Agent Deployment Script

SERVER_USER="deploy"
SERVER_HOST="agents.ciris.ai"
SERVER_PATH="/opt/ciris"
KEY_PATH="$HOME/.ssh/ciris_deploy"

echo "🚀 Deploying CIRIS Agent to agents.ciris.ai..."

# Test connection
echo "Testing SSH connection..."
ssh -i "$KEY_PATH" -o ConnectTimeout=5 "$SERVER_USER@$SERVER_HOST" "echo '✅ SSH connection successful'"
if [ $? -ne 0 ]; then
    echo "❌ SSH connection failed. Please check:"
    echo "   1. Public key is added to server's authorized_keys"
    echo "   2. Server is accessible"
    echo "   3. Username is correct"
    exit 1
fi

# Create deployment directory
echo "Setting up deployment directory..."
ssh -i "$KEY_PATH" "$SERVER_USER@$SERVER_HOST" "sudo mkdir -p $SERVER_PATH && sudo chown $SERVER_USER:$SERVER_USER $SERVER_PATH"

# Clone or update repository
echo "Updating code..."
ssh -i "$KEY_PATH" "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH && ([ -d CIRISAgent ] && cd CIRISAgent && git pull || git clone https://github.com/CIRISAI/CIRISAgent.git)"

# Create production .env if it doesn't exist
echo "Checking configuration..."
ssh -i "$KEY_PATH" "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH/CIRISAgent && [ ! -f .env ] && cp .env.example .env || true"

# Deploy with Docker Compose
echo "Deploying with Docker..."
ssh -i "$KEY_PATH" "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH/CIRISAgent && docker-compose -f docker-compose-api.yml pull && docker-compose -f docker-compose-api.yml up -d"

# Check status
echo "Checking deployment status..."
ssh -i "$KEY_PATH" "$SERVER_USER@$SERVER_HOST" "cd $SERVER_PATH/CIRISAgent && docker-compose -f docker-compose-api.yml ps"

echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "1. Configure .env with production values"
echo "2. Deploy CIRISManager for routing and multi-agent support"
echo "3. Test API: curl https://agents.ciris.ai/v1/system/health"
