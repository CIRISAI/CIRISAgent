"""
CIRIS Agent CLI - Desktop-first launcher with server fallback.

Usage after 'pip install ciris-agent':
    ciris-agent                          # Start server + launch desktop app
    ciris-agent --server                 # Start API server only (headless)
    ciris-agent --adapter api            # Legacy: same as --server
    ciris-agent --adapter discord        # Discord bot mode
"""

import os
import subprocess
import sys
from pathlib import Path

# Skip early FFI verification to avoid tokio runtime hang during Python import lock
# Binary self-verification still runs when get_license_status() is called
os.environ["CIRIS_SKIP_EARLY_VERIFY"] = "1"

from ciris_engine.logic.utils import win_console as _win_console  # noqa: E402

_win_console.setup()


def main() -> None:
    """
    Entry point for the ciris-agent CLI command.

    By default, starts the API server and launches the desktop app.
    Use --server or --adapter for headless/server modes.
    """
    # Check if user wants server/headless mode
    server_mode = False
    for arg in sys.argv[1:]:
        if arg in ("--server", "--headless", "--adapter", "-a"):
            server_mode = True
            break
        if arg in ("--help", "-h", "--version"):
            # Let main.py handle these
            server_mode = True
            break

    if server_mode:
        # Delegate to main.py for server/adapter modes
        _run_server_mode()
    else:
        # Start server then launch desktop app
        _run_desktop_mode()


def _run_desktop_mode() -> None:
    """Start API server and launch desktop application."""
    import time

    port = 8080
    server_url = f"http://localhost:{port}"

    # Find main.py
    parent_dir = Path(__file__).parent.parent
    main_py = parent_dir / "main.py"

    if not main_py.exists():
        print(f"ERROR: main.py not found at {main_py}", file=sys.stderr)
        print("Falling back to server-only mode...", file=sys.stderr)
        _run_server_mode()
        return

    print("Starting CIRIS API server...")

    # Start server in background (show output for debugging). Propagate the
    # UTF-8 stdio intent so the child main.py doesn't crash on cp1252 consoles.
    server_proc = subprocess.Popen(
        [sys.executable, str(main_py), "--adapter", "api", "--port", str(port)],
        cwd=str(parent_dir),
        env=_win_console.subprocess_env(),
    )

    # Wait briefly and check if server crashed during startup
    time.sleep(2.0)
    exit_code = server_proc.poll()
    if exit_code is not None:
        # Server process exited - it crashed during startup
        print(f"\n{'=' * 60}", file=sys.stderr)
        print("ERROR: CIRIS server failed to start!", file=sys.stderr)
        print(f"{'=' * 60}", file=sys.stderr)
        if exit_code != 0:
            print(f"Server exited with code: {exit_code}", file=sys.stderr)
        print("\nCommon causes:", file=sys.stderr)
        print(f"  - Port {port} is already in use by another process", file=sys.stderr)
        print("  - Missing configuration or dependencies", file=sys.stderr)
        print("\nTo check if port is in use:", file=sys.stderr)
        print(f"  lsof -i :{port}  (Linux/macOS)", file=sys.stderr)
        print(f"  netstat -ano | findstr :{port}  (Windows)", file=sys.stderr)
        print("\nTo kill processes using the port:", file=sys.stderr)
        print(f"  fuser -k {port}/tcp  (Linux)", file=sys.stderr)
        print(f"{'=' * 60}\n", file=sys.stderr)
        sys.exit(exit_code if exit_code != 0 else 1)

    try:
        # Launch bundled desktop app (it has its own server detection logic)
        try:
            from ciris_engine.desktop_launcher import launch_desktop_app

            print("\nLaunching CIRIS Desktop...")
            exit_code = launch_desktop_app(server_url=server_url)

        except ImportError as e:
            print(f"Desktop launcher not available: {e}", file=sys.stderr)
            print(f"\nServer running at: {server_url}")
            print("Press Ctrl+C to stop...")
            exit_code = 0
            # Keep running until interrupted
            try:
                server_proc.wait()
            except KeyboardInterrupt:
                pass
        except Exception as e:
            print(f"ERROR: Failed to launch desktop app: {e}", file=sys.stderr)
            print(f"\nServer still running at: {server_url}")
            print("Press Ctrl+C to stop...")
            exit_code = 1
            try:
                server_proc.wait()
            except KeyboardInterrupt:
                pass

    finally:
        # Shutdown server
        print("\nShutting down server...")
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    sys.exit(exit_code)


def _run_server_mode() -> None:
    """Run in server/adapter mode via main.py."""
    # Ensure parent directory is in path so we can import main
    parent_dir = Path(__file__).parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    # Import and run the existing main() function from main.py
    try:
        import main as ciris_main

        ciris_main.main()
    except ImportError as e:
        print(f"ERROR: Failed to import main module: {e}", file=sys.stderr)
        print("This should not happen in a properly installed package.", file=sys.stderr)
        sys.exit(1)


def server() -> None:
    """Entry point for ciris-server command (headless API server)."""
    # Insert --adapter api if not specified
    if "--adapter" not in sys.argv and "-a" not in sys.argv:
        sys.argv.insert(1, "--adapter")
        sys.argv.insert(2, "api")
    _run_server_mode()


def desktop() -> None:
    """Entry point for ciris-desktop command."""
    from ciris_engine.desktop_launcher import main as desktop_main

    desktop_main()


if __name__ == "__main__":
    main()
