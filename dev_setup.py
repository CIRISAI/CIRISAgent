#!/usr/bin/env python3
"""
CIRIS Developer Setup Script
Streamlines local development environment setup and management
"""

import os
import sys
import subprocess
import shutil
import argparse
import json
from pathlib import Path
from typing import Optional, List, Dict
import venv
import platform

# ANSI color codes for pretty output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_success(msg: str) -> None:
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")

def print_error(msg: str) -> None:
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_info(msg: str) -> None:
    print(f"{Colors.BLUE}ℹ {msg}{Colors.END}")

def print_header(msg: str) -> None:
    print(f"\n{Colors.BOLD}{msg}{Colors.END}")
    print("=" * len(msg))

class CIRISDevSetup:
    """Main development setup class"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.venv_path = self.project_root / "venv"
        self.db_path = self.project_root / "data" / "ciris_dev.db"
        self.logs_path = self.project_root / "logs"
        
    def check_python_version(self) -> bool:
        """Check if Python version meets requirements"""
        version = sys.version_info
        if version.major == 3 and version.minor >= 11:
            print_success(f"Python {version.major}.{version.minor}.{version.micro} detected")
            return True
        else:
            print_error(f"Python 3.11+ required, found {version.major}.{version.minor}")
            return False
    
    def check_docker(self) -> bool:
        """Check if Docker is installed and running"""
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                print_success("Docker is installed")
                
                # Check if Docker daemon is running
                result = subprocess.run(["docker", "ps"], capture_output=True, text=True)
                if result.returncode == 0:
                    print_success("Docker daemon is running")
                    return True
                else:
                    print_warning("Docker daemon is not running. Please start Docker.")
                    return False
            return False
        except FileNotFoundError:
            print_warning("Docker not found. Docker is optional but recommended.")
            return False
    
    def create_directories(self) -> None:
        """Create necessary directories"""
        dirs = [
            "data",
            "logs",
            "logs/archive",
            ".vscode",
            "scripts",
            "tests/data"
        ]
        
        for dir_name in dirs:
            dir_path = self.project_root / dir_name
            dir_path.mkdir(parents=True, exist_ok=True)
        
        print_success("Created project directories")
    
    def setup_virtual_env(self) -> None:
        """Create and activate virtual environment"""
        if self.venv_path.exists():
            print_info("Virtual environment already exists")
        else:
            print_info("Creating virtual environment...")
            venv.create(self.venv_path, with_pip=True)
            print_success("Virtual environment created")
        
        # Provide activation instructions
        if platform.system() == "Windows":
            activate_cmd = f"{self.venv_path}\\Scripts\\activate"
        else:
            activate_cmd = f"source {self.venv_path}/bin/activate"
        
        print_info(f"To activate: {activate_cmd}")
    
    def install_dependencies(self) -> None:
        """Install Python dependencies"""
        pip_cmd = [sys.executable, "-m", "pip"]
        
        # Upgrade pip
        print_info("Upgrading pip...")
        subprocess.run(pip_cmd + ["install", "--upgrade", "pip"], check=True)
        
        # Install requirements
        req_file = self.project_root / "requirements.txt"
        if req_file.exists():
            print_info("Installing dependencies...")
            subprocess.run(pip_cmd + ["install", "-r", str(req_file)], check=True)
            print_success("Dependencies installed")
        else:
            print_error("requirements.txt not found")
    
    def setup_development_env(self) -> None:
        """Create development environment files"""
        # Create .env.development
        env_dev = self.project_root / ".env.development"
        if not env_dev.exists():
            env_content = """# CIRIS Development Environment
CIRIS_ENV=development
CIRIS_DEBUG=true
CIRIS_LOG_LEVEL=DEBUG

# API Configuration
CIRIS_API_HOST=127.0.0.1
CIRIS_API_PORT=8080

# Mock LLM for development
CIRIS_MOCK_LLM=true
CIRIS_MOCK_LLM_DELAY=0.1

# Database
CIRIS_DB_PATH=./data/ciris_dev.db

# Reduce delays for faster development
PROCESSING_ROUND_DELAY=0.5
THOUGHT_PROCESSING_TIMEOUT=10

