#!/usr/bin/env bash
#
# CIRIS Standalone Installer
# ===========================
# One-command installation for CIRISAgent + CIRISGUI
#
# Usage:
#   curl -sSL https://ciris.ai/install.sh | bash
#
# Or with options:
#   curl -sSL https://ciris.ai/install.sh | bash -s -- --skip-service --install-dir ~/my-ciris
#
# Copyright © 2025 Eric Moore and CIRIS L3C | Apache 2.0 License
#

set -e
set -o pipefail

# Cleanup on error
cleanup_on_error() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        log_error "Installation failed with exit code $exit_code"
        log_info "Check the error messages above for details"
    fi
}
trap cleanup_on_error EXIT

# ============================================================================
# Configuration
# ============================================================================

INSTALL_DIR="${CIRIS_INSTALL_DIR:-$HOME/ciris}"
AGENT_REPO="https://github.com/CIRISAI/CIRISAgent.git"
GUI_REPO="https://github.com/CIRISAI/CIRISGUI.git"
AGENT_BRANCH="${CIRIS_AGENT_BRANCH:-main}"
GUI_BRANCH="${CIRIS_GUI_BRANCH:-main}"

# Service names
AGENT_SERVICE_NAME="ciris-agent"
GUI_SERVICE_NAME="ciris-gui"

# Ports
AGENT_PORT="${CIRIS_AGENT_PORT:-8080}"
GUI_PORT="${CIRIS_GUI_PORT:-3000}"

# Flags
SKIP_SERVICE=false
SKIP_DEPS=false
DEV_MODE=false
UNINSTALL=false

# ============================================================================
# Colors and Formatting
# ============================================================================

if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    MAGENTA='\033[0;35m'
    CYAN='\033[0;36m'
    BOLD='\033[1m'
    RESET='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    MAGENTA=''
    CYAN=''
    BOLD=''
    RESET=''
fi

# ============================================================================
# Helper Functions
# ============================================================================

log_info() {
    echo -e "${BLUE}ℹ${RESET} $1"
}

log_success() {
    echo -e "${GREEN}✓${RESET} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${RESET} $1"
}

log_error() {
    echo -e "${RED}✗${RESET} $1" >&2
}

log_step() {
    echo ""
    echo -e "${CYAN}${BOLD}▸ $1${RESET}"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

detect_os() {
    case "$(uname -s)" in
        Linux*)
            if grep -qi microsoft /proc/version 2>/dev/null; then
                echo "wsl"
            else
                echo "linux"
            fi
            ;;
        Darwin*)
            echo "macos"
            ;;
        CYGWIN*|MINGW*|MSYS*)
            echo "windows"
            ;;
        *)
            echo "unknown"
            ;;
    esac
}

detect_init_system() {
    if command_exists systemctl; then
        echo "systemd"
    elif command_exists launchctl; then
        echo "launchd"
    else
        echo "none"
    fi
}

get_package_manager() {
    if command_exists apt-get; then
        echo "apt"
    elif command_exists dnf; then
        echo "dnf"
    elif command_exists yum; then
        echo "yum"
    elif command_exists brew; then
        echo "brew"
    elif command_exists pacman; then
        echo "pacman"
    else
        echo "none"
    fi
}

# ============================================================================
# Dependency Installation
# ============================================================================

