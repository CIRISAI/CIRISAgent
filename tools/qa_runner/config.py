"""
QA Runner configuration and module definitions.
"""

from dataclasses import dataclass
from dataclasses import field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class QAModule(Enum):
    """Available QA test modules."""

    # API modules
    AUTH = "auth"
    TELEMETRY = "telemetry"
    AGENT = "agent"
    SYSTEM = "system"
    MEMORY = "memory"
    AUDIT = "audit"
    TOOLS = "tools"
    GUIDANCE = "guidance"
    CONSENT = "consent"
    DSAR = "dsar"  # DSAR automation testing
    DSAR_MULTI_SOURCE = "dsar_multi_source"  # Multi-source DSAR orchestration testing
    DSAR_TICKET_WORKFLOW = "dsar_ticket_workflow"  # DSAR ticket-based workflow testing
    PARTNERSHIP = "partnership"  # Partnership bilateral consent testing
    BILLING = "billing"
    BILLING_INTEGRATION = "billing_integration"  # Full OAuth user billing workflow
    MULTI_OCCURRENCE = "multi_occurrence"
    MESSAGE_ID_DEBUG = "message_id_debug"  # Message ID correlation debugging
    REDDIT = "reddit"  # Reddit adapter testing
    SQL_EXTERNAL_DATA = "sql_external_data"  # SQL external data service testing
    SETUP = "setup"  # Setup wizard testing (first-run configuration)
    STATE_TRANSITIONS = "state_transitions"  # Cognitive state behavior testing
    COGNITIVE_STATE_API = "cognitive_state"  # Cognitive state transition API testing
    MCP = "mcp"  # MCP (Model Context Protocol) adapter testing
    ADAPTER_CONFIG = "adapter_config"  # Adapter interactive configuration workflow testing
    ADAPTER_AUTOLOAD = "adapter_autoload"  # Adapter persistence and auto-load on restart testing
    ADAPTER_MANIFEST = "adapter_manifest"  # Adapter manifest validation (all adapters)
    ADAPTER_AVAILABILITY = "adapter_availability"  # Adapter availability, eligibility & installation testing
    IDENTITY_UPDATE = "identity_update"  # Identity update from template testing (--identity-update flag)
    CONTEXT_ENRICHMENT = "context_enrichment"  # Context enrichment tool testing
    VISION = "vision"  # Native multimodal vision testing
    AIR = "air"  # AIR (Artificial Interaction Reminder) parasocial prevention testing
    ACCORD = "accord"  # Accord invocation system (unfilterable kill switch) testing
    ACCORD_METRICS = "accord_metrics"  # Accord metrics trace capture and signing testing
    SYSTEM_MESSAGES = "system_messages"  # System message visibility for UI/UX testing
    HOSTED_TOOLS = "hosted_tools"  # CIRIS hosted tools (web search via proxy) testing
    UTILITY_ADAPTERS = "utility_adapters"  # Weather and navigation adapters testing
    HOMEASSISTANT_AGENTIC = "homeassistant_agentic"  # Live Home Assistant + Music Assistant integration testing
    DEFERRAL_TAXONOMY = "deferral_taxonomy"  # DSASPDMA rights/needs taxonomy coverage and routing tests
    HE300_BENCHMARK = "he300_benchmark"  # HE-300 ethical benchmark via A2A adapter
    CIRISNODE = "cirisnode"  # CIRISNode integration testing (deferral routing, trace forwarding)
    LICENSED_AGENT = "licensed_agent"  # Licensed agent device auth (RFC 8628) flow testing
    WALLET = "wallet"  # Wallet adapter testing (x402, validation, spending limits)
    DEGRADED_MODE = "degraded_mode"  # Degraded mode behavior testing (no LLM provider)
    MODEL_EVAL = "model_eval"  # Model quality evaluation with tough questions (requires --live)
    PARALLEL_LOCALES = "parallel_locales"  # 29-locale parallel multi-turn convo (per-user channels)
    SAFETY_BATTERY = "safety_battery"  # Run a canonical safety battery (cirisnodecore/SCHEMA.md §11) against the agent via A2A
    SAFETY_INTERPRET = "safety_interpret"  # Apply a rubric's criteria.json to a capture bundle; emit signed verdicts (cirisnodecore/FSD/INTERPRETER_AGENT.md)
    SECRETS_ENCRYPTION = "secrets_encryption"  # Secrets encryption testing (CIRISVerify v1.6.0+)
    MEMORY_BENCHMARK = "memory_benchmark"  # Memory usage benchmark under message load

    # Cognitive state live testing modules
    SOLITUDE_LIVE = "solitude_live"  # SOLITUDE state behavior testing
    PLAY_LIVE = "play_live"  # PLAY state behavior testing
    DREAM_LIVE = "dream_live"  # DREAM state behavior testing

    # Handler modules
    HANDLERS = "handlers"
    DEFERRAL = "deferral"  # Time-based deferral and TaskSchedulerService testing

    # Filter modules
    FILTERS = "filters"

    # SDK modules
    SDK = "sdk"

    # Extended modules
    EXTENDED_API = "extended_api"
    PAUSE_STEP = "pause_step"
    SINGLE_STEP_SIMPLE = "single_step_simple"
    SINGLE_STEP_COMPREHENSIVE = "single_step_comprehensive"
    STREAMING = "streaming"  # H3ERE pipeline streaming verification
    L4_ATTESTATION = "l4_attestation"  # Algorithm A (verify_tree) runtime contract — staged-QA L3+ floor + cache-population guard

    # Full suites
    API_FULL = "api_full"
    ALL = "all"


