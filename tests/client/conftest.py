"""
Conftest for client/Android tests.

Sets up sys.path to allow importing from the client/androidApp/src/main/python directory.
Creates a mock 'android' package structure for backward compatibility with existing imports.
"""

import importlib.util
import sys
from pathlib import Path

# Get the project root
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Path to the Python source files in the client directory
PYTHON_SRC_PATH = PROJECT_ROOT / "client" / "androidApp" / "src" / "main" / "python"

# Add the Python source path to sys.path (at the FRONT to override system modules)
if str(PYTHON_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(PYTHON_SRC_PATH))


def _load_module_from_path(name: str, path: Path):
    """Load a module from a specific file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Create a mock 'android' package hierarchy that points to the real modules
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

    # Load mobile_main from our Android Python source (uses path resolution from ciris_engine)
    mobile_main_path = PYTHON_SRC_PATH / "mobile_main.py"
    if mobile_main_path.exists():
        mobile_main = _load_module_from_path("mobile_main", mobile_main_path)
        if mobile_main:
            sys.modules["android.app.src.main.python.mobile_main"] = mobile_main
            android_mock.app.src.main.python.mobile_main = mobile_main

    # Load our custom Android psutil stub (NOT the system psutil!)
    android_psutil_path = PYTHON_SRC_PATH / "psutil.py"
    if android_psutil_path.exists():
        android_psutil = _load_module_from_path("android_psutil", android_psutil_path)
        if android_psutil:
            sys.modules["android.app.src.main.python.psutil"] = android_psutil
            android_mock.app.src.main.python.psutil = android_psutil
