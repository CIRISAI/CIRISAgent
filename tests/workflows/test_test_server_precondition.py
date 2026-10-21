"""Bring-up must assert exactly what the flow that follows it requires.

The Android gate reported, three lines apart:

    [OK] AndroidTestAutomationServer reachable at http://localhost:8091
    [FAIL] CIRIS Desktop app is not running with test mode enabled.

Both about the same URL, in the same process, seconds apart. Bring-up checked
`status == "ok"`; the very next step checked `status == "ok" AND testMode`. A
precondition looser than its consumer's is not a check — it is a false green
that moves the failure somewhere it cannot be explained, and the message it
lands in named the DESKTOP app on an Android run.
"""

from __future__ import annotations

import asyncio
import inspect

from tools.qa_runner.modules.web_ui import __main__ as m
from tools.qa_runner.modules.web_ui.desktop_app_helper import (
    check_desktop_app_running,
    describe_test_server,
)


def test_bring_up_requires_test_mode_like_its_consumer() -> None:
    src = inspect.getsource(m.run_android_up)
    assert 'payload.get("testMode", False)' in src, (
        "android bring-up accepts a server that the next step will reject"
    )


def test_the_consumer_still_requires_it_too() -> None:
    src = inspect.getsource(check_desktop_app_running)
    assert 'data.get("testMode", False)' in src


def test_an_unreachable_server_is_described_as_such() -> None:
    msg = asyncio.run(describe_test_server("http://localhost:59999"))
    assert "nothing answered" in msg
    assert "59999" in msg, "the message must name the port it tried"


def test_the_failure_message_is_platform_specific() -> None:
    """An Android run must not be told to start the desktop app.

    The old message hard-coded desktop instructions — and pointed at a `client/`
    gradle module this repo no longer contains — for every platform.
    """
    src = inspect.getsource(m.run_desktop_tests)
    assert 'platform == "android"' in src
    assert 'platform == "ios"' in src
    assert "cd client && ./gradlew :desktopApp:run" not in src, "stale, and desktop-only"
