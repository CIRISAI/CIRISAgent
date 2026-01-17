"""
Mobile QA Runner CLI.

Usage:
    python -m tools.mobile_qa_runner status       # Check device and server status
    python -m tools.mobile_qa_runner bridge       # Start port forwarding
    python -m tools.mobile_qa_runner setup        # Create .env on device
    python -m tools.mobile_qa_runner reset        # Delete .env (reset to first-run)
    python -m tools.mobile_qa_runner restart      # Restart the app
    python -m tools.mobile_qa_runner logs         # Show recent logcat
    python -m tools.mobile_qa_runner run <module> # Run QA tests via bridge
    python -m tools.mobile_qa_runner wait         # Wait for server to be ready
"""

import argparse
import sys

from .bridge import EmulatorBridge
from .config import MobileQAConfig


def cmd_status(bridge: EmulatorBridge, args):
    """Check device and server status."""
    print("=" * 60)
    print("CIRIS Mobile QA Runner - Status")
    print("=" * 60)

    # Check device
    try:
        device = bridge.get_device()
        print(f"\n✓ Device: {device.serial}")
        print(f"  Type: {'Emulator' if device.is_emulator else 'Physical'}")
        print(f"  State: {device.state}")
        if device.model:
            print(f"  Model: {device.model}")
    except Exception as e:
        print(f"\n✗ No device: {e}")
        return False

    # Check first-run status
    is_first_run = bridge.check_first_run()
    print(f"\n{'!' if is_first_run else '✓'} First-run: {is_first_run}")
    if is_first_run:
        print("  (No .env file - setup wizard will show)")

    # Check server
    print("\n" + "-" * 40)
    print("Starting port forward...")
    bridge.start_port_forward()

    status = bridge.check_server_status()
    if status.reachable:
        print("\n✓ Server reachable")
        print(f"  Healthy: {status.healthy}")
        print(f"  Services: {status.services_online}/{status.total_services}")
        if status.is_first_run:
            print("  Mode: First-run (10 services)")
    else:
        print(f"\n✗ Server not reachable: {status.error}")

    print("\n" + "=" * 60)
    return status.healthy


def cmd_bridge(bridge: EmulatorBridge, args):
    """Start port forwarding."""
    print("Starting ADB port forwarding...")
    success = bridge.start_port_forward()
    if success:
        print(f"\nBridge active: localhost:{bridge.config.local_port} → device:{bridge.config.device_port}")
        print("\nYou can now run the main QA runner:")
        print(f"  python -m tools.qa_runner auth --url http://localhost:{bridge.config.local_port} --no-auto-start")
        print("\nPress Ctrl+C to stop...")
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping bridge...")
            bridge.stop_port_forward()
    return success


def cmd_setup(bridge: EmulatorBridge, args):
    """Create .env on device to complete setup."""
    if not args.llm_api_key:
        print("Error: --llm-api-key is required for setup")
        print("Usage: python -m tools.mobile_qa_runner setup --llm-api-key sk-...")
        return False

    print("Creating .env file on device...")
    success = bridge.create_env_file(
        llm_api_key=args.llm_api_key,
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
        admin_password=args.admin_password,
    )

    if success:
        print("\n✓ Setup complete. Restart the app to apply:")
        print("  python -m tools.mobile_qa_runner restart")

    return success


def cmd_reset(bridge: EmulatorBridge, args):
    """Delete .env to reset to first-run state."""
    print("Resetting to first-run state...")
    success = bridge.delete_env_file()

    if success:
        print("\n✓ Reset complete. Restart the app to show setup wizard:")
        print("  python -m tools.mobile_qa_runner restart")

    return success


def cmd_restart(bridge: EmulatorBridge, args):
    """Restart the CIRIS app."""
    print("Restarting CIRIS app...")
    return bridge.restart_app()


def cmd_logs(bridge: EmulatorBridge, args):
    """Show recent logcat output."""
    lines = args.lines or 100
    print(f"Last {lines} lines of Python logcat:")
    print("-" * 60)
    print(bridge.get_logcat(lines=lines))
    return True


