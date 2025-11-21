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
DRY_RUN=false
DOCKER_MODE=false

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
# Docker Installation
# ============================================================================

ensure_docker() {
    log_step "Checking Docker availability"

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would verify docker and docker compose availability"
        return
    fi

    if ! command_exists docker; then
        log_error "Docker is required for --docker installs. Please install Docker Desktop or docker-ce."
        exit 1
    fi

    if ! docker compose version >/dev/null 2>&1; then
        log_error "docker compose plugin is required. Please upgrade Docker to include 'docker compose'."
        exit 1
    fi
}

create_docker_compose_file() {
    log_step "Preparing Docker Compose configuration"

    local compose_file="$INSTALL_DIR/docker-compose.yml"
    local init_script="$INSTALL_DIR/init_permissions.sh"

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would write Docker Compose file to $compose_file using GHCR images"
        return
    fi

    # Create directories for container (will be owned by ciris user inside container)
    mkdir -p "$INSTALL_DIR/data" "$INSTALL_DIR/logs" "$INSTALL_DIR/.ciris_keys" "$INSTALL_DIR/config"

    # Create init script that runs as root, fixes permissions, then switches to ciris user
    # This is the only robust way to handle arbitrary host UIDs
    cat > "$init_script" << 'INIT_SCRIPT'
#!/bin/bash
# CIRIS Docker Init - runs as root, fixes permissions, switches to ciris user
set -e

echo "Initializing CIRIS directories..."

# Ensure directories exist
mkdir -p /app/data /app/logs /app/.ciris_keys /app/config

# Fix ownership to ciris user (UID 1000)
chown -R ciris:ciris /app/data /app/logs /app/.ciris_keys /app/config

# Set secure permissions (application enforces 755 for data/logs/config, 700 for keys)
chmod 755 /app/data /app/logs /app/config
chmod 700 /app/.ciris_keys

echo "Starting CIRIS agent as user 'ciris'..."

# Create a temporary script to run as ciris user with the exact command
TMPSCRIPT=$(mktemp)
{
    echo '#!/bin/bash'
    echo 'cd /app'
    printf 'exec'
    for arg in "$@"; do
        printf ' %q' "$arg"
    done
    echo
} > "$TMPSCRIPT"
chmod +x "$TMPSCRIPT"
chown ciris:ciris "$TMPSCRIPT"

# Execute the script as ciris user
exec su ciris -c "$TMPSCRIPT"
INIT_SCRIPT

    chmod +x "$init_script"

    cat > "$compose_file" << EOF
version: "3.8"

services:
  ciris-agent:
    image: ghcr.io/cirisai/ciris-agent:latest
    container_name: ciris-agent
    platform: linux/amd64
    user: "0:0"  # Run as root to fix permissions, init script switches to ciris user
    entrypoint: ["/init_permissions.sh"]
    command: ["python", "main.py", "--adapter", "api"]
    env_file:
      - $INSTALL_DIR/.env
    environment:
      - CIRIS_API_HOST=0.0.0.0
      - CIRIS_API_PORT=8080
      - CIRIS_PORT=${CIRIS_AGENT_PORT:-8080}
    ports:
      - "${CIRIS_AGENT_PORT:-8080}:8080"
    volumes:
      - "$INSTALL_DIR/data:/app/data"
      - "$INSTALL_DIR/logs:/app/logs"
      - "$INSTALL_DIR/.ciris_keys:/app/.ciris_keys"
      - "$INSTALL_DIR/config:/app/config"
      - "$INSTALL_DIR/init_permissions.sh:/init_permissions.sh:ro"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/v1/system/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    networks:
      - ciris-network

  ciris-gui:
    image: ghcr.io/cirisai/ciris-gui:latest
    container_name: ciris-gui
    platform: linux/amd64
    environment:
      - NODE_ENV=production
      - NEXT_PUBLIC_API_BASE_URL=http://ciris-agent:8080
    ports:
      - "${CIRIS_GUI_PORT:-3000}:3000"
    depends_on:
      ciris-agent:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget --no-verbose --tries=1 --spider http://localhost:3000 || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    networks:
      - ciris-network

networks:
  ciris-network:
    name: ciris-standalone
    driver: bridge
EOF

    log_success "Docker Compose file created at $compose_file"
    log_info "Container will run as 'ciris' user (UID 1000), directories configured for container access"
}