install_dependencies() {
    log_step "Installing system dependencies"

    local os_type
    os_type=$(detect_os)
    local pkg_mgr
    pkg_mgr=$(get_package_manager)

    # Check Python
    if ! command_exists python3; then
        log_warn "Python 3 not found, installing..."
        case "$pkg_mgr" in
            apt)
                sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
                ;;
            dnf|yum)
                sudo "$pkg_mgr" install -y python3 python3-pip
                ;;
            brew)
                brew install python@3.12
                ;;
            pacman)
                sudo pacman -S --noconfirm python python-pip
                ;;
            *)
                log_error "Cannot automatically install Python. Please install Python 3.9+ manually."
                exit 1
                ;;
        esac
    else
        # Check Python version
        local py_version
        py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        log_success "Python $py_version found"

        # Verify minimum version (3.9)
        if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 9) else 1)'; then
            log_error "Python 3.9+ required, found $py_version"
            exit 1
        fi
    fi

    # Check Node.js
    if ! command_exists node; then
        log_warn "Node.js not found, installing..."
        case "$pkg_mgr" in
            apt)
                curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
                sudo apt-get install -y nodejs
                ;;
            dnf|yum)
                curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
                sudo "$pkg_mgr" install -y nodejs
                ;;
            brew)
                brew install node@20
                ;;
            pacman)
                sudo pacman -S --noconfirm nodejs npm
                ;;
            *)
                log_error "Cannot automatically install Node.js. Please install Node.js 18+ manually from https://nodejs.org"
                exit 1
                ;;
        esac
    else
        local node_version
        node_version=$(node --version | cut -d'v' -f2)
        log_success "Node.js $node_version found"
    fi

    # Install pnpm
    if ! command_exists pnpm; then
        log_info "Installing pnpm..."
        npm install -g pnpm
    else
        log_success "pnpm $(pnpm --version) found"
    fi

    # Install git
    if ! command_exists git; then
        log_warn "Git not found, installing..."
        case "$pkg_mgr" in
            apt)
                sudo apt-get install -y git
                ;;
            dnf|yum)
                sudo "$pkg_mgr" install -y git
                ;;
            brew)
                brew install git
                ;;
            pacman)
                sudo pacman -S --noconfirm git
                ;;
        esac
    else
        log_success "Git $(git --version | cut -d' ' -f3) found"
    fi

    # Install additional tools
    if ! command_exists curl; then
        log_warn "curl not found, installing..."
        case "$pkg_mgr" in
            apt)
                sudo apt-get install -y curl
                ;;
            dnf|yum)
                sudo "$pkg_mgr" install -y curl
                ;;
            brew)
                brew install curl
                ;;
            pacman)
                sudo pacman -S --noconfirm curl
                ;;
        esac
    fi
}

# ============================================================================
# Repository Setup
# ============================================================================

clone_repositories() {
    log_step "Cloning repositories"

    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"

    # Clone CIRISAgent
    if [ -d "CIRISAgent" ]; then
        log_info "CIRISAgent already exists, pulling latest..."
        cd CIRISAgent
        git fetch origin
        git checkout "$AGENT_BRANCH"
        git pull origin "$AGENT_BRANCH"
        cd ..
    else
        log_info "Cloning CIRISAgent..."
        git clone --branch "$AGENT_BRANCH" "$AGENT_REPO" CIRISAgent
    fi

    # Clone CIRISGUI
    if [ -d "CIRISGUI" ]; then
        log_info "CIRISGUI already exists, pulling latest..."
        cd CIRISGUI
        git fetch origin
        git checkout "$GUI_BRANCH"
        git pull origin "$GUI_BRANCH"
        cd ..
    else
        log_info "Cloning CIRISGUI..."
        git clone --branch "$GUI_BRANCH" "$GUI_REPO" CIRISGUI
    fi

    log_success "Repositories ready at $INSTALL_DIR"
}

setup_agent() {
    log_step "Setting up CIRISAgent"

    cd "$INSTALL_DIR/CIRISAgent" || {
        log_error "Failed to enter CIRISAgent directory"
        return 1
    }

    # Create virtual environment
    if [ ! -d "venv" ]; then
        log_info "Creating Python virtual environment..."
        python3 -m venv venv || {
            log_error "Failed to create virtual environment"
            return 1
        }
    fi

    # Activate and install dependencies
    log_info "Installing Python dependencies (this may take several minutes)..."
    # shellcheck disable=SC1091
    . venv/bin/activate || {
        log_error "Failed to activate virtual environment"
        return 1
    }

    pip install --upgrade pip setuptools wheel -q || log_warn "Failed to upgrade pip tools"
    pip install -r requirements.txt || {
        log_error "Failed to install Python dependencies"
        return 1
    }

    if [ "$DEV_MODE" = true ]; then
        log_info "Installing development dependencies..."
        pip install -r requirements-dev.txt || log_warn "Failed to install dev dependencies"
    fi

    log_success "CIRISAgent setup complete"
}

