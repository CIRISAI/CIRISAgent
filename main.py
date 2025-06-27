# Load environment variables from .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is optional; skip if not installed
import os

import asyncio
import json
import logging
import signal
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

import click

from ciris_engine.logic.utils.runtime_utils import load_config, run_with_shutdown_handler
from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.logic.utils.logging_config import setup_basic_logging
from ciris_engine.logic.processors.support.task_manager import TaskManager
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus

logger = logging.getLogger(__name__)


def setup_signal_handlers(runtime: CIRISRuntime) -> None:
    """Setup signal handlers for graceful shutdown."""
    shutdown_initiated = {"value": False}  # Use dict to allow modification in nested function
    
    def signal_handler(signum, frame):
        if shutdown_initiated["value"]:
            logger.warning(f"Signal {signum} received again, forcing immediate exit")
            sys.exit(1)
        
        shutdown_initiated["value"] = True
        logger.info(f"Received signal {signum}, requesting graceful shutdown...")
        
        try:
            runtime.request_shutdown(f"Signal {signum}")
        except Exception as e:
            logger.error(f"Error during shutdown request: {e}")
            sys.exit(1)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def setup_global_exception_handler() -> None:
    """Setup global exception handler to catch all uncaught exceptions."""
    def handle_exception(exc_type, exc_value, exc_traceback):
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
    await handler_instance.handle(result, thought, {"channel_id": runtime.startup_channel_id})