start_docker_stack() {
    log_step "Starting CIRIS with Docker"

    local compose_file="$INSTALL_DIR/docker-compose.yml"

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would pull GHCR images and run 'docker compose -f $compose_file up -d'"
        return
    fi

    docker compose -f "$compose_file" pull
    docker compose -f "$compose_file" up -d

    log_success "Docker containers are running"
}

# ============================================================================
# Dependency Installation
# ============================================================================

check_macos_prerequisites() {
    # On macOS, check if we have either Homebrew or Command Line Tools
    # CRITICAL: Avoid triggering macOS Python installation popup dialog
    local os_type
    os_type=$(detect_os)

    if [ "$os_type" != "macos" ]; then
        return 0  # Not macOS, nothing to check
    fi

    # Check if Homebrew is installed
    if command_exists brew; then
        log_success "Homebrew found"
        return 0
    fi

    # No Homebrew - check if Python 3 is available without triggering popup
    if command_exists python3; then
        # Get python3 path
        local python_path
        python_path=$(which python3 2>/dev/null)

        # If it's the system stub, check Xcode CLT BEFORE running python3
        if [ "$python_path" = "/usr/bin/python3" ]; then
            # Check if Xcode Command Line Tools are installed
            if ! xcode-select -p >/dev/null 2>&1; then
                # CLT not installed - DO NOT run python3 (would trigger popup)
                log_error "macOS system Python detected but Xcode Command Line Tools not installed."
                echo ""
                echo "Install Xcode Command Line Tools:"
                echo "  xcode-select --install"
                echo ""
                echo "Or install Homebrew to manage dependencies:"
                echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                exit 1
            fi
            # CLT installed, safe to proceed
        fi

        # Safe to run python3 now (either not stub, or stub with CLT)
        local py_version
        py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo "0.0")

        # Check if it meets minimum requirements (3.10+ required for PEP 604 union types)
        if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            log_success "Python $py_version found (system)"
            log_warn "Homebrew not found - using system Python. Some dependencies may need manual installation."
            return 0
        fi
    fi

    # No suitable Python and no Homebrew - bail out with helpful message
    log_error "macOS requires Homebrew to install dependencies automatically."
    echo ""
    echo "Please install Homebrew first:"
    echo "  /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    echo ""
    echo "Alternatively, if you have Python 3.10+ installed manually:"
    echo "  Run this script with --skip-deps and ensure you have:"
    echo "    - Python 3.10+ (python3 --version) - Required for PEP 604 union types"
    echo "    - Node.js 18+ (node --version)"
    echo "    - pnpm (npm install -g pnpm)"
    echo "    - git"
    exit 1
}

get_best_python() {
    # On macOS, prefer Homebrew Python over system Python
    # Returns the path to the best Python 3.10+ available
    local os_type
    os_type=$(detect_os)

    if [ "$os_type" != "macos" ]; then
        echo "python3"
        return
    fi

    # Try Homebrew Python locations first (supports both Intel and Apple Silicon)
    local homebrew_pythons=(
        "/opt/homebrew/bin/python3"      # Apple Silicon
        "/opt/homebrew/bin/python3.12"
        "/opt/homebrew/bin/python3.11"
        "/opt/homebrew/bin/python3.10"
        "/usr/local/bin/python3"         # Intel Mac
        "/usr/local/bin/python3.12"
        "/usr/local/bin/python3.11"
        "/usr/local/bin/python3.10"
    )

    for py in "${homebrew_pythons[@]}"; do
        if [ -x "$py" ]; then
            # Check if it's 3.10+
            if "$py" -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
                echo "$py"
                return
            fi
        fi
    done

    # Fall back to system Python if it's 3.10+
    if command_exists python3; then
        if python3 -c 'import sys; exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
            echo "python3"
            return
        fi
    fi

    # No suitable Python found
    echo ""
}

