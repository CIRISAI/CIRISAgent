"""
QA Runner CLI interface.
"""

import argparse
import sys
from pathlib import Path
from typing import List

from .config import QAConfig, QAModule
from .runner import QARunner
from .status_tracker import get_failing_modules, get_not_run_modules, print_status_dashboard


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="CIRIS QA Test Runner - Modular quality assurance testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show QA status dashboard
  python -m tools.qa_runner --status

  # List failing modules
  python -m tools.qa_runner --failing

  # List modules that haven't been run
  python -m tools.qa_runner --not-run

  # Run everything (default)
  python -m tools.qa_runner

  # Run all API tests
  python -m tools.qa_runner api_full

  # Run specific modules
  python -m tools.qa_runner auth telemetry agent

  # Run handler tests
  python -m tools.qa_runner handlers

  # Run with custom configuration
  python -m tools.qa_runner auth --url http://localhost:8080 --no-auto-start

  # Run in parallel with JSON output
  python -m tools.qa_runner --parallel --json --report-dir ./reports

  # Run tests against both SQLite and PostgreSQL backends (automatically parallel)
  python -m tools.qa_runner auth --database-backends sqlite postgres

Available modules:
  auth            - Authentication endpoints
  telemetry       - Telemetry and metrics
  agent           - Agent interaction
  system          - System management
  memory          - Memory operations
  audit           - Audit trail
  tools           - Tool management
  tasks           - Task management
  guidance        - Guidance system
  consent         - Consent management
  dsar            - DSAR automation
  partnership     - Partnership management
  billing         - Billing and credit system
  reddit          - Reddit adapter testing
  sql_external_data - SQL external data service testing
  handlers        - Message handlers
  simple_handlers - Simple handler tests
  streaming       - H3ERE pipeline streaming verification
  sdk             - SDK tests
  pause_step      - Enhanced single-step/pause debugging
  single_step_comprehensive - Complete 17-phase ACCORD single-step validation
  accord        - Accord invocation system (kill switch) tests
  accord_metrics - Accord metrics trace capture and signing
  homeassistant_agentic - Live Home Assistant configuration and Music Assistant verification
  deferral_taxonomy - DSASPDMA taxonomy coverage and localized deferral classification
  cirisnode       - CIRISNode integration (deferral routing, trace forwarding)
  licensed_agent  - Licensed agent device auth (RFC 8628) flow testing
  model_eval      - Model quality evaluation with tough questions (requires --live)
  api_full        - All API modules
  handlers_full   - All handler modules
  all             - Everything
