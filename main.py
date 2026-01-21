#!/usr/bin/env python3
# Load environment variables from .env if present
# Load from all standard config paths in priority order
try:
    from pathlib import Path

    from dotenv import load_dotenv

    # Priority order: ./env (highest), ~/ciris/.env, /etc/ciris/.env (lowest)
    # Note: ~/.ciris/ is for keys/secrets only, NOT config!
    config_paths = [
        Path.cwd() / ".env",
        Path.home() / "ciris" / ".env",
        Path("/etc/ciris/.env"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            load_dotenv(config_path, override=False)  # Don't override already-set vars

except ImportError:
    pass  # dotenv is optional; skip if not installed
import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.logic.utils.logging_config import setup_basic_logging
from ciris_engine.logic.utils.runtime_utils import load_config
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought

logger = logging.getLogger(__name__)


def setup_signal_handlers(runtime: CIRISRuntime) -> None:
    """Setup signal handlers for graceful shutdown."""
    shutdown_initiated = {"value": False}  # Use dict to allow modification in nested function

    def signal_handler(signum: int, frame: Any) -> None:
        if shutdown_initiated["value"]:
            logger.warning(f"Signal {signum} received again, forcing immediate exit")
            # Don't call sys.exit() in async context - just raise to let Python handle it
            raise KeyboardInterrupt("Forced shutdown")

        shutdown_initiated["value"] = True
        logger.info(f"Received signal {signum}, requesting graceful shutdown...")

        try:
            runtime.request_shutdown(f"Signal {signum}")
        except Exception as e:
            logger.error(f"Error during shutdown request: {e}")
            # Don't call sys.exit() in async context - raise instead
            raise KeyboardInterrupt("Shutdown error") from e

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def setup_global_exception_handler() -> None:
    """Setup global exception handler to catch all uncaught exceptions."""

    def handle_exception(exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            # Let KeyboardInterrupt be handled by signal handlers
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.error("UNCAUGHT EXCEPTION:", exc_info=(exc_type, exc_value, exc_traceback))
        logger.error("This should never happen - please report this bug!")

    sys.excepthook = handle_exception


def _create_thought() -> Thought:
    now = datetime.now(timezone.utc).isoformat()
    return Thought(
        thought_id=str(uuid.uuid4()),
        source_task_id=str(uuid.uuid4()),
        thought_type="standard",
        status=ThoughtStatus.PENDING,
        created_at=now,
        updated_at=now,
        content="manual invocation",
        context={},
    )


async def _execute_handler(runtime: CIRISRuntime, handler: str, params: Optional[str]) -> None:
    if not runtime.agent_processor:
        raise RuntimeError("Agent processor not initialized")
    handler_type = HandlerActionType[handler.upper()]
    dispatcher = runtime.agent_processor.action_dispatcher
    handler_instance = dispatcher.handlers.get(handler_type)
    if not handler_instance:
        raise ValueError(f"Handler {handler} not registered")
    payload = json.loads(params) if params else {}
    result = ActionSelectionDMAResult(
        selected_action=handler_type,
        action_parameters=payload,
        rationale="manual trigger",
    )
    thought = _create_thought()
    # Create a proper DispatchContext
    from ciris_engine.schemas.runtime.contexts import DispatchContext
    from ciris_engine.schemas.runtime.system_context import ChannelContext

    dispatch_context = DispatchContext(
        channel_context=ChannelContext(
            channel_id=runtime.startup_channel_id, channel_type="CLI", created_at=datetime.now(timezone.utc)
        ),
        author_id="system",
        author_name="System",
        origin_service="main",
        handler_name=handler,
        action_type=handler_type,
        thought_id=thought.thought_id,
        task_id=thought.source_task_id,
        source_task_id=thought.source_task_id,
        event_summary=f"Manual trigger: {handler}",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
    )
    await handler_instance.handle(result, thought, dispatch_context)


def _check_mock_llm_env() -> bool:
    """Check if mock LLM should be enabled via environment variable."""
    from ciris_engine.logic.config.env_utils import get_env_var

    mock_llm_env = get_env_var("CIRIS_MOCK_LLM", "")
    if mock_llm_env and mock_llm_env.lower() in ("true", "1", "yes", "on"):
        logger.info("CIRIS_MOCK_LLM environment variable detected, enabling mock LLM")
        return True
    return False


def _check_python_installation() -> None:
    """Check macOS Python installation and exit if invalid."""
    from ciris_engine.logic.setup.first_run import check_macos_python

    python_valid, python_message = check_macos_python()
    if not python_valid:
        click.echo("=" * 70, err=True)
        click.echo("PYTHON INSTALLATION ISSUE", err=True)
        click.echo("=" * 70, err=True)
        click.echo(python_message, err=True)
        click.echo("=" * 70, err=True)
        sys.exit(1)


def _get_adapter_types_from_env() -> list[str]:
    """Get adapter types from environment variable."""
    from ciris_engine.logic.config.env_utils import get_env_var

    env_adapter = get_env_var("CIRIS_ADAPTER")
    if env_adapter:
        return [a.strip() for a in env_adapter.split(",")]
    return ["api"]


def _show_configuration_required_message() -> None:
    """Display configuration required message for non-interactive CLI mode."""
    click.echo("=" * 70, err=True)
    click.echo("CONFIGURATION REQUIRED", err=True)
    click.echo("=" * 70, err=True)
    click.echo("CIRIS is not configured. Please set environment variables:", err=True)
    click.echo("", err=True)
    click.echo("Required:", err=True)
    click.echo("  OPENAI_API_KEY=your_api_key", err=True)
    click.echo("  CIRIS_ADAPTER=api", err=True)
    click.echo("", err=True)
    click.echo("For local LLM (Ollama, LM Studio, etc.):", err=True)
    click.echo("  OPENAI_API_KEY=local", err=True)
    click.echo("  OPENAI_API_BASE=http://localhost:11434", err=True)
    click.echo("  OPENAI_MODEL=llama3", err=True)
    click.echo("", err=True)
    click.echo("Or mount a .env file at:", err=True)
    click.echo("  ~/.ciris/.env", err=True)
    click.echo("  ./.env", err=True)
    click.echo("=" * 70, err=True)
    sys.exit(1)


def _run_cli_setup_wizard() -> None:
    """Run the CLI setup wizard for first-time interactive setup."""
    from ciris_engine.logic.setup.wizard import run_setup_wizard

    try:
        click.echo()
        click.echo("=" * 70)
        click.echo("First run detected - running CLI setup wizard...")
        click.echo("=" * 70)
        config_path = run_setup_wizard()
        try:
            from dotenv import load_dotenv

            load_dotenv(config_path)
            click.echo(f"Configuration loaded from: {config_path}")
        except ImportError:
            pass
    except KeyboardInterrupt:
        click.echo("\nSetup cancelled by user")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\nSetup failed: {e}", err=True)
        click.echo("You can configure manually by creating a .env file", err=True)
        sys.exit(1)


def _handle_first_run(
    first_run: bool, adapter_types_list: tuple[str, ...], is_cli_mode: bool
) -> None:
    """Handle first-run setup logic."""
    from ciris_engine.logic.setup.first_run import is_interactive_environment

    if not first_run or adapter_types_list:
        return

    if is_cli_mode and not is_interactive_environment():
        _show_configuration_required_message()
    elif is_cli_mode and is_interactive_environment():
        _run_cli_setup_wizard()


def _show_api_key_required_message() -> None:
    """Display API key required message."""
    click.echo("=" * 70, err=True)
    click.echo("LLM API KEY REQUIRED", err=True)
    click.echo("=" * 70, err=True)
    click.echo("No OPENAI_API_KEY found in environment.", err=True)
    click.echo("", err=True)
    click.echo("Options:", err=True)
    click.echo("  1. Set OPENAI_API_KEY environment variable", err=True)
    click.echo("  2. Add to .env file", err=True)
    click.echo("  3. Use --mock-llm flag for testing only", err=True)
    click.echo("", err=True)
    click.echo("For local LLM:", err=True)
    click.echo("  export OPENAI_API_KEY=local", err=True)
    click.echo("  export OPENAI_API_BASE=http://localhost:11434", err=True)
    click.echo("  export OPENAI_MODEL=llama3", err=True)
    click.echo("=" * 70, err=True)
    sys.exit(1)


def _validate_discord_adapter(
    adapter_type: str, discord_bot_token: Optional[str]
) -> bool:
    """Validate Discord adapter has required token. Returns True if valid."""
    from ciris_engine.logic.config.env_utils import get_env_var

    base_adapter_type, instance_id = (adapter_type.split(":", 1) + [None])[:2]
    token_vars = []
    if instance_id:
        token_vars.extend(
            [f"DISCORD_{instance_id.upper()}_BOT_TOKEN", f"DISCORD_BOT_TOKEN_{instance_id.upper()}"]
        )
    token_vars.append("DISCORD_BOT_TOKEN")

    has_token = discord_bot_token or any(get_env_var(var) for var in token_vars)
    if not has_token:
        click.echo(
            f"ERROR: No Discord bot token found for {adapter_type}. Discord adapter cannot start without a bot token.",
            err=True,
        )
        click.echo(
            "Please set DISCORD_BOT_TOKEN environment variable or use --discord-bot-token flag.", err=True
        )
    return True  # Always return True to continue (adapter will fail properly)


def _validate_adapter_tokens(
    adapter_types: list[str], discord_bot_token: Optional[str]
) -> list[str]:
    """Validate tokens for all adapters that require them."""
    validated = []
    for adapter_type in adapter_types:
        if adapter_type.startswith("discord"):
            _validate_discord_adapter(adapter_type, discord_bot_token)
        validated.append(adapter_type)
    return validated


def _check_modular_service_config(manifest: Any) -> list[str]:
    """Check modular service configuration. Returns list of missing required vars."""
    from ciris_engine.logic.config.env_utils import get_env_var

    missing_required = []
    if manifest.configuration:
        for config_key, config_spec in manifest.configuration.items():
            env_var = config_spec.env
            if env_var and not get_env_var(env_var):
                if config_spec.default is None:
                    missing_required.append(f"{env_var}")
    return missing_required


def _categorize_adapters(
    adapter_types: list[str], adapter_map: dict[str, Any]
) -> tuple[list[str], list[tuple[str, Any]]]:
    """Categorize adapters into built-in and modular services."""
    builtin_adapters = ["cli", "api", "discord"]
    final_adapter_types = []
    adapters_to_load = []

    for adapter_type in adapter_types:
        base_type = adapter_type.split(":")[0]

        if any(base_type.startswith(builtin) for builtin in builtin_adapters):
            final_adapter_types.append(adapter_type)
        elif base_type.lower() in adapter_map:
            manifest = adapter_map[base_type.lower()]
            logger.info(f"Found modular service '{manifest.module.name}' for adapter type '{adapter_type}'")

            missing = _check_modular_service_config(manifest)
            if missing:
                click.echo(
                    f"ERROR: Modular service '{manifest.module.name}' requires configuration:",
                    err=True,
                )
                for var in missing:
                    click.echo(f"  - {var}", err=True)
                click.echo(
                    f"Skipping modular service '{manifest.module.name}' due to missing configuration.",
                    err=True,
                )
                continue

            adapters_to_load.append((adapter_type, manifest))
            logger.info(f"Modular service '{manifest.module.name}' validated and will be loaded")
        else:
            click.echo(
                f"WARNING: Unknown adapter type '{adapter_type}'. Not a built-in adapter or modular service.",
                err=True,
            )
            final_adapter_types.append(adapter_type)

    return final_adapter_types, adapters_to_load


async def _load_app_config(
    config_file_path: Optional[str], template: str
) -> Any:
    """Load application configuration."""
    if config_file_path and not Path(config_file_path).exists():
        logger.error(f"Configuration file not found: {config_file_path}")
        raise SystemExit(1)

    cli_overrides: dict[str, Any] = {}
    if template and template != "default":
        cli_overrides["default_template"] = template

    return await load_config(config_file_path, cli_overrides)


def _handle_config_load_error(e: Exception) -> None:
    """Handle configuration load errors."""
    import time

    error_msg = f"Failed to load config: {e}"
    logger.error(error_msg)
    print(error_msg, file=sys.stderr)
    sys.stdout.flush()
    sys.stderr.flush()
    for log_handler in logger.handlers:
        log_handler.flush()
    time.sleep(0.1)
    if sys.gettrace() is not None or "coverage" in sys.modules:
        logger.debug("EXITING NOW VIA os._exit(1) AT _handle_precommit_wrapper coverage")
        os._exit(1)
    else:
        logger.debug("EXITING NOW VIA sys.exit(1) AT _handle_precommit_wrapper")
        sys.exit(1)


def _configure_api_adapter(
    adapter_type: str, api_host: Optional[str], api_port: Optional[int]
) -> tuple[Any, str]:
    """Configure API adapter. Returns (AdapterConfig, channel_id)."""
    from ciris_engine.logic.adapters.api.config import APIAdapterConfig
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

    api_config = APIAdapterConfig()
    api_config.load_env_vars()
    if api_host:
        api_config.host = api_host
    if api_port:
        api_config.port = api_port

    adapter_config = AdapterConfig(
        adapter_type="api", enabled=True, settings=api_config.model_dump()
    )
    channel_id = api_config.get_home_channel_id(api_config.host, api_config.port)
    return adapter_config, channel_id


def _configure_discord_adapter(
    adapter_type: str, discord_bot_token: Optional[str]
) -> tuple[Any, Optional[str]]:
    """Configure Discord adapter. Returns (AdapterConfig, channel_id or None)."""
    from ciris_engine.logic.adapters.discord.config import DiscordAdapterConfig
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

    discord_config = DiscordAdapterConfig()
    if discord_bot_token:
        discord_config.bot_token = discord_bot_token
    discord_config.load_env_vars()

    adapter_config = AdapterConfig(
        adapter_type="discord",
        enabled=True,
        settings=discord_config.model_dump(),
    )
    discord_channel_id = discord_config.get_home_channel_id()
    formatted_channel_id = discord_config.get_formatted_startup_channel_id() if discord_channel_id else None
    return adapter_config, formatted_channel_id


def _configure_cli_adapter(
    adapter_type: str, cli_interactive: bool
) -> tuple[Any, str]:
    """Configure CLI adapter. Returns (AdapterConfig, channel_id)."""
    from ciris_engine.logic.adapters.cli.config import CLIAdapterConfig
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

    cli_config = CLIAdapterConfig()
    if not cli_interactive:
        cli_config.interactive = False

    adapter_config = AdapterConfig(
        adapter_type="cli", enabled=True, settings=cli_config.model_dump()
    )
    channel_id = cli_config.get_home_channel_id()
    return adapter_config, channel_id


def _configure_adapters(
    adapter_types: list[str],
    app_config: Any,
    api_host: Optional[str],
    api_port: Optional[int],
    discord_bot_token: Optional[str],
    cli_interactive: bool,
) -> tuple[dict[str, Any], Optional[str]]:
    """Configure all adapters. Returns (adapter_configs, startup_channel_id)."""
    adapter_configs: dict[str, Any] = {}
    startup_channel_id: Optional[str] = getattr(app_config, "startup_channel_id", None)

    for adapter_type in adapter_types:
        channel_id: Optional[str] = None
        if adapter_type.startswith("api"):
            config, channel_id = _configure_api_adapter(adapter_type, api_host, api_port)
            adapter_configs[adapter_type] = config
            if not startup_channel_id:
                startup_channel_id = channel_id

        elif adapter_type.startswith("discord"):
            config, channel_id = _configure_discord_adapter(adapter_type, discord_bot_token)
            adapter_configs[adapter_type] = config
            if channel_id and not startup_channel_id:
                startup_channel_id = channel_id

        elif adapter_type.startswith("cli"):
            config, channel_id = _configure_cli_adapter(adapter_type, cli_interactive)
            adapter_configs[adapter_type] = config
            if not startup_channel_id:
                startup_channel_id = channel_id

    return adapter_configs, startup_channel_id


async def _flush_all_handlers() -> None:
    """Flush all output streams and log handlers."""

    async def flush_handler(handler: Any) -> None:
        try:
            await asyncio.to_thread(handler.flush)
        except Exception:
            pass

    flush_tasks = [
        asyncio.create_task(asyncio.to_thread(sys.stdout.flush)),
        asyncio.create_task(asyncio.to_thread(sys.stderr.flush)),
    ]
    for log_handler in logging.getLogger().handlers:
        flush_tasks.append(asyncio.create_task(flush_handler(log_handler)))

    await asyncio.gather(*flush_tasks, return_exceptions=True)


async def _create_cli_monitor(runtime: CIRISRuntime) -> asyncio.Task[None]:
    """Create CLI shutdown monitor task."""
    shutdown_event = asyncio.Event()
    runtime._shutdown_event = shutdown_event

    async def monitor_shutdown() -> None:
        await shutdown_event.wait()
        logger.info("CLI runtime shutdown complete, preparing clean exit")
        await asyncio.sleep(0.2)
        await _flush_all_handlers()
        logger.info("Forcing exit to handle blocking CLI input thread")

    return asyncio.create_task(monitor_shutdown())


async def _handle_cli_exit(selected_adapter_types: list[str]) -> None:
    """Handle CLI adapter exit with proper flushing."""
    if "cli" not in selected_adapter_types:
        return

    logger.info("CLI runtime completed, forcing exit")
    await asyncio.sleep(0.5)
    await _flush_all_handlers()
    logger.debug("EXITING NOW VIA os._exit(0) AT CLI runtime completed")
    os._exit(0)


def _handle_final_exit() -> None:
    """Handle final exit logic for main function."""
    import time

    sys.stdout.flush()
    sys.stderr.flush()
    logger.info("CIRIS agent exiting cleanly")

    if "--adapter" in sys.argv and "api" in sys.argv and "--timeout" in sys.argv:
        logger.debug("EXITING NOW VIA os._exit(0) AT API mode subprocess tests")
        os._exit(0)

    if "--adapter" in sys.argv and "cli" in sys.argv:
        logger.info("CLI mode completed, forcing exit to handle blocking input thread")
        sys.stdout.flush()
        sys.stderr.flush()
        for log_handler in logging.getLogger().handlers:
            log_handler.flush()
        time.sleep(0.1)
        logger.debug("EXITING NOW VIA os._exit(0) AT CLI mode force exit")
        os._exit(0)

    logger.debug("EXITING NOW VIA sys.exit(0) AT end of main")
    sys.exit(0)


async def _run_runtime(runtime: CIRISRuntime, timeout: Optional[int], num_rounds: Optional[int] = None) -> None:
    """Run the runtime with optional timeout and graceful shutdown."""
    logger.debug(f"[DEBUG] _run_runtime called with timeout={timeout}, num_rounds={num_rounds}")
    shutdown_called = False
    try:
        if timeout:
            # Create task and handle timeout manually to allow graceful shutdown
            logger.debug(f"[DEBUG] Setting up timeout for {timeout} seconds")
            runtime_task = asyncio.create_task(runtime.run(num_rounds))

            try:
                # Wait for either the task to complete or timeout
                await asyncio.wait_for(asyncio.shield(runtime_task), timeout=timeout)
            except asyncio.TimeoutError:
                logger.info(f"Timeout of {timeout} seconds reached, initiating graceful shutdown...")
                # Request shutdown but don't cancel the task immediately
                runtime.request_shutdown(f"Runtime timeout after {timeout} seconds")

                # Give the shutdown processor time to run (up to 30 seconds)
                try:
                    await asyncio.wait_for(runtime_task, timeout=30.0)
                    logger.info("Graceful shutdown completed within timeout")
                except asyncio.TimeoutError:
                    logger.warning("Graceful shutdown did not complete within 30 seconds, cancelling...")
                    runtime_task.cancel()
                    try:
                        await runtime_task
                    except asyncio.CancelledError:
                        # Expected when we cancel the task
                        pass  # NOSONAR - Intentionally not re-raising after timeout cancellation

                    # Ensure shutdown is called if the task was cancelled
                    logger.info("Calling shutdown explicitly after task cancellation")
                    await runtime.shutdown()

                shutdown_called = True
        else:
            # Run without timeout
            logger.debug("[DEBUG] Running without timeout")
            await runtime.run(num_rounds)
    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down gracefully...")
        runtime.request_shutdown("User interrupt")
        # Don't call shutdown here if runtime.run() will handle it
        if not shutdown_called:
            await runtime.shutdown()
    except Exception as e:
        logger.error(f"FATAL ERROR: Unhandled exception in runtime: {e}", exc_info=True)
        try:
            runtime.request_shutdown(f"Fatal error: {e}")
            if not shutdown_called:
                await runtime.shutdown()
        except Exception as shutdown_error:
            logger.error(f"Error during emergency shutdown: {shutdown_error}", exc_info=True)
        raise  # Re-raise to ensure non-zero exit code


@click.command()
@click.option(
    "--adapter",
    "adapter_types_list",
    multiple=True,
    default=[],
    help="One or more adapters to run. Specify multiple times for multiple adapters (e.g., --adapter cli --adapter api --adapter discord).",
)
@click.option("--template", default="default", help="Agent template name (only used for first-time setup)")
@click.option(
    "--identity-update/--no-identity-update",
    default=False,
    help="Update existing identity from template (admin operation, requires --template)",
)
@click.option("--config", "config_file_path", type=click.Path(), help="Path to app config")
@click.option("--task", multiple=True, help="Task description to add before starting")
@click.option("--timeout", type=int, help="Maximum runtime duration in seconds")
@click.option("--handler", help="Direct handler to execute and exit")
@click.option("--params", help="JSON parameters for handler execution")
@click.option(
    "--host",
    "api_host",
    default=None,
    help="API host (default: 127.0.0.1 for security, use 0.0.0.0 for all interfaces)",
)
@click.option("--port", "api_port", default=None, type=int, help="API port (default: 8080)")
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
@click.option(
    "--no-interactive/--interactive", "cli_interactive", default=True, help="Enable/disable interactive CLI input"
)
@click.option(
    "--discord-token", "discord_bot_token", default=os.environ.get("DISCORD_BOT_TOKEN"), help="Discord bot token"
)
@click.option("--mock-llm/--no-mock-llm", default=False, help="Use the mock LLM service for offline testing")
@click.option("--num-rounds", type=int, help="Maximum number of processing rounds (default: infinite)")
def main(
    adapter_types_list: tuple[str, ...],
    template: str,
    identity_update: bool,
    config_file_path: Optional[str],
    task: tuple[str],
    timeout: Optional[int],
    handler: Optional[str],
    params: Optional[str],
    api_host: Optional[str],
    api_port: Optional[int],
    debug: bool,
    cli_interactive: bool,
    discord_bot_token: Optional[str],
    mock_llm: bool,
    num_rounds: Optional[int],
) -> None:
    """Unified CIRIS agent entry point."""
    # Setup basic console logging first (without file logging)
    # File logging will be set up later once TimeService is available
    setup_basic_logging(
        level=logging.DEBUG if debug else logging.INFO,
        log_to_file=False,
        console_output=True,
        enable_incident_capture=False,  # Will be enabled later with TimeService
    )

    async def _async_main() -> None:
        nonlocal mock_llm
        from ciris_engine.logic.config.env_utils import get_env_var
        from ciris_engine.logic.setup.first_run import is_first_run
        from ciris_engine.logic.runtime.adapter_loader import AdapterLoader

        # Check for CIRIS_MOCK_LLM environment variable
        if not mock_llm and _check_mock_llm_env():
            mock_llm = True

        # Check macOS Python installation
        _check_python_installation()

        # Determine first-run status
        first_run = is_first_run()
        if os.environ.get("CIRIS_IMPORT_MODE") == "true":
            first_run = False

        # Handle adapter selection
        final_adapter_types_list = list(adapter_types_list) if adapter_types_list else _get_adapter_types_from_env()
        is_cli_mode = any(adapter.startswith("cli") for adapter in final_adapter_types_list)

        # Handle first-run setup
        _handle_first_run(first_run, adapter_types_list, is_cli_mode)

        # Check for API key
        api_key = get_env_var("OPENAI_API_KEY")
        if not mock_llm and not api_key and not first_run:
            _show_api_key_required_message()

        # Validate adapter tokens
        selected_adapter_types = _validate_adapter_tokens(list(final_adapter_types_list), discord_bot_token)

        # Discover modular services
        adapter_loader = AdapterLoader()
        discovered_services = adapter_loader.discover_services()
        adapter_map = {svc.module.name.lower().replace("_adapter", ""): svc for svc in discovered_services}

        # Categorize adapters
        selected_adapter_types, adapters_to_load = _categorize_adapters(selected_adapter_types, adapter_map)

        # Load config
        try:
            app_config = await _load_app_config(config_file_path, template)
        except SystemExit:
            raise
        except Exception as e:
            _handle_config_load_error(e)
            return  # Unreachable but makes type checker happy

        # Build modules to load
        modules_to_load = ["mock_llm"] if mock_llm else []
        if mock_llm:
            logger.info("Mock LLM module will be loaded")
        for adapter_type, manifest in adapters_to_load:
            modules_to_load.append(f"modular:{manifest.module.name}")
            logger.info(f"Modular service '{manifest.module.name}' added to modules to load")

        # Configure adapters
        adapter_configs, startup_channel_id = _configure_adapters(
            selected_adapter_types, app_config, api_host, api_port, discord_bot_token, cli_interactive
        )

        # Setup global exception handling
        setup_global_exception_handler()

        # Create and initialize runtime
        runtime = CIRISRuntime(
            adapter_types=selected_adapter_types,
            essential_config=app_config,
            startup_channel_id=startup_channel_id,
            adapter_configs=adapter_configs,
            interactive=cli_interactive,
            host=api_host,
            port=api_port,
            discord_bot_token=discord_bot_token,
            modules=modules_to_load,
            identity_update=identity_update,
            template_name=template if template != "default" else None,
        )
        await runtime.initialize()
        setup_signal_handlers(runtime)

        # Store preload tasks
        preload_tasks = list(task) if task else []
        runtime.set_preload_tasks(preload_tasks)

        # Handle direct handler execution
        if handler:
            await _execute_handler(runtime, handler, params)
            await runtime.shutdown()
            return

        # Determine effective num_rounds
        effective_num_rounds = num_rounds
        if effective_num_rounds is None:
            from ciris_engine.logic.utils.constants import DEFAULT_NUM_ROUNDS
            effective_num_rounds = DEFAULT_NUM_ROUNDS

        # Create CLI monitor if needed
        monitor_task = None
        if "cli" in selected_adapter_types:
            monitor_task = await _create_cli_monitor(runtime)

        # Run the runtime
        try:
            await _run_runtime(runtime, timeout, effective_num_rounds)
        finally:
            if monitor_task and not monitor_task.done():
                logger.debug("Waiting for CLI monitor task to detect shutdown completion...")
                try:
                    await asyncio.wait_for(monitor_task, timeout=5.0)
                except asyncio.TimeoutError:
                    logger.warning("Monitor task did not complete within 5 seconds")
                    monitor_task.cancel()
                except Exception as e:
                    logger.error(f"Monitor task error: {e}")

        # Handle CLI exit
        await _handle_cli_exit(selected_adapter_types)

    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user, exiting...")
        logger.debug("EXITING NOW VIA sys.exit(0) AT KeyboardInterrupt in main")
        sys.exit(0)
    except SystemExit:
        raise  # Re-raise SystemExit to exit with the correct code
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        logger.debug("EXITING NOW VIA sys.exit(1) AT Fatal error in main")
        sys.exit(1)

    # Handle final exit
    _handle_final_exit()


if __name__ == "__main__":
    main()