install_dependencies() {
    log_step "Installing system dependencies"

    local os_type
    os_type=$(detect_os)
    local pkg_mgr
    pkg_mgr=$(get_package_manager)

    # Check macOS prerequisites first (brew or existing Python)
    check_macos_prerequisites

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would verify Python 3.10+, Node.js 18+, pnpm, git, and curl using $pkg_mgr"
        return
    fi

    # Check Python - prefer Homebrew on macOS
    local python_cmd
    python_cmd=$(get_best_python)

    if [ -z "$python_cmd" ]; then
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
            none|*)
                if [ "$os_type" = "macos" ]; then
                    log_error "Cannot install Python without Homebrew or system Python."
                    echo ""
                    echo "Please either:"
                    echo "  1. Install Homebrew: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
                    echo "  2. Install Python 3.10+ from python.org: https://www.python.org/downloads/macos/"
                    echo "  3. Run with --skip-deps if you already have Python 3.10+ installed"
                else
                    log_error "Cannot automatically install Python. Please install Python 3.10+ manually."
                fi
                exit 1
                ;;
        esac
    else
        # Check Python version
        local py_version
        py_version=$("$python_cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

        if [ "$python_cmd" != "python3" ]; then
            log_success "Python $py_version found at $python_cmd (Homebrew)"
        else
            log_success "Python $py_version found"
        fi

        # Version already verified by get_best_python()
    fi

    # Check Node.js
    if ! command_exists node; then
        log_warn "Node.js not found, installing..."
        case "$pkg_mgr" in
            apt)
                curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
                sudo apt-get install -y nodejs
                ;;
            dnf|yum)
                curl -fsSL https://rpm.nodesource.com/setup_22.x | sudo bash -
                sudo "$pkg_mgr" install -y nodejs
                ;;
            brew)
                brew install node
                ;;
            pacman)
                sudo pacman -S --noconfirm nodejs npm
                ;;
            none|*)
                if [ "$os_type" = "macos" ]; then
                    log_error "Cannot install Node.js without Homebrew."
                    echo ""
                    echo "Please either:"
                    echo "  1. Install Homebrew first, then re-run this script"
                    echo "  2. Install Node.js manually from https://nodejs.org/en/download/package-manager"
                    echo "  3. Run with --skip-deps if you already have Node.js 18+ installed"
                else
                    log_error "Cannot automatically install Node.js. Please install Node.js 18+ manually from https://nodejs.org"
                fi
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

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would create $INSTALL_DIR and clone CIRISAgent ($AGENT_BRANCH) and CIRISGUI ($GUI_BRANCH)"
        return
    fi

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

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would create a virtual environment and install Python dependencies in $INSTALL_DIR/CIRISAgent"
        return
    fi

    cd "$INSTALL_DIR/CIRISAgent" || {
        log_error "Failed to enter CIRISAgent directory"
        return 1
    }

    # Get best Python (prefer Homebrew on macOS)
    local python_cmd
    python_cmd=$(get_best_python)

    if [ -z "$python_cmd" ]; then
        log_error "No suitable Python 3.10+ found"
        return 1
    fi

    # Create virtual environment
    if [ ! -d "venv" ]; then
        log_info "Creating Python virtual environment with $python_cmd..."
        "$python_cmd" -m venv venv || {
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

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would install Node dependencies and build the GUI in $INSTALL_DIR/CIRISGUI"
        return
    fi

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

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would generate $env_file with LLM and system defaults"
        return
    fi

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

    # Create wrapper script that loads .env before starting agent
    cat > "$INSTALL_DIR/scripts/launchd-agent-wrapper.sh" << 'WRAPPER_EOF'
#!/bin/bash
# Wrapper script for launchd to load .env file before starting CIRIS agent

INSTALL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$INSTALL_DIR/.env"

# Load environment variables from .env if it exists
if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
fi

# Start the agent with venv Python
cd "$INSTALL_DIR/CIRISAgent"
exec "$INSTALL_DIR/CIRISAgent/venv/bin/python" main.py --adapter api --port "${CIRIS_AGENT_PORT:-8080}"
WRAPPER_EOF
    chmod +x "$INSTALL_DIR/scripts/launchd-agent-wrapper.sh"

    # Agent service - use wrapper script
    cat > "$launch_agents_dir/ai.ciris.agent.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>ai.ciris.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>$INSTALL_DIR/scripts/launchd-agent-wrapper.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$INSTALL_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>$INSTALL_DIR/CIRISAgent/venv/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
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

    # GUI service - needs PATH with Homebrew for node/pnpm
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
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
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

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would install system services for $AGENT_SERVICE_NAME and $GUI_SERVICE_NAME"
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

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would create start/stop/status scripts in $INSTALL_DIR/scripts"
        return
    fi

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

detect_installation_type() {
    # Detect if existing installation is Docker or local
    # Returns: "docker", "local", or "none"

    if [ ! -d "$INSTALL_DIR" ]; then
        echo "none"
        return
    fi

    if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
        echo "docker"
    elif [ -d "$INSTALL_DIR/CIRISAgent" ] || [ -d "$INSTALL_DIR/CIRISGUI" ]; then
        echo "local"
    else
        echo "unknown"
    fi
}

check_existing_installation() {
    # Check for existing installation and prompt user
    # Sets UNINSTALL=true if user chooses to uninstall

    local install_type
    install_type=$(detect_installation_type)

    if [ "$install_type" = "none" ]; then
        return 0
    fi

    # Installation exists - prompt user
    log_warn "Existing CIRIS installation detected at: $INSTALL_DIR"
    log_info "Installation type: $install_type"

    # In non-interactive mode, abort
    if [ ! -t 1 ] || [ ! -r /dev/tty ]; then
        log_error "Non-interactive mode: cannot prompt for action"
        log_info "Use --uninstall to remove, or choose a different --install-dir"
        exit 1
    fi

    echo ""
    echo "What would you like to do?"
    echo "  1) Re-install (remove existing and install fresh)"
    echo "  2) Uninstall only (remove existing installation)"
    echo "  3) Cancel (exit without changes)"
    echo ""

    local choice
    read -r -p "Enter choice [1-3]: " choice </dev/tty || choice="3"

    case "$choice" in
        1)
            log_info "Re-installing: removing existing installation..."
            UNINSTALL=true
            uninstall_ciris
            UNINSTALL=false
            log_success "Ready to install fresh"
            ;;
        2)
            log_info "Uninstalling..."
            UNINSTALL=true
            uninstall_ciris
            exit 0
            ;;
        3|*)
            log_info "Installation cancelled"
            exit 0
            ;;
    esac
}

