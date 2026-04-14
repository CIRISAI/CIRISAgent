#!/usr/bin/env python3
"""
CIRIS 2.3 Demo Clip Recorder

Records demo clips for the CIRIS 2.3 YouTube video using:
- Desktop test mode automation (HTTP API at localhost:8091)
- Platform-specific video recording:
  - macOS: SwiftCapture (ScreenCaptureKit CLI)
  - Linux: ffmpeg with x11grab + xdotool for window detection
- In-process /screenshot endpoint for verification screenshots

Usage:
    # Record all clips (app must be running with CIRIS_TEST_MODE=true)
    python3 tools/record_demo_clips.py --output ~/demo_clips/

    # Record a single clip
    python3 tools/record_demo_clips.py --clip 1 --output ~/demo_clips/

    # Auto-launch the desktop app, then record
    python3 tools/record_demo_clips.py --launch --output ~/demo_clips/

    # Login first, then record
    python3 tools/record_demo_clips.py --login --output ~/demo_clips/

Prerequisites:
    - CIRIS desktop app running with CIRIS_TEST_MODE=true
    - macOS: SwiftCapture built: tools/SwiftCapture/.build/release/SwiftCapture
    - Linux: ffmpeg and xdotool installed (apt install ffmpeg xdotool)
    - Logged in to the app (Interact screen visible) for clips 5-8
    - For Demo 8: Home Assistant adapter connected

Demo clips:
    1  Wipe Data — Navigate to Data Management, factory reset (~15s)
    2  First Run Wizard — Welcome screen, proceed through steps (~12s)
    3  Opt-In Traces + Location — Enable traces, add Chicago (~15s)
    4  Set Up Home Assistant — Toggle adapter, configure (~15s)
    5  CIRISVerify 5/5 Attestation (~12s)
    6  CIRISVerify 3/5 Attestation (~10s)
    7  Adapter Panel All Green (~10s)
    8  Home Assistant Lamp Chat (~12s)
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

# --- Configuration ---

TEST_SERVER = "http://localhost:8091"
API_SERVER = "http://localhost:8080"
DEFAULT_OUTPUT_DIR = Path.home() / "demo_clips"
SCAP_BINARY = Path(__file__).parent / "SwiftCapture" / ".build" / "release" / "SwiftCapture"
CIRIS_APP_NAME = "CIRIS Agent"  # Window title as seen by ScreenCaptureKit
CIRIS_WINDOW_CLASS = "CIRIS"  # Window class for X11 matching

# Detect platform
PLATFORM = platform.system()  # "Linux", "Darwin", "Windows"


# Clip files - extension depends on platform
def get_clip_files() -> dict[int, str]:
    """Get clip filenames with platform-appropriate extension."""
    ext = ".mp4" if PLATFORM == "Linux" else ".mov"
    return {
        1: f"demo1_wipe_data{ext}",
        2: f"demo2_first_run_wizard{ext}",
        3: f"demo3_opt_in_traces_location{ext}",
        4: f"demo4_account_finish{ext}",
        5: f"demo5_attestation_5of5{ext}",
        6: f"demo6_attestation_3of5{ext}",
        7: f"demo7_adapter_panel{ext}",
        8: f"demo8_lamp_chat{ext}",
    }


CLIP_FILES = get_clip_files()


# --- SwiftCapture Video Recording (macOS) ---


def check_swiftcapture() -> bool:
    """Verify SwiftCapture binary exists (macOS only)."""
    if SCAP_BINARY.exists():
        print(f"  SwiftCapture: {SCAP_BINARY}")
        return True
    print(f"ERROR: SwiftCapture not found at {SCAP_BINARY}", file=sys.stderr)
    print("  Build it: cd tools/SwiftCapture && swift build -c release", file=sys.stderr)
    return False


def start_recording_macos(duration_ms: int, output: Path) -> subprocess.Popen:
    """
    Start recording the CIRIS app window using SwiftCapture (ScreenCaptureKit).
    Returns Popen handle. Recording auto-stops after duration_ms milliseconds.
    """
    cmd = [
        str(SCAP_BINARY),
        "--app",
        CIRIS_APP_NAME,
        "--duration",
        str(duration_ms),
        "--output",
        str(output),
        "--fps",
        "30",
        "--quality",
        "high",
        "--show-cursor",
        "--force",  # Overwrite without prompting
    ]
    print(f"  Recording: {output.name} ({duration_ms / 1000:.0f}s)")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    # Give SwiftCapture a moment to initialize + permission prompt
    time.sleep(1.5)
    return proc


# --- Linux Video Recording (ffmpeg + x11grab) ---


def check_linux_tools() -> bool:
    """Verify ffmpeg and xdotool are installed (Linux only)."""
    missing = []

    if not shutil.which("ffmpeg"):
        missing.append("ffmpeg")
    if not shutil.which("xdotool"):
        missing.append("xdotool")
    if not shutil.which("xwininfo"):
        missing.append("x11-utils (xwininfo)")

    if missing:
        print(f"ERROR: Missing Linux tools: {', '.join(missing)}", file=sys.stderr)
        print("  Install: sudo apt install ffmpeg xdotool x11-utils", file=sys.stderr)
        return False

    print(f"  ffmpeg: {shutil.which('ffmpeg')}")
    print(f"  xdotool: {shutil.which('xdotool')}")
    return True


def find_window_geometry() -> Optional[Tuple[int, int, int, int]]:
    """
    Find the CIRIS window geometry using xdotool + xwininfo.
    Returns (x, y, width, height) or None if not found.
    """
    # Try multiple window name patterns
    patterns = [
        CIRIS_APP_NAME,
        "CIRIS",
        "ciris",
        "CIRIS Agent",
    ]

    window_id = None
    for pattern in patterns:
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", pattern],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Take the first matching window
                window_id = result.stdout.strip().split("\n")[0]
                break
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    if not window_id:
        # Try by class name
        try:
            result = subprocess.run(
                ["xdotool", "search", "--class", CIRIS_WINDOW_CLASS],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip().split("\n")[0]
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    if not window_id:
        print("  ERROR: Could not find CIRIS window", file=sys.stderr)
        return None

    # Get window geometry using xwininfo
    try:
        result = subprocess.run(
            ["xwininfo", "-id", window_id],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            print(f"  ERROR: xwininfo failed: {result.stderr}", file=sys.stderr)
            return None

        output = result.stdout

        # Parse xwininfo output
        x_match = re.search(r"Absolute upper-left X:\s+(\d+)", output)
        y_match = re.search(r"Absolute upper-left Y:\s+(\d+)", output)
        w_match = re.search(r"Width:\s+(\d+)", output)
        h_match = re.search(r"Height:\s+(\d+)", output)

        if not all([x_match, y_match, w_match, h_match]):
            print("  ERROR: Could not parse window geometry", file=sys.stderr)
            return None

        x = int(x_match.group(1))
        y = int(y_match.group(1))
        w = int(w_match.group(1))
        h = int(h_match.group(1))

        # Ensure dimensions are even (required for many video codecs)
        w = w if w % 2 == 0 else w - 1
        h = h if h % 2 == 0 else h - 1

        print(f"  Window: {window_id} at {x},{y} size {w}x{h}")
        return (x, y, w, h)

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  ERROR: xwininfo error: {e}", file=sys.stderr)
        return None


def start_recording_linux(duration_ms: int, output: Path) -> Optional[subprocess.Popen]:
    """
    Start recording the CIRIS app window using ffmpeg x11grab.
    Returns Popen handle or None if window not found.
    """
    geometry = find_window_geometry()
    if not geometry:
        return None

    x, y, w, h = geometry
    duration_s = duration_ms / 1000

    # Get display from environment
    display = os.environ.get("DISPLAY", ":0")

    cmd = [
        "ffmpeg",
        "-y",  # Overwrite output
        "-video_size",
        f"{w}x{h}",
        "-framerate",
        "30",
        "-f",
        "x11grab",
        "-i",
        f"{display}+{x},{y}",
        "-t",
        str(duration_s),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",  # Fast encoding for real-time
        "-crf",
        "18",  # High quality
        "-pix_fmt",
        "yuv420p",  # Compatibility
        str(output),
    ]

    print(f"  Recording: {output.name} ({duration_s:.0f}s)")

    # Run ffmpeg with suppressed output
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Brief pause to let ffmpeg initialize
    time.sleep(0.5)
    return proc


# --- Platform-agnostic Recording Interface ---


def check_recording_tools() -> bool:
    """Check that platform-appropriate recording tools are available."""
    if PLATFORM == "Darwin":
        return check_swiftcapture()
    elif PLATFORM == "Linux":
        return check_linux_tools()
    else:
        print(f"ERROR: Unsupported platform: {PLATFORM}", file=sys.stderr)
        print("  Supported: macOS (Darwin), Linux", file=sys.stderr)
        return False


def start_recording(duration_ms: int, output: Path) -> Optional[subprocess.Popen]:
    """
    Start recording the CIRIS app window using platform-appropriate tool.
    Returns Popen handle or None on failure.
    """
    if PLATFORM == "Darwin":
        return start_recording_macos(duration_ms, output)
    elif PLATFORM == "Linux":
        return start_recording_linux(duration_ms, output)
    else:
        print(f"  ERROR: Recording not supported on {PLATFORM}", file=sys.stderr)
        return None


def wait_for_recording(proc: Optional[subprocess.Popen], timeout: int = 60) -> bool:
    """Wait for a recording process to complete."""
    if proc is None:
        return False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        if proc.returncode != 0:
            print(f"  Recording error: {stderr.decode()[:200]}")
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        return False


# --- Test Automation API ---


def test_api(method: str, endpoint: str, data: Optional[dict] = None, timeout: int = 10) -> dict:
    """Make a request to the test automation server."""
    url = f"{TEST_SERVER}{endpoint}"
    req_data = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"} if data else {}

    request = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def click(tag: str) -> dict:
    """Click an element by test tag."""
    result = test_api("POST", "/click", {"testTag": tag})
    if result.get("success"):
        print(f"    click: {tag}")
    else:
        print(f"    click FAILED: {tag} -- {result.get('error', 'unknown')}")
    return result


def input_text(tag: str, text: str, clear_first: bool = True) -> dict:
    """Input text to an element by test tag."""
    result = test_api("POST", "/input", {"testTag": tag, "text": text, "clearFirst": clear_first})
    if result.get("success"):
        print(f"    input: {tag} = '{text}'")
    else:
        print(f"    input FAILED: {tag} -- {result.get('error', 'unknown')}")
    return result


def wait_for(tag: str, timeout_ms: int = 5000) -> dict:
    """Wait for an element to appear."""
    result = test_api("POST", "/wait", {"testTag": tag, "timeoutMs": timeout_ms})
    if result.get("success"):
        print(f"    wait: {tag} (found)")
    else:
        print(f"    wait TIMEOUT: {tag} -- {result.get('error', 'unknown')}")
    return result


def get_screen() -> str:
    """Get the current screen name."""
    result = test_api("GET", "/screen")
    return result.get("screen", "Unknown")


def get_tree() -> dict:
    """Get the full UI element tree."""
    return test_api("GET", "/tree")


def take_screenshot(output_path: str) -> bool:
    """Take a screenshot via the in-process /screenshot endpoint (java.awt.Robot)."""
    result = test_api("POST", "/screenshot", {"path": output_path})
    if result.get("success"):
        print(f"    screenshot: {output_path}")
        return True
    else:
        print(f"    screenshot FAILED: {result.get('error', 'unknown')}")
        return False


# --- Navigation Helpers ---


def ensure_interact_screen():
    """Navigate back to the Interact (chat) screen if not already there."""
    screen = get_screen()
    print(f"  Current screen: {screen}")

    if screen == "Interact":
        return True

    # Try common back buttons for different screens
    back_buttons = [
        "btn_trust_back",
        "btn_adapters_back",
        "btn_services_back",
        "btn_settings_back",
        "btn_back",
    ]
    for btn in back_buttons:
        result = test_api("POST", "/click", {"testTag": btn})
        if result.get("success"):
            time.sleep(0.5)
            if get_screen() == "Interact":
                return True

    print("  WARNING: Could not navigate to Interact screen")
    return False


def do_login():
    """Login via test automation."""
    screen = get_screen()
    if screen != "Login":
        print(f"  Not on login screen (current: {screen}), skipping login")
        return

    print("  Logging in...")
    wait_for("input_username", 10000)
    input_text("input_username", "admin")
    input_text("input_password", "qa_test_password_12345")
    click("btn_login_submit")
    print("  Waiting for Interact screen...")
    wait_for("input_message", 30000)
    time.sleep(1)
    print("  Login complete!")


# --- Demo Clip Functions ---


def record_demo_1_wipe_data(output_dir: Path):
    """
    Demo 1 -- Wipe Data (~15s)
    Navigate from Interact to Data Management, perform factory reset.
    After wipe, the desktop app shuts down the Python server and restarts it.
    The JAR stays alive and navigates to the setup wizard.
    """
    print("\n=== DEMO 1: Wipe Data ===")
    ensure_interact_screen()

    output = output_dir / CLIP_FILES[1]
    proc = start_recording(15000, output)

    time.sleep(1)  # Establish context on Interact screen
    click("btn_data_menu")  # Open Data dropdown menu
    time.sleep(0.5)  # Menu animation
    click("menu_data_management")  # Navigate to Data Management
    time.sleep(1.5)  # Wait for screen load
    time.sleep(2)  # Hold for viewer to see screen
    click("btn_reset_account")  # Click "Reset Account"
    time.sleep(1)  # Wait for confirmation dialog
    time.sleep(2)  # Hold so viewer reads dialog
    click("btn_reset_confirm")  # Confirm reset
    time.sleep(4)  # Wait for reset animation

    wait_for_recording(proc)
    print(f"  Saved: {output}")

    # Wait for server restart + first-run detection + setup wizard
    print("  Waiting for server restart and setup wizard...")
    for i in range(30):
        screen = get_screen()
        if screen == "Setup":
            print(f"  Setup wizard ready after {i * 2}s")
            break
        time.sleep(2)
    else:
        print("  WARNING: Setup wizard not detected after 60s")
        # Take a diagnostic screenshot
        take_screenshot(str(output_dir / "debug_after_wipe.png"))


def record_demo_2_first_run_wizard(output_dir: Path):
    """
    Demo 2 -- First Run Wizard (~18s)
    Welcome → Preferences (Schaumburg) → LLM Config (OpenRouter).
    Assumes we arrived at Setup from Demo 1 (wipe).
    """
    print("\n=== DEMO 2: First Run Wizard ===")

    # Should already be on Setup from Demo 1
    screen = get_screen()
    if screen != "Setup":
        print(f"  WARNING: Expected Setup screen, got {screen}")
        wait_for("btn_next", 30000)
    time.sleep(1)

    # Read OpenRouter key
    key_path = Path.home() / ".openrouter_key"
    openrouter_key = key_path.read_text().strip() if key_path.exists() else ""

    output = output_dir / CLIP_FILES[2]
    proc = start_recording(18000, output)

    time.sleep(2)  # Hold on Welcome screen
    click("btn_next")  # Welcome -> Preferences
    time.sleep(1.5)

    # Set location: Schaumburg
    input_text("input_location_search", "Schaumburg")
    time.sleep(2)
    click("btn_next")  # Preferences -> LLM Config
    time.sleep(1.5)

    # LLM Config: OpenRouter
    click("input_llm_provider")  # Open provider dropdown
    time.sleep(0.5)
    click("menu_provider_openrouter")  # Select OpenRouter
    time.sleep(0.5)
    input_text("input_api_key", openrouter_key)
    time.sleep(0.5)
    input_text("input_llm_model_text", "mistralai/mistral-small-2603")
    time.sleep(1.5)  # Hold for viewer to see config
    click("btn_next")  # LLM Config -> Optional Features
    time.sleep(2)  # Hold on Optional Features

    wait_for_recording(proc)
    print(f"  Saved: {output}")


def record_demo_3_opt_in_traces(output_dir: Path):
    """
    Demo 3 -- Opt-In Features + Email (~20s)
    Enable traces, toggle navigation + weather adapters, enter email,
    scroll to show adapter cards.
    """
    print("\n=== DEMO 3: Opt-In Features ===")

    time.sleep(0.5)

    output = output_dir / CLIP_FILES[3]
    proc = start_recording(20000, output)

    time.sleep(1)
    click("item_accord_metrics_consent")  # Toggle Accord metrics ON
    time.sleep(1)

    # Scroll down slightly to reveal location traces toggle
    test_api("POST", "/scroll", {"testTag": "item_accord_metrics_consent", "direction": "down", "amount": 200})
    time.sleep(0.5)
    click("item_share_location_traces")  # Toggle location traces ON
    time.sleep(1)

    # Toggle public API services to show email field
    click("item_public_api_services")
    time.sleep(0.5)
    input_text("input_public_api_email", "eric@ciris.ai")
    time.sleep(1)

    # Toggle advanced settings to show adapter toggles
    click("item_toggle_advanced_settings")
    time.sleep(1)

    # Scroll down to reveal adapter toggles
    test_api("POST", "/scroll", {"testTag": "item_toggle_advanced_settings", "direction": "down", "amount": 400})
    time.sleep(1)

    # Enable navigation adapter
    click("adapter_toggle_navigation")
    time.sleep(0.8)

    # Scroll more to reveal weather
    test_api("POST", "/scroll", {"testTag": "adapter_toggle_navigation", "direction": "down", "amount": 300})
    time.sleep(0.5)

    # Enable weather adapter
    click("adapter_toggle_weather")
    time.sleep(1)

    time.sleep(2)  # Hold for viewer to see adapter cards

    click("btn_next")  # Optional Features -> Account
    time.sleep(2)

    wait_for_recording(proc)
    print(f"  Saved: {output}")


def record_demo_4_setup_home_assistant(output_dir: Path):
    """
    Demo 4 -- Account Creation + Finish (~12s)
    Set credentials emoore/ciristest1 and complete setup.
    """
    print("\n=== DEMO 4: Account + Finish Setup ===")

    output = output_dir / CLIP_FILES[4]
    proc = start_recording(12000, output)

    time.sleep(1)
    input_text("input_username", "emoore")
    time.sleep(0.5)
    input_text("input_password", "ciristest1")
    time.sleep(1.5)  # Hold for viewer to see credentials
    click("btn_next")  # Finish Setup
    time.sleep(6)  # Wait for setup completion + agent start

    wait_for_recording(proc)
    print(f"  Saved: {output}")


def record_demo_5_attestation_5of5(output_dir: Path):
    """
    Demo 5 -- CIRISVerify 5/5 Attestation (~12s)
    """
    print("\n=== DEMO 5: 5/5 Attestation ===")
    ensure_interact_screen()

    output = output_dir / CLIP_FILES[5]
    proc = start_recording(12000, output)

    time.sleep(1)
    click("btn_trust_shield")
    time.sleep(1.5)
    click("btn_trust_refresh")
    time.sleep(4)
    time.sleep(3)

    wait_for_recording(proc)
    print(f"  Saved: {output}")


def record_demo_6_attestation_3of5(output_dir: Path):
    """
    Demo 6 -- CIRISVerify 3/5 Attestation (~10s)
    """
    print("\n=== DEMO 6: 3/5 Attestation ===")

    screen = get_screen()
    if screen != "Trust":
        ensure_interact_screen()
        click("btn_trust_shield")
        time.sleep(1.5)

    output = output_dir / CLIP_FILES[6]
    proc = start_recording(10000, output)

    time.sleep(3)
    time.sleep(3)
    click("btn_trust_back")
    time.sleep(2)

    wait_for_recording(proc)
    print(f"  Saved: {output}")


def record_demo_7_adapter_panel(output_dir: Path):
    """
    Demo 7 -- Adapter Panel All Green (~10s)
    """
    print("\n=== DEMO 7: Adapter Panel ===")
    ensure_interact_screen()

    output = output_dir / CLIP_FILES[7]
    proc = start_recording(10000, output)

    time.sleep(1)
    click("btn_adapters_menu")
    time.sleep(0.5)
    click("menu_adapters")
    time.sleep(1)
    time.sleep(6)

    wait_for_recording(proc)
    print(f"  Saved: {output}")


def record_demo_8_lamp_chat(output_dir: Path):
    """
    Demo 8 -- Home Assistant Lamp (~12s)
    """
    print("\n=== DEMO 8: Home Assistant Lamp ===")

    screen = get_screen()
    if screen != "Interact":
        click("btn_adapters_back")
        time.sleep(0.5)

    ensure_interact_screen()

    output = output_dir / CLIP_FILES[8]
    proc = start_recording(12000, output)

    time.sleep(1)
    click("input_message")
    time.sleep(0.3)
    input_text("input_message", "Turn on the bedroom lamp.")
    time.sleep(0.5)
    click("btn_send")
    time.sleep(5)
    time.sleep(3)

    wait_for_recording(proc)
    print(f"  Saved: {output}")


# --- Main ---


DEMO_FUNCTIONS = {
    1: record_demo_1_wipe_data,
    2: record_demo_2_first_run_wizard,
    3: record_demo_3_opt_in_traces,
    4: record_demo_4_setup_home_assistant,
    5: record_demo_5_attestation_5of5,
    6: record_demo_6_attestation_3of5,
    7: record_demo_7_adapter_panel,
    8: record_demo_8_lamp_chat,
}


def wait_for_test_server(timeout: int = 30) -> bool:
    """Wait for the test automation server to be ready."""
    print(f"Waiting for test server at {TEST_SERVER}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            result = test_api("GET", "/health")
            if result.get("status") == "ok":
                print(f"  Test server ready (testMode={result.get('testMode')})")
                return True
        except Exception:
            pass
        time.sleep(1)
    print("ERROR: Test server not responding", file=sys.stderr)
    return False


def launch_desktop_app() -> Optional[subprocess.Popen]:
    """Launch the CIRIS desktop app in test mode."""
    print("Launching CIRIS desktop in test mode...")
    env = os.environ.copy()
    env["CIRIS_TEST_MODE"] = "true"

    proc = subprocess.Popen(
        [sys.executable, "-m", "ciris_engine.cli"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  Started (PID {proc.pid})")
    return proc


def main():
    parser = argparse.ArgumentParser(
        description="Record CIRIS 2.3 demo clips using desktop test automation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Demo clips:
  1  Wipe Data -- Factory reset from Data Management (~15s)
  2  First Run Wizard -- Welcome + LLM config steps (~12s)
  3  Opt-In Traces + Location -- Enable traces, set Chicago (~15s)
  4  Set Up Home Assistant -- Configure HA adapter (~15s)
  5  CIRISVerify 5/5 Attestation (~12s)
  6  CIRISVerify 3/5 Attestation (~10s)
  7  Adapter Panel All Green (~10s)
  8  Home Assistant Lamp Chat (~12s)

Recording order:
  Clips 1-4 form a continuous setup flow (wipe -> wizard -> traces -> HA).
  Clips 5-8 are independent demos from a running agent.

Examples:
  python3 tools/record_demo_clips.py --output ~/demo_clips/
  python3 tools/record_demo_clips.py --clip 3 --output ~/demo_clips/
  python3 tools/record_demo_clips.py --launch --login --output ~/demo_clips/
  python3 tools/record_demo_clips.py --clip 1 --clip 2 --clip 3 --clip 4 -o ~/demo_clips/
""",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--clip",
        "-c",
        type=int,
        action="append",
        choices=list(range(1, 9)),
        help="Record specific clip(s) (1-8). Can specify multiple. Default: all.",
    )
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Launch the desktop app in test mode before recording.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Perform login via automation before recording.",
    )
    parser.add_argument(
        "--screenshot",
        type=str,
        help="Take a single screenshot and save to path, then exit.",
    )
    parser.add_argument(
        "--list-apps",
        action="store_true",
        help="List recordable windows/apps and exit.",
    )
    parser.add_argument(
        "--list-windows",
        action="store_true",
        help="(Linux) List all X11 windows with IDs and exit.",
    )

    args = parser.parse_args()

    # List apps/windows mode
    if args.list_apps:
        if PLATFORM == "Darwin":
            if not check_swiftcapture():
                sys.exit(1)
            subprocess.run([str(SCAP_BINARY), "--app-list"])
        elif PLATFORM == "Linux":
            print("Searching for CIRIS windows...")
            geometry = find_window_geometry()
            if geometry:
                x, y, w, h = geometry
                print(f"  Found: CIRIS window at ({x}, {y}) size {w}x{h}")
            else:
                print("  No CIRIS window found. Is the app running?")
                print("\n  Tip: Use --list-windows to see all X11 windows")
        return

    if args.list_windows:
        if PLATFORM != "Linux":
            print("--list-windows is only available on Linux")
            sys.exit(1)
        print("X11 windows (via xdotool):")
        subprocess.run(["xdotool", "search", "--name", ".", "getwindowname", "%@"], shell=False)
        return

    # Screenshot mode
    if args.screenshot:
        if not wait_for_test_server(timeout=5):
            sys.exit(1)
        take_screenshot(args.screenshot)
        return

    # Check recording tools (platform-specific)
    print(f"Platform: {PLATFORM}")
    if not check_recording_tools():
        sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {args.output}")

    # Launch app if requested
    app_proc = None
    if args.launch:
        app_proc = launch_desktop_app()
        time.sleep(5)  # Give server time to start

    # Wait for test server
    if not wait_for_test_server():
        print("\nMake sure the desktop app is running with CIRIS_TEST_MODE=true:")
        print("  CIRIS_TEST_MODE=true python3 -m ciris_engine.cli")
        if app_proc:
            app_proc.terminate()
        sys.exit(1)

    # Login if requested
    if args.login:
        do_login()

    # Determine which clips to record
    clips_to_record = args.clip if args.clip else list(range(1, 9))

    print(f"\nRecording clips: {clips_to_record}")
    if PLATFORM == "Darwin":
        print(f"Video: SwiftCapture ({SCAP_BINARY.name})")
    else:
        print(f"Video: ffmpeg x11grab")
    print(f"Window: {CIRIS_APP_NAME}")
    print("=" * 50)

    # Record clips
    for clip_num in clips_to_record:
        DEMO_FUNCTIONS[clip_num](args.output)
        if clip_num != clips_to_record[-1]:
            time.sleep(1)  # Brief pause between clips

    # Summary
    print("\n" + "=" * 50)
    print("Recording complete!")
    print(f"\nOutput files in {args.output}:")
    for clip_num in clips_to_record:
        filepath = args.output / CLIP_FILES[clip_num]
        size = filepath.stat().st_size if filepath.exists() else 0
        status = f"{size / 1024 / 1024:.1f} MB" if size > 0 else "MISSING"
        print(f"  {CLIP_FILES[clip_num]:45s} {status}")

    # Cleanup
    if app_proc:
        print("\nShutting down desktop app...")
        app_proc.terminate()
        try:
            app_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            app_proc.kill()


if __name__ == "__main__":
    main()