setup_gui() {
    log_step "Setting up CIRISGUI"

    cd "$INSTALL_DIR/CIRISGUI" || {
        log_error "Failed to enter CIRISGUI directory"
        return 1
    }

    # Install pnpm dependencies (can take 5-10 minutes)
    log_info "Installing Node.js dependencies (this may take 5-10 minutes)..."
    log_info "Installing packages for monorepo..."

    # Install root dependencies first
    if ! pnpm install; then
        log_error "Failed to install root dependencies"
        log_warn "You can manually run: cd $INSTALL_DIR/CIRISGUI && pnpm install"
        return 1
    fi

    # Install workspace dependencies (apps/agui needs its own node_modules)
    log_info "Installing workspace dependencies..."
    if ! pnpm install -r --filter ./apps/agui 2>/dev/null; then
        # Fallback: install directly in apps/agui if workspace install fails
        log_info "Installing agui dependencies directly..."
        (cd apps/agui && pnpm install) || log_warn "Could not install agui dependencies"
    fi

    log_success "Node.js dependencies installed"

    # Build frontend for production
    if [ "$DEV_MODE" = false ]; then
        log_info "Building frontend for production..."
        cd apps/agui || {
            log_error "Failed to enter agui directory"
            return 1
        }

        # Export environment variables from .env file for Next.js build
        # Next.js embeds NEXT_PUBLIC_* variables at build time
        if [ -f "$INSTALL_DIR/.env" ]; then
            log_info "Loading environment variables for build..."
            set -a
            source "$INSTALL_DIR/.env"
            set +a
        fi

        if ! pnpm build; then
            log_warn "Failed to build frontend, will use dev mode instead"
            cd ../..
            return 0
        fi
        cd ../..
    fi

    log_success "CIRISGUI setup complete"
}

# ============================================================================
# Configuration
# ============================================================================

