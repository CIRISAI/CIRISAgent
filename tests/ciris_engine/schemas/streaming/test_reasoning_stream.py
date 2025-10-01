"""
Unit tests for reasoning stream schemas.

NOTE: These tests are currently disabled as they test the deprecated 11-step streaming system.
The new simplified 5-event reasoning stream uses different schemas and patterns.
Tests for the new system are in tests/ciris_engine/logic/infrastructure/test_step_streaming.py
"""

import pytest

# Skip all tests in this file - testing deprecated functionality
pytestmark = pytest.mark.skip(reason="Tests for deprecated 11-step streaming system - replaced with 5-event system")