# Discord (optional - add your bot token if testing Discord)
# DISCORD_BOT_TOKEN=your_token_here

# OpenAI (optional - add if testing real LLM)
# OPENAI_API_KEY=your_key_here
"""
            env_dev.write_text(env_content)
            print_success("Created .env.development")
        
        # Create VS Code launch configuration
        vscode_dir = self.project_root / ".vscode"
        launch_json = vscode_dir / "launch.json"
        if not launch_json.exists():
            launch_config = {
                "version": "0.2.0",
                "configurations": [
                    {
                        "name": "CIRIS CLI (Mock)",
                        "type": "python",
                        "request": "launch",
                        "program": "${workspaceFolder}/main.py",
                        "args": ["--mock-llm", "--adapter", "cli"],
                        "console": "integratedTerminal",
                        "envFile": "${workspaceFolder}/.env.development"
                    },
                    {
                        "name": "CIRIS API (Mock)",
                        "type": "python",
                        "request": "launch",
                        "program": "${workspaceFolder}/main.py",
                        "args": ["--mock-llm", "--adapter", "api"],
                        "console": "integratedTerminal",
                        "envFile": "${workspaceFolder}/.env.development"
                    },
                    {
                        "name": "Run Tests",
                        "type": "python",
                        "request": "launch",
                        "module": "pytest",
                        "args": ["-v", "tests/"],
                        "console": "integratedTerminal",
                        "envFile": "${workspaceFolder}/.env.development"
                    }
                ]
            }
            launch_json.write_text(json.dumps(launch_config, indent=4))
            print_success("Created VS Code debug configurations")
    
    def initialize_database(self) -> None:
        """Initialize the SQLite database"""
        print_info("Initializing database...")
        
        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Run migrations
        try:
            # Import and run migration logic
            sys.path.insert(0, str(self.project_root))
            from ciris_engine.logic.infrastructure.database_manager import DatabaseManager
            
            db_manager = DatabaseManager(str(self.db_path))
            db_manager._run_migrations()
            print_success("Database initialized")
        except Exception as e:
            print_warning(f"Could not auto-initialize database: {e}")
            print_info("Database will be created on first run")
    
    def create_helper_scripts(self) -> None:
        """Create helpful development scripts"""
        scripts_dir = self.project_root / "scripts"
        
        # Create run_dev.sh
        run_dev = scripts_dir / "run_dev.sh"
        run_dev.write_text("""#!/bin/bash
# Quick development runner

# Load development environment
export $(cat .env.development | grep -v '^#' | xargs)

# Run with mock LLM in CLI mode
python main.py --mock-llm --adapter cli
""")
        run_dev.chmod(0o755)
        
        # Create test_watch.sh
        test_watch = scripts_dir / "test_watch.sh"
        test_watch.write_text("""#!/bin/bash
# Run tests with file watching

# Install pytest-watch if not present
pip install pytest-watch

# Run tests with watching
pytest-watch -- -v tests/
""")
        test_watch.chmod(0o755)
        
        # Create clean_dev.sh
        clean_dev = scripts_dir / "clean_dev.sh"
        clean_dev.write_text("""#!/bin/bash
# Clean development environment

echo "Cleaning development environment..."

# Remove database
rm -f data/ciris_dev.db