create_env_file() {
    log_step "Creating environment configuration"

    local env_file="$INSTALL_DIR/.env"

    if [ -f "$env_file" ]; then
        log_warn "Environment file already exists at $env_file"
        # Prompt if we have a terminal (even when piped)
        if [ -t 1 ] && [ -r /dev/tty ]; then
            read -r -p "Overwrite? [y/N] " response </dev/tty || response="N"
            if [[ ! "$response" =~ ^[Yy]$ ]]; then
                log_info "Keeping existing .env file"
                return
            fi
        else
            log_info "Keeping existing .env file (non-interactive mode)"
            return
        fi
    fi

    # Generate encryption keys
    local secrets_key
    local telemetry_key
    secrets_key=$(openssl rand -base64 32)
    telemetry_key=$(openssl rand -base64 32)

    # LLM Configuration
    local llm_provider="openai"
    local llm_api_key=""
    local llm_base_url=""
    local llm_model=""

    if [ -t 1 ] && [ -r /dev/tty ]; then
        # Interactive mode - ask about LLM provider
        echo ""
        read -r -p "Will you be using OpenAI or another OpenAI-compatible provider? (local models, Together, Groq, etc.) [openai/other] (default: openai): " provider_choice </dev/tty || provider_choice="openai"
        provider_choice=${provider_choice:-openai}

        if [[ "$provider_choice" =~ ^[Oo]penai$ ]] || [[ -z "$provider_choice" ]]; then
            # OpenAI configuration (only if explicitly "openai" or empty)
            llm_provider="openai"
            read -r -p "Enter your OpenAI API key (or press Enter to skip): " llm_api_key </dev/tty || llm_api_key=""
        else
            # Any other provider (ollama, anthropic, groq, together, etc.)
            llm_provider="$provider_choice"

            read -r -p "Enter the LLM base URL (default: http://localhost:11434 for Ollama): " llm_base_url </dev/tty || llm_base_url="http://localhost:11434"
            llm_base_url=${llm_base_url:-http://localhost:11434}

            read -r -p "Enter the model name (e.g., llama3, mistral, meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo): " llm_model </dev/tty || llm_model="llama3"
            llm_model=${llm_model:-llama3}

            read -r -p "Enter API key (or 'local' if no auth required) (default: local): " llm_api_key </dev/tty || llm_api_key="local"
            llm_api_key=${llm_api_key:-local}
        fi
    else
        # Non-interactive mode - default to OpenAI
        log_info "Non-interactive mode: defaulting to OpenAI (configure manually in .env)"
        llm_provider="openai"
    fi

    # Create .env file
    cat > "$env_file" << EOF
# CIRIS Configuration
# Generated on $(date)

# ============================================================================
# LLM Configuration
# ============================================================================

EOF

    # Add LLM configuration based on provider choice
    if [ "$llm_provider" != "openai" ]; then
        cat >> "$env_file" << EOF
# OpenAI-Compatible LLM Configuration
OPENAI_API_KEY="$llm_api_key"
OPENAI_API_BASE="$llm_base_url"
OPENAI_MODEL="$llm_model"

# Popular OpenAI-compatible providers:
#
# Local Models:
#   Ollama:    http://localhost:11434
#   LM Studio: http://localhost:1234/v1
#   vLLM:      http://localhost:8000/v1
#   LocalAI:   http://localhost:8080/v1
#
# Commercial Providers:
#   Together AI: https://api.together.xyz/v1
#   Groq:        https://api.groq.com/openai/v1
#   Fireworks:   https://api.fireworks.ai/inference/v1
#   Anyscale:    https://api.endpoints.anyscale.com/v1

EOF
    else
        cat >> "$env_file" << EOF
# OpenAI Configuration
OPENAI_API_KEY="${llm_api_key:-your_openai_api_key_here}"

# Optional: Use a different OpenAI model
# OPENAI_MODEL="gpt-4"

# Optional: Use OpenAI-compatible endpoint
# OPENAI_API_BASE="https://api.openai.com/v1"

EOF
    fi

    cat >> "$env_file" << EOF
# ============================================================================
# Security Keys (auto-generated)
# ============================================================================

SECRETS_MASTER_KEY="$secrets_key"
TELEMETRY_ENCRYPTION_KEY="$telemetry_key"

# ============================================================================
# Application Configuration
# ============================================================================

# Log Level
LOG_LEVEL="INFO"

# Ports
CIRIS_AGENT_PORT=$AGENT_PORT
NEXT_PUBLIC_API_BASE_URL="http://localhost:$AGENT_PORT"

# Database Paths
CIRIS_DB_PATH="./data/ciris_engine.db"
CIRIS_DATA_DIR="./data"
SECRETS_DB_PATH="./secrets.db"
AUDIT_LOG_PATH="./audit_logs.jsonl"

# ============================================================================
# Optional: Discord Integration
# ============================================================================

# Uncomment and configure if using Discord adapter
# DISCORD_BOT_TOKEN="your_discord_bot_token_here"
# DISCORD_CHANNEL_ID="your_channel_id_here"

# ============================================================================
# Optional: Reddit Integration
# ============================================================================

# Uncomment and configure if using Reddit adapter
# CIRIS_REDDIT_CLIENT_ID="your_client_id"
# CIRIS_REDDIT_CLIENT_SECRET="your_client_secret"
# CIRIS_REDDIT_USERNAME="your_username"
# CIRIS_REDDIT_PASSWORD="your_password"

# ============================================================================
# Optional: Production Settings
# ============================================================================

# CIRISNode Configuration
# CIRISNODE_BASE_URL="https://your-cirisnode.com:8001"
# CIRISNODE_AGENT_SECRET_JWT="your_jwt_token"

EOF

    log_success "Environment file created at $env_file"

    if [ -z "$llm_api_key" ]; then
        if [ "$llm_provider" = "local" ]; then
            log_warn "Don't forget to configure your local LLM in $env_file"
        else
            log_warn "Don't forget to add your OpenAI API key to $env_file"
        fi
    fi
}

# ============================================================================
# Service Installation
# ============================================================================

install_systemd_service() {
    log_step "Installing systemd services"

    local user_service_dir="$HOME/.config/systemd/user"
    mkdir -p "$user_service_dir"

    # Agent service
    cat > "$user_service_dir/$AGENT_SERVICE_NAME.service" << EOF
[Unit]
Description=CIRIS Agent API
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/CIRISAgent
Environment=PATH=$INSTALL_DIR/CIRISAgent/venv/bin:/usr/local/bin:/usr/bin:/bin
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/CIRISAgent/venv/bin/python main.py --adapter api --port $AGENT_PORT
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

    # GUI service
    cat > "$user_service_dir/$GUI_SERVICE_NAME.service" << EOF
[Unit]
Description=CIRIS Web UI
After=network.target $AGENT_SERVICE_NAME.service
Requires=$AGENT_SERVICE_NAME.service

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR/CIRISGUI/apps/agui
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$(command -v pnpm) start --port $GUI_PORT
Restart=always
RestartSec=10

[Install]
WantedBy=default.target
EOF

    # Reload systemd and enable services
    systemctl --user daemon-reload
    systemctl --user enable "$AGENT_SERVICE_NAME" "$GUI_SERVICE_NAME"

    log_success "Systemd services installed"
    log_info "Start services with: systemctl --user start $AGENT_SERVICE_NAME $GUI_SERVICE_NAME"
}

install_launchd_service() {
    log_step "Installing launchd services"

    local launch_agents_dir="$HOME/Library/LaunchAgents"
    mkdir -p "$launch_agents_dir"

    # Agent service
    cat > "$launch_agents_dir/ai.ciris.agent.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.ciris.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/CIRISAgent/venv/bin/python</string>
        <string>main.py</string>
        <string>--adapter</string>
        <string>api</string>
        <string>--port</string>
        <string>$AGENT_PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR/CIRISAgent</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$INSTALL_DIR/CIRISAgent/venv/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/logs/agent.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/logs/agent.err.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

    # GUI service
    cat > "$launch_agents_dir/ai.ciris.gui.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.ciris.gui</string>
    <key>ProgramArguments</key>
    <array>
        <string>$(command -v pnpm)</string>
        <string>start</string>
        <string>--port</string>
        <string>$GUI_PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR/CIRISGUI/apps/agui</string>
    <key>StandardOutPath</key>
    <string>$INSTALL_DIR/logs/gui.log</string>
    <key>StandardErrorPath</key>
    <string>$INSTALL_DIR/logs/gui.err.log</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF

    # Load services
    launchctl load "$launch_agents_dir/ai.ciris.agent.plist"
    launchctl load "$launch_agents_dir/ai.ciris.gui.plist"

    log_success "Launchd services installed"
}

install_services() {
    if [ "$SKIP_SERVICE" = true ]; then
        log_info "Skipping service installation"
        return
    fi

    local init_system
    init_system=$(detect_init_system)

    case "$init_system" in
        systemd)
            install_systemd_service
            ;;
        launchd)
            install_launchd_service
            ;;
        *)
            log_warn "No supported init system found, skipping service installation"
            log_info "You can start CIRIS manually with: $INSTALL_DIR/scripts/start.sh"
            ;;
    esac
}

