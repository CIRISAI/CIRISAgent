# CIRIS Standalone Installation

Get CIRIS Agent + GUI running in minutes without Docker.

## Quick Start

```bash
curl -sSL https://ciris.ai/install.sh | bash
```

That's it! The installer will:
- ✅ Install all dependencies (Python 3.9+, Node.js 20+, pnpm)
- ✅ Clone CIRISAgent and CIRISGUI repositories
- ✅ Set up Python virtual environment
- ✅ Install all packages
- ✅ Generate secure encryption keys
- ✅ Create systemd/launchd services (optional)
- ✅ Provide helper scripts for start/stop/status

## What You Get

After installation, you'll have:

```
~/ciris/
├── CIRISAgent/          # Agent backend (Python)
├── CIRISGUI/            # Web UI (Next.js)
├── .env                 # Configuration file
├── scripts/
│   ├── start.sh         # Start both services
│   ├── stop.sh          # Stop both services
│   └── status.sh        # Check service status
└── logs/                # Service logs (if using systemd/launchd)
```

## Installation Options

### Custom Installation Directory

```bash
curl -sSL https://ciris.ai/install.sh | bash -s -- --install-dir /opt/ciris
```

### Skip Service Installation

```bash
curl -sSL https://ciris.ai/install.sh | bash -s -- --skip-service
```

### Development Mode

Installs development dependencies and builds in dev mode:

```bash
curl -sSL https://ciris.ai/install.sh | bash -s -- --dev
```

### Install Specific Branches

```bash
curl -sSL https://ciris.ai/install.sh | bash -s -- --agent-branch release/1.6.2 --gui-branch develop
```

### Environment Variables

You can also configure via environment variables:

```bash
export CIRIS_INSTALL_DIR="/opt/ciris"
export CIRIS_AGENT_PORT="8080"
export CIRIS_GUI_PORT="3000"
curl -sSL https://ciris.ai/install.sh | bash
```

## Post-Installation

### 1. Configure Your API Key

Edit `~/ciris/.env` and add your OpenAI API key:

```bash
nano ~/ciris/.env
```

Replace `your_openai_api_key_here` with your actual key.

### 2. Start CIRIS

**Option A: As a Service (Linux with systemd)**

```bash
systemctl --user start ciris-agent ciris-gui
systemctl --user enable ciris-agent ciris-gui  # Start on boot
systemctl --user status ciris-agent ciris-gui  # Check status
```

**Option B: As a Service (macOS with launchd)**

Services start automatically after installation. To check:

```bash
launchctl list | grep ciris
```

**Option C: Manual Start**

```bash
~/ciris/scripts/start.sh
```

Press Ctrl+C to stop.

### 3. Open the Web UI

Open your browser to: **http://localhost:3000**

The agent API is available at: **http://localhost:8080**

## Management Commands

### Check Status

```bash
~/ciris/scripts/status.sh
```

### Stop Services

**Systemd:**
```bash
systemctl --user stop ciris-agent ciris-gui
```

**Launchd:**
```bash
launchctl unload ~/Library/LaunchAgents/ai.ciris.agent.plist
launchctl unload ~/Library/LaunchAgents/ai.ciris.gui.plist
```

**Manual:**
```bash
~/ciris/scripts/stop.sh
```

### View Logs

**Systemd:**
```bash
journalctl --user -u ciris-agent -f
journalctl --user -u ciris-gui -f
```

**Launchd:**
```bash
tail -f ~/ciris/logs/agent.log
tail -f ~/ciris/logs/gui.log
```

**Manual:**
```bash
tail -f ~/ciris/CIRISAgent/logs/latest.log
```

### Update CIRIS

```bash
cd ~/ciris/CIRISAgent
git pull origin main
source venv/bin/activate
pip install -r requirements.txt

cd ~/ciris/CIRISGUI
git pull origin main
pnpm install
cd apps/agui && pnpm build

# Restart services
systemctl --user restart ciris-agent ciris-gui
```

## Uninstallation

```bash
curl -sSL https://ciris.ai/install.sh | bash -s -- --uninstall
```

Or manually:

```bash
# Stop services
systemctl --user stop ciris-agent ciris-gui
systemctl --user disable ciris-agent ciris-gui
rm ~/.config/systemd/user/ciris-*.service

# Remove installation
rm -rf ~/ciris
```

## Supported Platforms

| Platform | Support | Init System | Package Manager |
|----------|---------|-------------|-----------------|
| Ubuntu 20.04+ | ✅ Full | systemd | apt |
| Debian 11+ | ✅ Full | systemd | apt |
| Fedora 36+ | ✅ Full | systemd | dnf |
| CentOS 8+ | ✅ Full | systemd | dnf/yum |
| Arch Linux | ✅ Full | systemd | pacman |
| macOS 11+ | ✅ Full | launchd | brew |
| WSL2 (Ubuntu) | ✅ Full | systemd | apt |
| Windows (native) | ⚠️ Manual | - | - |

## Troubleshooting

### Dependencies Installation Failed

**Issue**: Installer cannot install Python/Node automatically

**Solution**: Install manually:

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3 python3-pip python3-venv nodejs npm

# macOS
brew install python@3.12 node@20

