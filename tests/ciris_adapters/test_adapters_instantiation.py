"""Tests to verify adapters can be instantiated without NameErrors."""

import pytest
from ciris_adapters.clawdbot_1password.service import OnepasswordToolService
from ciris_adapters.clawdbot_github.service import GithubToolService

def test_instantiate_adapters():
    """Test that adapters can be instantiated and _build_tool_info called."""
    # Test 1Password
    op_service = OnepasswordToolService()
    op_info = op_service._build_tool_info()
    assert op_info.name == "1password"
    assert op_info.documentation is not None

    # Test GitHub
    gh_service = GithubToolService()
    gh_info = gh_service._build_tool_info()
    assert gh_info.name == "github"
    assert gh_info.documentation is not None
