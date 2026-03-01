#!/usr/bin/env python3
"""Screenshot tool for capturing the desktop app.

Usage:
    python -m tools.screenshot                    # Capture full screen
    python -m tools.screenshot --window CIRIS     # Capture window by title
    python -m tools.screenshot --output path.png  # Custom output path
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def capture_screen(output_path: Path | None = None, monitor: int = 1) -> Path:
    """Capture the entire screen or a specific monitor.

    Args:
        output_path: Optional path to save the screenshot
        monitor: Monitor number (1-based, 1 = primary)

    Returns:
        Path to the saved screenshot
    """
    try:
        import mss
        from PIL import Image
    except ImportError:
        print("ERROR: mss and pillow required. Install with: pip install mss pillow")
        sys.exit(1)

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"/tmp/screenshot_{timestamp}.png")

    with mss.mss() as sct:
        # Get the monitor (1-indexed in mss, 0 is "all monitors")
        if monitor > len(sct.monitors) - 1:
            monitor = 1

        mon = sct.monitors[monitor]
        screenshot = sct.grab(mon)

        # Convert to PIL Image and save
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        img.save(str(output_path))

    print(f"Screenshot saved to: {output_path}")
    return output_path


def find_window_by_title(title: str) -> tuple[int, int, int, int] | None:
    """Find a window by title and return its geometry.

    Returns:
        Tuple of (x, y, width, height) or None if not found
    """
    try:
        # Try using xdotool
        result = subprocess.run(
            ["xdotool", "search", "--name", title],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            window_id = result.stdout.strip().split("\n")[0]

            # Get window geometry
            geo_result = subprocess.run(
                ["xdotool", "getwindowgeometry", window_id],
                capture_output=True,
                text=True,
            )
            if geo_result.returncode == 0:
                # Parse geometry output
                lines = geo_result.stdout.strip().split("\n")
                for line in lines:
                    if "Position:" in line:
                        pos = line.split(":")[1].strip().split(",")
                        x = int(pos[0])
                        y = int(pos[1].split()[0])
                    if "Geometry:" in line:
                        geo = line.split(":")[1].strip().split("x")
                        width = int(geo[0])
                        height = int(geo[1])

                return (x, y, width, height)
    except FileNotFoundError:
        pass  # xdotool not installed
    except Exception as e:
        print(f"Warning: Could not find window: {e}")

    return None


def capture_window(title: str, output_path: Path | None = None) -> Path | None:
    """Capture a specific window by title.

    Args:
        title: Window title to search for
        output_path: Optional path to save the screenshot

    Returns:
        Path to the saved screenshot, or None if window not found
    """
    try:
        import mss
        from PIL import Image
    except ImportError:
        print("ERROR: mss and pillow required. Install with: pip install mss pillow")
        sys.exit(1)

    geometry = find_window_by_title(title)
    if geometry is None:
        print(f"Window with title '{title}' not found. Capturing full screen instead.")
        return capture_screen(output_path)

    x, y, width, height = geometry

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = Path(f"/tmp/screenshot_{title.replace(' ', '_')}_{timestamp}.png")

    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": width, "height": height}
        screenshot = sct.grab(monitor)

        # Convert to PIL Image and save
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
        img.save(str(output_path))

    print(f"Window screenshot saved to: {output_path}")
    return output_path


def capture_with_delay(delay: float = 2.0, **kwargs) -> Path:
    """Capture screenshot after a delay (useful for capturing menus/tooltips).

    Args:
        delay: Seconds to wait before capturing
        **kwargs: Arguments to pass to capture_screen or capture_window

    Returns:
        Path to the saved screenshot
    """
    print(f"Capturing in {delay} seconds...")
    time.sleep(delay)

    if "title" in kwargs:
        return capture_window(**kwargs)
    else:
        return capture_screen(**kwargs)


def main():
    parser = argparse.ArgumentParser(
        description="Capture screenshots of the desktop or specific windows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m tools.screenshot                     # Full screen
  python -m tools.screenshot --window CIRIS      # CIRIS app window
  python -m tools.screenshot --delay 3           # Capture after 3 seconds
  python -m tools.screenshot -o ~/screenshot.png # Custom output path
""",
    )

    parser.add_argument(
        "--window",
        "-w",
        type=str,
        help="Window title to capture (partial match)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Output file path (default: /tmp/screenshot_<timestamp>.png)",
    )
    parser.add_argument(
        "--delay",
        "-d",
        type=float,
        default=0,
        help="Delay in seconds before capturing",
    )
    parser.add_argument(
        "--monitor",
        "-m",
        type=int,
        default=1,
        help="Monitor number to capture (default: 1 = primary)",
    )

    args = parser.parse_args()

    output_path = Path(args.output) if args.output else None

    if args.delay > 0:
        if args.window:
            path = capture_with_delay(args.delay, title=args.window, output_path=output_path)
        else:
            path = capture_with_delay(args.delay, output_path=output_path, monitor=args.monitor)
    elif args.window:
        path = capture_window(args.window, output_path)
    else:
        path = capture_screen(output_path, args.monitor)

    if path:
        print(f"\nTo view: Read tool with path: {path}")


if __name__ == "__main__":
    main()