uninstall_ciris() {
    log_step "Uninstalling CIRIS"

    if [ "$DRY_RUN" = true ]; then
        log_info "[dry-run] Would stop services and remove installation at $INSTALL_DIR"
        return
    fi

    # Detect installation type
    local install_type
    install_type=$(detect_installation_type)

    if [ "$install_type" = "none" ]; then
        log_warn "No installation found at $INSTALL_DIR"
        return 0
    fi

    # Handle Docker installation
    if [ "$install_type" = "docker" ]; then
        log_info "Stopping Docker containers..."
        if [ -f "$INSTALL_DIR/docker-compose.yml" ]; then
            (cd "$INSTALL_DIR" && docker compose down -v 2>/dev/null) || true
        fi
        # Also try to stop by container name in case compose file is corrupted
        docker stop ciris-agent ciris-gui 2>/dev/null || true
        docker rm ciris-agent ciris-gui 2>/dev/null || true
    fi

    # Handle local installation
    if [ "$install_type" = "local" ]; then
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
    fi

    # Ask about data removal (only in interactive mode and not during re-install)
    local response="N"
    if [ "$UNINSTALL" = true ]; then
        # Full uninstall - ask about data
        if [ -t 1 ] && [ -r /dev/tty ]; then
            read -r -p "Remove all data including databases and logs? [y/N] " response </dev/tty || response="N"
        else
            log_info "Non-interactive mode: keeping data at $INSTALL_DIR"
        fi
    else
        # Re-install - always remove
        response="Y"
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
  --dry-run             Print the actions without executing them
  --docker              Use Docker images from GHCR instead of local build
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
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            --docker)
                DOCKER_MODE=true
                SKIP_SERVICE=true
                SKIP_DEPS=true
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

    # Check for existing installation and prompt user
    check_existing_installation

    if [ "$DOCKER_MODE" = true ]; then
        log_info "Docker mode enabled: using GHCR images"

        ensure_docker
        mkdir -p "$INSTALL_DIR"
        create_env_file
        create_docker_compose_file
        start_docker_stack

        if [ "$DRY_RUN" = true ]; then
            log_success "Dry run complete. Docker commands were not executed."
            return
        fi

        echo ""
        echo -e "${GREEN}${BOLD}✓ Docker deployment Complete!${RESET}"
        echo ""
        echo "Agent API:  http://localhost:$AGENT_PORT"
        echo "Web UI:     http://localhost:$GUI_PORT"
        echo "Compose:    $INSTALL_DIR/docker-compose.yml"
        return
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

    if [ "$DRY_RUN" = true ]; then
        log_warn "Dry run enabled: no changes will be made"
    fi

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

    if [ "$DRY_RUN" = true ]; then
        log_success "Dry run complete. No changes were made."
        return
    fi

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
