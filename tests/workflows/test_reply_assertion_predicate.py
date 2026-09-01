"""What counts as "the agent replied" — the rule that decides five platforms.

Every case below is a way this assertion has already gone green, or would have,
while the product was silent or broken. A gate is only worth having if it can
fail, and a predicate that accepts an error message is worse than no predicate:
it reports success at the exact moment the product stops working.
"""

from __future__ import annotations

import pytest

from tools.qa_runner.modules.web_ui.__main__ import _is_new_agent_reply

SENT = "Hello, can you hear me?"
REPLY = "Hello! Yes, I can hear you. How can I assist you today?"


def _msg(**kw):
    base = {"id": "m-new", "message_type": "agent", "content": REPLY}
    base.update(kw)
    return base


def test_a_new_agent_row_is_a_reply() -> None:
    assert _is_new_agent_reply(_msg(), set(), SENT)


def test_an_error_row_is_not_a_reply() -> None:
    """THE ONE THAT MATTERED MOST.

    routes/agent.py sets `is_agent = True` for message_type "system" AND "error"
    deliberately, so the agent does not re-observe its own notifications. The
    first version of this assertion keyed on `is_agent`, so the error text
    emitted when processing FAILED counted as proof that it had succeeded — the
    gate going green precisely when the product broke.
    """
    assert not _is_new_agent_reply(_msg(message_type="error"), set(), SENT)


def test_a_system_notification_is_not_a_reply() -> None:
    assert not _is_new_agent_reply(_msg(message_type="system"), set(), SENT)


def test_a_row_from_an_earlier_interaction_is_not_a_reply() -> None:
    """Without a pre-send baseline, "an agent row exists" is trivially true.

    Any prior conversation in the same channel satisfies it, so the gate would
    pass on a send that produced nothing at all.
    """
    assert not _is_new_agent_reply(_msg(id="m-old"), {"m-old"}, SENT)


def test_our_own_echo_is_not_a_reply() -> None:
    assert not _is_new_agent_reply(_msg(content=SENT), set(), SENT)


@pytest.mark.parametrize("content", ["", "   ", None])
def test_an_empty_row_is_not_a_reply(content) -> None:
    assert not _is_new_agent_reply(_msg(content=content), set(), SENT)


def test_a_user_row_is_not_a_reply() -> None:
    assert not _is_new_agent_reply(_msg(message_type="user", content="something else"), set(), SENT)


def test_the_predicate_does_not_key_on_is_agent() -> None:
    """Pin the distinction itself, not just its consequences.

    An error row carries is_agent=True and message_type="error". If someone
    later "simplifies" this back to `is_agent`, this row starts passing and the
    hole reopens silently — so assert the exact shape that would reopen it.
    """
    error_row = _msg(message_type="error", content="I encountered an issue processing your request.")
    error_row["is_agent"] = True
    assert not _is_new_agent_reply(error_row, set(), SENT)


def test_the_history_check_follows_the_configured_backend_port() -> None:
    """`--port 9000` must not leave the assertion talking to 8080.

    Everything else honours --port: the adb forward, the health probe, the app's
    own backend. A hardcoded 8080 here meant the UI could send successfully to
    the configured port while the reply assertion logged into a closed one — or
    worse, an unrelated server that answers, so the check would report on a
    conversation that was never had.
    """
    import argparse

    from tools.qa_runner.modules.web_ui.__main__ import _apply_platform_defaults

    args = argparse.Namespace(
        command="desktop-chat", platform="desktop", port=9000, api_port=None,
        desktop_port=8091, android=False, ios=False, ios_physical=False,
    )
    _apply_platform_defaults(args)
    assert args.api_port == 9000, "the reply assertion would query the wrong backend"


def test_the_port_default_is_unchanged_when_not_given() -> None:
    import argparse

    from tools.qa_runner.modules.web_ui.__main__ import _apply_platform_defaults

    args = argparse.Namespace(
        command="desktop-chat", platform="desktop", port=8080, api_port=None,
        desktop_port=8091, android=False, ios=False, ios_physical=False,
    )
    _apply_platform_defaults(args)
    assert args.api_port == 8080


def test_the_apk_is_built_and_found_in_the_same_tree() -> None:
    """Builder and finder must agree on where the Android app comes from.

    They did not: the finder pointed at apps/android/build/... while the builder
    ran gradle in `client/`, a directory this repo does not contain — so on a
    runner with a booted emulator the bring-up died with FileNotFoundError. And
    the finder looked for `androidApp-debug.apk`, the pre-migration module name,
    while gradle emits `android-debug.apk`.
    """
    from tools.qa_runner.modules.web_ui.__main__ import _apps_root

    apps = _apps_root()
    assert apps.name == "apps", "the app shells live in apps/, not client/"
    assert (apps / "settings.gradle.kts").exists()
    assert (apps / "gradlew").exists(), "no gradle wrapper in the build root"


def test_the_apk_finder_globs_rather_than_hardcoding_a_name() -> None:
    import inspect

    from tools.qa_runner.modules.web_ui import __main__ as m

    src = inspect.getsource(m._find_debug_apk)
    assert "glob" in src
    assert "androidApp-debug.apk" not in src, "that module name predates apps/settings.gradle.kts"
