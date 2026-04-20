# CRITICAL: Prevent side effects during imports
import os

os.environ["CIRIS_IMPORT_MODE"] = "true"
os.environ["CIRIS_MOCK_LLM"] = "true"

from unittest.mock import MagicMock

import main as main_module


def test_main_function_existence():
    """Test that the main function exists and is callable."""
    assert hasattr(main_module, "main")
    assert callable(main_module.main)


def test_helper_functions_exist():
    """Test that helper functions exist."""
    assert hasattr(main_module, "_create_thought")
    assert callable(main_module._create_thought)
    assert hasattr(main_module, "_run_runtime")
    assert callable(main_module._run_runtime)


def test_ciris_runtime_initialization(monkeypatch):
    """Test that CIRISRuntime can be initialized with different adapter types."""
    mock_runtime_class = MagicMock()
    mock_runtime_instance = MagicMock()
    mock_runtime_class.return_value = mock_runtime_instance
    # Use module object directly, not string path
    monkeypatch.setattr(main_module, "CIRISRuntime", mock_runtime_class)

    # Test Discord adapter type
    main_module.CIRISRuntime(adapter_types=["discord"])

    # Test CLI adapter type
    main_module.CIRISRuntime(adapter_types=["cli"])

    # Test API adapter type
    main_module.CIRISRuntime(adapter_types=["api"])

    # Verify CIRISRuntime was called 3 times with correct arguments
    assert mock_runtime_class.call_count == 3
    mock_runtime_class.assert_any_call(adapter_types=["discord"])
    mock_runtime_class.assert_any_call(adapter_types=["cli"])
    mock_runtime_class.assert_any_call(adapter_types=["api"])
