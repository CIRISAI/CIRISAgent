"""The desktop JAR must be launched with BOTH backend names pointed at the brain.

ciris-client >= 0.5.213 builds its ordinary API client from CIRIS_NODE_URL and
ignores CIRIS_API_URL there. A launcher that sets only CIRIS_API_URL points the
whole UI at the bare node on :4243 -- "Add provider" 404s, list-models 404s.
"""

import importlib

from ciris_engine import desktop_launcher


def test_both_names_point_at_the_brain_by_default():
    env = desktop_launcher.desktop_app_env("http://localhost:8080", base={})
    assert env["CIRIS_API_URL"] == "http://localhost:8080"
    assert env["CIRIS_NODE_URL"] == "http://localhost:8080"


def test_an_explicit_node_url_is_honoured_verbatim():
    """An operator attached to someone else's node (CIRISClient#26) keeps it."""
    env = desktop_launcher.desktop_app_env("http://localhost:8080", base={"CIRIS_NODE_URL": "http://10.0.0.7:4243"})
    assert env["CIRIS_API_URL"] == "http://localhost:8080"
    assert env["CIRIS_NODE_URL"] == "http://10.0.0.7:4243"


def test_blank_node_url_does_not_count_as_explicit():
    env = desktop_launcher.desktop_app_env("http://localhost:8080", base={"CIRIS_NODE_URL": "  "})
    assert env["CIRIS_NODE_URL"] == "http://localhost:8080"


def test_process_environment_is_inherited_not_replaced():
    env = desktop_launcher.desktop_app_env("http://localhost:8080", base={"PATH": "/x", "JAVA_HOME": "/j"})
    assert env["PATH"] == "/x" and env["JAVA_HOME"] == "/j"


def test_qa_harness_launches_with_the_same_urls_as_the_product(monkeypatch):
    """The gate must exercise the environment users get. This is the parity the
    first real desktop user found missing."""
    monkeypatch.delenv("CIRIS_DESKTOP_API_URL", raising=False)
    monkeypatch.delenv("CIRIS_DESKTOP_NODE_URL", raising=False)
    monkeypatch.delenv("CIRIS_NODE_URL", raising=False)
    web_ui = importlib.import_module("tools.qa_runner.modules.web_ui.__main__")
    api, node = web_ui._desktop_urls("http://localhost:8080")
    env = desktop_launcher.desktop_app_env("http://localhost:8080", base={})
    assert (api, node) == (env["CIRIS_API_URL"], env["CIRIS_NODE_URL"])
