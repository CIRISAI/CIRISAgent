"""
Mobile QA Runner configuration.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class MobileQAModule(Enum):
    """Mobile-specific QA test modules."""

    # Mobile infrastructure tests
    BRIDGE = "bridge"  # Test ADB bridge connectivity
    PYTHON_RUNTIME = "python"  # Test Python/Chaquopy initialization
    SERVER_HEALTH = "health"  # Test server health endpoint

    # Setup wizard tests
    SETUP_FIRST_RUN = "setup_first_run"  # First-run detection
    SETUP_WIZARD = "setup_wizard"  # Setup wizard completion
    SETUP_GOOGLE = "setup_google"  # Google OAuth setup path
    SETUP_BYOK = "setup_byok"  # BYOK setup path

    # Service startup tests
    SERVICES_MINIMAL = "services_minimal"  # 10/10 first-run services
    SERVICES_FULL = "services_full"  # 22/22 full services
    SERVICE_LIGHTS = "service_lights"  # UI light animation timing

    # Auth tests (via bridge to main QA runner)
    AUTH = "auth"

    # Telemetry tests (via bridge)
    TELEMETRY = "telemetry"

    # Agent interaction tests (via bridge)
    AGENT = "agent"

    # Full test suites
    MOBILE_CORE = "mobile_core"  # All mobile-specific tests
    API_VIA_BRIDGE = "api"  # All API tests via bridge
    ALL = "all"


@dataclass
class MobileQAConfig:
    """Configuration for mobile QA runner."""

    # ADB configuration
    adb_path: str = "adb"
    device_serial: Optional[str] = None  # None = use default device

    # Port forwarding
    device_port: int = 8080  # Port on device
    local_port: int = 8080  # Port on host (for QA runner)

    # Device paths
    device_data_dir: str = "/data/data/ai.ciris.mobile/files"
    device_ciris_home: str = "/data/data/ai.ciris.mobile/files/ciris"
    device_env_path: str = "/data/data/ai.ciris.mobile/files/ciris/.env"

    # API configuration (after port forwarding)
    base_url: str = "http://localhost:8080"

    # Test configuration
    timeout: float = 60.0
    retry_count: int = 3
    verbose: bool = False

    # Server startup wait
    server_startup_timeout: float = 120.0  # Mobile startup can be slower
    health_check_interval: float = 2.0

    # Authentication (for tests that require it)
    admin_username: str = "admin"
    admin_password: str = "ciris_admin_password"

    # LLM configuration for setup
    llm_provider: str = "openai"
    llm_api_key: str = ""  # Must be provided for BYOK tests
    llm_model: str = "gpt-4o"

    # Output
    report_dir: Path = field(default_factory=lambda: Path("qa_reports"))
    json_output: bool = False

    @property
    def android_sdk_path(self) -> Optional[Path]:
        """Get Android SDK path from environment."""
        import os

        sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if sdk:
            return Path(sdk)
        # Common default locations
        home = Path.home()
        for candidate in [
            home / "Android" / "Sdk",
            home / "Library" / "Android" / "sdk",
            Path("/usr/local/android-sdk"),
        ]:
            if candidate.exists():
                return candidate
        return None

    @property
    def adb_executable(self) -> str:
        """Get full path to adb executable."""
        if self.adb_path != "adb":
            return self.adb_path
        sdk = self.android_sdk_path
        if sdk:
            adb = sdk / "platform-tools" / "adb"
            if adb.exists():
                return str(adb)
        return "adb"  # Fall back to PATH