""",
    )

    parser.add_argument("modules", nargs="*", default=["all"], help="Modules to test (default: all)")

    # Status dashboard
    parser.add_argument("--status", action="store_true", help="Display QA status dashboard and exit")
    parser.add_argument("--failing", action="store_true", help="List only failing modules and exit")
    parser.add_argument("--not-run", action="store_true", help="List modules that haven't been run and exit")

    # Server configuration
    parser.add_argument(
        "--url", default="http://localhost:8080", help="Base URL of the API server (default: http://localhost:8080)"
    )
    parser.add_argument("--port", type=int, default=8080, help="API server port (default: 8080)")
    parser.add_argument("--no-auto-start", action="store_true", help="Don't automatically start the API server")
    parser.add_argument("--no-mock-llm", action="store_true", help="Don't use mock LLM (requires real LLM)")
    parser.add_argument(
        "--adapter", default="api", choices=["api", "cli", "discord"], help="Adapter to use (default: api)"
    )

    # Staged-env mode (run server from a venv installed from the canonical staged tree)
    parser.add_argument(
        "--from-staged",
        action="store_true",
        help=(
            "Run the server under test from a venv with the wheel built from the canonical "
            "staged tree (tools.dev.stage_runtime). Validates that the shipped wheel — not "
            "the dev tree — passes QA. Staged env reused at /tmp/ciris-staged-qa across runs."
        ),
    )
    parser.add_argument(
        "--rebuild-staged",
        action="store_true",
        help="Force a clean rebuild of the staged env (implies --from-staged).",
    )
    parser.add_argument(
        "--staged-root",
        type=Path,
        default=Path("/tmp/ciris-staged-qa"),
        help="Staged env root dir (default: /tmp/ciris-staged-qa).",
    )

    # Live LLM configuration (uses real API instead of mock)
    parser.add_argument(
        "--live", action="store_true", help="Use real LLM API instead of mock. Reads key from --live-key-file"
    )
    parser.add_argument(
        "--live-key-file", default="~/.groq_key", help="Path to file containing API key (default: ~/.groq_key)"
    )
    parser.add_argument(
        "--live-model",
        default="meta-llama/llama-4-maverick-17b-128e-instruct",
        help="Model to use for live LLM (default: meta-llama/llama-4-maverick-17b-128e-instruct)",
    )
    parser.add_argument(
        "--live-base-url",
        default="https://api.groq.com/openai/v1",
        help="Base URL for LLM API (default: https://api.groq.com/openai/v1)",
    )
    parser.add_argument(
        "--live-provider",
        choices=["openai", "anthropic", "google"],
        default=None,
        help="LLM provider (auto-detected from base URL if not specified)",
    )

    # Live Lens configuration (for accord_metrics tests)
    parser.add_argument(
        "--live-lens",
        action="store_true",
        help="Use real Lens server (https://lens.ciris-services-1.ai/lens-api/api/v1) instead of mock logshipper for accord_metrics tests",
    )

    # Live CIRISNode configuration (for cirisnode tests)
    parser.add_argument(
        "--live-node",
        action="store_true",
        help="Run additional tests against live CIRISNode server (node.ciris-services-1.ai) for cirisnode tests",
    )

    # Live Portal configuration (for licensed_agent tests)
    parser.add_argument(
        "--live-portal",
        action="store_true",
        help="Run tests against live CIRISPortal server (portal.ciris.ai) for licensed_agent tests",
    )

    # Database backend configuration
    parser.add_argument(
        "--database-backends",
        nargs="+",
        choices=["sqlite", "postgres"],
        default=None,
        help="Database backends to test (default: sqlite only). Multiple backends run in parallel for proper state isolation.",
    )
    parser.add_argument(
        "--postgres-url",
        default="postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db",
        help="PostgreSQL connection URL (default: postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db)",
    )
    parser.add_argument(
        "--postgres-port",
        type=int,
        default=8001,
        help="Port for PostgreSQL backend server (default: 8001, SQLite uses --port)",
    )
    parser.add_argument(
        "--parallel-backends",
        action="store_true",
        help="(Deprecated: now automatic) Multiple backends always run in parallel for proper state isolation",
    )

    # Data management
    parser.add_argument(
        "--wipe-data",
        action="store_true",
        help="(Now automatic) Data is always wiped for clean QA state",
    )

    # Authentication
    parser.add_argument("--username", default="jeff", help="Test username (default: jeff)")
    parser.add_argument(
        "--password",
        default="__auto_detect__",
        help="Admin password (default: auto-detected from server output)",
    )

    # Test configuration
    parser.add_argument("--parallel", action="store_true", help="Run tests in parallel")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel workers (default: 4)")
    parser.add_argument("--timeout", type=float, default=300.0, help="Total timeout in seconds (default: 300)")
    parser.add_argument("--retry", type=int, default=3, help="Number of retries for failed tests (default: 3)")
    parser.add_argument(
        "--proceed-anyway",
        action="store_true",
        help="Continue running tests after first failure (default: fail-fast)",
    )
    parser.add_argument(
        "--test-timeout",
        type=float,
        default=30.0,
        help="Timeout for individual test interactions in seconds (default: 30)",
    )

    # Memory benchmark configuration
    parser.add_argument(
        "--message-count",
        type=int,
        default=100,
        help="Number of messages to send in memory_benchmark (default: 100)",
    )
    parser.add_argument(
        "--concurrent-channels",
        type=int,
        default=4,
        help="Number of concurrent channels for memory_benchmark parallel testing (default: 4)",
    )
    parser.add_argument(
        "--model-eval-languages",
        default="am,zh,en,es",
        help="Comma-separated language codes for multilingual model_eval (default: en; use e.g. am,zh,en,es for multilingual runs)",
    )
    parser.add_argument(
        "--model-eval-concurrency",
        type=int,
        default=6,
        help="Maximum simultaneous in-flight model_eval interactions (default: 6)",
    )
    parser.add_argument(
        "--no-model-eval-memory-profile",
        action="store_true",
        help="Disable memory profiling during model_eval",
    )
    parser.add_argument(
        "--model-eval-questions",
        default="",
        help=(
            "Comma-separated EvalQuestion categories to include (case-insensitive). "
            "Empty = all questions in the loaded pool. "
            "Examples: 'Theology' (one category), 'AI Ethics,Epistemology' (two)."
        ),
    )
    parser.add_argument(
        "--model-eval-questions-file",
        default="",
        help=(
            "Path to a JSON file with EvalQuestion entries to use instead of the "
            "in-tree default pool. Format: list of {category, question, evaluates, "
            "translations} objects; `translations` is an optional {lang_code: text} "
            "dict. Sensitive / attractor-bait question sets live OUT OF TREE — "
            "drop them in `~/bounce-test/model_eval_questions/*.json` or anywhere "
            "else, point this flag at the path. The in-tree default is "
            "deliberately generic (theodicy / AI ethics / epistemology only)."
        ),
    )
    # Safety battery — loads a canonical battery from tests/safety/{lang_eng}_{domain}/
    # and submits each question via /v1/agent/interact. See cirisnodecore/SCHEMA.md §11.
    parser.add_argument(
        "--safety-battery-lang",
        default="am",
        help=(
            "ISO 639-1 language code for the safety battery cell "
            "(default: am). Source of truth: ciris_engine/data/localized/manifest.json."
        ),
    )
    parser.add_argument(
        "--safety-battery-domain",
        default="mental_health",
        help=(
            "Domain axis for the safety battery cell (default: mental_health). "
            "Future cells extend the domain axis to entries from "
            "ciris_engine/logic/buses/prohibitions.py."
        ),
    )
    parser.add_argument(
        "--safety-battery-template",
        default="default",
        help=(
            "Template ID for the agent persona (default: 'default' renders "
            "the Ally persona). Joins the result-key tuple per "
            "cirisnodecore/FSD/SAFETY_BATTERY_CI_LOOP.md §2 — same cell + "
            "version + model against different templates is distinct evidence. "
            "Available: default, datum, scout, echo-speculative, echo, "
            "echo-core, sage, test."
        ),
    )
    parser.add_argument(
        "--safety-interpret-capture-dir",
        default=None,
        help=(
            "Path to a safety_battery bundle directory (the capture artifact). "
            "Required when running the safety_interpret module. The interpret "
            "module reads results.jsonl + manifest_signed.json from this dir "
            "and applies the rubric criteria to each response."
        ),
    )
    parser.add_argument(
        "--safety-interpret-criteria-file",
        default=None,
        help=(
            "Optional path to criteria.json for the safety_interpret module. "
            "If omitted, resolved from the capture bundle's BatteryManifest "
            "(criteria_path field)."
        ),
    )

    # Output configuration
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--json", action="store_true", help="Generate JSON report")
    parser.add_argument("--html", action="store_true", help="Generate HTML report")
    parser.add_argument("--report-dir", default="qa_reports", help="Directory for reports (default: qa_reports)")

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Handle status dashboard commands (exit early)
    if args.status:
        print_status_dashboard()
        sys.exit(0)

    if args.failing:
        failing = get_failing_modules()
        if failing:
            print("Failing modules:")
            for name in sorted(failing):
                print(f"  - {name}")
            sys.exit(1)
        else:
            print("No failing modules!")
            sys.exit(0)

    if args.not_run:
        not_run = get_not_run_modules()
        if not_run:
            print("Modules not yet run:")
            for name in sorted(not_run):
                print(f"  - {name}")
        else:
            print("All modules have been run!")
        sys.exit(0)

    # Handle --wipe-data: Clear data directory to reset state
    if args.wipe_data:
        import shutil

        data_dir = Path("data")
        if data_dir.exists():
            print(f"🧹 Wiping data directory: {data_dir}")
            try:
                shutil.rmtree(data_dir)
                print("   ✅ Data directory cleared")
            except Exception as e:
                print(f"   ⚠️  Failed to wipe data directory: {e}")
        else:
            print(f"   ℹ️  Data directory does not exist: {data_dir}")

    # Parse modules (default to "all" if none specified)
    module_names = args.modules if args.modules else ["all"]
    modules: List[QAModule] = []
    for module_name in module_names:
        try:
            module = QAModule(module_name.lower())
            modules.append(module)
        except ValueError:
            print(f"❌ Unknown module: {module_name}")
            print(f"Available modules: {', '.join(m.value for m in QAModule)}")
            sys.exit(1)

    # Generic live-LLM enforcement driven by module-class metadata.
    # See tools/qa_runner/modules/_module_metadata.py — a module sets
    # REQUIRES_LIVE_LLM = True (and optional LIVE_LLM_DEFAULTS = {...})
    # and the runner here either auto-applies defaults (when the default
    # key file exists) or fails fast with a clear message.
    from .modules._module_metadata import get_metadata

    _live_default_key_file = args.live_key_file  # so we can detect if user passed --live-key-file
    _user_set_live_key_file = "--live-key-file" in sys.argv
    _user_set_live_model = "--live-model" in sys.argv
    _user_set_live_base_url = "--live-base-url" in sys.argv
    _user_set_live_provider = "--live-provider" in sys.argv
    for _mod in modules:
        _md = get_metadata(_mod)
        if not _md.requires_live_llm:
            continue
        if not args.live:
            # Try auto-enable from module defaults.
            _defaults = _md.live_llm_defaults
            _default_key = Path(_defaults.get("key_file", args.live_key_file)).expanduser()
            if _default_key.exists():
                args.live = True
                if not _user_set_live_key_file:
                    args.live_key_file = str(_default_key)
                if not _user_set_live_base_url and _defaults.get("base_url"):
                    args.live_base_url = _defaults["base_url"]
                if not _user_set_live_model and _defaults.get("model"):
                    args.live_model = _defaults["model"]
                if not _user_set_live_provider and _defaults.get("provider"):
                    args.live_provider = _defaults["provider"]
                print(
                    f"   ✅ {_mod.value} requires live LLM — auto-enabled "
                    f"(key={_default_key}, model={args.live_model})"
                )
            else:
                print(f"❌ {_mod.value} module requires --live (live LLM required)")
                if _defaults.get("key_file"):
                    print(f"   Expected key file at {_default_key} (from module defaults).")
                print(
                    f"   Create the key file or pass --live --live-key-file <path> "
                    f"--live-base-url ... --live-model ... explicitly."
                )
                sys.exit(1)

    # HE-300 benchmark module-specific defaults
    is_he300 = QAModule.HE300_BENCHMARK in modules
    if is_he300:
        print("🧪 HE-300 Benchmark Mode:")
        print("   📋 Template: he-300-benchmark (speak + task_complete only)")
        print("   🔓 Benchmark Mode: CIRIS_BENCHMARK_MODE=true (disables EpistemicHumility conscience)")
        # Auto-enable --wipe-data for clean state (do it now since wipe already ran above)
        if not args.wipe_data:
            print("   ℹ️  Auto-wiping data for clean benchmark state")
            import shutil

            data_dir = Path("data")
            if data_dir.exists():
                try:
                    shutil.rmtree(data_dir)
                    print("   ✅ Data directory cleared")
                except Exception as e:
                    print(f"   ⚠️  Failed to wipe data directory: {e}")
            args.wipe_data = True  # Mark as done
        # Warn if not using --live mode
        if not args.live:
            print("   ⚠️  WARNING: Running HE-300 without --live flag uses mock LLM")
            print(
                "   ⚠️  For real benchmarking, use: --live --live-key-file ~/.openai_key --live-model gpt-4o-mini --live-base-url https://api.openai.com/v1"
            )
        else:
            print("   ✅ Live LLM mode enabled for real ethical benchmarking")
        # Set OpenAI defaults if --live but using Groq defaults
        if args.live and "groq" in args.live_base_url.lower():
            print("   ℹ️  Tip: For OpenAI, use --live-base-url https://api.openai.com/v1 --live-model gpt-4o-mini")

    # Handle --live mode: read API key and configure live LLM
    live_api_key = None
    live_model = None
    live_base_url = None
    live_provider = None
    if args.live:
        key_path = Path(args.live_key_file).expanduser()
        if not key_path.exists():
            print(f"❌ Live mode requires API key file: {key_path}")
            print(f"   Create the file with your API key or use --live-key-file to specify path")
            sys.exit(1)
        try:
            live_api_key = key_path.read_text().strip()
            if not live_api_key:
                print(f"❌ API key file is empty: {key_path}")
                sys.exit(1)
            live_model = args.live_model
            live_base_url = args.live_base_url

            # Auto-detect provider from key file name or base URL if not specified
            live_provider = args.live_provider
            if not live_provider:
                key_file_name = key_path.name.lower()
                base_url_lower = live_base_url.lower() if live_base_url else ""

                if "anthropic" in key_file_name or "anthropic" in base_url_lower:
                    live_provider = "anthropic"
                    # For native Anthropic, we don't use a base URL (SDK handles it)
                    live_base_url = None
                elif (
                    "google" in key_file_name
                    or "gemini" in key_file_name
                    or "generativelanguage.googleapis" in base_url_lower
                ):
                    live_provider = "google"
                elif "openrouter" in key_file_name or "openrouter.ai" in base_url_lower:
                    live_provider = "openrouter"
                elif "groq" in key_file_name or "groq.com" in base_url_lower:
                    live_provider = "groq"
                elif "together" in key_file_name or "together" in base_url_lower:
                    live_provider = "together"
                elif base_url_lower and base_url_lower != "https://api.openai.com/v1":
                    live_provider = "openai_compatible"
                else:
                    live_provider = "openai"

            print(f"🔑 Live mode enabled:")
            print(f"   Provider: {live_provider}")
            print(f"   Key: {live_api_key[:10]}...{live_api_key[-4:]}")
            print(f"   Model: {live_model}")
            if live_base_url:
                print(f"   Base URL: {live_base_url}")
        except Exception as e:
            print(f"❌ Failed to read API key: {e}")
            sys.exit(1)

    # --live implies --live-lens (always use real Lens server with live LLM)
    if args.live and not args.live_lens:
        args.live_lens = True
        print("   ✅ Auto-enabling --live-lens (real Lens server for accord traces)")

    # QA runner ALWAYS wipes data to ensure clean state and use setup wizard
    # This ensures predictable test behavior with a known admin user/password
    if not args.wipe_data:
        print("ℹ️  Auto-wiping data for clean QA state (setup wizard creates test user)")
        import shutil

        data_dir = Path("data")
        if data_dir.exists():
            try:
                shutil.rmtree(data_dir)
                print("   ✅ Data directory cleared")
            except Exception as e:
                print(f"   ⚠️  Failed to wipe data directory: {e}")
        args.wipe_data = True

    # Staged-env preparation (if requested) — must happen BEFORE config
    # creation so the resulting StagedEnvironment can be passed in.
    # `--rebuild-staged` implies `--from-staged`.
    staged_env = None
    if args.from_staged or args.rebuild_staged:
        from .staged_env import prepare as prepare_staged_env

        repo_root = Path(__file__).resolve().parent.parent.parent
        print(
            f"[staged] Preparing staged QA environment at {args.staged_root} "
            f"(rebuild={args.rebuild_staged})"
        )
        staged_env = prepare_staged_env(
            src=repo_root,
            root=args.staged_root,
            rebuild=args.rebuild_staged,
        )
        print(f"[staged] Ready. Server will run from: {staged_env.ciris_server}")
        print(f"[staged] Canonical tree hash: {staged_env.total_hash}")

    # Create configuration
    # --live implies --no-mock-llm
    use_mock_llm = not args.no_mock_llm and not args.live

    config = QAConfig(
        base_url=args.url,
        api_port=args.port,
        admin_username=args.username,
        admin_password=args.password,
        parallel_tests=args.parallel,
        max_workers=args.workers,
        timeout=args.timeout,
        retry_count=args.retry,
        verbose=args.verbose,
        json_output=args.json,
        html_report=args.html,
        report_dir=Path(args.report_dir),
        auto_start_server=not args.no_auto_start,
        mock_llm=use_mock_llm,
        adapter=args.adapter,
        database_backends=args.database_backends,
        postgres_url=args.postgres_url,
        postgres_port=args.postgres_port,
        parallel_backends=args.parallel_backends,
        # Live LLM configuration
        live_api_key=live_api_key,
        live_model=live_model,
        live_base_url=live_base_url,
        live_provider=live_provider,
        # Live Lens configuration (for accord_metrics tests)
        live_lens=args.live_lens,
        # Staged-env mode (server runs from canonical-staged-tree wheel in a venv)
        staged_env=staged_env,
        # Live CIRISNode configuration (for cirisnode tests)
        live_node=args.live_node,
        # Live Portal configuration (for licensed_agent tests)
        live_portal=args.live_portal,
        # Fail-fast configuration
        fail_fast=not args.proceed_anyway,
        test_timeout=args.test_timeout,
        # Data management
        wipe_data=args.wipe_data,
        # Memory benchmark configuration
        message_count=args.message_count,
        concurrent_channels=args.concurrent_channels,
        # Model eval configuration
        model_eval_languages=[lang.strip() for lang in args.model_eval_languages.split(",") if lang.strip()],
        model_eval_concurrency=args.model_eval_concurrency,
        model_eval_profile_memory=not args.no_model_eval_memory_profile,
        model_eval_question_categories=[
            cat.strip() for cat in args.model_eval_questions.split(",") if cat.strip()
        ],
        model_eval_questions_file=(args.model_eval_questions_file or None),
        safety_battery_lang=args.safety_battery_lang,
        safety_battery_domain=args.safety_battery_domain,
        safety_battery_template=args.safety_battery_template,
        safety_interpret_capture_dir=args.safety_interpret_capture_dir,
        safety_interpret_criteria_file=args.safety_interpret_criteria_file,
        setup_template_id=(
            args.safety_battery_template
            if any(m.value == "safety_battery" for m in modules)
            else None
        ),
    )

    # Create and run runner
    runner = QARunner(config, modules=modules)
    success = runner.run(modules)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
