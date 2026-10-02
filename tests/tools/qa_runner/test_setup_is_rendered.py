"""The harness only accepts the Setup wizard once it is actually rendered (CIRISClient#149).

On iOS after a device reset the client reported screen 'Setup' while the Startup
splash -- with an EMPTY element tree -- was still what was on screen. Waiting on
the name alone passed in 535 ms and the run then failed one step later on a
misleading "age_band_adult not found".
"""

import inspect

from tools.qa_runner.modules.web_ui import __main__ as web_ui
from tools.qa_runner.modules.web_ui.__main__ import setup_is_rendered


def test_named_setup_with_nothing_composed_is_not_rendered():
    assert setup_is_rendered("Setup", []) is False


def test_named_setup_with_elements_is_rendered():
    assert setup_is_rendered("Setup", [object()]) is True


def test_other_screens_never_count():
    assert setup_is_rendered("Startup", [object()]) is False
    assert setup_is_rendered("Login", [object(), object()]) is False


def test_the_setup_wait_uses_the_rendered_check():
    """Guard: the wait must not go back to trusting the screen name alone."""
    src = inspect.getsource(web_ui)
    wait = src[src.index("async def wait_for_setup()") : src.index('await self.run_test("wait_for_setup_wizard"')]
    assert "setup_is_rendered(screen, await self.helper.get_elements())" in wait
    assert 'if screen == "Setup":\n                    return' not in wait
