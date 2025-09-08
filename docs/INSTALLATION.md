# CIRIS Agent Installation Guide

Step-by-step installation guide for CIRIS Agent across different environments.

## Table of Contents

- [System Requirements](#system-requirements)
- [Pre-Installation Setup](#pre-installation-setup)
- [Installation Methods](#installation-methods)
- [Post-Installation Configuration](#post-installation-configuration)
- [Verification](#verification)
- [Platform-Specific Instructions](#platform-specific-instructions)

## System Requirements

### Minimum Requirements

- **Operating System**: Linux (Ubuntu 20.04+), macOS (10.15+), Windows 10/11 (with WSL2)
- **Python**: 3.9 or higher
- **Memory**: 512MB RAM minimum, 2GB+ recommended for production
- **Storage**: 1GB free space for databases, logs, and temporary files
- **Network**: Internet connectivity for LLM API calls and package downloads

### Recommended Requirements

- **CPU**: 2+ cores for concurrent processing
- **Memory**: 4GB+ RAM for production workloads
- **Storage**: 5GB+ free space with SSD for database performance
- **Network**: Stable broadband connection (10 Mbps+)

### Dependencies

- **Runtime dependencies**: Listed in `requirements.txt`
- **Development dependencies**: Listed in `requirements-dev.txt` (testing, type checking, code analysis)
- **System packages**: OpenSSL, SQLite3, Git
- **Optional**: Docker, Docker Compose for containerized deployment

## Pre-Installation Setup

### 1. System Preparation

**Ubuntu/Debian**:
```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install required system packages
sudo apt install -y python3 python3-pip python3-venv git openssl sqlite3 curl

# Install development tools (optional)
sudo apt install -y build-essential python3-dev
```

**CentOS/RHEL/Fedora**:
```bash
# Update system packages
sudo dnf update -y

# Install required packages
sudo dnf install -y python3 python3-pip git openssl sqlite curl

# Install development tools (optional)
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y python3-devel
```

**macOS**:
```bash
# Install Homebrew (if not already installed)
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install required packages
brew install python git openssl sqlite

# Install development tools (optional)
xcode-select --install
```

**Windows (WSL2)**:
```bash
# Install WSL2 with Ubuntu (run in PowerShell as Administrator)
wsl --install -d Ubuntu

# Follow Ubuntu instructions above within WSL2
```

### 2. User Account Setup

```bash
# Create dedicated user for CIRIS (recommended for production)
sudo useradd -m -s /bin/bash ciris
sudo usermod -aG sudo ciris  # Optional: if sudo access needed

# Switch to CIRIS user
sudo su - ciris

# Create necessary directories
mkdir -p ~/ciris/{logs,data,config,keys}
```

### 3. Environment Setup

```bash
# Create Python virtual environment
python3 -m venv ~/ciris/venv
source ~/ciris/venv/bin/activate

# Upgrade pip and essential tools
pip install --upgrade pip setuptools wheel
```

## Installation Methods

### Method 1: Git Clone Installation (Recommended)

```bash
# Clone the repository
cd ~/ciris
git clone https://github.com/your-org/CIRISAgent.git
cd CIRISAgent

# Activate virtual environment
source ~/ciris/venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# For development (testing, type checking, code analysis):
pip install -r requirements-dev.txt

# Install CIRIS package in development mode
pip install -e .
```

### Method 2: Package Installation

```bash
# Install from PyPI (when available)
pip install ciris-agent

# Or install from wheel file
pip install ciris_agent-1.0.0-py3-none-any.whl
```

### Method 3: Docker Installation

```bash
# Clone repository for Docker files
git clone https://github.com/your-org/CIRISAgent.git
cd CIRISAgent

# Build Docker image
docker build -t ciris-agent:latest -f docker/Dockerfile .

# Or use pre-built image
docker pull alignordie/cirisagent:latest
```

### Method 4: Docker Compose Installation

```bash
# Clone repository
git clone https://github.com/your-org/CIRISAgent.git
cd CIRISAgent

# Copy and customize Docker Compose configuration
cp docker-compose.yml docker-compose.local.yml
# Edit docker-compose.local.yml as needed

# Start services
docker-compose -f docker-compose.local.yml up -d
```

## Post-Installation Configuration

### 1. Environment Variables

Create environment configuration:

```bash
# Create environment file
cat > ~/.ciris_env << 'EOF'
# Core Configuration
export OPENAI_API_KEY="your_openai_api_key_here"
export LOG_LEVEL="INFO"

# Discord Configuration (if using Discord mode)
export DISCORD_BOT_TOKEN="your_discord_bot_token_here"
export DISCORD_CHANNEL_ID="your_channel_id_here"

# Security Configuration
export SECRETS_MASTER_KEY="$(openssl rand -base64 32)"
export TELEMETRY_ENCRYPTION_KEY="$(openssl rand -base64 32)"

# Database Paths
export CIRIS_DB_PATH="./data/ciris_engine.db"
export CIRIS_DATA_DIR="./data"
export SECRETS_DB_PATH="./secrets.db"
export AUDIT_LOG_PATH="./audit_logs.jsonl"

# Optional: CIRISNode Configuration
export CIRISNODE_BASE_URL="https://your-cirisnode.com:8001"
export CIRISNODE_AGENT_SECRET_JWT="your_jwt_token"
EOF

# Load environment variables
source ~/.ciris_env

# Add to shell profile for persistence
echo "source ~/.ciris_env" >> ~/.bashrc
```

### 2. Configuration Files

```bash
# Copy base configuration
cp config/base.yaml config/local.yaml

# Customize configuration
cat > config/local.yaml << 'EOF'
version: "1.0"
log_level: "INFO"

# Database Configuration
database:
  db_filename: "./data/ciris_engine.db"
  data_directory: "./data"
  graph_memory_filename: "./data/graph_memory.pkl"

# LLM Configuration
llm_services:
  openai:
    model_name: "gpt-4o-mini"
    timeout_seconds: 30.0
    max_retries: 3
    api_key_env_var: "OPENAI_API_KEY"

# Workflow Configuration
workflow:
  max_active_tasks: 10
  max_active_thoughts: 50
  round_delay_seconds: 1.0

# Enable core services
telemetry:
  enabled: true
secrets:
  enabled: true
audit:
  enable_signed_audit: false  # Enable for production
  enable_jsonl_audit: true
EOF
```

### 3. Security Setup

```bash
# Generate encryption keys
mkdir -p ~/ciris/keys

# Generate secrets master key
openssl rand -base64 32 > ~/ciris/keys/secrets_master.key
export SECRETS_MASTER_KEY=$(cat ~/ciris/keys/secrets_master.key)

# Generate telemetry encryption key
openssl rand -base64 32 > ~/ciris/keys/telemetry.key
export TELEMETRY_ENCRYPTION_KEY=$(cat ~/ciris/keys/telemetry.key)

# Set secure permissions
chmod 600 ~/ciris/keys/*.key

# Generate audit keys (for production)
mkdir -p ~/ciris/audit_keys
openssl genrsa -out ~/ciris/audit_keys/audit_private.pem 4096
openssl rsa -in ~/ciris/audit_keys/audit_private.pem \
  -pubout -out ~/ciris/audit_keys/audit_public.pem
chmod 600 ~/ciris/audit_keys/audit_private.pem
chmod 644 ~/ciris/audit_keys/audit_public.pem
```

### 4. Database Initialization

```bash
# Initialize databases
python -c "
from ciris_engine.persistence.db.setup import initialize_database
initialize_database()
print('✅ Database initialized successfully')
"

# Verify database creation
ls -la data/
```

### 5. Agent Template Configuration (For New Agent Creation Only)

⚠️ **IMPORTANT**: Profile templates are ONLY used during initial agent creation. After creation, identity is managed through the graph database.

```bash
# Create custom agent template for new agent creation
cat > ciris_profiles/production.yaml << 'EOF'
name: "production"
description: "Template for production agents"
dsdma_identifier: "ProductionDSDMA"
permitted_actions:
  - "OBSERVE"
  - "SPEAK"
  - "TOOL"
  - "MEMORIZE"
  - "RECALL"
  - "DEFER"
  - "PONDER"

guardrails_config:
  entropy_threshold: 0.8
  coherence_threshold: 0.7
  optimization_veto_enabled: true
  epistemic_humility_threshold: 0.9

csdma_overrides:
  temperature: 0.7
  max_tokens: 1000

action_selection_pdma_overrides:
  reasoning_depth: "thorough"
EOF
```

## Verification

### 1. Installation Verification

```bash
# Test basic imports
python -c "
from ciris_engine.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.config.config_loader import ConfigLoader
print('✅ Core modules imported successfully')
"

# Test configuration loading
python -c "
from ciris_engine.config.config_loader import ConfigLoader
import asyncio

async def test_config():
    config = await ConfigLoader.load_config()
    print(f'✅ Configuration loaded: {config.version}')

asyncio.run(test_config())
"

# Test database connection
python -c "
from ciris_engine.persistence.db.core import get_db_connection
conn = get_db_connection()
if conn:
    print('✅ Database connection successful')
    conn.close()
else:
    print('❌ Database connection failed')
"
```

### 2. Service Verification

```bash
# Test LLM service
python -c "
import os
import openai
openai.api_key = os.getenv('OPENAI_API_KEY')
try:
    models = openai.Model.list()
    print('✅ OpenAI API connection successful')
except Exception as e:
    print(f'❌ OpenAI API error: {e}')
"

# Test Discord service (if configured)
python -c "
import os
import discord
import asyncio

async def test_discord():
    if not os.getenv('DISCORD_BOT_TOKEN'):
        print('⚠️  Discord token not configured')
        return

    try:
        client = discord.Client()
        await client.login(os.getenv('DISCORD_BOT_TOKEN'))
        await client.close()
        print('✅ Discord connection successful')
    except Exception as e:
        print(f'❌ Discord error: {e}')

asyncio.run(test_discord())
"
```

### 3. End-to-End Test

```bash
# Test CLI mode
python main.py --mode cli --test-mode &  # Profile only needed with --wa-bootstrap
CIRIS_PID=$!

# Wait for startup
sleep 5

# Check if process is running
if kill -0 $CIRIS_PID 2>/dev/null; then
    echo "✅ CIRIS Agent started successfully"
    # Stop the test
    kill $CIRIS_PID
else
    echo "❌ CIRIS Agent failed to start"
fi

# Check logs
if [ -f "logs/latest.log" ]; then
    echo "Recent log entries:"
    tail -5 logs/latest.log
fi
```

## Platform-Specific Instructions

### Ubuntu/Debian Production Setup

```bash
# Create systemd service
sudo tee /etc/systemd/system/ciris-agent.service << 'EOF'
[Unit]
Description=CIRIS Agent
After=network.target

[Service]
Type=simple
User=ciris
Group=ciris
WorkingDirectory=/home/ciris/CIRISAgent
Environment=PATH=/home/ciris/ciris/venv/bin
ExecStart=/home/ciris/ciris/venv/bin/python main.py --mode discord
EnvironmentFile=/home/ciris/.ciris_env
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable ciris-agent
sudo systemctl start ciris-agent

# Check status
sudo systemctl status ciris-agent
```

### Docker Production Setup

```bash
# Create production docker-compose.yml
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  ciris-agent:
    image: alignordie/cirisagent:latest
    container_name: ciris-agent-prod
    restart: unless-stopped
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN}
      - DISCORD_CHANNEL_ID=${DISCORD_CHANNEL_ID}
      - SECRETS_MASTER_KEY=${SECRETS_MASTER_KEY}
      - LOG_LEVEL=WARNING
    volumes:
      - ./data:/app/data
      - ./config:/app/config
      - ./logs:/app/logs
      - ./audit_keys:/app/audit_keys
    networks:
      - ciris-network

networks:
  ciris-network:
    driver: bridge
EOF

# Start production deployment
docker-compose -f docker-compose.prod.yml up -d

# Monitor logs
docker-compose -f docker-compose.prod.yml logs -f
```

### macOS Development Setup

```bash
# Install additional development tools
brew install --cask docker visual-studio-code

# Create launchd service for auto-start
mkdir -p ~/Library/LaunchAgents
cat > ~/Library/LaunchAgents/com.ciris.agent.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ciris.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/CIRISAgent/main.py</string>
        <string>--mode</string>
        <string>cli</string>
        <!-- Profile only used with --wa-bootstrap for new agents -->
        <string>default</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/CIRISAgent</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

# Load the service
launchctl load ~/Library/LaunchAgents/com.ciris.agent.plist
```

### Windows WSL2 Setup

```bash
# Install Windows-specific tools in PowerShell
winget install Docker.DockerDesktop
winget install Microsoft.VisualStudioCode

# In WSL2, set up CIRIS
cd /home/$USER
git clone https://github.com/your-org/CIRISAgent.git
cd CIRISAgent

# Follow standard Linux installation steps
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# For development: pip install -r requirements-dev.txt

# Create Windows batch file for easy startup
cat > /mnt/c/Users/$USER/Desktop/start-ciris.bat << 'EOF'
@echo off
wsl -d Ubuntu -e bash -c "cd /home/$USER/CIRISAgent && source venv/bin/activate && python main.py --mode cli"
EOF
```

## Troubleshooting Installation

### Common Issues

1. **Permission Denied Errors**:
   ```bash
   # Fix file permissions
   chmod +x main.py
   chmod 600 ~/ciris/keys/*
   sudo chown -R ciris:ciris /home/ciris/
   ```

2. **Python Module Not Found**:
   ```bash
   # Ensure virtual environment is activated
   source ~/ciris/venv/bin/activate
   # Reinstall dependencies
   pip install -r requirements.txt
   # For development: pip install -r requirements-dev.txt
   ```

3. **Database Lock Errors**:
   ```bash
   # Remove lock files
   rm -f data/*.db-wal data/*.db-shm
   # Restart with clean database
   rm -f data/ciris_engine.db
   python -c "from ciris_engine.persistence.db.setup import initialize_database; initialize_database()"
   ```

4. **API Key Issues**:
   ```bash
   # Test API key directly
   curl -H "Authorization: Bearer $OPENAI_API_KEY" https://api.openai.com/v1/models
   ```

### Getting Help

- **Documentation**: Check module READMEs in `ciris_engine/*/README.md`
- **Logs**: Review `logs/latest.log` for error details
- **Configuration**: Verify with `python -c "from ciris_engine.config import load_config; print(load_config())"`
- **Tests**: Run test suite with `pytest tests/`
- **Community**: Submit issues to GitHub repository

### Next Steps

After successful installation:

1. **Read the [Deployment Guide](DEPLOYMENT_GUIDE.md)** for production setup
2. **Review [Security Setup](SECURITY_SETUP.md)** for enterprise security
3. **Check [Troubleshooting Guide](TROUBLESHOOTING.md)** for common issues
4. **Explore agent templates** in `ciris_profiles/` directory (used only during creation)
5. **Run test suite** with `pytest tests/` to verify functionality

Congratulations! Your CIRIS Agent installation is complete.
