"""
Service initialization for CIRIS Agent runtime.

Handles the initialization of all core services.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiofiles

from ciris_engine.config.ciris_services import get_billing_url
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.config.config_accessor import ConfigAccessor
from ciris_engine.logic.persistence import get_sqlite_db_full_path
from ciris_engine.logic.registries.base import Priority, ServiceRegistry

# CoreToolService removed - SELF_HELP moved to memory per user request
# BasicTelemetryCollector removed - using GraphTelemetryService instead
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.governance.adaptive_filter import AdaptiveFilterService

# Removed AuditSinkManager - audit is consolidated, no sink needed
from ciris_engine.logic.services.governance.wise_authority import WiseAuthorityService
from ciris_engine.logic.services.graph.audit_service import GraphAuditService as AuditService
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.logic.services.infrastructure.database_maintenance import DatabaseMaintenanceService
from ciris_engine.logic.services.lifecycle.initialization import InitializationService
from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService

# Import new infrastructure services
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.logic.services.runtime.llm_service import OpenAICompatibleClient
from ciris_engine.logic.utils.path_resolution import get_data_dir
from ciris_engine.protocols.services import LLMService, TelemetryService
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.manifest import ServiceManifest
from ciris_engine.schemas.services.capabilities import LLMCapabilities

logger = logging.getLogger(__name__)

# Total core services for startup logging (22 per architecture)
TOTAL_CORE_SERVICES = 22

# First-run minimal services (10 services needed to serve setup wizard)
FIRST_RUN_SERVICES = 10

# Services started during resume_from_first_run (remaining 12)
RESUME_SERVICES = 12

# Service names in initialization order for UI display
SERVICE_NAMES = [
    "TimeService",  # 1 - Infrastructure
    "ShutdownService",  # 2 - Infrastructure
    "InitializationService",  # 3 - Infrastructure
    "ResourceMonitor",  # 4 - Infrastructure
    "SecretsService",  # 5 - Memory Foundation
    "MemoryService",  # 6 - Memory Foundation
    "ConfigService",  # 7 - Graph Services
    "AuditService",  # 8 - Graph Services
    "TelemetryService",  # 9 - Graph Services
    "IncidentManagement",  # 10 - Graph Services
    "TSDBConsolidation",  # 11 - Graph Services
    "ConsentService",  # 12 - Graph Services
    "WiseAuthority",  # 13 - Security
    "LLMService",  # 14 - Runtime
    "AuthenticationService",  # 15 - Runtime (adapter-provided)
    "DatabaseMaintenance",  # 16 - Infrastructure
    "RuntimeControl",  # 17 - Runtime (adapter-provided)
    "TaskScheduler",  # 18 - Lifecycle
    "AdaptiveFilter",  # 19 - Governance
    "VisibilityService",  # 20 - Governance
    "SelfObservation",  # 21 - Governance
    "SecretsToolService",  # 22 - Tool Services
]

# Track which phase we're in for logging clarity
_current_phase: str = "STARTUP"


def _set_service_phase(phase: str) -> None:
    """Set the current service initialization phase for logging."""
    global _current_phase
    _current_phase = phase
    logger.warning(f"[SERVICES] === {phase} PHASE ===")
    print(f"[SERVICES] === {phase} PHASE ===")


def _log_service_started(service_num: int, service_name: str, success: bool = True) -> None:
    """Log service startup status in a format parseable by the UI."""
    status = "STARTED" if success else "FAILED"
    phase_prefix = f"[{_current_phase}] " if _current_phase != "STARTUP" else ""
    msg = f"{phase_prefix}[SERVICE {service_num}/{TOTAL_CORE_SERVICES}] {service_name} {status}"
    # Use WARNING level so it shows up in incident logs for easy parsing
    logger.warning(msg)
    # Also print to console/stdout for Android logcat visibility
    print(msg)


class ServiceInitializer:
    """Manages initialization of all core services."""

    def __init__(self, essential_config: Optional[EssentialConfig] = None) -> None:
        self.service_registry: Optional[ServiceRegistry] = None
        self.bus_manager: Optional[Any] = None  # Will be BusManager
        self.essential_config = essential_config or EssentialConfig()
        self.config_accessor: Optional[ConfigAccessor] = None

        # Infrastructure services (initialized first)
        self.time_service: Optional[TimeService] = None
        self.shutdown_service: Optional[ShutdownService] = None
        self.initialization_service: Optional[InitializationService] = None

        # Create initial config accessor without graph (bootstrap only)
        self.config_accessor = ConfigAccessor(None, self.essential_config)

        # Core services
        self.memory_service: Optional[LocalGraphMemoryService] = None
        self.secrets_service: Optional[SecretsService] = None
        self.wa_auth_system: Optional[WiseAuthorityService] = None
        self.telemetry_service: Optional[TelemetryService] = None
        self.llm_service: Optional[LLMService] = None
        self.audit_service: Optional[AuditService] = None
        # Removed audit_sink_manager - audit is consolidated
        self.adaptive_filter_service: Optional[AdaptiveFilterService] = None
        self.secrets_tool_service: Optional[Any] = None  # SecretsToolService
        self.maintenance_service: Optional[DatabaseMaintenanceService] = None
        self.incident_management_service: Optional[Any] = None  # Will be IncidentManagementService
        self.tsdb_consolidation_service: Optional[Any] = None  # Will be TSDBConsolidationService
        self.resource_monitor_service: Optional[Any] = None  # Will be ResourceMonitorService
        self.config_service: Optional[Any] = None  # Will be GraphConfigService
        self.self_observation_service: Optional[Any] = None  # Will be SelfObservationService
        self.visibility_service: Optional[Any] = None  # Will be VisibilityService
        self.consent_service: Optional[Any] = None  # Will be ConsentService
        self.runtime_control_service: Optional[Any] = None  # Will be RuntimeControlService

        # Module management
        self.module_loader: Optional[Any] = None  # Will be ModuleLoader
        self.loaded_modules: List[str] = []
        self._skip_llm_init: bool = False  # Set to True if MOCK LLM module detected

        # Metrics tracking for v1.4.3
        self._services_started_count: int = 0
        self._initialization_errors: int = 0
        self._dependencies_resolved: int = 0
        self._startup_start_time: Optional[float] = None
        self._startup_end_time: Optional[float] = None

    def _is_first_run_mode(self) -> bool:
        """Check if we're in first-run mode."""
        from ciris_engine.logic.setup.first_run import is_first_run

        return is_first_run()

    async def initialize_infrastructure_services(self) -> None:
        """Initialize infrastructure services that all other services depend on."""
        # Track startup time
        import time

        if self._startup_start_time is None:
            self._startup_start_time = time.time()

        # Set phase for logging - this is the first phase of initialization
        _set_service_phase("FIRST-RUN" if self._is_first_run_mode() else "FULL-STARTUP")

        # Initialize TimeService first - everyone needs time
        try:
            self.time_service = TimeService()
            await self.time_service.start()
            self._services_started_count += 1
            _log_service_started(1, "TimeService")
        except Exception as e:
            self._initialization_errors += 1
            _log_service_started(1, "TimeService", success=False)
            logger.error(f"Failed to initialize TimeService: {e}")
            raise
        assert self.time_service is not None  # For type checker

        # Note: TimeService will be registered in ServiceRegistry later
        # when the registry is created in initialize_all_services()

        # Initialize ShutdownService
        self.shutdown_service = ShutdownService()
        await self.shutdown_service.start()
        self._services_started_count += 1
        _log_service_started(2, "ShutdownService")

        # Initialize InitializationService with TimeService
        self.initialization_service = InitializationService(self.time_service)
        await self.initialization_service.start()
        self._services_started_count += 1
        _log_service_started(3, "InitializationService")

        # Initialize ResourceMonitorService
        from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceMonitorService
        from ciris_engine.schemas.services.resources_core import ResourceBudget

        # Create default resource budget
        budget = ResourceBudget()  # Uses defaults from schema

        # Credit provider: Controls billing for CIRIS LLM proxy usage
        # - Server: CIRIS_BILLING_API_KEY set → API key auth
        # - Android: Using CIRIS proxy + Google ID token → JWT auth
        # - Not using CIRIS proxy → No billing (credit_provider = None)
        from typing import Optional

        from ciris_engine.protocols.services.infrastructure.credit_gate import CreditGateProtocol

        credit_provider: Optional[CreditGateProtocol] = None
        is_android = "ANDROID_DATA" in os.environ

        # Check if using CIRIS LLM proxy (Android only - billing required for proxy)
        # Matches both legacy ciris.ai and new ciris-services infrastructure
        llm_base_url = os.getenv("OPENAI_API_BASE", "")
        using_ciris_proxy = "ciris.ai" in llm_base_url or "ciris-services" in llm_base_url

        # Server: Simple API key check
        api_key = os.getenv("CIRIS_BILLING_API_KEY", "")
        # Android: Google ID token for JWT auth with CIRIS proxy
        google_id_token = os.getenv("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")

        if api_key and not is_android:
            # Server with API key - use API key auth
            from ciris_engine.logic.services.infrastructure.resource_monitor import CIRISBillingProvider

            base_url = get_billing_url()
            timeout = float(os.getenv("CIRIS_BILLING_TIMEOUT_SECONDS", "5.0"))
            cache_ttl = int(os.getenv("CIRIS_BILLING_CACHE_TTL_SECONDS", "15"))
            fail_open = os.getenv("CIRIS_BILLING_FAIL_OPEN", "false").lower() == "true"

            credit_provider = CIRISBillingProvider(
                api_key=api_key,
                base_url=base_url,
                timeout_seconds=timeout,
                cache_ttl_seconds=cache_ttl,
                fail_open=fail_open,
            )
            logger.info("Using CIRISBillingProvider with API key auth (URL: %s)", base_url)

        elif is_android and using_ciris_proxy:
            # Android using CIRIS LLM proxy - requires billing
            if google_id_token:
                # Have Google ID token - use JWT auth
                from ciris_engine.logic.services.infrastructure.resource_monitor import CIRISBillingProvider

                base_url = get_billing_url()
                timeout = float(os.getenv("CIRIS_BILLING_TIMEOUT_SECONDS", "5.0"))
                cache_ttl = int(os.getenv("CIRIS_BILLING_CACHE_TTL_SECONDS", "15"))
                fail_open = os.getenv("CIRIS_BILLING_FAIL_OPEN", "false").lower() == "true"

                credit_provider = CIRISBillingProvider(
                    google_id_token=google_id_token,
                    base_url=base_url,
                    timeout_seconds=timeout,
                    cache_ttl_seconds=cache_ttl,
                    fail_open=fail_open,
                )
                logger.info("Using CIRISBillingProvider with JWT auth (CIRIS LLM proxy)")
            else:
                # No token yet - user needs to sign in with Google
                logger.warning(
                    "Android using CIRIS LLM proxy without Google ID token - "
                    "user needs to sign in with Google to use LLM features"
                )
                # credit_provider stays None - LLM calls will fail until signed in

        elif is_android and not using_ciris_proxy:
            # Android but not using CIRIS proxy - no billing needed
            logger.info("Android not using CIRIS proxy - no billing required")
            # credit_provider stays None

        else:
            # Server without API key - no billing
            logger.info("No billing configured (CIRIS_BILLING_API_KEY not set)")

        self.resource_monitor_service = ResourceMonitorService(
            budget=budget,
            db_path=get_sqlite_db_full_path(self.essential_config),
            time_service=self.time_service,
            credit_provider=credit_provider,
        )
        await self.resource_monitor_service.start()
        self._services_started_count += 1
        _log_service_started(4, "ResourceMonitor")

    async def initialize_memory_service(self, config: Any) -> None:
        """Initialize the memory service."""
        # Initialize secrets service first (memory service depends on it)
        import os
        from pathlib import Path

        # Use configurable secrets key path from essential config
        keys_dir = Path(self.essential_config.security.secrets_key_path)
        keys_dir.mkdir(parents=True, exist_ok=True)

        # Load or generate master key
        master_key_path = keys_dir / "secrets_master.key"
        master_key = None
        is_android = "ANDROID_DATA" in os.environ

        if is_android:
            # Android: Use Keystore-wrapped key for hardware-backed protection
            try:
                from android_keystore import load_or_create_wrapped_master_key, migrate_plain_key_to_wrapped

                # Migrate existing plain key if present
                migrate_plain_key_to_wrapped(master_key_path)

                # Load or create wrapped key
                master_key = load_or_create_wrapped_master_key(master_key_path)
                if master_key:
                    logger.info("Loaded secrets master key with Android Keystore protection")
                else:
                    logger.error("Failed to load/create Keystore-wrapped master key")
            except ImportError:
                logger.warning("Android Keystore module not available, falling back to file storage")
                is_android = False  # Fall through to standard path
            except Exception as e:
                logger.error(f"Android Keystore error: {e}, falling back to file storage")
                is_android = False

        if not is_android:
            # Standard path: plain file storage (server deployments)
            if master_key_path.exists():
                # Load existing master key
                async with aiofiles.open(master_key_path, "rb") as f:
                    master_key = await f.read()
                logger.info("Loaded existing secrets master key")
            else:
                # Generate new master key and save it
                import secrets

                master_key = secrets.token_bytes(32)
                async with aiofiles.open(master_key_path, "wb") as f:
                    await f.write(master_key)
                # Set restrictive permissions (owner read/write only)
                os.chmod(master_key_path, 0o600)
                logger.info("Generated and saved new secrets master key")

        # Create README if it doesn't exist
        readme_path = keys_dir / "README.md"
        if not readme_path.exists():
            readme_content = """# CIRIS Keys Directory

This directory contains critical cryptographic keys for the CIRIS system.

## Files

### secrets_master.key
- **Purpose**: Master encryption key for the SecretsService
- **Type**: 256-bit symmetric key
- **Usage**: Used to derive per-secret encryption keys via PBKDF2
- **Algorithm**: AES-256-GCM encryption
- **Critical**: Loss of this key means all encrypted secrets become unrecoverable

### audit_signing_private.pem
- **Purpose**: Private key for signing audit log entries
- **Type**: RSA 2048-bit private key
- **Usage**: Creates digital signatures for non-repudiation
- **Critical**: Keep this key secure - compromise allows forging audit entries

### audit_signing_public.pem
- **Purpose**: Public key for verifying audit signatures
- **Type**: RSA 2048-bit public key
- **Usage**: Verifies signatures on audit entries
- **Note**: Can be shared publicly for verification purposes

## Security Notes

1. **Permissions**: All key files should have restrictive permissions (600)
2. **Backup**: Regularly backup these keys to secure offline storage
3. **Rotation**: Consider key rotation policies for long-running deployments
4. **Access**: Only the CIRIS process should access these keys

## DO NOT
- Commit these files to version control
- Share the private keys or master key
- Store copies in insecure locations
"""
            async with aiofiles.open(readme_path, "w") as f:
                await f.write(readme_content)
            logger.info("Created .ciris_keys/README.md")

        # Use the proper helper function to get secrets database path
        # This handles PostgreSQL URL query parameter preservation correctly
        from ciris_engine.logic.config import get_secrets_db_full_path

        secrets_db_path = get_secrets_db_full_path(self.essential_config)

        if self.time_service is None:
            raise RuntimeError("TimeService must be initialized before SecretsService")

        self.secrets_service = SecretsService(
            db_path=secrets_db_path, time_service=self.time_service, master_key=master_key
        )
        await self.secrets_service.start()
        self._services_started_count += 1
        _log_service_started(5, "SecretsService")

        # Create and register CoreToolService
        from ciris_engine.logic.services.tools import CoreToolService

        self.secrets_tool_service = CoreToolService(
            secrets_service=self.secrets_service,
            time_service=self.time_service,
            # Don't pass db_path - let persistence layer use current config
            # This allows runtime database switching (SQLite → PostgreSQL via CIRIS_DB_URL)
        )
        await self.secrets_tool_service.start()
        self._services_started_count += 1
        _log_service_started(22, "SecretsToolService")

        # LocalGraphMemoryService needs the correct db path from our config
        db_path = get_sqlite_db_full_path(self.essential_config)
        self.memory_service = LocalGraphMemoryService(
            db_path=db_path, time_service=self.time_service, secrets_service=self.secrets_service
        )
        await self.memory_service.start()
        self._services_started_count += 1
        _log_service_started(6, "MemoryService")

        # Initialize GraphConfigService now that memory service is ready
        from ciris_engine.logic.registries.base import Priority, get_global_registry
        from ciris_engine.logic.services.graph.config_service import GraphConfigService
        from ciris_engine.schemas.runtime.enums import ServiceType

        if self.time_service is None:
            raise RuntimeError("TimeService must be initialized before GraphConfigService")
        self.config_service = GraphConfigService(self.memory_service, self.time_service)
        await self.config_service.start()
        self._services_started_count += 1
        _log_service_started(7, "ConfigService")

        # Register config service immediately so it's available for persistence operations
        registry = get_global_registry()
        # Store essential config on the service so db_paths can find it
        # Dynamic attribute assignment for runtime access to essential_config
        self.config_service.essential_config = self.essential_config  # type: ignore[attr-defined]
        registry.register_service(
            service_type=ServiceType.CONFIG,
            provider=self.config_service,
            priority=Priority.HIGH,
            capabilities=["get_config", "set_config", "list_configs"],
            metadata={"backend": "graph", "type": "essential"},
        )
        logger.info("Config service registered early in ServiceRegistry for persistence access")

        # Create config accessor with graph service
        self.config_accessor = ConfigAccessor(self.config_service, self.essential_config)
        self._dependencies_resolved += 1  # Graph config service dependency

        # Migrate essential config to graph
        await self._migrate_config_to_graph()

    async def verify_memory_service(self) -> bool:
        """Verify memory service is operational."""
        if not self.memory_service:
            logger.error("Memory service not initialized")
            return False

        # Test basic operations
        try:
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            # Use a different node type for test - don't pollute CONFIG namespace
            assert self.time_service is not None
            now = self.time_service.now()
            test_node = GraphNode(
                id="_verification_test",
                type=NodeType.OBSERVATION,  # Use OBSERVATION type for system verification test
                attributes={
                    "created_at": now.isoformat(),  # Serialize to ISO string
                    "updated_at": now.isoformat(),  # Serialize to ISO string
                    "created_by": "system_verification",
                    "tags": ["test", "verification"],
                    "verification_type": "memory_service",  # Custom field in attributes dict
                    "verifier": "system",  # Custom field in attributes dict
                },
                scope=GraphScope.LOCAL,
            )

            # Test memorize and recall
            await self.memory_service.memorize(test_node)

            from ciris_engine.schemas.services.operations import MemoryQuery

            query = MemoryQuery(
                node_id=test_node.id, scope=test_node.scope, type=test_node.type, include_edges=False, depth=1
            )
            nodes = await self.memory_service.recall(query)

            if not nodes:
                logger.error("Memory service verification failed: no nodes recalled")
                return False

            # Clean up
            await self.memory_service.forget(test_node)

            logger.info("✓ Memory service verified")
            return True

        except Exception as e:
            logger.error(f"Memory service verification error: {e}")
            return False

    async def initialize_security_services(self, config: Any, app_config: Any) -> None:
        """Initialize security-related services."""
        # SecretsService already initialized in initialize_memory_service

        # Initialize AuthenticationService first
        from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService

        if self.time_service is None:
            raise RuntimeError("TimeService must be initialized before AuthenticationService")

        if self.config_accessor is None:
            raise RuntimeError("ConfigAccessor must be initialized before AuthenticationService")
        # Get main database path for WiseAuthority (needs access to tasks table)
        main_db_path = get_sqlite_db_full_path(self.essential_config)

        # Use the proper helper function to get auth database path
        # This handles PostgreSQL URL query parameter preservation correctly
        from ciris_engine.logic.config import get_audit_db_full_path

        auth_db_path = get_audit_db_full_path(self.essential_config)
        self.auth_service = AuthenticationService(
            db_path=auth_db_path, time_service=self.time_service, key_dir=None  # Will use default ~/.ciris/
        )
        await self.auth_service.start()
        self._services_started_count += 1
        _log_service_started(15, "AuthenticationService")

        # Process pending users from setup wizard if file exists
        await self._process_pending_users_from_setup()

        # Initialize WA authentication system with TimeService and AuthService
        # Use the main database path - WiseAuthority needs access to tasks table
        self.wa_auth_system = WiseAuthorityService(
            time_service=self.time_service, auth_service=self.auth_service, db_path=main_db_path
        )
        await self.wa_auth_system.start()
        self._services_started_count += 1
        _log_service_started(13, "WiseAuthority")

        # Log summary for first-run mode
        if self._is_first_run_mode():
            msg = f"[FIRST-RUN] ✓ {self._services_started_count}/{FIRST_RUN_SERVICES} minimal services started - ready for setup wizard"
            logger.warning(msg)
            print(msg)

    async def verify_security_services(self) -> bool:
        """Verify security services are operational."""
        # Verify secrets service
        if not self.secrets_service:
            logger.error("Secrets service not initialized")
            return False

        # Verify WA auth system
        if not self.wa_auth_system:
            logger.error("WA authentication system not initialized")
            return False

        # Verify WA service is healthy
        if not await self.wa_auth_system.is_healthy():
            logger.error("WA auth service not healthy")
            return False

        logger.info("✓ Security services verified")
        return True

    async def initialize_all_services(
        self,
        config: Any,
        app_config: Any,
        agent_id: str,
        startup_channel_id: Optional[str] = None,
        modules_to_load: Optional[List[str]] = None,
    ) -> None:
        """Initialize all remaining core services.

        This is called:
        - During normal startup: After first-run services (completes all 22)
        - During resume_from_first_run: Starts the remaining 12 services after wizard
        """
        # Set phase for logging - RESUME if coming from first-run, otherwise continue FULL-STARTUP
        if self._services_started_count == FIRST_RUN_SERVICES:
            _set_service_phase(f"RESUME ({RESUME_SERVICES} remaining services)")
        else:
            _set_service_phase("CORE-SERVICES")

        from ciris_engine.logic.registries.base import get_global_registry

        self.service_registry = get_global_registry()

        # Register TimeService now that we have a registry
        if self.time_service:
            self.service_registry.register_service(
                service_type=ServiceType.TIME,
                provider=self.time_service,
                priority=Priority.CRITICAL,
                capabilities=["now", "format_timestamp", "parse_timestamp"],
                metadata={"timezone": "UTC"},
            )
            self._dependencies_resolved += 1  # Service registry dependency
            logger.info("TimeService registered in ServiceRegistry")

        # Pre-load module loader to check for MOCK modules BEFORE initializing services
        if modules_to_load:
            logger.info(f"Checking modules to load: {modules_to_load}")
            from ciris_engine.logic.runtime.module_loader import ModuleLoader

            self.module_loader = ModuleLoader()

            # Check modules for MOCK status WITHOUT loading them yet
            for module_name in modules_to_load:
                assert self.module_loader is not None
                module_path = self.module_loader.modules_dir / module_name
                manifest_path = module_path / "manifest.json"
                logger.info(f"Checking for manifest at: {manifest_path}")

                if manifest_path.exists():
                    try:
                        async with aiofiles.open(manifest_path) as f:
                            content = await f.read()
                            manifest_data = json.loads(content)

                        # Parse into typed manifest
                        manifest = ServiceManifest.model_validate(manifest_data)

                        if manifest.module.is_mock:
                            # This is a MOCK module - check what services it provides
                            for service in manifest.services:
                                if service.type == ServiceType.LLM:
                                    logger.info(
                                        f"Detected MOCK LLM module '{module_name}' will be loaded - skipping normal LLM initialization"
                                    )
                                    self._skip_llm_init = True
                                    break
                    except Exception as e:
                        logger.warning(f"Failed to pre-check module {module_name}: {e}")
        else:
            modules_to_load = []

        # Register previously initialized services in the registry
        # Register previously initialized services in the registry as per CLAUDE.md

        # Config service was already registered early in initialize_memory_service
        # to ensure it's available for persistence operations

        # Memory service was initialized in Phase 2, register it now
        if self.memory_service:
            self.service_registry.register_service(
                service_type=ServiceType.MEMORY,
                provider=self.memory_service,
                priority=Priority.HIGH,
                capabilities=[
                    "memorize",
                    "recall",
                    "forget",
                    "graph_operations",
                    "memorize_metric",
                    "memorize_log",
                    "recall_timeseries",
                    "export_identity_context",
                    "search",
                ],
                metadata={"backend": "sqlite", "graph_type": "local"},
            )
            self._dependencies_resolved += 1  # Memory service dependency
            logger.info("Memory service registered in ServiceRegistry")

        # WiseAuthority service was initialized in security phase, register it now
        if self.wa_auth_system:
            self.service_registry.register_service(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self.wa_auth_system,
                priority=Priority.HIGH,
                capabilities=[
                    "authenticate",
                    "authorize",
                    "validate",
                    "guidance",
                    "send_deferral",
                    "get_pending_deferrals",
                    "resolve_deferral",
                ],
                metadata={"type": "consolidated", "consensus": "single"},
            )
            self._dependencies_resolved += 1  # WiseAuthority service dependency
            logger.info("WiseAuthority service registered in ServiceRegistry")

        # Create BusManager first (without telemetry service)
        assert self.service_registry is not None
        assert self.time_service is not None
        self.bus_manager = BusManager(
            self.service_registry,
            self.time_service,
            None,  # telemetry_service will be set later
            None,  # audit_service will be set later
        )
        self._dependencies_resolved += 1  # BusManager dependency

        # Initialize telemetry service using GraphTelemetryService
        # This implements the "Graph Memory as Identity Architecture" patent
        # where telemetry IS memory stored in the agent's identity graph
        from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService

        assert self.bus_manager is not None
        assert self.time_service is not None
        try:
            # Create the concrete GraphTelemetryService instance
            telemetry_service_impl = GraphTelemetryService(
                memory_bus=self.bus_manager.memory, time_service=self.time_service  # Now we have the memory bus
            )
            # Attach service registry using protocol pattern
            # Use hasattr (protocol is not @runtime_checkable)
            if self.service_registry and hasattr(telemetry_service_impl, "attach_registry"):
                await telemetry_service_impl.attach_registry(self.service_registry)
            await telemetry_service_impl.start()
            # Assign to protocol-typed field after all setup is complete
            # Note: GraphTelemetryService structurally implements TelemetryService protocol
            self.telemetry_service = telemetry_service_impl  # type: ignore[assignment]
            self._services_started_count += 1
            _log_service_started(9, "TelemetryService")
        except Exception as e:
            self._initialization_errors += 1
            logger.error(f"Failed to initialize GraphTelemetryService: {e}")
            raise

        # Now set the telemetry service in bus manager and LLM bus
        self.bus_manager.telemetry_service = self.telemetry_service
        self.bus_manager.llm.telemetry_service = self.telemetry_service

        # Initialize LLM service(s) based on configuration
        await self._initialize_llm_services(config, modules_to_load)

        # Secrets service no longer needs LLM service reference

        # Initialize ALL THREE REQUIRED audit services
        await self._initialize_audit_services(config, agent_id)

        # Initialize adaptive filter service
        assert self.memory_service is not None
        assert self.time_service is not None
        assert self.config_service is not None
        self.adaptive_filter_service = AdaptiveFilterService(
            memory_service=self.memory_service,
            time_service=self.time_service,
            llm_service=self.llm_service,
            config_service=self.config_service,  # Pass GraphConfigService
        )
        await self.adaptive_filter_service.start()
        self._services_started_count += 1
        _log_service_started(19, "AdaptiveFilter")

        # GraphConfigService (initialized earlier) handles all configuration including agent config
        # No separate agent configuration service needed - see GraphConfigService documentation

        # Transaction orchestrator not needed - bus-based architecture handles
        # coordination without requiring distributed transactions

        # CoreToolService removed - tools are adapter-only per user request
        # SELF_HELP moved to memory service

        # Initialize task scheduler service
        from ciris_engine.logic.services.lifecycle.scheduler import TaskSchedulerService

        # Get the correct db path from our essential config
        db_path = get_sqlite_db_full_path(self.essential_config)
        self.task_scheduler_service = TaskSchedulerService(db_path=db_path, time_service=self.time_service)
        await self.task_scheduler_service.start()
        self._services_started_count += 1
        _log_service_started(18, "TaskScheduler")

        # Initialize TSDB consolidation service BEFORE maintenance
        # This ensures we consolidate any missed windows before maintenance runs
        from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService

        assert self.bus_manager is not None
        assert self.time_service is not None

        # Get configuration from essential config
        config = self.essential_config
        graph_config = config.graph if hasattr(config, "graph") else None

        # Get the correct db path from our essential config
        db_path = get_sqlite_db_full_path(self.essential_config)
        self.tsdb_consolidation_service = TSDBConsolidationService(
            memory_bus=self.bus_manager.memory,  # Use memory bus, not direct service
            time_service=self.time_service,  # Pass time service
            consolidation_interval_hours=6,  # Fixed for calendar alignment
            raw_retention_hours=graph_config.tsdb_raw_retention_hours if graph_config else 24,
            db_path=db_path,
        )
        await self.tsdb_consolidation_service.start()
        self._services_started_count += 1
        _log_service_started(11, "TSDBConsolidation")

        # Register TSDBConsolidationService in registry
        self.service_registry.register_service(
            service_type=ServiceType.TSDB_CONSOLIDATION,
            provider=self.tsdb_consolidation_service,
            priority=Priority.NORMAL,
            capabilities=["consolidate_data", "get_summaries"],
            metadata={"consolidation_interval": "6h", "type": "tsdb"},
        )
        logger.info("TSDBConsolidationService registered in ServiceRegistry")

        # Initialize maintenance service AFTER consolidation
        archive_dir_config = getattr(config, "data_archive_dir", "data_archive")
        # Resolve relative paths to absolute (critical for Android where CWD is read-only)
        archive_path = Path(archive_dir_config)
        if not archive_path.is_absolute():
            archive_path = get_data_dir() / archive_dir_config
        archive_dir = str(archive_path)
        archive_hours = getattr(config, "archive_older_than_hours", 24)
        assert self.time_service is not None
        assert self.config_service is not None
        assert self.bus_manager is not None
        self.maintenance_service = DatabaseMaintenanceService(
            time_service=self.time_service,
            archive_dir_path=archive_dir,
            archive_older_than_hours=archive_hours,
            config_service=self.config_service,
            bus_manager=self.bus_manager,
        )
        await self.maintenance_service.start()
        self._services_started_count += 1
        _log_service_started(16, "DatabaseMaintenance")

        # Initialize self observation service
        from ciris_engine.logic.services.governance.self_observation import SelfObservationService

        assert self.time_service is not None
        assert self.bus_manager is not None
        self.self_observation_service = SelfObservationService(
            time_service=self.time_service,
            memory_bus=self.bus_manager.memory,
            variance_threshold=0.20,  # 20% max variance from baseline
            observation_interval_hours=6,
        )
        # Attach service registry using protocol pattern
        # Use hasattr (protocol is not @runtime_checkable)
        if self.service_registry and hasattr(self.self_observation_service, "attach_registry"):
            await self.self_observation_service.attach_registry(self.service_registry)
        # Start the service for API mode (in other modes DREAM processor starts it)
        await self.self_observation_service.start()
        self._services_started_count += 1
        _log_service_started(21, "SelfObservation")

        # Initialize visibility service
        from ciris_engine.logic.services.governance.visibility import VisibilityService

        assert self.bus_manager is not None
        assert self.time_service is not None
        self.visibility_service = VisibilityService(
            bus_manager=self.bus_manager,
            time_service=self.time_service,
            db_path=get_sqlite_db_full_path(self.essential_config),
        )
        await self.visibility_service.start()
        self._services_started_count += 1
        _log_service_started(20, "VisibilityService")

        # Initialize consent service (Governance Service #5)
        from ciris_engine.logic.services.governance.consent import ConsentService

        assert self.time_service is not None
        assert self.bus_manager is not None
        self.consent_service = ConsentService(
            time_service=self.time_service,
            memory_bus=self.bus_manager.memory,  # Use memory bus for impact reporting and audit trail
            db_path=get_sqlite_db_full_path(self.essential_config),
        )
        await self.consent_service.start()
        self._services_started_count += 1
        _log_service_started(12, "ConsentService")

        # Initialize runtime control service
        from ciris_engine.logic.services.runtime.control_service import RuntimeControlService

        assert self.config_service is not None
        assert self.time_service is not None
        self.runtime_control_service = RuntimeControlService(
            runtime=None,  # Will be set by runtime after initialization
            adapter_manager=None,  # Will be created on demand
            config_manager=self.config_service,
            time_service=self.time_service,
        )
        await self.runtime_control_service.start()
        self._services_started_count += 1
        _log_service_started(17, "RuntimeControl")

        # Mark end of startup process
        import time

        self._startup_end_time = time.time()

    def _get_llm_service_config_value(self, config: Any, attr_name: str, default: Any) -> Any:
        """Get LLM service config value safely with fallback to default.

        Args:
            config: Configuration object
            attr_name: Attribute name to get from config.services
            default: Default value if not found

        Returns:
            Config value or default
        """
        if config and hasattr(config, "services") and config.services:
            return getattr(config.services, attr_name, default)
        return default

    async def _initialize_llm_services(self, config: Any, modules_to_load: Optional[List[str]] = None) -> None:
        """Initialize LLM service(s) based on configuration.

        CRITICAL: Only mock OR real LLM services are active, never both.
        This prevents attack vectors where mock responses could be confused with real ones.
        """
        # Skip if mock LLM module is being loaded
        if self._skip_llm_init:
            logger.info("🤖 MOCK LLM module detected - skipping real LLM service initialization")
            return

        # Validate config
        if not hasattr(config, "services"):
            raise ValueError("Configuration missing LLM service settings")

        # Get API key
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            logger.warning("No OPENAI_API_KEY found - LLM service will not be initialized")
            return

        # Initialize real LLM service
        logger.info("Initializing real LLM service")
        from ciris_engine.logic.services.runtime.llm_service import OpenAIConfig

        # Get config values using helper to reduce complexity
        base_url = os.environ.get("OPENAI_API_BASE") or self._get_llm_service_config_value(
            config, "llm_endpoint", "http://localhost:11434/v1"
        )
        model_name = os.environ.get("OPENAI_MODEL") or self._get_llm_service_config_value(
            config, "llm_model", "gpt-4o-mini"
        )

        llm_config = OpenAIConfig(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            instructor_mode=os.environ.get("INSTRUCTOR_MODE", "JSON"),
            timeout_seconds=self._get_llm_service_config_value(config, "llm_timeout", 60),
            max_retries=self._get_llm_service_config_value(config, "llm_max_retries", 3),
        )

        # Create and start service
        openai_service = OpenAICompatibleClient(
            config=llm_config, telemetry_service=self.telemetry_service, time_service=self.time_service
        )
        await openai_service.start()

        # Register service
        if self.service_registry:
            self.service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=openai_service,
                priority=Priority.HIGH,
                capabilities=[LLMCapabilities.CALL_LLM_STRUCTURED],
                metadata={"provider": "openai", "model": llm_config.model_name},
            )

        # Store reference
        self.llm_service = openai_service
        self._services_started_count += 1
        _log_service_started(14, "LLMService")

        # Register token refresh signal handler for ciris.ai authentication
        # This connects the LLM service to ResourceMonitor's signal bus
        if self.resource_monitor_service and hasattr(self.resource_monitor_service, "signal_bus"):
            self.resource_monitor_service.signal_bus.register("token_refreshed", openai_service.handle_token_refreshed)
            logger.info("Registered LLM service token refresh handler with ResourceMonitor")

        # Optional: Initialize secondary LLM service
        # Supports both API key auth and CIRIS proxy with JWT auth (Google ID token)
        second_api_key = os.environ.get("CIRIS_OPENAI_API_KEY_2", "")
        second_base_url = os.environ.get("CIRIS_OPENAI_API_BASE_2", "")
        google_id_token = os.environ.get("CIRIS_BILLING_GOOGLE_ID_TOKEN", "")

        # Check if secondary LLM is CIRIS proxy (requires JWT auth, not API key)
        is_ciris_proxy_secondary = "ciris.ai" in second_base_url

        if second_api_key:
            # Standard API key auth
            await self._initialize_secondary_llm(config, second_api_key)
        elif is_ciris_proxy_secondary and google_id_token:
            # CIRIS proxy with JWT auth - use Google ID token as auth
            logger.info("Secondary LLM using CIRIS proxy with JWT auth")
            await self._initialize_secondary_llm(config, google_id_token)

    async def _initialize_secondary_llm(self, config: Any, api_key: str) -> None:
        """Initialize optional secondary LLM service."""
        logger.info("Initializing secondary LLM service")

        from ciris_engine.logic.services.runtime.llm_service import OpenAIConfig

        # Get configuration from environment using helper
        base_url = os.environ.get(
            "CIRIS_OPENAI_API_BASE_2",
            self._get_llm_service_config_value(config, "llm_endpoint", "http://localhost:11434/v1"),
        )
        model_name = os.environ.get(
            "CIRIS_OPENAI_MODEL_NAME_2",
            self._get_llm_service_config_value(config, "llm_model", "llama3.2"),
        )

        # Create config
        llm_config = OpenAIConfig(
            base_url=base_url,
            model_name=model_name,
            api_key=api_key,
            instructor_mode=os.environ.get("INSTRUCTOR_MODE", "JSON"),
            timeout_seconds=self._get_llm_service_config_value(config, "llm_timeout", 60),
            max_retries=self._get_llm_service_config_value(config, "llm_max_retries", 3),
        )

        # Create and start service
        service = OpenAICompatibleClient(
            config=llm_config, telemetry_service=self.telemetry_service, time_service=self.time_service
        )
        await service.start()

        # Register with lower priority
        if self.service_registry:
            self.service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                capabilities=[LLMCapabilities.CALL_LLM_STRUCTURED],
                metadata={"provider": "openai_secondary", "model": model_name, "base_url": base_url},
            )

        logger.info(f"Secondary LLM service initialized: {model_name}")

    async def _process_pending_users_from_setup(self) -> None:
        """Process pending user creation from setup wizard.

        Checks for ~/.ciris/.ciris_pending_users.json file and creates users if found.
        This file is created by the setup wizard during first-run configuration.
        """
        import json
        from pathlib import Path

        # Check for pending users file in ~/.ciris directory
        pending_users_file = Path.home() / ".ciris" / ".ciris_pending_users.json"

        if not pending_users_file.exists():
            logger.debug("No pending users file found - skipping user creation")
            return

        try:
            logger.info("=" * 80)
            logger.info("Processing pending users from setup wizard")
            logger.info("=" * 80)

            # Read pending users data asynchronously
            async with aiofiles.open(pending_users_file, "r") as f:
                content = await f.read()
                users_data = json.loads(content)

            logger.info(f"Loaded pending users file created at: {users_data.get('created_at')}")

            # Process new user if specified
            if "new_user" in users_data:
                from ciris_engine.schemas.services.authority_core import WARole

                new_user = users_data["new_user"]
                username = new_user["username"]
                password = new_user["password"]
                role_str = new_user.get("role", "OBSERVER")

                # Map role string to WARole enum
                role_map = {
                    "ADMIN": WARole.AUTHORITY,
                    "AUTHORITY": WARole.AUTHORITY,
                    "OBSERVER": WARole.OBSERVER,
                    "USER": WARole.OBSERVER,
                }
                wa_role = role_map.get(role_str.upper(), WARole.OBSERVER)

                logger.info(f"Creating new user: {username} with role: {wa_role}")

                # Create WA certificate for the user
                wa_cert = await self.auth_service.create_wa(
                    name=username,
                    email=f"{username}@local",  # Placeholder email for local users
                    scopes=["read:any", "write:any"] if wa_role == WARole.AUTHORITY else ["read:any"],
                    role=wa_role,
                )

                # Hash password and update the WA
                password_hash = self.auth_service.hash_password(password)
                await self.auth_service.update_wa(wa_id=wa_cert.wa_id, password_hash=password_hash)

                logger.info(f"✅ Successfully created user: {username} (WA: {wa_cert.wa_id})")

            # Process system admin password update if specified
            if "system_admin" in users_data:
                admin_data = users_data["system_admin"]
                admin_username = admin_data["username"]
                new_password = admin_data["password"]

                logger.info(f"Updating system admin password for: {admin_username}")

                # Find the admin WA by username
                all_was = await self.auth_service.list_was(active_only=True)
                admin_wa = next((wa for wa in all_was if wa.name == admin_username), None)

                if admin_wa:
                    # Hash new password and update
                    password_hash = self.auth_service.hash_password(new_password)
                    await self.auth_service.update_wa(wa_id=admin_wa.wa_id, password_hash=password_hash)
                    logger.info(f"✅ Successfully updated admin password for {admin_username}")
                else:
                    logger.warning(f"⚠️  Admin user '{admin_username}' not found")

            # Delete the pending users file after processing
            pending_users_file.unlink()
            logger.info("Deleted pending users file after successful processing")
            logger.info("=" * 80)

        except Exception as e:
            logger.error(f"Error processing pending users file: {e}", exc_info=True)
            # Don't delete the file if processing failed - allow retry on next startup
            raise

    async def _initialize_audit_services(self, config: Any, agent_id: str) -> None:
        """Initialize the consolidated audit service with three storage backends.

        The single GraphAuditService writes to three places:
        1. SQLite hash chain database (cryptographic integrity)
        2. Graph memory via MemoryBus (primary storage, searchable)
        3. File export (optional, for compliance)
        """
        # Initialize the consolidated GraphAuditService
        logger.info("Initializing consolidated GraphAuditService...")

        # The GraphAuditService combines all audit functionality:
        # - Graph-based storage (primary)
        # - Optional file export for compliance
        # - Cryptographic hash chain for integrity
        # - Time-series capabilities built-in
        # Use config accessor for audit configuration
        assert self.config_accessor is not None
        audit_db_path = await self.config_accessor.get_path("database.audit_db", Path("data/ciris_audit.db"))
        audit_key_path = await self.config_accessor.get_path("security.audit_key_path", Path(".ciris_keys"))
        retention_days = await self.config_accessor.get_int("security.audit_retention_days", 90)

        from ciris_engine.logic.services.graph.audit_service import GraphAuditService

        # Use platform-aware path for audit log export (critical for Android)
        audit_export_path = get_data_dir() / "audit_logs.jsonl"
        graph_audit = GraphAuditService(
            memory_bus=None,  # Will be set via service registry
            time_service=self.time_service,
            export_path=str(audit_export_path),  # Platform-aware audit log path
            export_format="jsonl",
            enable_hash_chain=True,
            db_path=str(audit_db_path),
            key_path=str(audit_key_path),
            retention_days=retention_days,
        )
        # Runtime will be set later when available
        # Attach service registry using protocol pattern
        # Use hasattr (protocol is not @runtime_checkable)
        if self.service_registry and hasattr(graph_audit, "attach_registry"):
            await graph_audit.attach_registry(self.service_registry)
        await graph_audit.start()
        self._services_started_count += 1
        self.audit_service = graph_audit
        _log_service_started(8, "AuditService")

        # Update BusManager with the initialized audit service
        if self.bus_manager is not None:
            self.bus_manager.audit_service = self.audit_service
            logger.info(f"Updated BusManager with audit_service: {self.audit_service}")

        # Inject graph audit service into incident capture handlers
        from ciris_engine.logic.utils.incident_capture_handler import inject_graph_audit_service_to_handlers

        updated_handlers = inject_graph_audit_service_to_handlers(self.audit_service)
        logger.info(f"Injected graph audit service into {updated_handlers} incident capture handler(s)")

        # Audit sink manager removed - GraphAuditService handles its own lifecycle
        logger.info("GraphAuditService handles its own retention and cleanup")

        # Initialize incident management service (processes audit events as incidents)
        from ciris_engine.logic.services.graph.incident_service import IncidentManagementService

        assert self.bus_manager is not None
        self.incident_management_service = IncidentManagementService(
            memory_bus=self.bus_manager.memory, time_service=self.time_service
        )
        await self.incident_management_service.start()
        self._services_started_count += 1
        _log_service_started(10, "IncidentManagement")

    def verify_core_services(self) -> bool:
        """Verify all core services are operational."""
        try:
            # Check service registry
            if not self.service_registry:
                logger.error("Service registry not initialized")
                return False

            # Check critical services (LLM service is optional during first-run)
            from typing import Any, List

            from ciris_engine.logic.setup.first_run import is_first_run

            # Use named dict for better error messages
            critical_services: dict[str, Any] = {
                "telemetry_service": self.telemetry_service,
                "memory_service": self.memory_service,
                "secrets_service": self.secrets_service,
                "adaptive_filter_service": self.adaptive_filter_service,
            }

            # Only require LLM service if not in first-run mode
            if not is_first_run():
                critical_services["llm_service"] = self.llm_service
            elif not self.llm_service:
                logger.info("LLM service not initialized (first-run mode - will be initialized after setup)")

            for name, service in critical_services.items():
                if not service:
                    logger.error(f"Critical service '{name}' not initialized (is None)")
                    return False

            # Verify audit service
            if not self.audit_service:
                logger.error("Audit service not initialized")
                return False

            logger.info("✓ All core services verified")
            return True
        except Exception as e:
            logger.error(f"Core services verification failed: {e}")
            return False

    def _find_service_manifest(self, service_name: str, discovered_services: List[Any]) -> Any:
        """Find matching service manifest by normalized name.

        Args:
            service_name: Name to search for
            discovered_services: List of discovered service manifests

        Returns:
            Matching manifest or None
        """
        search_name_normalized = service_name.lower().replace("_adapter", "")
        for svc in discovered_services:
            svc_name_normalized = svc.module.name.lower().replace("_adapter", "")
            if svc_name_normalized == search_name_normalized:
                return svc
        return None

    def _register_tool_service(self, service_instance: Any, manifest: Any, service_def: Any) -> None:
        """Register a TOOL service with ServiceRegistry."""
        if not self.service_registry:
            return

        logger.info(f"Registering {manifest.module.name} as TOOL service")
        from ciris_engine.logic.registries.base import Priority

        priority_map = {
            "CRITICAL": Priority.CRITICAL,
            "HIGH": Priority.HIGH,
            "NORMAL": Priority.NORMAL,
            "LOW": Priority.LOW,
        }

        priority_value = (
            service_def.priority.value if hasattr(service_def.priority, "value") else service_def.priority.name
        )
        priority = priority_map.get(priority_value, Priority.NORMAL)

        self.service_registry.register_service(
            service_type=ServiceType.TOOL,
            provider=service_instance,
            priority=priority,
            capabilities=service_def.capabilities,
        )

    def _register_communication_service(self, service_instance: Any, manifest: Any, service_def: Any) -> None:
        """Register a COMMUNICATION service with ServiceRegistry."""
        if not self.service_registry:
            return

        logger.info(f"Registering {manifest.module.name} as COMMUNICATION service")
        from ciris_engine.logic.registries.base import Priority

        priority_map = {
            "CRITICAL": Priority.CRITICAL,
            "HIGH": Priority.HIGH,
            "NORMAL": Priority.NORMAL,
            "LOW": Priority.LOW,
        }

        priority_value = (
            service_def.priority.value if hasattr(service_def.priority, "value") else service_def.priority.name
        )
        priority = priority_map.get(priority_value, Priority.NORMAL)

        self.service_registry.register_service(
            service_type=ServiceType.COMMUNICATION,
            provider=service_instance,
            priority=priority,
            capabilities=service_def.capabilities,
        )

    def _register_llm_service(self, service_instance: Any, manifest: Any, service_def: Any) -> None:
        """Register an LLM service with ServiceRegistry."""
        if not self.service_registry:
            return

        logger.info(f"Registering {manifest.module.name} as LLM service")
        from ciris_engine.logic.registries.base import Priority

        priority_map = {
            "CRITICAL": Priority.CRITICAL,
            "HIGH": Priority.HIGH,
            "NORMAL": Priority.NORMAL,
            "LOW": Priority.LOW,
        }
        priority_value = (
            service_def.priority.value if hasattr(service_def.priority, "value") else service_def.priority.name
        )
        priority = priority_map.get(priority_value, Priority.NORMAL)

        self.service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=service_instance,
            priority=priority,
            capabilities=service_def.capabilities,
        )

    def _register_adapter(self, service_instance: Any, manifest: Any, service_def: Any) -> None:
        """Register a adapter with the appropriate bus/registry based on type."""
        if service_def.type == ServiceType.TOOL:
            self._register_tool_service(service_instance, manifest, service_def)
        elif service_def.type == ServiceType.COMMUNICATION:
            self._register_communication_service(service_instance, manifest, service_def)
        elif service_def.type == ServiceType.LLM:
            self._register_llm_service(service_instance, manifest, service_def)

    async def _load_adapter(self, service_name: str) -> None:
        """Load a adapter and register its services with appropriate buses.

        Args:
            service_name: Name of the adapter to load (e.g. "reddit_adapter")
        """
        from ciris_engine.logic.runtime.adapter_loader import AdapterLoader

        logger.info(f"Loading adapter: {service_name}")

        # Discover and find the service
        adapter_loader = AdapterLoader()
        discovered_services = adapter_loader.discover_services()

        manifest = self._find_service_manifest(service_name, discovered_services)
        if not manifest:
            raise ValueError(f"Adapter '{service_name}' not found")

        logger.info(f"Found manifest for adapter '{manifest.module.name}'")

        # Load each service defined in the manifest
        for service_def in manifest.services:
            try:
                # Load the specific service class for this service definition
                service_class = adapter_loader.load_service_class(manifest, service_def.class_path)
                if not service_class:
                    logger.error(f"Failed to load service class for {manifest.module.name}")
                    continue

                # Instantiate the service (services usually need minimal initialization)
                # Most adapters are self-contained and load config from env
                # Some services (like observers) may need runtime dependencies
                try:
                    # Try to inject runtime dependencies if the service accepts them
                    # Cast to Any for duck-typed optional runtime dependency injection
                    from typing import Any, cast

                    service_instance = cast(Any, service_class)(
                        bus_manager=self.bus_manager,
                        memory_service=self.memory_service,
                        agent_id=None,  # Will be set by observer from identity service
                        filter_service=self.adaptive_filter_service,
                        secrets_service=self.secrets_service,
                        time_service=self.time_service,
                        agent_occurrence_id=self.essential_config.agent_occurrence_id,
                    )
                except TypeError:
                    # Service doesn't accept runtime dependencies, instantiate without them
                    service_instance = service_class()

                # Start the service before registration to initialize resources (HTTP clients, credentials, etc.)
                if hasattr(service_instance, "start"):
                    start_result = service_instance.start()
                    # Handle both async and sync start methods
                    if hasattr(start_result, "__await__"):
                        await start_result
                    logger.info(f"Started adapter {manifest.module.name}")

                # Register with appropriate bus based on service type
                self._register_adapter(service_instance, manifest, service_def)

                logger.info(f"Successfully loaded and registered adapter: {manifest.module.name}")
                self.loaded_modules.append(f"modular:{service_name}")

            except Exception as e:
                logger.error(
                    f"Failed to load service {service_def.class_path} from {manifest.module.name}: {e}", exc_info=True
                )
                raise

    async def load_modules(self, modules: List[str], disable_core_on_mock: bool = True) -> None:
        """Load external modules with MOCK safety checks.

        Args:
            modules: List of module names to load (e.g. ["mockllm", "custom_tool", "modular:reddit_adapter"])
            disable_core_on_mock: If True, MOCK modules disable core services
        """
        if not self.module_loader:
            from ciris_engine.logic.runtime.module_loader import ModuleLoader

            self.module_loader = ModuleLoader()

        for module_name in modules:
            try:
                # Check if this is a adapter
                if module_name.startswith("modular:"):
                    service_name = module_name[8:]  # Remove "modular:" prefix
                    await self._load_adapter(service_name)
                    continue

                # Load module with safety checks
                if self.module_loader.load_module(module_name, disable_core_on_mock):
                    # Initialize services from module
                    result = await self.module_loader.initialize_module_services(module_name, self.service_registry)

                    if result.success:
                        self.loaded_modules.append(module_name)
                        logger.info(f"Module {module_name} loaded with {len(result.services_loaded)} services")

                        # Store first LLM service for compatibility
                        # Need to get actual service instance from registry
                        for service_meta in result.services_loaded:
                            if service_meta.service_type == ServiceType.LLM:
                                # Get the actual service from registry
                                if self.service_registry:
                                    providers = self.service_registry.get_services_by_type(ServiceType.LLM)
                                    if providers:
                                        self.llm_service = providers[0]  # First provider
                                        break
                    else:
                        logger.error(f"Failed to initialize services from {module_name}: {result.errors}")
                        for warning in result.warnings:
                            logger.warning(warning)
                else:
                    logger.error(f"Failed to load module: {module_name}")

            except Exception as e:
                logger.error(f"Error loading module {module_name}: {e}")
                raise

        # Display MOCK warnings if any
        if self.module_loader is not None:
            warnings = self.module_loader.get_mock_warnings()
            for warning in warnings:
                logger.warning(warning)

    def register_core_services(self) -> None:
        """Register core services in the service registry."""
        if not self.service_registry:
            return

        # Infrastructure services are single-instance - NO ServiceRegistry needed
        # Direct references only per "No Exceptions" principle

        # Memory service already registered above with full capabilities in initialize_all_services()
        # Don't re-register as it would overwrite the full capability list

        # Audit service is single-instance - NO ServiceRegistry needed

        # Telemetry service is single-instance - NO ServiceRegistry needed

        # Register LLM service(s) - handled by _initialize_llm_services

        # Secrets service is single-instance - NO ServiceRegistry needed

        # Adaptive filter service is single-instance - NO ServiceRegistry needed

        # Register WA service - can have multiple wisdom sources
        if self.wa_auth_system:
            self.service_registry.register_service(
                service_type=ServiceType.WISE_AUTHORITY,
                provider=self.wa_auth_system,
                priority=Priority.CRITICAL,
                capabilities=[
                    "authenticate",
                    "verify_token",
                    "provision_certificate",
                    "handle_deferral",
                    "provide_guidance",
                    "oauth_flow",
                    "send_deferral",
                    "get_pending_deferrals",
                    "resolve_deferral",
                ],
                metadata={"service_name": "WiseAuthorityService"},
            )

        # Config service is single-instance - NO ServiceRegistry needed
        # But it's used by RuntimeControlService so needs to be accessible

        # Transaction orchestrator is single-instance - NO ServiceRegistry needed

        # Register SecretsToolService for core secrets tools
        if self.secrets_tool_service:
            self.service_registry.register_service(
                service_type=ServiceType.TOOL,
                provider=self.secrets_tool_service,
                priority=Priority.HIGH,
                capabilities=[
                    "execute_tool",
                    "get_available_tools",
                    "get_tool_result",
                    "validate_parameters",
                    "get_tool_info",
                    "get_all_tool_info",
                ],
                metadata={"service_name": "SecretsToolService", "provider": "core"},
            )
            logger.info("SecretsToolService registered in ServiceRegistry")

        # Register ConsentService as a tool service (v1.4.6)
        if self.consent_service:
            self.service_registry.register_service(
                service_type=ServiceType.TOOL,
                provider=self.consent_service,
                priority=Priority.HIGH,
                capabilities=[
                    "execute_tool",
                    "get_available_tools",
                    "upgrade_relationship",
                    "degrade_relationship",
                ],
                metadata={"service_name": "ConsentService", "provider": "core"},
            )
            logger.info("ConsentService registered in ServiceRegistry as TOOL service")

        # Task scheduler is single-instance - NO ServiceRegistry needed

        # Incident management is single-instance - NO ServiceRegistry needed

    async def _migrate_config_to_graph(self) -> None:
        """Migrate essential config to graph for runtime management."""
        if not self.config_service:
            logger.warning("Cannot migrate config - GraphConfigService not available")
            return

        logger.info("Migrating essential configuration to graph...")

        # Migrate each config section
        config_dict = self.essential_config.model_dump()

        for section_name, section_data in config_dict.items():
            if isinstance(section_data, dict):
                # Migrate each key in the section
                for key, value in section_data.items():
                    full_key = f"{section_name}.{key}"
                    await self.config_service.set_config(
                        key=full_key,
                        value=value,  # Pass raw value, set_config will wrap it
                        updated_by="system_bootstrap",
                    )
                    logger.debug(f"Migrated config: {full_key}")
            else:
                # Top-level config value
                await self.config_service.set_config(
                    key=section_name,
                    value=section_data,  # Pass raw value, set_config will wrap it
                    updated_by="system_bootstrap",
                )
                logger.debug(f"Migrated config: {section_name}")

        logger.info("Configuration migration complete")

    def get_metrics(self) -> Dict[str, float]:
        """Get initializer metrics from the v1.4.3 set.

        Returns EXACTLY these metrics:
        - initializer_services_started: Services started count
        - initializer_startup_time_ms: Total startup time
        - initializer_errors: Initialization errors
        - initializer_dependencies_resolved: Dependencies resolved
        """
        # Calculate startup time in milliseconds
        startup_time_ms = 0.0
        if self._startup_start_time is not None and self._startup_end_time is not None:
            duration_seconds = self._startup_end_time - self._startup_start_time
            startup_time_ms = duration_seconds * 1000.0

        return {
            "initializer_services_started": float(self._services_started_count),
            "initializer_startup_time_ms": startup_time_ms,
            "initializer_errors": float(self._initialization_errors),
            "initializer_dependencies_resolved": float(self._dependencies_resolved),
        }
