"""The five platforms as one interface, so the UI automation stays DRY.

THE POINT. There is now exactly ONE client — the published CIRISClient Kotlin/
Compose app — running on Linux, macOS, Windows, Android and iOS. It exposes the
same `TestAutomationServer` (`/screen`, `/tree`, `/click`, `/input`) on port 9091
everywhere. So a test that drives it should be written ONCE and run five times,
not written five times.

What genuinely differs between platforms is only two things:

  * TRANSPORT — how the host reaches port 9091. Desktop binds it directly;
    Android needs `adb forward 8091->9091`; iOS needs `iproxy 18091->9091`.
  * CAPTURE — grabbing pixels is an OS primitive and cannot be shared. Desktop
    uses the app's own `/screenshot` (AWT `Robot`), Android `adb screencap`,
    iOS `simctl io screenshot`.

Everything else — every click, every assertion, every screen name — is identical,
because it is the same app. This module isolates those two differences so no
scenario ever has to branch on the platform again. `federation_walk_test.py`
already carries the principle in its own words: "the walk itself is
platform-agnostic — only the transport URLs and bring-up path differ." This
generalises that from one command to all of them.

WHY `capture` TAKES A KIND. Screenshots are the first need, not the last. Both
mobile platforms already record video natively (`adb shell screenrecord`,
`simctl io recordVideo`), and a p2p-chat or video-call scenario will want it. A
`capture(kind=...)` seam absorbs that without a second mechanism appearing
somewhere else.

WHY NOT `/screenshot` EVERYWHERE. It would be the DRY-est answer and it does not
work: `TestAutomationServer` implements it with `Robot.createScreenCapture`,
which is AWT — a desktop-JVM API that does not exist on Android or iOS
(CIRISAgent#1104). The genuinely DRY fix is in-process Compose capture
(`ImageComposeScene`), which lives in the shared layer and would collapse all
three implementations below into one. That is CIRISAgent#1104's first ask, and
until it lands this seam is the honest shape.

DESKTOP CAPTURE NEEDS A DEDICATED DISPLAY. `Robot` photographs the SCREEN, not
the window, so anything overlapping lands in the image (#1104 again). On CI that
is fine — the runner has nothing else on it — but on a developer machine it must
run against a nested display (Xephyr) or it will capture whatever the human is
doing. On Linux CI there is no display at all, so the app must be wrapped in
`xvfb-run`.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

#: The port `TestAutomationServer.kt` binds inside the client, on every platform.
CLIENT_TEST_SERVER_PORT = 9091


class CaptureKind:
    """What to capture. A class rather than an enum so callers can add kinds
    without this module gating them."""

    SCREENSHOT = "screenshot"
    VIDEO = "video"


@dataclass(frozen=True)
class PlatformPorts:
    """Where the host reaches the client, after any forwarding."""

    #: Host port that reaches the client's TestAutomationServer (9091 on-device).
    test_server: int
    #: Host port that reaches the agent's HTTP API (8080 on-device).
    api: int


class Platform(Protocol):
    """One target the shared UI automation can run against.

    Implementations own ONLY transport and capture. A `Scenario` never asks which
    platform it is on — if it needs to, that is a bug in this abstraction, not a
    reason to branch.
    """

    #: Stable identifier used on the CLI (`--platform`) and in artifact names.
    name: str

    @property
    def ports(self) -> PlatformPorts: ...

    async def bring_up(self, args) -> int:
        """Start whatever must exist before the client is reachable. 0 on success."""
        ...

    def capture(self, kind: str, dest: Path) -> Optional[Path]:
        """Capture `kind` to `dest`. Returns the path written, or None if the
        platform cannot capture that kind. Never raises for an unsupported kind —
        a missing screenshot must not fail an otherwise-passing run."""
        ...


#: Capture is REVIEW MATERIAL, never an assertion, so it must never be able to
#: outlive the run. adb can stall when it loses the emulator and simctl when the
#: simulator wedges — and both happen AFTER the scenario has already passed, so an
#: unbounded call turns a green run into a 75-minute timeout. Short, because a
#: screenshot that takes longer than this is not coming.
_CAPTURE_TIMEOUT_SECONDS = 60


def _run(cmd: list[str], timeout: float = _CAPTURE_TIMEOUT_SECONDS, **kw) -> subprocess.CompletedProcess:
    """Run a capture command, never blocking longer than `timeout`.

    A TimeoutExpired is returned as an ordinary non-zero result rather than
    raised, so the caller's existing "capture failed, say why, carry on" path
    handles it like any other failure.
    """
    try:
        return subprocess.run(cmd, capture_output=True, timeout=timeout, **kw)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, b"", f"timed out after {timeout}s".encode())


class DesktopPlatform:
    """Linux, macOS and Windows — the Compose Desktop app.

    Binds 9091 DIRECTLY (no forward), which is why the shared 8091 default is
    wrong here and `_apply_platform_defaults` special-cases it.
    """

    name = "desktop"

    def __init__(self, server_url: str, test_port: int = CLIENT_TEST_SERVER_PORT, api_port: int = 8080):
        self._server_url = server_url.rstrip("/")
        self._ports = PlatformPorts(test_server=test_port, api=api_port)

    @property
    def ports(self) -> PlatformPorts:
        return self._ports

    async def bring_up(self, args) -> int:
        from . import __main__ as web_ui_main

        return await web_ui_main.run_desktop_up(args)

    def capture(self, kind: str, dest: Path) -> Optional[Path]:
        """Ask the app for its own screenshot.

        Uses the client's `/screenshot` rather than an OS screengrab so this works
        identically on all three desktop OSes with no per-OS tooling. It is still
        a whole-screen capture underneath (#1104) — see the module docstring.
        """
        if kind != CaptureKind.SCREENSHOT:
            return None
        try:
            import httpx

            with httpx.Client(timeout=30.0) as client:
                r = client.get(f"{self._server_url}/screenshot")
                if r.status_code != 200 or not r.content:
                    return None
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(r.content)
                return dest
        except Exception:
            # A capture failure must never fail a passing run — the screenshot is
            # review material, not an assertion.
            return None


class AndroidPlatform:
    """An Android emulator or device, reached over `adb forward`."""

    name = "android"

    def __init__(self, serial: Optional[str] = None, test_port: int = 8091, api_port: int = 8080):
        self._serial = serial
        self._ports = PlatformPorts(test_server=test_port, api=api_port)

    @property
    def ports(self) -> PlatformPorts:
        return self._ports

    def _adb(self, *args: str) -> list[str]:
        """Resolve adb the way the rest of this module already does.

        NOT `shutil.which("adb")`. On a GitHub runner adb lives at
        `$ANDROID_SDK_ROOT/platform-tools/adb` and is NOT on PATH, so `which`
        finds nothing and every capture silently produced no screenshot — which
        is exactly what happened on the first green run: the flow passed on
        Android and the gallery had no tile for it.
        """
        from . import __main__ as web_ui_main

        try:
            adb = str(web_ui_main._android_sdk_paths()["adb"])
        except Exception:  # noqa: BLE001
            adb = shutil.which("adb") or "adb"
        cmd = [adb]
        if self._serial:
            cmd += ["-s", self._serial]
        return cmd + list(args)

    async def bring_up(self, args) -> int:
        from . import __main__ as web_ui_main

        return await web_ui_main.run_android_up(args)

    def capture(self, kind: str, dest: Path) -> Optional[Path]:
        if kind != CaptureKind.SCREENSHOT:
            # Video is `adb shell screenrecord`, which is a long-running call with
            # a stop signal — a different lifecycle than a one-shot grab. It
            # belongs here when a scenario needs it, not stubbed in early.
            return None
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            # exec-out streams the PNG straight to stdout: no /sdcard round-trip,
            # so nothing is left behind on the device and there is no pull to fail.
            cmd = self._adb("exec-out", "screencap", "-p")
            out = _run(cmd)
            if out.returncode != 0 or not out.stdout:
                # SAY WHY. "endpoint or tool unavailable" sent the reader looking
                # at the app when the real cause was adb resolution.
                why = (out.stderr or b"").decode(errors="replace")[:160] if isinstance(out.stderr, bytes) else (out.stderr or "")[:160]
                print(f"    android capture failed: {cmd[0]} rc={out.returncode} {why}".rstrip())
                return None
            dest.write_bytes(out.stdout)
            return dest
        except FileNotFoundError:
            print(f"    android capture failed: adb not found at {self._adb()[0]}")
            return None
        except Exception as exc:  # noqa: BLE001
            print(f"    android capture failed: {type(exc).__name__}: {exc}")
            return None


class IOSPlatform:
    """An iOS simulator (CI) or physical device, reached over iproxy.

    The simulator is the CI target: GitHub's macOS runners have no physical
    device, and `simctl` needs no signing identity, no provisioning profile and
    no UDID registration.
    """

    name = "ios"

    def __init__(
        self,
        udid: str = "booted",
        simulator: bool = True,
        test_port: Optional[int] = None,
        api_port: Optional[int] = None,
    ):
        self._udid = udid
        self._simulator = simulator
        # A SIMULATOR NEEDS NO FORWARD. It shares the host's network stack, so a
        # server bound on 9091 inside the app is reachable at localhost:9091 —
        # exactly like desktop. The 18091/18080 convention exists only for
        # PHYSICAL devices, where iproxy tunnels over USB and the offset avoids
        # colliding with a backend running on the host.
        #
        # An earlier version of this class applied the iproxy offset to both,
        # which would have pointed every simulator run at a port nothing listens
        # on and reported it as "the app is not running in test mode" — a failure
        # naming the wrong cause, which is the same trap `_apply_platform_defaults`
        # documents for desktop's 8091-vs-9091.
        default_test = CLIENT_TEST_SERVER_PORT if simulator else 18091
        default_api = 8080 if simulator else 18080
        self._ports = PlatformPorts(
            test_server=test_port or default_test,
            api=api_port or default_api,
        )

    @property
    def ports(self) -> PlatformPorts:
        return self._ports

    async def bring_up(self, args) -> int:
        """Simulator by default; devicectl+iproxy only for a physical device.

        The two paths share almost nothing — a simulator needs no USB tunnel and
        no second UDID namespace — so they are separate functions rather than one
        with a mode flag.
        """
        from . import __main__ as web_ui_main

        if self._simulator:
            return await web_ui_main.run_ios_simulator_up(args)
        return await web_ui_main.run_ios_up(args)

    def capture(self, kind: str, dest: Path) -> Optional[Path]:
        if kind != CaptureKind.SCREENSHOT:
            return None
        if not self._simulator:
            # Physical devices go through pymobiledevice3, which the mobile module
            # already implements (`ios_physical_test_cases.py`). Not duplicated
            # here — CI uses the simulator.
            return None
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            out = _run(["xcrun", "simctl", "io", self._udid, "screenshot", str(dest)])
            return dest if out.returncode == 0 and dest.exists() else None
        except Exception:
            return None


def build_platform(args) -> Platform:
    """Construct the Platform named by `--platform`.

    The ONLY place the automation is allowed to ask what it is running on.
    """
    requested = getattr(args, "platform", None) or "desktop"
    test_port = getattr(args, "desktop_port", None)
    api_port = getattr(args, "api_port", None)

    if requested == "android":
        return AndroidPlatform(
            serial=getattr(args, "android_device", None),
            test_port=test_port or 8091,
            api_port=api_port or 8080,
        )
    if requested == "ios":
        # Pass the ports through UNRESOLVED. IOSPlatform picks the default from
        # simulator-vs-physical, and defaulting them here would override that
        # decision with the physical convention before it is ever made.
        return IOSPlatform(
            udid=getattr(args, "ios_udid", None) or "booted",
            simulator=not getattr(args, "ios_physical", False),
            test_port=test_port,
            api_port=api_port,
        )
    port = test_port or CLIENT_TEST_SERVER_PORT
    return DesktopPlatform(
        server_url=f"http://localhost:{port}",
        test_port=port,
        api_port=api_port or 8080,
    )


__all__ = [
    "CLIENT_TEST_SERVER_PORT",
    "CaptureKind",
    "PlatformPorts",
    "Platform",
    "DesktopPlatform",
    "AndroidPlatform",
    "IOSPlatform",
    "build_platform",
]
