#!/usr/bin/env python3
"""
CIRIS Full-Stack Development Server
Runs both backend and frontend with hot reload
"""

import os
import sys
import time
import subprocess
import signal
import threading
import argparse
from pathlib import Path

from ciris_dev_server import Colors, CIRISDevServer

class CIRISFullStackServer:
    """Manages both backend and frontend development servers"""
    
    def __init__(self, backend_adapter='api', mock_llm=True):
        self.backend_adapter = backend_adapter
        self.mock_llm = mock_llm
        self.backend_server = None
        self.frontend_process = None
        self.running = True
        self.project_root = Path(__file__).parent
        self.gui_root = self.project_root / "CIRISGUI"
        
    def check_frontend_deps(self) -> bool:
        """Check if frontend dependencies are installed"""
        node_modules = self.gui_root / "node_modules"
        if not node_modules.exists():
            print(f"{Colors.YELLOW}Frontend dependencies not installed{Colors.END}")
            print(f"Run: cd CIRISGUI && pnpm install")
            return False
        return True
    
    def start_backend(self):
        """Start the backend server with hot reload"""
        print(f"{Colors.GREEN}Starting CIRIS Backend...{Colors.END}")
        self.backend_server = CIRISDevServer(
            adapter=self.backend_adapter,
            mock_llm=self.mock_llm
        )
        
        # Run backend in a thread
        backend_thread = threading.Thread(target=self.backend_server.run)
        backend_thread.daemon = True
        backend_thread.start()
        
        # Wait for backend to be ready
        time.sleep(5)
        print(f"{Colors.GREEN}Backend started on http://localhost:8080{Colors.END}")
    
    def start_frontend(self):
        """Start the frontend development server"""
        print(f"{Colors.GREEN}Starting CIRISGUI Frontend...{Colors.END}")
        
        # Set environment variables
        env = os.environ.copy()
        env.update({
            "NEXT_PUBLIC_API_URL": "http://localhost:8080",
            "NODE_ENV": "development"
        })
        
        # Start frontend process
        self.frontend_process = subprocess.Popen(
            ["pnpm", "dev"],
            cwd=self.gui_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Start output reader thread
        threading.Thread(
            target=self.read_frontend_output,
            daemon=True
        ).start()
        
        time.sleep(5)
        print(f"{Colors.GREEN}Frontend started on http://localhost:3000{Colors.END}")
    
    def read_frontend_output(self):
        """Read and display frontend output"""
        if not self.frontend_process:
            return
            
        for line in self.frontend_process.stdout:
            # Color code Next.js output
            if "error" in line.lower():
                print(f"{Colors.RED}[Frontend] {line.rstrip()}{Colors.END}")
            elif "warn" in line.lower():
                print(f"{Colors.YELLOW}[Frontend] {line.rstrip()}{Colors.END}")
            elif "ready" in line.lower() or "compiled" in line.lower():
                print(f"{Colors.GREEN}[Frontend] {line.rstrip()}{Colors.END}")
            else:
                print(f"{Colors.BLUE}[Frontend]{Colors.END} {line.rstrip()}")
    
    def stop_all(self):
        """Stop all servers"""
        print(f"\n{Colors.YELLOW}Stopping all servers...{Colors.END}")
        
        # Stop backend
        if self.backend_server:
            self.backend_server.running = False
            self.backend_server.cleanup()
        
        # Stop frontend
        if self.frontend_process:
            self.frontend_process.terminate()
            try:
                self.frontend_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.frontend_process.kill()
    
    def run(self):
        """Run the full-stack development environment"""
        print(f"{Colors.BOLD}CIRIS Full-Stack Development Server{Colors.END}")
        print(f"Backend: {self.backend_adapter} mode (Mock LLM: {self.mock_llm})")
        print(f"Frontend: Next.js development server")
        print(f"{Colors.YELLOW}Press Ctrl+C to stop{Colors.END}\n")
        
        # Check frontend dependencies
        if not self.check_frontend_deps():
            return
        
        try:
            # Start servers
            self.start_backend()
            self.start_frontend()
            
            print(f"\n{Colors.BOLD}🚀 Full-stack environment ready!{Colors.END}")
            print(f"   Backend API: {Colors.CYAN}http://localhost:8080{Colors.END}")
            print(f"   Frontend GUI: {Colors.CYAN}http://localhost:3000{Colors.END}")
            print(f"   API Docs: {Colors.CYAN}http://localhost:8080/docs{Colors.END}")
            print(f"\n{Colors.YELLOW}Both servers have hot reload enabled{Colors.END}")
            
            # Keep running
            while self.running:
                time.sleep(1)
                
        except KeyboardInterrupt:
            pass
        finally:
            self.stop_all()
            print(f"{Colors.GREEN}Full-stack server stopped.{Colors.END}")
    
    def handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        self.running = False

def main():
    parser = argparse.ArgumentParser(
        description="CIRIS Full-Stack Development Server"
    )
    parser.add_argument(
        "--backend-adapter",
        choices=["cli", "api", "discord"],
        default="api",
        help="Backend adapter to use"
    )
    parser.add_argument(
        "--no-mock",
        action="store_true",
        help="Disable mock LLM (use real LLM)"
    )
    
    args = parser.parse_args()
    
    # Check dependencies
    try:
        import watchdog
    except ImportError:
        print(f"{Colors.RED}Error: watchdog not installed{Colors.END}")
        print("Install it with: pip install watchdog")
        sys.exit(1)
    
    # Check for pnpm
    try:
        subprocess.run(["pnpm", "--version"], capture_output=True, check=True)
    except:
        print(f"{Colors.RED}Error: pnpm not installed{Colors.END}")
        print("Install it with: npm install -g pnpm")
        sys.exit(1)
    
    server = CIRISFullStackServer(
        backend_adapter=args.backend_adapter,
        mock_llm=not args.no_mock
    )
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, server.handle_signal)
    signal.signal(signal.SIGTERM, server.handle_signal)
    
    server.run()

if __name__ == "__main__":
    main()