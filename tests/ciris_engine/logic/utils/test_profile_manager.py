import importlib
import logging

def test_importing_profile_manager_logs_deprecation_warning(caplog):
    """
    Tests that importing the deprecated profile_manager module logs a warning.
    """
    # The module is already imported by the test runner, so we need to reload it
    # to trigger the top-level warning log again.
    from ciris_engine.logic.utils import profile_manager

    with caplog.at_level(logging.WARNING):
        importlib.reload(profile_manager)

    assert len(caplog.records) > 0
    assert "profile_manager.py is deprecated" in caplog.text
    assert "graph-based identity system" in caplog.text