# ============================================================================
# Helper Scripts
# ============================================================================

create_helper_scripts() {
    log_step "Creating helper scripts"

    local scripts_dir="$INSTALL_DIR/scripts"
    mkdir -p "$scripts_dir"

    # Start script
    cat > "$scripts_dir/start.sh" << 'EOF'
#!/usr/bin/env bash
set -e
CIRIS_DIR="$(dirname "$0")/.."
cd "$CIRIS_DIR"

# Load environment
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi

# Start agent
echo "Starting CIRIS Agent..."
cd CIRISAgent
./venv/bin/python main.py --adapter api --port "${CIRIS_AGENT_PORT:-8080}" &
AGENT_PID=$!
cd ..

# Wait for agent to be ready
echo "Waiting for agent to start..."
sleep 5

# Start GUI
echo "Starting CIRISGUI..."
cd CIRISGUI/apps/agui
pnpm start --port "${CIRIS_GUI_PORT:-3000}" &
GUI_PID=$!
cd ../../..

echo ""
echo "✓ CIRIS is running!"
echo "  Agent API: http://localhost:${CIRIS_AGENT_PORT:-8080}"
echo "  Web UI:    http://localhost:${CIRIS_GUI_PORT:-3000}"
echo ""
echo "Press Ctrl+C to stop"

# Graceful shutdown handler
shutdown() {
    echo ""
    echo "Stopping CIRIS..."

    # Send SIGTERM for graceful shutdown
    kill -TERM $AGENT_PID 2>/dev/null || true
    kill -TERM $GUI_PID 2>/dev/null || true

    # Wait up to 10 seconds for graceful shutdown
    local timeout=10
    local elapsed=0
    while kill -0 $AGENT_PID 2>/dev/null || kill -0 $GUI_PID 2>/dev/null; do
        if [ $elapsed -ge $timeout ]; then
            echo "Timeout waiting for graceful shutdown, forcing..."
            kill -KILL $AGENT_PID 2>/dev/null || true
            kill -KILL $GUI_PID 2>/dev/null || true
            break
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done

    echo "✓ CIRIS stopped"
    exit 0
}

trap shutdown INT TERM
wait $AGENT_PID $GUI_PID
EOF
    chmod +x "$scripts_dir/start.sh"

    # Stop script
    cat > "$scripts_dir/stop.sh" << 'EOF'
#!/usr/bin/env bash
pkill -f "python.*main.py.*--adapter api" || true
pkill -f "pnpm.*start" || true
pkill -f "next.*start" || true
echo "✓ CIRIS stopped"
EOF
    chmod +x "$scripts_dir/stop.sh"

    # Status script
    cat > "$scripts_dir/status.sh" << 'EOF'
#!/usr/bin/env bash
AGENT_PORT="${CIRIS_AGENT_PORT:-8080}"
GUI_PORT="${CIRIS_GUI_PORT:-3000}"

echo "CIRIS Status:"
echo "============="

# Check agent
if curl -s "http://localhost:$AGENT_PORT/v1/status" >/dev/null 2>&1; then
    echo "✓ Agent API:  Running on port $AGENT_PORT"
else
    echo "✗ Agent API:  Not running"
fi

# Check GUI
if curl -s "http://localhost:$GUI_PORT" >/dev/null 2>&1; then
    echo "✓ Web UI:     Running on port $GUI_PORT"
else
    echo "✗ Web UI:     Not running"
fi
EOF
    chmod +x "$scripts_dir/status.sh"

    log_success "Helper scripts created at $scripts_dir"
}