# Clear logs
rm -f logs/*.log
rm -f logs/archive/*.log

# Clear Python cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete

echo "Development environment cleaned!"
""")
        clean_dev.chmod(0o755)
        
        print_success("Created helper scripts in scripts/")
    
    def create_docker_compose_dev(self) -> None:
        """Create a simplified docker-compose for development"""
        docker_dev = self.project_root / "docker-compose.dev.yml"
        docker_content = """version: '3.8'

services:
  ciris-dev:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ciris-dev
    environment:
      - CIRIS_ENV=development
      - CIRIS_DEBUG=true
      - CIRIS_MOCK_LLM=true
      - CIRIS_API_HOST=0.0.0.0
      - CIRIS_API_PORT=8080
      - PROCESSING_ROUND_DELAY=0.5
      - THOUGHT_PROCESSING_TIMEOUT=10
    ports:
      - "8080:8080"
    volumes:
      - ./ciris_engine:/app/ciris_engine
      - ./ciris_modular_services:/app/ciris_modular_services
      - ./logs:/app/logs
      - ./data:/app/data
    command: python main.py --mock-llm --adapter api
    restart: unless-stopped

  # Optional: Add a database service if needed
  # postgres:
  #   image: postgres:15
  #   environment:
  #     POSTGRES_DB: ciris_dev
  #     POSTGRES_USER: ciris
  #     POSTGRES_PASSWORD: ciris_dev_password
  #   ports:
  #     - "5432:5432"
  #   volumes:
  #     - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
"""
        docker_dev.write_text(docker_content)
        print_success("Created docker-compose.dev.yml")
    
    def setup_git_hooks(self) -> None:
        """Setup helpful git hooks"""
        hooks_dir = self.project_root / ".git" / "hooks"
        if not hooks_dir.exists():
            print_warning("Git not initialized, skipping hooks")
            return
        
        # Pre-commit hook for running tests
        pre_commit = hooks_dir / "pre-commit"
        pre_commit_content = """#!/bin/bash
# Run quick tests before commit

echo "Running quick tests..."
python -m pytest tests/unit/ -x --tb=short

if [ $? -ne 0 ]; then
    echo "Tests failed! Fix issues before committing."
    exit 1
fi
"""
        pre_commit.write_text(pre_commit_content)
        pre_commit.chmod(0o755)
        print_success("Created git pre-commit hook")
    
    def print_next_steps(self) -> None:
        """Print helpful next steps"""
        print_header("Setup Complete! Next Steps:")
        
        print(f"""
1. Activate virtual environment:
   {Colors.BOLD}source venv/bin/activate{Colors.END} (Linux/Mac)
   {Colors.BOLD}venv\\Scripts\\activate{Colors.END} (Windows)

2. Run in development mode:
   {Colors.BOLD}python main.py --mock-llm --adapter cli{Colors.END}
   or
   {Colors.BOLD}./scripts/run_dev.sh{Colors.END}

3. Run with Docker:
   {Colors.BOLD}docker-compose -f docker-compose.dev.yml up{Colors.END}

4. Run tests:
   {Colors.BOLD}pytest tests/{Colors.END}
   or with watching:
   {Colors.BOLD}./scripts/test_watch.sh{Colors.END}

5. Debug in VS Code:
   - Open VS Code in project directory
   - Press F5 to start debugging
   - Choose "CIRIS CLI (Mock)" or "CIRIS API (Mock)"

6. View logs:
   {Colors.BOLD}tail -f logs/ciris_latest.log{Colors.END}

Happy coding! 🚀
""")
    
    def run_full_setup(self) -> None:
        """Run the complete setup process"""
        print_header("CIRIS Development Setup")
        
        # Check prerequisites
        if not self.check_python_version():
            sys.exit(1)
        
        self.check_docker()
        
        # Setup environment
        self.create_directories()
        self.setup_virtual_env()
        
        # Only install dependencies if in venv or user confirms
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            self.install_dependencies()
        else:
            response = input("\nNot in virtual environment. Install dependencies anyway? (y/N): ")
            if response.lower() == 'y':
                self.install_dependencies()
            else:
                print_info("Skipping dependency installation")
        
        # Setup development files
        self.setup_development_env()
        self.initialize_database()
        self.create_helper_scripts()
        self.create_docker_compose_dev()
        self.setup_git_hooks()
        
        # Print next steps
        self.print_next_steps()

def main():
    parser = argparse.ArgumentParser(description="CIRIS Development Setup")
    parser.add_argument("--clean", action="store_true", help="Clean development environment")
    parser.add_argument("--deps-only", action="store_true", help="Only install dependencies")
    
    args = parser.parse_args()
    
    setup = CIRISDevSetup()
    
    if args.clean:
        print_header("Cleaning Development Environment")
        subprocess.run(["./scripts/clean_dev.sh"], shell=True)
    elif args.deps_only:
        setup.install_dependencies()
    else:
        setup.run_full_setup()

if __name__ == "__main__":
    main()