@dataclass
class QATestCase:
    """Definition of a QA test case."""

    name: str
    module: QAModule
    endpoint: str
    method: str = "GET"
    payload: Optional[Dict] = None
    expected_status: int = 200
    requires_auth: bool = True
    description: Optional[str] = None
    timeout: float = 30.0

    # Advanced validation
    validation_rules: Optional[Dict[str, Callable[[Dict], bool]]] = None
    custom_validation: Optional[Callable] = None
    custom_handler: Optional[str] = None  # For CUSTOM method tests

    # Test execution options
    repeat_count: int = 1


@dataclass
class QAConfig:
    """Configuration for QA runner."""

    # Server configuration
    base_url: str = "http://localhost:8080"  # Matches DEFAULT_API_PORT in constants.py
    api_port: int = 8080  # Default API port (matches DEFAULT_API_PORT in constants.py)

    # Authentication
    # QA runner always wipes data and uses setup wizard to create test user
    # with these known credentials
    admin_username: str = "jeff"
    admin_password: str = "qa_test_password_12345"

    # OAuth test user configuration (for billing integration tests)
    oauth_test_user_id: str = "google:999888777666555444"
    oauth_test_email: str = "test.billing@example.com"
    oauth_test_provider: str = "google"
    oauth_test_external_id: str = "999888777666555444"

    # Billing backend configuration (for billing integration tests)
    billing_enabled: bool = False
    billing_api_key: Optional[str] = None
    billing_api_url: str = "https://billing.ciris.ai"

    # Test configuration
    parallel_tests: bool = False
    max_workers: int = 4
    timeout: float = 300.0  # 5 minutes total timeout
    retry_count: int = 3
    retry_delay: float = 2.0

    # Output configuration
    verbose: bool = False
    json_output: bool = False
    html_report: bool = False
    report_dir: Path = Path("qa_reports")

    # Server management
    auto_start_server: bool = True
    server_startup_timeout: float = (
        600.0  # Wakeup with rate-limited LLM: 60 LLM calls × ~40K tokens = 2.4M tokens, at 300K TPM = ~8-10 min
    )
    mock_llm: bool = True
    adapter: str = "api"
    wipe_data: bool = False  # Wipe data directory before starting server

    # Staged-environment mode
    # When set, APIServerManager launches the server from a venv built off the
    # canonical staged tree (tools.dev.stage_runtime → wheel → venv) instead of
    # `sys.executable main.py` from the dev tree. Validates that the SHIPPED
    # wheel passes QA, not just the source tree. Use Any to avoid a circular
    # import at module-load time; the actual type is StagedEnvironment from
    # tools.qa_runner.staged_env.
    staged_env: Optional[Any] = None

    # Database backend configuration (for parallel testing)
    database_backends: List[str] = None  # None = ["sqlite"], or ["sqlite", "postgres"] for parallel
    postgres_url: str = "postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db"
    postgres_port: int = 8001  # Port for PostgreSQL backend server (SQLite uses api_port)
    parallel_backends: bool = False  # Run backend tests in parallel instead of sequentially

    # Live LLM configuration (--live flag)
    live_api_key: Optional[str] = None
    live_model: Optional[str] = None
    live_base_url: Optional[str] = None
    live_provider: Optional[str] = None  # "openai", "anthropic", "google", or auto-detect from base_url

    # Live Lens configuration (--live-lens flag for accord_metrics tests)
    # When True, uses https://lens.ciris-services-1.ai/lens-api/api/v1 instead of mock logshipper
    live_lens: bool = False

    # Live CIRISNode configuration (--live-node flag for cirisnode tests)
    # When True, runs additional tests against live CIRISNode server
    live_node: bool = False

    # Live Portal configuration (--live-portal flag for licensed_agent tests)
    # When True, runs tests against live CIRISPortal server
    live_portal: bool = False

    # Fail-fast configuration
    fail_fast: bool = True  # Exit on first test failure (use --proceed-anyway to disable)
    test_timeout: float = 30.0  # Timeout for individual test interactions

    # Memory benchmark configuration
    message_count: int = 100  # Number of messages to send in memory benchmark
    concurrent_channels: int = 4  # Number of concurrent channels for parallel testing

    # Model evaluation configuration
    model_eval_languages: List[str] = field(default_factory=lambda: ["am", "zh", "en", "es"])
    model_eval_concurrency: int = 6
    model_eval_profile_memory: bool = True
    # Filter the model_eval question set by category (exact match, case-insensitive).
    # Empty list = run all curated questions. Use to scope a run to a single
    # topic e.g. ["RLHFTradeoffs"] for one bias-torque axis, or two like
    # ["BenchmarkLegitimacy","ArchitectureTradeoffs"]. Combine with
    # --model-eval-languages to run a single (question, language) pair for
    # tight iteration loops.
    model_eval_question_categories: List[str] = field(default_factory=list)
    # Optional path to an external JSON questions file. When set, overrides
    # the in-tree EVAL_QUESTIONS default. Sensitive / attractor-bait
    # question sets live out-of-tree; point this at e.g.
    # `~/bounce-test/model_eval_questions/v1_sensitive.json`.
    model_eval_questions_file: Optional[str] = None

    # Safety battery configuration. Loads a canonical battery from
    # tests/safety/{lang_eng}_{domain}/v{N}_*_arc.json and runs each question
    # through the agent via /v1/agent/interact. See cirisnodecore/SCHEMA.md §11.
    safety_battery_lang: str = "am"  # ISO 639-1 from manifest.json
    safety_battery_domain: str = "mental_health"  # cell's domain axis
    safety_battery_template: str = "default"  # template_id for the agent persona

    # Safety interpret module configuration. See cirisnodecore/FSD/JUDGE_MODEL.md.
    # Reads a capture bundle (produced by safety_battery) and applies the
    # rubric's criteria.json to each (response, criterion) pair. The
    # judge is a foundation model (default Claude Opus 4.7) called
    # directly — NOT a CIRIS agent.
    safety_interpret_capture_dir: Optional[str] = None  # required when module selected
    safety_interpret_criteria_file: Optional[str] = None  # override; default resolved from BatteryManifest
    safety_interpret_anthropic_key_file: Optional[str] = None  # default ~/.anthropic_key
    safety_interpret_judge_model: Optional[str] = None  # default claude-opus-4-7

    # Setup-wizard template_id (read by server.py during setup completion).
    # Modules that need a non-default template should set this; today only
    # safety_battery uses it (see runner.py SAFETY_BATTERY construction case).
    setup_template_id: Optional[str] = None

    def get_module_tests(self, module: QAModule, admin_password: Optional[str] = None) -> List[QATestCase]:
        """Get test cases for a specific module.

        Args:
            module: The QA module to get tests for.
            admin_password: The admin password to use for auth tests.
                           If None, uses the config's admin_password.
        """
        from .modules import APITestModule, HandlerTestModule, SDKTestModule
        from .modules.comprehensive_api_tests import ComprehensiveAPITestModule
        from .modules.comprehensive_single_step_tests import ComprehensiveSingleStepTestModule
        from .modules.filter_tests import FilterTestModule
        from .modules.multi_occurrence_tests import MultiOccurrenceTestModule
        from .modules.setup_tests import SetupTestModule
        from .modules.simple_single_step_tests import SimpleSingleStepTestModule

        effective_password = admin_password or self.admin_password
        effective_username = self.admin_username

        # API test modules
        if module == QAModule.AUTH:
            return APITestModule.get_auth_tests(admin_username=effective_username, admin_password=effective_password)
        elif module == QAModule.TELEMETRY:
            return APITestModule.get_telemetry_tests()
        elif module == QAModule.AGENT:
            return APITestModule.get_agent_tests()
        elif module == QAModule.SYSTEM:
            return APITestModule.get_system_tests()
        elif module == QAModule.MEMORY:
            return APITestModule.get_memory_tests()
        elif module == QAModule.AUDIT:
            return APITestModule.get_audit_tests()
        elif module == QAModule.TOOLS:
            return APITestModule.get_tool_tests()
        elif module == QAModule.GUIDANCE:
            return APITestModule.get_guidance_tests()
        elif module == QAModule.SETUP:
            return SetupTestModule.get_setup_tests()
        elif module == QAModule.CONSENT:
            # Consent tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.DSAR:
            # DSAR tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.DSAR_MULTI_SOURCE:
            # DSAR multi-source tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.DSAR_TICKET_WORKFLOW:
            # DSAR ticket workflow tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.PARTNERSHIP:
            # Partnership tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.BILLING:
            # Billing tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.BILLING_INTEGRATION:
            # Billing integration tests use SDK client with OAuth user
            return []  # Will be handled separately by runner
        elif module == QAModule.MULTI_OCCURRENCE:
            return MultiOccurrenceTestModule.get_all_multi_occurrence_tests()
        elif module == QAModule.MESSAGE_ID_DEBUG:
            # Message ID debug tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.REDDIT:
            # Reddit tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.SQL_EXTERNAL_DATA:
            # SQL external data tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.STATE_TRANSITIONS:
            # State transition tests use SDK client pattern
            return []  # Will be handled separately by runner
        elif module == QAModule.MCP:
            # MCP tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.ADAPTER_CONFIG:
            # Adapter configuration tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.ADAPTER_AUTOLOAD:
            # Adapter auto-load tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.ADAPTER_MANIFEST:
            # Adapter manifest validation tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.IDENTITY_UPDATE:
            # Identity update tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.VISION:
            # Vision tests use direct API calls
            return []  # Will be handled separately by runner
        elif module == QAModule.AIR:
            # AIR parasocial prevention tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.ACCORD:
            # Accord tests run standalone (no server needed)
            return []  # Will be handled separately by runner
        elif module == QAModule.ACCORD_METRICS:
            # Accord metrics trace capture tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.SYSTEM_MESSAGES:
            # System messages visibility tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.HOSTED_TOOLS:
            # CIRIS hosted tools tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.UTILITY_ADAPTERS:
            # Utility adapters (weather, navigation) tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.HE300_BENCHMARK:
            from .modules.he300_benchmark_tests import HE300BenchmarkModule

            return HE300BenchmarkModule.get_he300_benchmark_tests()
        elif module == QAModule.CIRISNODE:
            # CIRISNode integration tests use SDK client
            return []  # Will be handled separately by runner
        elif module == QAModule.DEGRADED_MODE:
            # Degraded mode tests use SDK client
            return []  # Will be handled separately by runner

        # Handler test modules
        elif module == QAModule.HANDLERS:
            return HandlerTestModule.get_handler_tests()

        # Filter test modules
        elif module == QAModule.FILTERS:
            return FilterTestModule.get_filter_tests()

        # SDK test modules
        elif module == QAModule.SDK:
            return SDKTestModule.get_sdk_tests(admin_username=effective_username, admin_password=effective_password)

        # Extended API tests
        elif module == QAModule.EXTENDED_API:
            return ComprehensiveAPITestModule.get_all_extended_tests()

        # Pause/step testing (redirected to comprehensive single-step)
        elif module == QAModule.PAUSE_STEP:
            return ComprehensiveSingleStepTestModule.get_comprehensive_single_step_tests()

        # Simple single-step testing
        elif module == QAModule.SINGLE_STEP_SIMPLE:
            return SimpleSingleStepTestModule.get_simple_single_step_tests()

        # Comprehensive single-step testing
        elif module == QAModule.SINGLE_STEP_COMPREHENSIVE:
            return ComprehensiveSingleStepTestModule.get_comprehensive_single_step_tests()

        # Streaming verification
        elif module == QAModule.STREAMING:
            from .modules.streaming_verification import StreamingVerificationModule

            return StreamingVerificationModule.get_streaming_verification_tests()

        # L4 attestation contract (verify_tree / Algorithm A)
        elif module == QAModule.L4_ATTESTATION:
            from .modules.l4_attestation_tests import L4AttestationModule

            return L4AttestationModule.get_l4_attestation_tests()

        # Aggregate modules
        elif module == QAModule.API_FULL:
            tests = []
            for m in [
                QAModule.AUTH,
                QAModule.TELEMETRY,
                QAModule.AGENT,
                QAModule.SYSTEM,
                QAModule.MEMORY,
                QAModule.AUDIT,
                QAModule.TOOLS,
                QAModule.GUIDANCE,
            ]:
                tests.extend(self.get_module_tests(m))
            return tests

        elif module == QAModule.ALL:
            tests = []
            # Run all modules in sequence - comprehensive test suite
            for m in [
                # Streaming tests FIRST (requires clean queue state)
                QAModule.STREAMING,
                # L4 attestation contract — runs early so failures surface
                # before downstream modules waste cycles against a broken
                # attestation cache.
                QAModule.L4_ATTESTATION,
                # Core API modules
                QAModule.AUTH,
                QAModule.TELEMETRY,
                QAModule.AGENT,
                QAModule.SYSTEM,
                QAModule.MEMORY,
                QAModule.AUDIT,
                QAModule.TOOLS,
                QAModule.GUIDANCE,
                QAModule.CONSENT,
                QAModule.DSAR,
                QAModule.DSAR_MULTI_SOURCE,
                QAModule.PARTNERSHIP,
                QAModule.BILLING,
                QAModule.REDDIT,
                QAModule.SQL_EXTERNAL_DATA,
                QAModule.MULTI_OCCURRENCE,
                # Handler modules
                QAModule.HANDLERS,
                # Filter modules
                QAModule.FILTERS,
                # SDK modules
                QAModule.SDK,
                # Extended modules
                QAModule.EXTENDED_API,
                QAModule.SINGLE_STEP_SIMPLE,
                QAModule.SINGLE_STEP_COMPREHENSIVE,
            ]:
                tests.extend(self.get_module_tests(m))
            return tests

        return []
