#!/usr/bin/env python3
"""
CIRIS Development Server with Hot Reload
Provides automatic reloading when code changes are detected
"""

import os
import sys
import time
import subprocess
import signal
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import queue
import argparse

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class CIRISReloader(FileSystemEventHandler):
    """Handles file system events and triggers reload"""
    
    def __init__(self, restart_callback):
        self.restart_callback = restart_callback
        self.last_restart = 0
        self.restart_delay = 1.0  # Debounce delay
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Only watch Python files
        if event.src_path.endswith('.py'):
            current_time = time.time()
            if current_time - self.last_restart > self.restart_delay:
                self.last_restart = current_time
                print(f"{Colors.YELLOW}Change detected in {event.src_path}{Colors.END}")
                self.restart_callback()

class CIRISDevServer:
    """Development server with hot reload capability"""
    
    def __init__(self, adapter='cli', mock_llm=True):
        self.adapter = adapter
        self.mock_llm = mock_llm
        self.process = None
        self.observer = None
        self.restart_queue = queue.Queue()
        self.running = True
        
    def build_command(self):
        """Build the command to run CIRIS"""
        cmd = [sys.executable, "main.py", "--adapter", self.adapter]
        if self.mock_llm:
            cmd.append("--mock-llm")
        return cmd
    
    def start_ciris(self):
        """Start the CIRIS process"""
        if self.process:
            self.stop_ciris()
            
        print(f"{Colors.GREEN}Starting CIRIS in {self.adapter} mode...{Colors.END}")
        
        # Set development environment variables
        env = os.environ.copy()
        env.update({
            "CIRIS_ENV": "development",
            "CIRIS_DEBUG": "true",
            "PROCESSING_ROUND_DELAY": "0.5",
            "THOUGHT_PROCESSING_TIMEOUT": "10"
        })
        
        self.process = subprocess.Popen(
            self.build_command(),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Start output reader thread
        threading.Thread(target=self.read_output, daemon=True).start()
    
    def stop_ciris(self):
        """Stop the CIRIS process"""
        if self.process:
            print(f"{Colors.YELLOW}Stopping CIRIS...{Colors.END}")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None
    
    def read_output(self):
        """Read and display process output"""
        if not self.process:
            return
            
        for line in self.process.stdout:
            # Color code the output
            if "ERROR" in line or "Exception" in line:
                print(f"{Colors.RED}{line.rstrip()}{Colors.END}")
            elif "WARNING" in line:
                print(f"{Colors.YELLOW}{line.rstrip()}{Colors.END}")
            elif "INFO" in line or "Starting" in line:
                print(f"{Colors.BLUE}{line.rstrip()}{Colors.END}")
            else:
                print(line.rstrip())
    
    def request_restart(self):
        """Queue a restart request"""
        self.restart_queue.put("restart")
    
    def setup_file_watcher(self):
        """Setup file system watcher for hot reload"""
        self.observer = Observer()
        handler = CIRISReloader(self.request_restart)
        
        # Watch specific directories
        watch_paths = [
            "./ciris_engine",
            "./ciris_modular_services",
            "./logic"
        ]
        
        for path in watch_paths:
            if os.path.exists(path):
                self.observer.schedule(handler, path, recursive=True)
                print(f"{Colors.BLUE}Watching {path} for changes...{Colors.END}")
        
        self.observer.start()
    
    def run(self):
        """Main development server loop"""
        print(f"{Colors.BOLD}CIRIS Development Server{Colors.END}")
        print(f"Adapter: {self.adapter}")
        print(f"Mock LLM: {self.mock_llm}")
        print(f"{Colors.YELLOW}Press Ctrl+C to stop{Colors.END}\n")
        
        # Setup file watcher
        self.setup_file_watcher()
        
        # Start CIRIS
        self.start_ciris()
        
        # Handle restart requests
        try:
            while self.running:
                try:
                    self.restart_queue.get(timeout=1)
                    print(f"\n{Colors.YELLOW}Restarting CIRIS...{Colors.END}")
                    self.stop_ciris()
                    time.sleep(0.5)  # Brief pause
                    self.start_ciris()
                except queue.Empty:
                    pass
                except KeyboardInterrupt:
                    break
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Clean up resources"""
        print(f"\n{Colors.YELLOW}Shutting down...{Colors.END}")
        self.running = False
        
        if self.observer:
            self.observer.stop()
            self.observer.join()
            
        self.stop_ciris()
        print(f"{Colors.GREEN}Development server stopped.{Colors.END}")
    
    def handle_signal(self, signum, frame):
        """Handle shutdown signals"""
        self.running = False

def main():
    parser = argparse.ArgumentParser(description="CIRIS Development Server with Hot Reload")
    parser.add_argument("--adapter", choices=["cli", "api", "discord"], 
                       default="cli", help="Adapter to use")
    parser.add_argument("--no-mock", action="store_true", 
                       help="Disable mock LLM (use real LLM)")
    parser.add_argument("--no-reload", action="store_true",
                       help="Disable hot reload")
    
    args = parser.parse_args()
    
    # Check if watchdog is installed
    try:
        import watchdog
    except ImportError:
        print(f"{Colors.RED}Error: watchdog not installed{Colors.END}")
        print("Install it with: pip install watchdog")
        sys.exit(1)
    
    server = CIRISDevServer(
        adapter=args.adapter,
        mock_llm=not args.no_mock
    )
    
    # Setup signal handlers
    signal.signal(signal.SIGINT, server.handle_signal)
    signal.signal(signal.SIGTERM, server.handle_signal)
    
    try:
        if args.no_reload:
            # Just run without watching
            server.start_ciris()
            server.process.wait()
        else:
            # Run with hot reload
            server.run()
    except KeyboardInterrupt:
        server.cleanup()

if __name__ == "__main__":
    main()