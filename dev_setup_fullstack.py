#!/usr/bin/env python3
"""
CIRIS Full-Stack Developer Setup Script
Includes both backend (CIRIS) and frontend (CIRISGUI) setup
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path
from typing import Optional
import json

# Import colors from the original setup
from dev_setup import Colors, print_success, print_warning, print_error, print_info, print_header

class CIRISFullStackSetup:
    """Full-stack development setup including GUI"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.gui_root = self.project_root / "CIRISGUI"
        self.backend_setup_done = False
        self.frontend_setup_done = False
        
    def check_prerequisites(self) -> bool:
        """Check all prerequisites for full-stack development"""
        all_good = True
        
        # Python check
        version = sys.version_info
        if version.major == 3 and version.minor >= 11:
            print_success(f"Python {version.major}.{version.minor}.{version.micro} detected")
        else:
            print_error(f"Python 3.11+ required, found {version.major}.{version.minor}")
            all_good = False
            
        # Node.js check
        try:
            result = subprocess.run(["node", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                node_version = result.stdout.strip()
                print_success(f"Node.js {node_version} detected")
            else:
                print_error("Node.js not found")
                all_good = False
        except FileNotFoundError:
            print_error("Node.js not found. Please install Node.js 18+ from https://nodejs.org/")
            all_good = False
            
        # pnpm check
        try:
            result = subprocess.run(["pnpm", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                print_success(f"pnpm {result.stdout.strip()} detected")
            else:
                print_warning("pnpm not found, will install via npm")
        except FileNotFoundError:
            print_warning("pnpm not found, will install via npm")
            
        # Docker check (optional)
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                print_success("Docker is installed (optional)")
        except:
            print_info("Docker not found (optional for development)")
            
        return all_good
    
    def setup_backend(self) -> bool:
        """Run backend setup using existing dev_setup.py"""
        print_header("Setting up CIRIS Backend")
        
        # Import and run the backend setup
        sys.path.insert(0, str(self.project_root))
        from dev_setup import CIRISDevSetup
        
        backend_setup = CIRISDevSetup()
        backend_setup.run_full_setup()
        
        self.backend_setup_done = True
        return True
    
    def install_pnpm(self) -> bool:
        """Install pnpm if not present"""
        try:
            subprocess.run(["pnpm", "--version"], capture_output=True, check=True)
            return True
        except:
            print_info("Installing pnpm...")
            try:
                subprocess.run(["npm", "install", "-g", "pnpm"], check=True)
                print_success("pnpm installed")
                return True
            except:
                print_error("Failed to install pnpm")
                return False
    
    def setup_frontend(self) -> bool:
        """Setup CIRISGUI frontend"""
        print_header("Setting up CIRISGUI Frontend")
        
        if not self.gui_root.exists():
            print_error(f"CIRISGUI directory not found at {self.gui_root}")
            return False
            
        # Install pnpm if needed
        if not self.install_pnpm():
            return False
            
        # Install frontend dependencies
        print_info("Installing frontend dependencies...")
        os.chdir(self.gui_root)
        
        try:
            subprocess.run(["pnpm", "install"], check=True)
            print_success("Frontend dependencies installed")
        except subprocess.CalledProcessError:
            print_error("Failed to install frontend dependencies")
            return False
            
        # Create development environment file
        self.create_frontend_env()
        
        self.frontend_setup_done = True
        return True
    
    def create_frontend_env(self) -> None:
        """Create frontend .env.development file"""
        env_file = self.gui_root / "apps" / "agui" / ".env.development"
        
        if not env_file.exists():
            env_content = """# CIRISGUI Development Environment
NEXT_PUBLIC_API_URL=http://localhost:8081/api
NEXT_PUBLIC_APP_NAME=CIRIS Development
NEXT_PUBLIC_APP_VERSION=dev

# Optional: Add your OpenAI key for testing
# OPENAI_API_KEY=your_key_here
"""
            env_file.write_text(env_content)
            print_success("Created frontend .env.development")
    
    def create_fullstack_scripts(self) -> None:
        """Create helpful full-stack development scripts"""
        scripts_dir = self.project_root / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        
        # Full-stack development script
        fullstack_dev = scripts_dir / "dev_fullstack.sh"
        fullstack_dev.write_text("""#!/bin/bash
# Start full-stack development environment

echo "Starting CIRIS Full-Stack Development..."

# Function to kill processes on exit
cleanup() {
    echo "\\nShutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}
trap cleanup EXIT INT TERM

# Start backend with hot reload
echo "Starting backend..."
python ciris_dev_server.py --adapter api &
BACKEND_PID=$!

# Wait for backend to be ready
sleep 5

# Start frontend
echo "Starting frontend..."
cd CIRISGUI && pnpm dev &
FRONTEND_PID=$!

echo ""
echo "🚀 Full-stack development environment running!"
echo "   Backend API: http://localhost:8080"
echo "   Frontend GUI: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for processes
wait
""")
        fullstack_dev.chmod(0o755)
        
        # Test runner for full-stack
        test_fullstack = scripts_dir / "test_fullstack.sh"
        test_fullstack.write_text("""#!/bin/bash
# Run both backend and frontend tests

echo "Running Full-Stack Tests..."

# Backend tests
echo "\\n=== Backend Tests ==="
python ciris_test_runner.py tests/

# Frontend tests
echo "\\n=== Frontend Tests ==="
cd CIRISGUI && pnpm test

echo "\\n✅ All tests complete!"
""")
        test_fullstack.chmod(0o755)
        
        print_success("Created full-stack helper scripts")
    
    def create_docker_compose_fullstack(self) -> None:
        """Create docker-compose for full-stack development"""
        docker_compose = self.project_root / "docker-compose.fullstack.yml"
        docker_content = """version: '3.8'

services:
  # CIRIS Backend
  ciris-backend:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: ciris-backend-dev
    environment:
      - CIRIS_ENV=development
      - CIRIS_DEBUG=true
      - CIRIS_MOCK_LLM=true
      - CIRIS_API_HOST=0.0.0.0
      - CIRIS_API_PORT=8080
      - PROCESSING_ROUND_DELAY=0.5
    ports:
      - "8080:8080"
    volumes:
      - ./ciris_engine:/app/ciris_engine
      - ./ciris_modular_services:/app/ciris_modular_services
      - ./logs:/app/logs
      - ./data:/app/data
    command: python main.py --mock-llm --adapter api
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/v1/system/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  # CIRISGUI Frontend
  ciris-frontend:
    build:
      context: ./CIRISGUI
      dockerfile: Dockerfile.frontend
    container_name: ciris-frontend-dev
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8080
      - NODE_ENV=development
    ports:
      - "3000:3000"
    volumes:
      - ./CIRISGUI/apps/agui:/app/apps/agui
      - /app/apps/agui/node_modules
      - /app/apps/agui/.next
    depends_on:
      ciris-backend:
        condition: service_healthy
    command: pnpm dev

volumes:
  postgres_data:
"""
        docker_compose.write_text(docker_content)
        print_success("Created docker-compose.fullstack.yml")
    
    def create_vscode_fullstack(self) -> None:
        """Create VS Code configurations for full-stack development"""
        vscode_dir = self.project_root / ".vscode"
        vscode_dir.mkdir(exist_ok=True)
        
        # Update launch.json with frontend debugging
        launch_json = vscode_dir / "launch.json"
        launch_config = {
            "version": "0.2.0",
            "configurations": [
                {
                    "name": "CIRIS Backend (Mock)",
                    "type": "python",
                    "request": "launch",
                    "program": "${workspaceFolder}/main.py",
                    "args": ["--mock-llm", "--adapter", "api"],
                    "console": "integratedTerminal",
                    "envFile": "${workspaceFolder}/.env.development"
                },
                {
                    "name": "CIRIS Frontend",
                    "type": "node",
                    "request": "launch",
                    "runtimeExecutable": "pnpm",
                    "runtimeArgs": ["dev"],
                    "cwd": "${workspaceFolder}/CIRISGUI",
                    "console": "integratedTerminal"
                },
                {
                    "name": "Full-Stack Debug",
                    "type": "node",
                    "request": "launch",
                    "runtimeExecutable": "${workspaceFolder}/scripts/dev_fullstack.sh",
                    "console": "integratedTerminal"
                }
            ],
            "compounds": [
                {
                    "name": "Backend + Frontend",
                    "configurations": ["CIRIS Backend (Mock)", "CIRIS Frontend"]
                }
            ]
        }
        
        launch_json.write_text(json.dumps(launch_config, indent=4))
        print_success("Created VS Code full-stack debug configurations")
    
    def print_fullstack_next_steps(self) -> None:
        """Print next steps for full-stack development"""
        print_header("Full-Stack Setup Complete!")
        
        print(f"""
{Colors.BOLD}Quick Start Commands:{Colors.END}

1. Start full-stack development:
   {Colors.BOLD}./scripts/dev_fullstack.sh{Colors.END}
   
2. Or start separately:
   Backend: {Colors.BOLD}python ciris_dev_server.py --adapter api{Colors.END}
   Frontend: {Colors.BOLD}cd CIRISGUI && pnpm dev{Colors.END}

3. Run all tests:
   {Colors.BOLD}./scripts/test_fullstack.sh{Colors.END}

4. Docker full-stack:
   {Colors.BOLD}docker-compose -f docker-compose.fullstack.yml up{Colors.END}

{Colors.BOLD}Access Points:{Colors.END}
   🔧 Backend API: http://localhost:8080
   🎨 Frontend GUI: http://localhost:3000
   📚 API Docs: http://localhost:8080/docs

{Colors.BOLD}Development Tips:{Colors.END}
   - Backend hot reloads on Python file changes
   - Frontend hot reloads on TypeScript/React changes
   - Use VS Code compound debugging for both
   - Check debug tools: {Colors.BOLD}python ciris_debug_tools.py{Colors.END}

Happy full-stack coding! 🚀
""")
    
    def run_setup(self) -> None:
        """Run the complete full-stack setup"""
        print_header("CIRIS Full-Stack Development Setup")
        
        # Check prerequisites
        if not self.check_prerequisites():
            print_error("Prerequisites check failed. Please install missing dependencies.")
            sys.exit(1)
        
        # Setup backend
        if not self.setup_backend():
            print_error("Backend setup failed")
            sys.exit(1)
            
        # Setup frontend
        if not self.setup_frontend():
            print_error("Frontend setup failed")
            sys.exit(1)
            
        # Create additional tools
        self.create_fullstack_scripts()
        self.create_docker_compose_fullstack()
        self.create_vscode_fullstack()
        
        # Print next steps
        self.print_fullstack_next_steps()

def main():
    setup = CIRISFullStackSetup()
    setup.run_setup()

if __name__ == "__main__":
    main()