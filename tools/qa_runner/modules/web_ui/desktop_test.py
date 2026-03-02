#!/usr/bin/env python3
"""
Desktop App Test CLI

Simple CLI for testing the CIRIS desktop app via the TestAutomationServer.

Usage:
    python -m tools.qa_runner.modules.web_ui.desktop_test status
    python -m tools.qa_runner.modules.web_ui.desktop_test login
    python -m tools.qa_runner.modules.web_ui.desktop_test navigate Adapters
    python -m tools.qa_runner.modules.web_ui.desktop_test click btn_menu
    python -m tools.qa_runner.modules.web_ui.desktop_test input input_username admin
"""

import asyncio
import sys

from .desktop_app_helper import DesktopAppConfig, DesktopAppHelper


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tools.qa_runner.modules.web_ui.desktop_test <command> [args...]")
        print("\nCommands:")
        print("  status              - Show current screen and elements")
        print("  login [user] [pass] - Login with credentials")
        print("  navigate <screen>   - Navigate to a screen (e.g., Adapters)")
        print("  click <tag>         - Click an element")
        print("  input <tag> <text>  - Input text to an element")
        print("  wait-screen <name>  - Wait for a screen")
        print("  wait-element <tag>  - Wait for an element")
        return

    command = sys.argv[1]
    args = sys.argv[2:]

    helper = DesktopAppHelper(DesktopAppConfig(poll_interval_ms=100))

    try:
        await helper.start()
    except RuntimeError as e:
        print(f"Error: {e}")
        return

    try:
        if command == "status":
            status = await helper.status()
            print(f"Screen: {status['screen']}")
            print(f"Elements ({status['count']}):")
            for tag in sorted(status["elements"]):
                print(f"  {tag}")

        elif command == "login":
            username = args[0] if len(args) > 0 else "admin"
            password = args[1] if len(args) > 1 else "ciris_admin_password"
            print(f"Logging in as {username}...")
            success = await helper.login(username, password)
            print(f"Login: {'success' if success else 'failed'}")
            if success:
                status = await helper.status()
                print(f"Now on: {status['screen']}")

        elif command == "navigate":
            if not args:
                print("Usage: navigate <screen>")
                return
            screen = args[0]
            print(f"Navigating to {screen}...")
            success = await helper.navigate_to(screen)
            print(f"Navigate: {'success' if success else 'failed'}")
            if success:
                status = await helper.status()
                print(f"Now on: {status['screen']}")
                print(f"Elements: {status['elements']}")

        elif command == "click":
            if not args:
                print("Usage: click <tag>")
                return
            tag = args[0]
            print(f"Clicking {tag}...")
            success = await helper.click(tag)
            print(f"Click: {'success' if success else 'failed'}")
            # Poll for status update
            await asyncio.sleep(0.2)
            status = await helper.status()
            print(f"Screen: {status['screen']}, Elements: {status['elements']}")

        elif command == "input":
            if len(args) < 2:
                print("Usage: input <tag> <text>")
                return
            tag = args[0]
            text = " ".join(args[1:])
            print(f"Inputting '{text}' to {tag}...")
            success = await helper.input_text(tag, text)
            print(f"Input: {'success' if success else 'failed'}")

        elif command == "wait-screen":
            if not args:
                print("Usage: wait-screen <name>")
                return
            screen = args[0]
            print(f"Waiting for screen {screen}...")
            success = await helper.wait_for_screen(screen, timeout=10000)
            print(f"Wait: {'found' if success else 'timeout'}")

        elif command == "wait-element":
            if not args:
                print("Usage: wait-element <tag>")
                return
            tag = args[0]
            print(f"Waiting for element {tag}...")
            success = await helper.wait_for_element(tag, timeout=10000)
            print(f"Wait: {'found' if success else 'timeout'}")

        else:
            print(f"Unknown command: {command}")

    finally:
        await helper.stop()


if __name__ == "__main__":
    asyncio.run(main())