# ============================================================================
# Uninstallation
# ============================================================================

uninstall_ciris() {
    log_step "Uninstalling CIRIS"

    # Stop services
    log_info "Stopping services..."
    local init_system
    init_system=$(detect_init_system)

    case "$init_system" in
        systemd)
            systemctl --user stop "$AGENT_SERVICE_NAME" "$GUI_SERVICE_NAME" 2>/dev/null || true
            systemctl --user disable "$AGENT_SERVICE_NAME" "$GUI_SERVICE_NAME" 2>/dev/null || true
            rm -f "$HOME/.config/systemd/user/$AGENT_SERVICE_NAME.service"
            rm -f "$HOME/.config/systemd/user/$GUI_SERVICE_NAME.service"
            systemctl --user daemon-reload
            ;;
        launchd)
            launchctl unload "$HOME/Library/LaunchAgents/ai.ciris.agent.plist" 2>/dev/null || true
            launchctl unload "$HOME/Library/LaunchAgents/ai.ciris.gui.plist" 2>/dev/null || true
            rm -f "$HOME/Library/LaunchAgents/ai.ciris.agent.plist"
            rm -f "$HOME/Library/LaunchAgents/ai.ciris.gui.plist"
            ;;
    esac

    # Stop any running processes
    pkill -f "python.*main.py" || true
    pkill -f "pnpm.*start" || true

    # Ask about data removal (only in interactive mode)
    local response="N"
    if [ -t 1 ] && [ -r /dev/tty ]; then
        read -r -p "Remove all data including databases and logs? [y/N] " response </dev/tty || response="N"
    else
        log_info "Non-interactive mode: keeping data at $INSTALL_DIR"
    fi

    if [[ "$response" =~ ^[Yy]$ ]]; then
        log_info "Removing installation at $INSTALL_DIR..."
        rm -rf "$INSTALL_DIR"
        log_success "CIRIS completely removed"
    else
        log_info "Keeping data at $INSTALL_DIR"
        log_info "To remove manually: rm -rf $INSTALL_DIR"
    fi
}

# ============================================================================
# Main Installation Flow
# ============================================================================

