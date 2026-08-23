"""How hosted tools finds the OAuth token it authenticates with.

Hosted tool calls and tool-balance requests carry the same OAuth ID token as
billing and the LLM proxy. When this method disagreed with the others about
which variable that token lives in, tool requests went on using the stale
setup-time credential after a client refresh had already revived the rest of
the agent — the same outage, in the one subsystem nobody thought to check.

So the property under test is agreement, not mechanism: whatever the shared
selector would choose, from the environment or from the `.env` file, is what
these requests must carry.
"""

from __future__ import annotations

import base64
import json
import time

import pytest

PROXY_VARS = (
    "CIRIS_BILLING_GOOGLE_ID_TOKEN",
    "CIRIS_BILLING_APPLE_ID_TOKEN",
    "CIRIS_BILLING_OAUTH_TOKEN",
)


def jwt(exp_offset_seconds: float) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": time.time() + exp_offset_seconds}).encode())
        .decode()
        .rstrip("=")
    )
    return f"header.{payload}.signature"


@pytest.fixture
def service():
    from ciris_adapters.ciris_hosted_tools.services import CIRISHostedToolService

    return CIRISHostedToolService.__new__(CIRISHostedToolService)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for var in PROXY_VARS + ("GOOGLE_ID_TOKEN",):
        monkeypatch.delenv(var, raising=False)
    # Point the .env search at an empty directory so the file branch cannot
    # pick up a developer's real token during the environment-only cases.
    monkeypatch.setenv("CIRIS_HOME", str(tmp_path))
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    return tmp_path


class TestFromTheEnvironment:
    @pytest.mark.parametrize("var", PROXY_VARS)
    def test_any_name_the_selector_knows_is_accepted(self, service, monkeypatch, var):
        monkeypatch.setenv(var, "the-token")
        assert service._get_google_id_token() == "the-token"

    def test_the_freshest_wins_when_several_are_present(self, service, monkeypatch):
        fresh, stale = jwt(3600), jwt(-600)
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", stale)
        monkeypatch.setenv("CIRIS_BILLING_OAUTH_TOKEN", fresh)
        assert service._get_google_id_token() == fresh

    def test_the_legacy_variable_still_works(self, service, monkeypatch):
        monkeypatch.setenv("GOOGLE_ID_TOKEN", "legacy-token")
        assert service._get_google_id_token() == "legacy-token"

    def test_nothing_anywhere_is_None_not_an_exception(self, service):
        assert service._get_google_id_token() is None


class TestFromTheEnvFile:
    """The path that exists because the client rewrites .env after we started."""

    def test_a_refreshed_token_is_read_back_from_the_file(self, service, clean_env):
        (clean_env / ".env").write_text('CIRIS_BILLING_GOOGLE_ID_TOKEN="from-the-file"\n')
        assert service._get_google_id_token() == "from-the-file"

    def test_the_legacy_desktop_name_is_read_back_too(self, service, clean_env):
        """The exact stranding case: the client wrote its refresh into this
        file under its own name, and the scan used to walk past it."""
        (clean_env / ".env").write_text("CIRIS_BILLING_OAUTH_TOKEN=refreshed-by-legacy-desktop\n")
        assert service._get_google_id_token() == "refreshed-by-legacy-desktop"

    def test_the_file_is_ranked_the_same_way_as_the_environment(self, service, clean_env):
        fresh, stale = jwt(3600), jwt(-600)
        (clean_env / ".env").write_text(
            f"CIRIS_BILLING_GOOGLE_ID_TOKEN={stale}\nCIRIS_BILLING_OAUTH_TOKEN={fresh}\n"
        )
        assert service._get_google_id_token() == fresh

    def test_single_quoted_values_are_unwrapped(self, service, clean_env):
        (clean_env / ".env").write_text("CIRIS_BILLING_GOOGLE_ID_TOKEN='quoted-token'\n")
        assert service._get_google_id_token() == "quoted-token"

    def test_an_empty_assignment_is_not_a_token(self, service, clean_env):
        (clean_env / ".env").write_text('CIRIS_BILLING_GOOGLE_ID_TOKEN=""\n')
        assert service._get_google_id_token() is None

    def test_the_environment_beats_the_file(self, service, clean_env, monkeypatch):
        (clean_env / ".env").write_text("CIRIS_BILLING_GOOGLE_ID_TOKEN=from-file\n")
        monkeypatch.setenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "from-env")
        assert service._get_google_id_token() == "from-env"
