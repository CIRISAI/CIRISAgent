"""
Android on-device entrypoint for CIRIS.

This module starts the full CIRIS runtime on-device with the API adapter,
with all LLM calls routed to a remote OpenAI-compatible endpoint.

Architecture:
- Python runtime: On-device (via Chaquopy)
- CIRIS Runtime: Full 22 services + agent processor
- FastAPI server: On-device (localhost:8080)
- Web UI: On-device (bundled assets)
- LLM provider: Remote (OpenAI-compatible endpoint)
- Database: On-device SQLite
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Constants to avoid string duplication (SonarCloud S1192)
PYDANTIC_CORE_SO_PATTERN = "_pydantic_core*.so"
CHAQUOPY_BASE_PATH = "/data/data/ai.ciris.mobile/files/chaquopy"
ANDROID_PACKAGE_NAME = "ai.ciris.mobile"

# Configure logging for Android (logcat-friendly)
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(name)s: %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


# =============================================================================
# PYDANTIC_CORE NATIVE LIBRARY LOADER
# =============================================================================
# Chaquopy's extractPackages directive isn't extracting the .so file from .imy
# archives in Python 3.10. This workaround manually extracts and loads it.
#
# ROOT CAUSE: Chaquopy serves packages from .imy (zip) files via AssetFinder,
# but native .so files require real filesystem paths for dlopen(). Additionally,
# Chaquopy's AssetFinder uses sys.meta_path hooks that take precedence over
# sys.path, so we must install our own finder BEFORE AssetFinder.
#
# SYMPTOMS:
#   - "No module named 'pydantic_core._pydantic_core'"
#   - extract-packages directory is empty/missing
#   - pydantic_core found in AssetFinder but .so won't load
#   - ctypes.CDLL succeeds but import fails (AssetFinder interference)
#
# FIX: Extract to filesystem, install meta_path finder BEFORE AssetFinder
# =============================================================================


class PydanticCoreFinder:
    """
    Custom finder that intercepts ALL pydantic_core imports BEFORE Chaquopy's AssetFinder.
    This ensures Python loads from our extracted location, including native extensions.

    Chaquopy's AssetFinder intercepts imports before PathFinder checks sys.path,
    so we must handle both .py files AND native extensions (.so files) ourselves.
    """

    def __init__(self, extract_path: str):
        self.extract_path = extract_path
        self.pydantic_core_dir = os.path.join(extract_path, "pydantic_core")
        # Find the .so file pattern for this platform
        import glob

        so_files = glob.glob(os.path.join(self.pydantic_core_dir, PYDANTIC_CORE_SO_PATTERN))
        self.so_path = so_files[0] if so_files else None

    def find_module(self, fullname, path=None):
        """Return self for all pydantic_core imports."""
        if not fullname.startswith("pydantic_core"):
            return None

        if fullname == "pydantic_core":
            init_path = os.path.join(self.pydantic_core_dir, "__init__.py")
            return self if os.path.exists(init_path) else None

        # For submodules
        parts = fullname.split(".")
        rel_name = parts[-1]

        # Handle native extension (_pydantic_core)
        if rel_name == "_pydantic_core" and self.so_path:
            return self

        # Handle .py files
        py_path = os.path.join(self.pydantic_core_dir, rel_name + ".py")
        return self if os.path.exists(py_path) else None

    def load_module(self, fullname):
        """Load pydantic_core module from our extracted location."""
        import importlib.machinery
        import importlib.util

        if fullname in sys.modules:
            return sys.modules[fullname]

        parts = fullname.split(".")
        rel_name = parts[-1] if len(parts) > 1 else None

        # Handle the main pydantic_core package
        if fullname == "pydantic_core":
            module_path = os.path.join(self.pydantic_core_dir, "__init__.py")
            spec = importlib.util.spec_from_file_location(
                fullname, module_path, submodule_search_locations=[self.pydantic_core_dir]
            )
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            spec.loader.exec_module(module)
            return module

        # Handle native extension
        if rel_name == "_pydantic_core" and self.so_path:
            loader = importlib.machinery.ExtensionFileLoader(fullname, self.so_path)
            spec = importlib.util.spec_from_loader(fullname, loader, origin=self.so_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            spec.loader.exec_module(module)
            return module

        # Handle .py submodules
        module_path = os.path.join(self.pydantic_core_dir, rel_name + ".py")
        if os.path.exists(module_path):
            spec = importlib.util.spec_from_file_location(fullname, module_path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = module
            spec.loader.exec_module(module)
            return module

        raise ImportError(f"PydanticCoreFinder: {fullname} not found")


# =============================================================================
# SETUP HELPER FUNCTIONS (extracted for cognitive complexity reduction)
# =============================================================================


def _detect_architecture() -> str:
    """Detect the Android CPU architecture.

    Returns one of: 'arm64-v8a', 'armeabi-v7a', 'x86_64'
    """
    import platform

    machine = platform.machine().lower()
    if "aarch64" in machine or "arm64" in machine:
        return "arm64-v8a"
    if "armv7" in machine or "arm" in machine:
        return "armeabi-v7a"
    return "x86_64"


def _find_existing_so(pydantic_core_dir: Path) -> Optional[str]:
    """Find an existing pydantic_core .so file.

    Returns the path to the .so file or None if not found.
    """
    import glob

    so_pattern = str(pydantic_core_dir / PYDANTIC_CORE_SO_PATTERN)
    existing_so = glob.glob(so_pattern)
    return existing_so[0] if existing_so else None


def _clear_pydantic_modules() -> List[str]:
    """Remove any cached pydantic_core modules from sys.modules.

    Returns the list of modules that were removed.
    """
    modules_to_remove = [k for k in sys.modules.keys() if k.startswith("pydantic_core")]
    for mod in modules_to_remove:
        del sys.modules[mod]
    return modules_to_remove


def _configure_import_system(extract_path: str) -> None:
    """Configure sys.path and sys.meta_path for pydantic_core loading."""
    # Add our path FIRST in sys.path
    if extract_path in sys.path:
        sys.path.remove(extract_path)
    sys.path.insert(0, extract_path)

    # Install our finder FIRST in sys.meta_path (before AssetFinder)
    our_finder = PydanticCoreFinder(extract_path)

    # Remove any existing PydanticCoreFinder
    sys.meta_path = [f for f in sys.meta_path if not isinstance(f, PydanticCoreFinder)]
    sys.meta_path.insert(0, our_finder)


def _test_ctypes_load(so_path: str) -> bool:
    """Test loading the native library with ctypes.

    Returns True if successful, False otherwise.
    """
    import ctypes

    try:
        ctypes.CDLL(so_path)
        print("[6/6] ctypes.CDLL: SUCCESS")
        return True
    except OSError as e:
        print(f"[6/6] ctypes.CDLL: FAILED - {e}")
        _print_ctypes_failure_diagnosis()
        return False


def _print_ctypes_failure_diagnosis() -> None:
    """Print diagnosis information for ctypes load failure."""
    print("=" * 60)
    print("DIAGNOSIS: The .so file exists but cannot be loaded.")
    print("Possible causes:")
    print("  - Missing dependency libraries")
    print("  - ABI mismatch (wrong Python version or architecture)")
    print("  - SELinux blocking execution from app data dir")
    print("=" * 60)


def _test_python_import() -> bool:
    """Test importing pydantic_core via Python.

    Returns True if successful, False otherwise.
    """
    try:
        import pydantic_core

        print(f"[6/6] import pydantic_core: SUCCESS (v{pydantic_core.__version__})")
        print(f"[6/6] Location: {pydantic_core.__file__}")
        print("=" * 60)
        print("PYDANTIC_CORE READY")
        print("=" * 60)
        return True
    except ImportError as e:
        print(f"[6/6] import pydantic_core: FAILED - {e}")
        return False


def _print_import_failure_debug(extract_path: str) -> None:
    """Print debug information when Python import fails."""
    print("=" * 60)
    print("DIAGNOSIS: ctypes loaded .so but Python import failed.")
    print("This may be an import path or meta_path issue.")
    print(f"sys.path[0:3]: {sys.path[0:3]}")
    print(f"sys.meta_path[0:3]: {[type(f).__name__ for f in sys.meta_path[0:3]]}")

    # Extra debug: list what's in our extract dir
    print(f"Contents of {extract_path}:")
    _print_extract_dir_contents(extract_path)
    print("=" * 60)


def _print_extract_dir_contents(extract_path: str) -> None:
    """Print contents of the extract directory for debugging."""
    for item in os.listdir(extract_path):
        item_path = os.path.join(extract_path, item)
        if os.path.isdir(item_path):
            print(f"  {item}/")
            for sub in os.listdir(item_path)[:5]:
                print(f"    {sub}")
        else:
            print(f"  {item}")


def setup_pydantic_core() -> bool:
    """
    Extract and load pydantic_core native library for Android.

    Returns True if pydantic_core is ready to use, False otherwise.
    """
    import platform

    print("=" * 60)
    print("PYDANTIC_CORE NATIVE LIBRARY SETUP")
    print("=" * 60)

    # Step 1: Detect architecture
    arch = _detect_architecture()
    print(f"[1/6] Architecture: {arch} (machine={platform.machine().lower()})")

    # Step 2: Define paths - use Chaquopy's expected extract-packages location
    chaquopy_base = Path(CHAQUOPY_BASE_PATH)
    extract_dir = chaquopy_base / "extract-packages"
    pydantic_core_dir = extract_dir / "pydantic_core"
    print(f"[2/6] Extract target: {extract_dir}")

    # Step 3: Check if already extracted
    so_path = _find_existing_so(pydantic_core_dir)
    if so_path:
        print(f"[3/6] Found existing .so: {Path(so_path).name}")
    else:
        print("[3/6] No existing .so found, extracting from .imy...")
        so_path = _extract_from_imy(arch, chaquopy_base.parent, extract_dir)
        if not so_path:
            print("[FAILED] Could not extract pydantic_core from .imy")
            return False

    # Step 4: Remove any cached pydantic_core modules
    modules_removed = _clear_pydantic_modules()
    if modules_removed:
        for mod in modules_removed:
            print(f"[4/6] Cleared cached module: {mod}")
    else:
        print("[4/6] No cached modules to clear")

    # Step 5: Configure import system
    extract_path = str(extract_dir)
    _configure_import_system(extract_path)
    print(f"[5/6] sys.path[0] = {extract_path}")
    print("[5/6] Installed PydanticCoreFinder at meta_path[0]")

    # Step 6: Test loading the native library
    print("[6/6] Testing native library load...")

    if not _test_ctypes_load(so_path):
        return False

    if _test_python_import():
        return True

    _print_import_failure_debug(extract_path)
    return False


def _extract_from_imy(arch: str, data_dir: Path, extract_dir: Path) -> str:
    """Extract pydantic_core from .imy asset to filesystem."""
    import glob
    import zipfile

    try:
        from java import jclass

        # Get Android context
        ActivityThread = jclass("android.app.ActivityThread")
        context = ActivityThread.currentApplication()

        if context is None:
            print("    ActivityThread.currentApplication() returned None")
            return ""

        # Get AssetManager and read .imy
        asset_manager = context.getAssets()
        imy_asset_path = f"chaquopy/requirements-{arch}.imy"
        print(f"    Opening: {imy_asset_path}")

        input_stream = asset_manager.open(imy_asset_path)

        # Read all bytes
        from java.io import ByteArrayOutputStream

        buffer = bytearray(8192)
        baos = ByteArrayOutputStream()

        while True:
            bytes_read = input_stream.read(buffer)
            if bytes_read == -1:
                break
            baos.write(buffer, 0, bytes_read)

        input_stream.close()
        imy_bytes = bytes(baos.toByteArray())
        baos.close()

        print(f"    Read {len(imy_bytes):,} bytes from .imy")

        # Write to temp file
        temp_imy = data_dir / f"temp_requirements_{arch}.imy"
        with open(temp_imy, "wb") as f:
            f.write(imy_bytes)

        # Extract pydantic_core to the extract directory
        extract_dir.mkdir(parents=True, exist_ok=True)
        extracted_files = []

        with zipfile.ZipFile(temp_imy, "r") as zf:
            for name in zf.namelist():
                if name.startswith("pydantic_core/"):
                    zf.extract(name, extract_dir)
                    extracted_files.append(name)

        # Clean up temp file
        temp_imy.unlink()

        print(f"    Extracted {len(extracted_files)} files")

        # Find the .so file
        so_files = glob.glob(str(extract_dir / "pydantic_core" / PYDANTIC_CORE_SO_PATTERN))
        if so_files:
            so_path = so_files[0]
            so_size = Path(so_path).stat().st_size
            print(f"    Found: {Path(so_path).name} ({so_size:,} bytes)")
            return so_path
        else:
            print("    ERROR: No .so file found after extraction!")
            for f in extracted_files:
                print(f"      - {f}")
            return ""

    except Exception as e:
        print(f"    Extraction error: {e}")
        import traceback

        traceback.print_exc()
        return ""


# Run setup before any pydantic imports
_pydantic_ready = False
try:
    _pydantic_ready = setup_pydantic_core()
except Exception as e:
    print(f"PYDANTIC_CORE SETUP ERROR: {e}")
    import traceback

    traceback.print_exc()

if not _pydantic_ready:
    print("")
    print("!" * 60)
    print("WARNING: pydantic_core native library not loaded!")
    print("CIRIS will fail to start. Check the logs above for diagnosis.")
    print("!" * 60)
    print("")


# =============================================================================
# DEBUG HELPER FUNCTIONS (extracted for cognitive complexity reduction)
# =============================================================================


def _debug_print_sys_path() -> None:
    """Print all sys.path entries for debugging."""
    print("DEBUG: sys.path entries:")
    for i, p in enumerate(sys.path):
        print(f"  [{i}] {p}")


def _debug_check_arch_requirements(asset_finder: Path) -> None:
    """Check architecture-specific requirements directories."""
    for arch in ["arm64-v8a", "armeabi-v7a", "x86_64"]:
        arch_reqs = asset_finder / f"requirements-{arch}"
        if arch_reqs.exists():
            print(f"DEBUG: Found arch-specific requirements: {arch_reqs}")
            _debug_print_pydantic_core_contents(arch_reqs / "pydantic_core", arch)


def _debug_print_pydantic_core_contents(pcore: Path, arch: str) -> None:
    """Print contents of a pydantic_core directory."""
    if not pcore.exists():
        return
    print(f"DEBUG: pydantic_core in {arch}:")
    for f in pcore.iterdir():
        size_info = f.stat().st_size if f.is_file() else "dir"
        print(f"    - {f.name} ({size_info})")


def _debug_check_extract_packages(extract_dir: Path) -> None:
    """Check the extract-packages directory."""
    if extract_dir.exists():
        print(f"DEBUG: extract-packages exists: {extract_dir}")
        for item in extract_dir.rglob("*"):
            print(f"    - {item}")
    else:
        print(f"DEBUG: extract-packages directory MISSING: {extract_dir}")


def _debug_check_user_data_location() -> None:
    """Check alternative user data location for pydantic files."""
    user_data = Path(f"/data/user/0/{ANDROID_PACKAGE_NAME}/files/chaquopy")
    if not user_data.exists():
        return
    print(f"DEBUG: user_data chaquopy exists: {user_data}")
    for subdir in user_data.iterdir():
        print(f"  - {subdir.name}")
        if "extract" in subdir.name.lower() or "native" in subdir.name.lower():
            _debug_find_pydantic_in_subdir(subdir)


def _debug_find_pydantic_in_subdir(subdir: Path) -> None:
    """Find pydantic files in a subdirectory."""
    for item in subdir.rglob("*pydantic*"):
        print(f"    pydantic found: {item}")


def _debug_check_importlib_spec() -> None:
    """Check if pydantic_core can be found via importlib."""
    import importlib.util

    spec = importlib.util.find_spec("pydantic_core")
    if not spec:
        print("DEBUG: pydantic_core not found by importlib")
        return

    print(f"DEBUG: pydantic_core found at: {spec.origin}")
    print(f"DEBUG: pydantic_core submodule_search_locations: {spec.submodule_search_locations}")

    if spec.submodule_search_locations:
        _debug_print_spec_locations(spec.submodule_search_locations)


def _debug_print_spec_locations(locations: List[str]) -> None:
    """Print contents of spec submodule search locations."""
    for loc in locations:
        loc_path = Path(loc)
        if loc_path.exists():
            print(f"DEBUG: Contents of {loc}:")
            for f in loc_path.iterdir():
                size_info = f.stat().st_size if f.is_file() else "dir"
                print(f"  - {f.name} ({size_info})")


def _debug_list_chaquopy_subdirs(chaquopy_base: Path) -> None:
    """List all subdirectories in chaquopy base."""
    if not chaquopy_base.exists():
        return
    print("DEBUG: All chaquopy subdirs:")
    for subdir in chaquopy_base.iterdir():
        print(f"  - {subdir.name}")


# Legacy debug function (kept for reference)
def debug_pydantic_core() -> None:
    """Debug function to check pydantic_core loading issues.

    Refactored to use helper functions for reduced cognitive complexity.
    """
    _debug_print_sys_path()

    # Check architecture-specific requirements paths
    chaquopy_base = Path(CHAQUOPY_BASE_PATH)
    asset_finder = chaquopy_base / "AssetFinder"
    _debug_check_arch_requirements(asset_finder)

    # Check for extract-packages directory
    extract_dir = chaquopy_base / "extract-packages"
    _debug_check_extract_packages(extract_dir)

    # Check alternative locations
    _debug_check_user_data_location()

    # Try to find pydantic_core via importlib
    _debug_check_importlib_spec()

    # List ALL chaquopy subdirs
    _debug_list_chaquopy_subdirs(chaquopy_base)


# Note: debug_pydantic_core() is kept for manual debugging but not called automatically
# The new setup_pydantic_core() handles everything with clear logging


def setup_android_environment():
    """Configure environment for Android on-device operation.

    Sets up CIRIS_HOME and loads .env if present.
    First-run detection is handled by is_first_run() which is Android-aware.
    """
    from dotenv import load_dotenv

    if "ANDROID_DATA" not in os.environ:
        logger.warning("ANDROID_DATA not set - not running on Android?")
        return

    # Running on Android device
    android_data = Path(os.environ["ANDROID_DATA"])
    app_data = android_data / "data" / "ai.ciris.mobile"

    # Ensure directories exist
    ciris_home = app_data / "files" / "ciris"
    ciris_home.mkdir(parents=True, exist_ok=True)
    (ciris_home / "databases").mkdir(parents=True, exist_ok=True)
    (ciris_home / "logs").mkdir(parents=True, exist_ok=True)

    # Configure CIRIS environment - use standard paths
    # CIRIS_HOME is used by path_resolution.py for Android-aware path detection
    os.environ.setdefault("CIRIS_HOME", str(ciris_home))
    os.environ.setdefault("CIRIS_DATA_DIR", str(ciris_home))
    os.environ.setdefault("CIRIS_DB_PATH", str(ciris_home / "databases" / "ciris.db"))
    os.environ.setdefault("CIRIS_LOG_DIR", str(ciris_home / "logs"))

    # Load .env file if it exists (sets OPENAI_API_KEY, OPENAI_API_BASE, etc.)
    # First-run detection is handled by is_first_run() - don't duplicate logic here
    env_file = ciris_home / ".env"
    if env_file.exists():
        logger.info(f"Loading configuration from {env_file}")
        load_dotenv(env_file, override=True)
        logger.info(f"Loaded .env - OPENAI_API_KEY set: {bool(os.environ.get('OPENAI_API_KEY'))}")
        logger.info(f"Loaded .env - OPENAI_API_BASE: {os.environ.get('OPENAI_API_BASE', 'NOT SET')}")
    else:
        logger.info(f"No .env file at {env_file} - is_first_run() will detect this")

    # Disable ciris.ai cloud components
    os.environ["CIRIS_OFFLINE_MODE"] = "true"
    os.environ["CIRIS_CLOUD_SYNC"] = "false"

    # Optimize for low-resource devices
    os.environ.setdefault("CIRIS_MAX_WORKERS", "1")
    os.environ.setdefault("CIRIS_LOG_LEVEL", "INFO")
    os.environ.setdefault("CIRIS_API_HOST", "127.0.0.1")
    os.environ.setdefault("CIRIS_API_PORT", "8080")


async def start_mobile_runtime():
    """Start the full CIRIS runtime with API adapter for Android."""
    from ciris_engine.logic.adapters.api.config import APIAdapterConfig
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
    from ciris_engine.logic.utils.runtime_utils import load_config
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

    logger.info("Starting CIRIS on-device runtime...")
    logger.info("API endpoint: http://127.0.0.1:8080")
    logger.info(f"LLM endpoint: {os.environ.get('OPENAI_API_BASE', 'NOT CONFIGURED')}")

    # On Android, we skip file-based config loading and use defaults directly
    # since the app doesn't have access to config/essential.yaml
    # The path resolution in EssentialConfig will use CIRIS_HOME env var
    # which was set by setup_android_environment()
    from ciris_engine.logic.utils.path_resolution import get_ciris_home, get_data_dir
    from ciris_engine.schemas.config.essential import DatabaseConfig, EssentialConfig, SecurityConfig

    # Get Android-specific paths
    ciris_home = get_ciris_home()
    data_dir = get_data_dir()

    # Create security config with absolute paths (Android CWD is read-only)
    security_config = SecurityConfig(
        secrets_key_path=ciris_home / ".ciris_keys",
        audit_key_path=ciris_home / "audit_keys",
    )

    # Create database config with absolute paths
    db_config = DatabaseConfig(
        main_db=data_dir / "ciris_engine.db",
        secrets_db=data_dir / "secrets.db",
        audit_db=data_dir / "ciris_audit.db",
    )

    # Create config with Android-specific paths
    app_config = EssentialConfig(
        security=security_config,
        database=db_config,
        template_directory=ciris_home / "ciris_templates",
    )
    logger.info(f"Using Android config - CIRIS_HOME: {ciris_home}, data_dir: {data_dir}")

    # Configure API adapter
    api_config = APIAdapterConfig()
    api_config.host = "127.0.0.1"
    api_config.port = 8080

    adapter_configs = {"api": AdapterConfig(adapter_type="api", enabled=True, settings=api_config.model_dump())}

    startup_channel_id = api_config.get_home_channel_id(api_config.host, api_config.port)

    # Create the full CIRIS runtime
    runtime = CIRISRuntime(
        adapter_types=["api"],
        essential_config=app_config,
        startup_channel_id=startup_channel_id,
        adapter_configs=adapter_configs,
        interactive=False,  # No interactive CLI on Android
        host="127.0.0.1",
        port=8080,
    )

    # Initialize all services (22 services, buses, etc.)
    logger.info("Initializing CIRIS services...")
    await runtime.initialize()
    logger.info("CIRIS runtime initialized successfully")

    # Run the runtime (includes API server and agent processor)
    try:
        await runtime.run()
    except KeyboardInterrupt:
        logger.info("Runtime interrupted, shutting down...")
        runtime.request_shutdown("User interrupt")
    except Exception as e:
        logger.error(f"Runtime error: {e}", exc_info=True)
        runtime.request_shutdown(f"Error: {e}")
    finally:
        await runtime.shutdown()


def main():
    """Main entrypoint for Android app."""
    logger.info("CIRIS Mobile - Full On-Device Runtime (LLM Remote)")
    setup_android_environment()

    try:
        asyncio.run(start_mobile_runtime())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