# Then run installer with --skip-deps
curl -sSL https://ciris.ai/install.sh | bash -s -- --skip-deps
```

### Port Already in Use

**Issue**: Port 8080 or 3000 already in use

**Solution**: Configure different ports:

```bash
export CIRIS_AGENT_PORT="8081"
export CIRIS_GUI_PORT="3001"
curl -sSL https://ciris.ai/install.sh | bash
```

Or edit `~/ciris/.env` after installation.

### Services Won't Start

**Issue**: systemd/launchd services fail to start

**Solution**: Check logs:

```bash
# Systemd
journalctl --user -u ciris-agent -n 50

# Launchd
tail -50 ~/ciris/logs/agent.err.log

# Or start manually to see errors
~/ciris/scripts/start.sh
```

### GUI Cannot Connect to Agent

**Issue**: Web UI shows "Cannot connect to agent"

**Solution**:

1. Check agent is running: `curl http://localhost:8080/v1/status`
2. Check `.env` has correct `NEXT_PUBLIC_CIRIS_API_URL`
3. Check firewall isn't blocking localhost connections

### Python Version Too Old

**Issue**: Python 3.9+ required

**Solution**:

```bash
# Ubuntu: Use deadsnakes PPA
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv

# macOS
brew install python@3.12

# Then re-run installer
```

## Manual Installation

If you prefer not to use the installer script:

### 1. Install Dependencies

```bash
# Ubuntu/Debian
sudo apt-get install python3 python3-pip python3-venv nodejs npm git curl

# macOS
brew install python@3.12 node@20 git

# Install pnpm
npm install -g pnpm
```

### 2. Clone Repositories

```bash
mkdir -p ~/ciris
cd ~/ciris
git clone https://github.com/CIRISAI/CIRISAgent.git
git clone https://github.com/CIRISAI/CIRISGUI.git
```

### 3. Setup CIRISAgent

```bash
cd ~/ciris/CIRISAgent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Setup CIRISGUI

```bash
cd ~/ciris/CIRISGUI
pnpm install
cd apps/agui
pnpm build
```

### 5. Configure Environment

```bash
cd ~/ciris
cat > .env << 'EOF'
OPENAI_API_KEY="your_api_key_here"
SECRETS_MASTER_KEY="$(openssl rand -base64 32)"
TELEMETRY_ENCRYPTION_KEY="$(openssl rand -base64 32)"
LOG_LEVEL="INFO"
CIRIS_AGENT_PORT=8080
NEXT_PUBLIC_CIRIS_API_URL="http://localhost:8080"
EOF
```

### 6. Start Services

**Terminal 1 - Agent:**
```bash
cd ~/ciris/CIRISAgent
source venv/bin/activate
source ../.env
python main.py --adapter api --port 8080
```

**Terminal 2 - GUI:**
```bash
cd ~/ciris/CIRISGUI/apps/agui
source ../../.env
pnpm start --port 3000
```

## Advanced Configuration

### PostgreSQL Backend

By default, CIRIS uses SQLite. For production, configure PostgreSQL:

1. Install PostgreSQL:
   ```bash
   # Ubuntu
   sudo apt-get install postgresql postgresql-contrib

   # macOS
   brew install postgresql@15
   ```

2. Create database:
   ```bash
   sudo -u postgres psql
   CREATE DATABASE ciris_db;
   CREATE USER ciris_user WITH PASSWORD 'your_password';
   GRANT ALL PRIVILEGES ON DATABASE ciris_db TO ciris_user;
   \q
   ```

3. Configure in `~/ciris/.env`:
   ```bash
   CIRIS_DB_URL="postgresql://ciris_user:your_password@localhost:5432/ciris_db"
   ```

### Discord Integration

1. Create Discord bot at https://discord.com/developers/applications
2. Add bot token to `~/ciris/.env`:
   ```bash
   DISCORD_BOT_TOKEN="your_bot_token"
   DISCORD_CHANNEL_ID="your_channel_id"
   ```

3. Start with Discord adapter:
   ```bash
   cd ~/ciris/CIRISAgent
   source venv/bin/activate
   python main.py --adapter discord
   ```

### Reddit Integration

1. Create Reddit app at https://www.reddit.com/prefs/apps
2. Add credentials to `~/ciris/.env`:
   ```bash
   CIRIS_REDDIT_CLIENT_ID="your_client_id"
   CIRIS_REDDIT_CLIENT_SECRET="your_client_secret"
   CIRIS_REDDIT_USERNAME="your_username"
   CIRIS_REDDIT_PASSWORD="your_password"
   ```

3. Start with Reddit adapter:
   ```bash
   python main.py --adapter api --adapter reddit
   ```

## Getting Help

- **Documentation**: https://docs.ciris.ai
- **GitHub Issues**: https://github.com/CIRISAI/CIRISAgent/issues
- **Community**: Discord (link in README)

## Next Steps

- ✅ **[Quick Start Guide](QUICKSTART.md)** - Learn the basics
- ✅ **[API Reference](API_SPEC.md)** - REST API documentation
- ✅ **[Architecture Overview](ARCHITECTURE.md)** - System design
- ✅ **[Developer Guide](FOR_NERDS.md)** - Contributing and extending

---

**CIRIS: Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude**

*Ethical AI with human oversight, complete transparency, and deployment reliability.*