def cmd_wait(bridge: EmulatorBridge, args):
    """Wait for server to become healthy."""
    print("Waiting for server to be ready...")
    bridge.start_port_forward()

    timeout = args.timeout or 120
    status = bridge.wait_for_server(timeout=timeout)

    if status.healthy:
        print(f"\n✓ Server ready: {status.services_online}/{status.total_services} services")
        return True
    else:
        print(f"\n✗ Server not ready: {status.error}")
        return False


def cmd_run(bridge: EmulatorBridge, args):
    """Run QA tests via the bridge."""
    if not args.modules:
        print("Error: No modules specified")
        print("Usage: python -m tools.mobile_qa_runner run auth telemetry")
        return False

    print("Starting port forward...")
    bridge.start_port_forward()

    print("Checking server health...")
    status = bridge.check_server_status()
    if not status.healthy:
        print(f"Warning: Server not healthy ({status.services_online}/{status.total_services} services)")
        if not args.force:
            print("Use --force to run anyway")
            return False

    all_success = True
    for module in args.modules:
        print(f"\n{'=' * 60}")
        print(f"Running module: {module}")
        print("=" * 60)

        success, message = bridge.run_qa_module(module)
        print(f"\n{module}: {'✓ PASSED' if success else '✗ FAILED'} - {message}")

        if not success:
            all_success = False

    return all_success


def main():
    parser = argparse.ArgumentParser(
        description="CIRIS Mobile QA Runner - Test CIRIS on Android emulators",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  status    Check device and server status
  bridge    Start ADB port forwarding (keeps running)
  setup     Create .env on device (completes first-run setup)
  reset     Delete .env (reset to first-run state)
  restart   Restart the CIRIS app
  logs      Show recent Python logcat
  wait      Wait for server to become healthy
  run       Run QA tests via the bridge

Examples:
  # Check current status
  python -m tools.mobile_qa_runner status

  # Setup device with API key (bypasses setup wizard)
  python -m tools.mobile_qa_runner setup --llm-api-key sk-...

  # Reset to first-run and restart
  python -m tools.mobile_qa_runner reset
  python -m tools.mobile_qa_runner restart

  # Run auth tests via bridge
  python -m tools.mobile_qa_runner run auth

  # Run multiple test modules
  python -m tools.mobile_qa_runner run auth telemetry agent
""",
    )

    # Global options
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-s", "--device", dest="device_serial", help="Device serial (default: first emulator)")
    parser.add_argument("--port", type=int, default=8080, help="Local port for bridge (default: 8080)")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Status command
    subparsers.add_parser("status", help="Check device and server status")

    # Bridge command
    subparsers.add_parser("bridge", help="Start ADB port forwarding")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Create .env on device")
    setup_parser.add_argument("--llm-api-key", required=True, help="LLM API key")
    setup_parser.add_argument("--llm-provider", default="openai", help="LLM provider (default: openai)")
    setup_parser.add_argument("--llm-model", default="gpt-4o", help="LLM model (default: gpt-4o)")
    setup_parser.add_argument("--admin-password", help="Admin password (auto-generated if not provided)")

    # Reset command
    subparsers.add_parser("reset", help="Delete .env (reset to first-run)")

    # Restart command
    subparsers.add_parser("restart", help="Restart the CIRIS app")

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show recent logcat")
    logs_parser.add_argument("-n", "--lines", type=int, default=100, help="Number of lines")

    # Wait command
    wait_parser = subparsers.add_parser("wait", help="Wait for server to be healthy")
    wait_parser.add_argument("-t", "--timeout", type=float, default=120, help="Timeout in seconds")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run QA tests via bridge")
    run_parser.add_argument("modules", nargs="+", help="Test modules to run")
    run_parser.add_argument("--force", action="store_true", help="Run even if server not healthy")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Create config
    config = MobileQAConfig(
        verbose=args.verbose,
        device_serial=args.device_serial,
        local_port=args.port,
    )

    # Create bridge
    bridge = EmulatorBridge(config)

    # Dispatch command
    commands = {
        "status": cmd_status,
        "bridge": cmd_bridge,
        "setup": cmd_setup,
        "reset": cmd_reset,
        "restart": cmd_restart,
        "logs": cmd_logs,
        "wait": cmd_wait,
        "run": cmd_run,
    }

    handler = commands.get(args.command)
    if handler:
        success = handler(bridge, args)
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