async def _run_runtime(runtime: CIRISRuntime, timeout: Optional[int], num_rounds: Optional[int] = None) -> None:
    """Run the runtime with optional timeout and graceful shutdown."""
    logger.info(f"[DEBUG] _run_runtime called with timeout={timeout}, num_rounds={num_rounds}")
    shutdown_called = False
    try:
        if timeout:
            # Create task and handle timeout manually to allow graceful shutdown
            logger.info(f"[DEBUG] Setting up timeout for {timeout} seconds")
            runtime_task = asyncio.create_task(runtime.run(num_rounds=num_rounds))
            
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
                        pass
                
                shutdown_called = True
        else:
            # Run without timeout
            logger.info(f"[DEBUG] Running without timeout")
            await runtime.run(num_rounds=num_rounds)
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
@click.option("--adapter", "adapter_types_list", multiple=True, default=[], help="One or more adapters to run. Specify multiple times for multiple adapters (e.g., --adapter cli --adapter api --adapter discord).")
@click.option("--template", default="default", help="Agent template name (only used for first-time setup)")
@click.option("--config", "config_file_path", type=click.Path(), help="Path to app config")
@click.option("--task", multiple=True, help="Task description to add before starting")
@click.option("--timeout", type=int, help="Maximum runtime duration in seconds")
@click.option("--handler", help="Direct handler to execute and exit")
@click.option("--params", help="JSON parameters for handler execution")
@click.option("--host", "api_host", default=None, help="API host (default: 0.0.0.0)")
@click.option("--port", "api_port", default=None, type=int, help="API port (default: 8080)")
@click.option("--debug/--no-debug", default=False, help="Enable debug logging")
@click.option("--no-interactive/--interactive", "cli_interactive", default=True, help="Enable/disable interactive CLI input")
@click.option("--discord-token", "discord_bot_token", default=os.environ.get("DISCORD_BOT_TOKEN"), help="Discord bot token")
@click.option("--mock-llm/--no-mock-llm", default=False, help="Use the mock LLM service for offline testing")
@click.option("--num-rounds", type=int, help="Maximum number of processing rounds (default: infinite)")
def main(
    adapter_types_list: tuple[str, ...],
    template: str,
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
        enable_incident_capture=False  # Will be enabled later with TimeService
    )

    async def _async_main() -> None:
        nonlocal mock_llm, handler, params, task, num_rounds
        from ciris_engine.logic.config.env_utils import get_env_var

        # Check for API key and auto-enable mock LLM if none is set
        api_key = get_env_var("OPENAI_API_KEY")
        if not mock_llm and not api_key:
            click.echo(
                "no API key set, if using a local LLM set key as LOCAL, starting with mock LLM"
            )
            mock_llm = True

        # Handle adapter types - if none specified, default to CLI
        final_adapter_types_list = list(adapter_types_list)
        if not final_adapter_types_list:
            final_adapter_types_list = ["cli"]
        
        # Support multiple instances of same adapter type
        selected_adapter_types = []
        for adapter_type in final_adapter_types_list:
            if ":" in adapter_type:
                # Support instance-specific adapter types like "discord:instance1" or "api:port8081"
                selected_adapter_types.append(adapter_type)
            else:
                selected_adapter_types.append(adapter_type)

        # Validate Discord adapter types have tokens available
        validated_adapter_types = []
        for adapter_type in selected_adapter_types:
            if adapter_type.startswith("discord"):
                base_adapter_type, instance_id = (adapter_type.split(":", 1) + [None])[:2]
                # Check for instance-specific token or fallback to general token
                token_vars = []
                if instance_id:
                    token_vars.extend([f"DISCORD_{instance_id.upper()}_BOT_TOKEN", f"DISCORD_BOT_TOKEN_{instance_id.upper()}"])
                token_vars.append("DISCORD_BOT_TOKEN")
                
                has_token = discord_bot_token or any(get_env_var(var) for var in token_vars)
                if not has_token:
                    click.echo(f"No Discord bot token found for {adapter_type}, falling back to CLI adapter type")
                    validated_adapter_types.append("cli")
                else:
                    validated_adapter_types.append(adapter_type)
            else:
                validated_adapter_types.append(adapter_type)
        
        selected_adapter_types = validated_adapter_types

        # Load config
        try:
            # Validate config file exists if provided
            if config_file_path and not Path(config_file_path).exists():
                logger.error(f"Configuration file not found: {config_file_path}")
                raise SystemExit(1)
            
            # Create CLI overrides including the template parameter
            cli_overrides = {}
            if template and template != "default":
                cli_overrides["default_template"] = template
                
            app_config = await load_config(config_file_path, cli_overrides)
        except SystemExit:
            raise  # Re-raise SystemExit to exit cleanly
        except Exception as e:
            error_msg = f"Failed to load config: {e}"
            logger.error(error_msg)
            # Write directly to stderr to ensure it's captured
            print(error_msg, file=sys.stderr)
            # Ensure outputs are flushed before exit
            sys.stdout.flush()
            sys.stderr.flush()
            # Also flush logging handlers
            for handler in logger.handlers:
                handler.flush()
            # Give a tiny bit of time for output to be written
            import time
            time.sleep(0.1)
            # Force immediate exit to avoid hanging in subprocess
            # Use os._exit only when running under coverage
            if sys.gettrace() is not None or 'coverage' in sys.modules:
                os._exit(1)
            else:
                sys.exit(1)

        # Handle mock LLM as a module to load
        modules_to_load = []
        if mock_llm:
            modules_to_load.append("mock_llm")
            logger.info("Mock LLM module will be loaded")

        
        # Create adapter configurations for each adapter type and determine startup channel
        adapter_configs = {}
        startup_channel_id = getattr(app_config, 'startup_channel_id', None)
        # No discord_channel_id in EssentialConfig
        
        for adapter_type in selected_adapter_types:
            if adapter_type.startswith("api"):
                base_adapter_type, instance_id = (adapter_type.split(":", 1) + [None])[:2]
                from ciris_engine.logic.adapters.api.config import APIAdapterConfig
                
                api_config = APIAdapterConfig()
                if api_host:
                    api_config.host = api_host
                if api_port:
                    api_config.port = api_port
                
                # Load environment variables with instance-specific support
                if instance_id:
                    api_config.load_env_vars_with_instance(instance_id)
                else:
                    api_config.load_env_vars()
                
                adapter_configs[adapter_type] = api_config
                api_channel_id = api_config.get_home_channel_id(api_config.host, api_config.port)
                if not startup_channel_id:
                    startup_channel_id = api_channel_id
                    
            elif adapter_type.startswith("discord"):
                base_adapter_type, instance_id = (adapter_type.split(":", 1) + [None])[:2]
                from ciris_engine.logic.adapters.discord.config import DiscordAdapterConfig
                
                discord_config = DiscordAdapterConfig()
                if discord_bot_token:
                    discord_config.bot_token = discord_bot_token
                
                # Load environment variables with instance-specific support
                if instance_id:
                    discord_config.load_env_vars_with_instance(instance_id)
                else:
                    discord_config.load_env_vars()
                
                adapter_configs[adapter_type] = discord_config
                discord_channel_id = discord_config.get_home_channel_id()
                if discord_channel_id and not startup_channel_id:
                    startup_channel_id = discord_channel_id
                    
            elif adapter_type.startswith("cli"):
                base_adapter_type, instance_id = (adapter_type.split(":", 1) + [None])[:2]
                from ciris_engine.logic.adapters.cli.config import CLIAdapterConfig
                
                cli_config = CLIAdapterConfig()
                
                # Load environment variables first, then override with CLI args
                if instance_id:
                    cli_config.load_env_vars_with_instance(instance_id)
                else:
                    cli_config.load_env_vars()
                
                # CLI arguments take precedence over environment variables
                if not cli_interactive:
                    cli_config.interactive = False
                
                adapter_configs[adapter_type] = cli_config
                cli_channel_id = cli_config.get_home_channel_id()
                if not startup_channel_id:
                    startup_channel_id = cli_channel_id

        # Setup global exception handling
        setup_global_exception_handler()
        
        # Template parameter is now passed via cli_overrides to the essential config
            
        # Create runtime using new CIRISRuntime directly with adapter configs
        runtime = CIRISRuntime(
            adapter_types=selected_adapter_types,
            essential_config=app_config,  # app_config is actually EssentialConfig
            startup_channel_id=startup_channel_id,
            adapter_configs=adapter_configs,
            interactive=cli_interactive,
            host=api_host,
            port=api_port,
            discord_bot_token=discord_bot_token,
            modules=modules_to_load,  # Pass modules to load
        )
        await runtime.initialize()
        
        # Setup signal handlers for graceful shutdown
        setup_signal_handlers(runtime)

        # Store preload tasks to be loaded after WORK state transition
        preload_tasks = list(task) if task else []
        runtime.set_preload_tasks(preload_tasks)

        if handler:
            await _execute_handler(runtime, handler, params)
            await runtime.shutdown()
            return

        # Use CLI num_rounds if provided, otherwise fall back to config
        effective_num_rounds = num_rounds
        # Use default num_rounds if not specified
        if effective_num_rounds is None:
            from ciris_engine.logic.utils.constants import DEFAULT_NUM_ROUNDS
            effective_num_rounds = DEFAULT_NUM_ROUNDS

        await _run_runtime(runtime, timeout, effective_num_rounds)

    try:
        asyncio.run(_async_main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user, exiting...")
        sys.exit(0)
    except SystemExit:
        raise  # Re-raise SystemExit to exit with the correct code
    except Exception as e:
        logger.error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)
    
    # Ensure clean exit after successful run
    # Force flush all outputs
    sys.stdout.flush()
    sys.stderr.flush()
    
    # asyncio.run() already closes the event loop, so we don't need to do it again
    # Just exit cleanly
    logger.info("CIRIS agent exiting cleanly")
    
    # For API mode subprocess tests, ensure immediate exit
    if "--adapter" in sys.argv and "api" in sys.argv and "--timeout" in sys.argv:
        import os
        os._exit(0)
    
    sys.exit(0)


if __name__ == "__main__":
    main()