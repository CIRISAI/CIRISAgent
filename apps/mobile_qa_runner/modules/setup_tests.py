"""
Setup wizard tests - bridges to main QA runner's setup module.

The main QA runner (tools/qa_runner) has comprehensive setup tests.
This module provides mobile-specific wrappers and the bridge connection.
"""

import sys
from pathlib import Path

# Add main project to path for importing QA runner
_project_root = Path(__file__).parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


class SetupTestModule:
    """
    Bridge to main QA runner's setup test module.

    The main QA runner has these setup tests:
    - Get setup status (/v1/setup/status)
    - List LLM providers (/v1/setup/providers)
    - List agent templates (/v1/setup/templates)
    - List available adapters (/v1/setup/adapters)
    - Validate LLM configuration (/v1/setup/validate-llm)
    - Complete setup (/v1/setup/complete)
    - Login as created user (/v1/auth/login)

    All endpoints are unauthenticated during first-run mode.
    """

    @staticmethod
    def get_main_qa_setup_tests():
        """Import and return tests from main QA runner."""
        try:
            from tools.qa_runner.modules.setup_tests import SetupTestModule as MainSetupModule

            return MainSetupModule.get_setup_tests()
        except ImportError as e:
            print(f"Warning: Cannot import main QA runner: {e}")
            return []

    @staticmethod
    def run_via_bridge(bridge, module: str = "setup") -> bool:
        """
        Run setup tests via the emulator bridge.

        Args:
            bridge: EmulatorBridge instance
            module: Module name to run (default: "setup")

        Returns:
            True if all tests passed
        """
        success, message = bridge.run_qa_module(module)
        print(f"Setup tests: {'PASSED' if success else 'FAILED'} - {message}")
        return success
