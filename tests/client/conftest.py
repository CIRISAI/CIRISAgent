"""
Conftest for client/Android tests.

Sets up sys.path to allow importing from the client/androidApp/src/main/python directory.
Creates a mock 'android' package structure for backward compatibility with existing imports.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# Get the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Path to the Python source files in the client directory
PYTHON_SRC_PATH = PROJECT_ROOT / "client" / "androidApp" / "src" / "main" / "python"

# Add the Python source path to sys.path
if str(PYTHON_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC_PATH))

# Create a mock 'android' package hierarchy that points to the real mobile_main
# This allows tests to use the old import style: from android.app.src.main.python import mobile_main
class AndroidModuleMock:
    """Mock android module hierarchy for test imports."""

    class App:
        class Src:
            class Main:
                class Python:
                    pass

    app = App()
    app.src = App.Src()
    app.src.main = App.Src.Main()
    app.src.main.python = App.Src.Main.Python()


# Only create mock if android module doesn't exist
if "android" not in sys.modules:
    android_mock = AndroidModuleMock()
    sys.modules["android"] = android_mock
    sys.modules["android.app"] = android_mock.app
    sys.modules["android.app.src"] = android_mock.app.src
    sys.modules["android.app.src.main"] = android_mock.app.src.main
    sys.modules["android.app.src.main.python"] = android_mock.app.src.main.python

    # Import the actual mobile_main module
    import mobile_main

    # Make it available via the mock path
    sys.modules["android.app.src.main.python.mobile_main"] = mobile_main
    android_mock.app.src.main.python.mobile_main = mobile_main