show_usage() {
    cat << EOF
CIRIS Standalone Installer

Usage:
  $0 [OPTIONS]

Options:
  --install-dir DIR     Installation directory (default: ~/ciris)
  --skip-service        Skip systemd/launchd service installation
  --skip-deps           Skip dependency installation
  --dev                 Install development dependencies
  --agent-branch NAME   CIRISAgent branch to install (default: main)
  --gui-branch NAME     CIRISGUI branch to install (default: main)
  --uninstall           Uninstall CIRIS
  -h, --help            Show this help message

Environment Variables:
  CIRIS_INSTALL_DIR     Installation directory
  CIRIS_AGENT_PORT      Agent API port (default: 8080)
  CIRIS_GUI_PORT        Web UI port (default: 3000)

Examples:
  # Default installation
  curl -sSL https://ciris.ai/install.sh | bash

  # Custom installation directory
  curl -sSL https://ciris.ai/install.sh | bash -s -- --install-dir /opt/ciris

  # Development installation
  curl -sSL https://ciris.ai/install.sh | bash -s -- --dev

EOF
}

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --install-dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            --skip-service)
                SKIP_SERVICE=true
                shift
                ;;
            --skip-deps)
                SKIP_DEPS=true
                shift
                ;;
            --dev)
                DEV_MODE=true
                shift
                ;;
            --agent-branch)
                AGENT_BRANCH="$2"
                shift 2
                ;;
            --gui-branch)
                GUI_BRANCH="$2"
                shift 2
                ;;
            --uninstall)
                UNINSTALL=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # Handle uninstall
    if [ "$UNINSTALL" = true ]; then
        uninstall_ciris
        exit 0
    fi

    # Show banner
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  ██████╗██╗██████╗ ██╗███████╗"
    echo " ██╔════╝██║██╔══██╗██║██╔════╝"
    echo " ██║     ██║██████╔╝██║███████╗"
    echo " ██║     ██║██╔══██╗██║╚════██║"
    echo " ╚██████╗██║██║  ██║██║███████║"
    echo "  ╚═════╝╚═╝╚═╝  ╚═╝╚═╝╚══════╝"
    echo ""
    echo "  Standalone Installer"
    echo -e "${RESET}"

    log_info "Installing CIRIS to $INSTALL_DIR"
    log_info "OS: $(detect_os)"
    log_info "Init: $(detect_init_system)"

    # Installation steps
    if [ "$SKIP_DEPS" = false ]; then
        install_dependencies
    fi

    clone_repositories
    setup_agent

    # CRITICAL: Create .env file BEFORE building GUI
    # Next.js embeds NEXT_PUBLIC_* variables at build time, not runtime
    create_env_file

    # GUI setup is optional - don't fail installation if it doesn't work
    if setup_gui; then
        log_success "GUI setup completed successfully"
    else
        log_warn "GUI setup failed - you can set it up manually later"
        log_info "To setup GUI: cd $INSTALL_DIR/CIRISGUI && pnpm install"
    fi

    create_helper_scripts
    install_services

    # Success message
    echo ""
    echo -e "${GREEN}${BOLD}✓ Installation Complete!${RESET}"
    echo ""
    echo "Next steps:"
    echo "  1. Review/edit configuration in: $INSTALL_DIR/.env"
    echo "  2. Start CIRIS with one of these methods:"
    echo ""

    local init_system
    init_system=$(detect_init_system)

    case "$init_system" in
        systemd)
            echo -e "     ${CYAN}# Start as service${RESET}"
            echo "     systemctl --user start $AGENT_SERVICE_NAME $GUI_SERVICE_NAME"
            echo ""
            echo -e "     ${CYAN}# Check status${RESET}"
            echo "     systemctl --user status $AGENT_SERVICE_NAME $GUI_SERVICE_NAME"
            ;;
        launchd)
            echo -e "     ${CYAN}# Services start automatically${RESET}"
            echo "     launchctl list | grep ciris"
            ;;
    esac

    echo ""
    echo -e "     ${CYAN}# Or start manually${RESET}"
    echo "     $INSTALL_DIR/scripts/start.sh"
    echo ""
    echo "  3. Open your browser to:"
    echo -e "     ${BOLD}http://localhost:$GUI_PORT${RESET}"
    echo ""
    echo "     Default credentials: admin / ciris_admin_password"
    echo ""
    echo "Documentation: https://github.com/CIRISAI/CIRISAgent/blob/main/docs/README.md"
    echo "Support: https://github.com/CIRISAI/CIRISAgent/issues"
    echo ""
}

# Run main if not sourced
# Also run if piped (BASH_SOURCE will be /dev/fd/... or empty)
if [ "${BASH_SOURCE[0]}" = "${0}" ] || [[ "${BASH_SOURCE[0]}" == /dev/fd/* ]] || [ -z "${BASH_SOURCE[0]}" ]; then
    main "$@"
fi
