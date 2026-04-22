"""
A2A (Agent-to-Agent) Adapter for CIRIS.

Provides an A2A protocol endpoint for HE-300 ethical benchmarking.
Exposes a JSON-RPC 2.0 compatible endpoint at POST /a2a.

This adapter is optimized for high-concurrency benchmarking scenarios
with direct LLM access and minimal overhead.
"""

import asyncio
import logging
import os
from typing import Any, List, Optional

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from uvicorn import Server

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .schemas import (
    A2ARequest,
    A2AResponse,
    BenchmarkRequest,
    create_benchmark_error_response,
    create_benchmark_response,
    create_error_response,
    create_success_response,
)
from .services import A2AService

logger = logging.getLogger(__name__)


class A2AAdapter(Service):
    """
    A2A adapter for CIRIS ethical benchmarking.

    Provides a JSON-RPC 2.0 compatible endpoint for the HE-300 benchmark
    protocol. Optimized for high concurrency (10-50+ simultaneous requests).

    Configuration:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8100)
        system_prompt: Custom system prompt for ethical reasoning
        timeout: Timeout for LLM calls in seconds (default: 60)
    """

    def __init__(self, runtime: Any, context: Optional[Any] = None, **kwargs: Any) -> None:
        """Initialize A2A adapter.

        Args:
            runtime: CIRIS runtime instance
            context: Optional runtime context
            **kwargs: Additional configuration (may include adapter_config)
        """
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Extract config - environment variables take precedence
        adapter_config = kwargs.get("adapter_config", {})

        # Default values
        default_host = "0.0.0.0"
        default_port = 8100
        default_timeout = 60.0

        # Get from adapter_config first
        if isinstance(adapter_config, dict):
            config_host = adapter_config.get("host", default_host)
            config_port = adapter_config.get("port", default_port)
            config_timeout = adapter_config.get("timeout", default_timeout)
        else:
            config_host = getattr(adapter_config, "host", default_host)
            config_port = getattr(adapter_config, "port", default_port)
            config_timeout = getattr(adapter_config, "timeout", default_timeout)

        # Environment variables override config (for AgentBeats/Docker)
        self._host = os.environ.get("CIRIS_A2A_HOST", config_host)
        self._port = int(os.environ.get("CIRIS_A2A_PORT", config_port))
        self._timeout = float(os.environ.get("CIRIS_A2A_TIMEOUT", config_timeout))

        # Create A2A service with runtime for pipeline access
        self.a2a_service = A2AService(
            runtime=runtime,
            timeout_seconds=self._timeout,
        )

        # Create FastAPI app
        self.app = self._create_app()

        # Server state
        self._server: Optional[Server] = None
        self._server_task: Optional[asyncio.Task[Any]] = None
        self._running = False

        logger.info(f"A2A adapter initialized - host: {self._host}, port: {self._port}")

    def _create_app(self) -> FastAPI:
        """Create the FastAPI application.

        Returns:
            Configured FastAPI app with /a2a endpoint
        """
        app = FastAPI(
            title="CIRIS A2A Protocol",
            description="Agent-to-Agent protocol endpoint for ethical benchmarking",
            version="1.0.0",
        )

        # Add CORS for cross-origin requests
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Health check endpoint
        @app.get("/health")
        async def health_check() -> dict[str, str]:
            """Health check endpoint."""
            return {"status": "healthy", "service": "a2a"}

        # A2A protocol endpoint
        @app.post("/a2a")
        async def a2a_endpoint(request: Request) -> JSONResponse:
            """Handle A2A protocol requests.

            Accepts JSON-RPC 2.0 formatted requests and returns ethical
            judgments. Supports both tasks/send and benchmark.evaluate methods.
            """
            try:
                # Parse request body
                body = await request.json()
                method = body.get("method", "")
                request_id = body.get("id", "unknown")

                # Route based on method
                if method == "benchmark.evaluate":
                    return await self._handle_benchmark_evaluate(body, request_id)
                elif method == "tasks/send":
                    return await self._handle_tasks_send(body, request_id)
                else:
                    response = create_error_response(
                        request_id=request_id,
                        code=-32601,
                        message=f"Method not found: {method}. Supported: tasks/send, benchmark.evaluate",
                    )
                    return JSONResponse(content=response.model_dump())

            except ValidationError as e:
                # Invalid request format
                response = create_error_response(
                    request_id=body.get("id", "unknown") if isinstance(body, dict) else "unknown",
                    code=-32600,
                    message="Invalid request",
                    data=str(e),
                )
                return JSONResponse(content=response.model_dump(), status_code=400)

            except Exception as e:
                logger.error(f"A2A endpoint error: {e}")
                response = create_error_response(
                    request_id="unknown",
                    code=-32700,
                    message="Parse error",
                    data=str(e),
                )
                return JSONResponse(content=response.model_dump(), status_code=400)

        # Metrics endpoint
        @app.get("/metrics")
        async def metrics() -> dict[str, Any]:
            """Get A2A service metrics."""
            return self.a2a_service.get_metrics()

        # AgentBeats agent manifest endpoint
        @app.get("/.well-known/agent.json")
        async def agent_manifest() -> dict[str, Any]:
            """AgentBeats agent manifest for discovery."""
            return {
                "name": "CIRIS Agent",
                "version": "1.9.4",
                "description": "CIRIS ethical AI agent for ethical evaluation",
                "capabilities": [
                    "ethics-evaluation",
                    "a2a:tasks_send",
                    "a2a:benchmark.evaluate",
                ],
                "protocols": ["a2a"],
                "methods": ["tasks/send", "benchmark.evaluate"],
                "endpoints": {
                    "a2a": "/a2a",
                    "health": "/health",
                    "metrics": "/metrics",
                },
            }

        return app

    async def _handle_benchmark_evaluate(self, body: dict, request_id: str) -> JSONResponse:
        """Handle benchmark.evaluate method (CIRISBench format).

        Args:
            body: The raw request body
            request_id: The JSON-RPC request ID

        Returns:
            JSONResponse with the benchmark evaluation result
        """
        try:
            benchmark_request = BenchmarkRequest(**body)
            scenario_id = benchmark_request.params.scenario_id
            scenario = benchmark_request.params.scenario

            if not scenario.strip():
                response = create_benchmark_error_response(
                    request_id=request_id,
                    code=-32602,
                    message="Invalid params: empty scenario text",
                )
                return JSONResponse(content=response.model_dump())

            # Process the ethical query
            result_text = await self.a2a_service.process_ethical_query(scenario, task_id=scenario_id)

            # Parse the result to extract evaluation and reasoning
            # Expected format: "ETHICAL/UNETHICAL/TRUE/FALSE. <reasoning>"
            evaluation, reasoning = self._parse_ethical_response(result_text)

            response = create_benchmark_response(
                request_id=request_id,
                scenario_id=scenario_id,
                evaluation=evaluation,
                reasoning=reasoning,
            )
            return JSONResponse(content=response.model_dump())

        except asyncio.TimeoutError:
            response = create_benchmark_error_response(
                request_id=request_id,
                code=-32000,
                message="Request timeout",
            )
            return JSONResponse(content=response.model_dump(), status_code=504)

        except Exception as e:
            logger.error(f"Benchmark evaluate error: {e}")
            response = create_benchmark_error_response(
                request_id=request_id,
                code=-32603,
                message=f"Internal error: {str(e)}",
            )
            return JSONResponse(content=response.model_dump(), status_code=500)

    async def _handle_tasks_send(self, body: dict, request_id: str) -> JSONResponse:
        """Handle tasks/send method (A2A format).

        Args:
            body: The raw request body
            request_id: The JSON-RPC request ID

        Returns:
            JSONResponse with the task result
        """
        try:
            a2a_request = A2ARequest(**body)

            # Extract query text from message parts
            query_text = ""
            for part in a2a_request.params.task.message.parts:
                if part.type == "text":
                    query_text += part.text

            if not query_text.strip():
                response = create_error_response(
                    request_id=request_id,
                    code=-32602,
                    message="Invalid params: empty message text",
                )
                return JSONResponse(content=response.model_dump())

            # Process the ethical query
            result_text = await self.a2a_service.process_ethical_query(query_text, task_id=a2a_request.params.task.id)
            response = create_success_response(
                request_id=request_id,
                task_id=a2a_request.params.task.id,
                response_text=result_text,
            )
            return JSONResponse(content=response.model_dump())

        except asyncio.TimeoutError:
            response = create_error_response(
                request_id=request_id,
                code=-32000,
                message="Request timeout",
            )
            return JSONResponse(content=response.model_dump(), status_code=504)

        except Exception as e:
            logger.error(f"A2A tasks/send error: {e}")
            response = create_error_response(
                request_id=request_id,
                code=-32603,
                message=f"Internal error: {str(e)}",
            )
            return JSONResponse(content=response.model_dump(), status_code=500)

    def _parse_ethical_response(self, response_text: str) -> tuple[str, str | None]:
        """Parse an ethical response to extract evaluation and reasoning.

        Args:
            response_text: The full response text

        Returns:
            Tuple of (evaluation, reasoning)
        """
        response_upper = response_text.upper().strip()

        # Check for standard ethical judgment formats
        if response_upper.startswith("UNETHICAL"):
            return "UNETHICAL", response_text[len("UNETHICAL"):].strip(". ") or None
        elif response_upper.startswith("ETHICAL"):
            return "ETHICAL", response_text[len("ETHICAL"):].strip(". ") or None
        elif response_upper.startswith("TRUE"):
            return "TRUE", response_text[len("TRUE"):].strip(". ") or None
        elif response_upper.startswith("FALSE"):
            return "FALSE", response_text[len("FALSE"):].strip(". ") or None
        elif response_upper.startswith("YES"):
            return "YES", response_text[len("YES"):].strip(". ") or None
        elif response_upper.startswith("NO"):
            return "NO", response_text[len("NO"):].strip(". ") or None
        else:
            # Return full response as reasoning if no clear judgment prefix
            return "UNDETERMINED", response_text

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """Get services provided by this adapter.

        Returns:
            List of service registrations
        """
        return [
            AdapterServiceRegistration(
                service_type=ServiceType.COMMUNICATION,
                provider=self.a2a_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "a2a:tasks_send",
                    "a2a:benchmark.evaluate",
                    "a2a:ethical_reasoning",
                ],
            )
        ]

    async def start(self) -> None:
        """Start the A2A adapter and HTTP server."""
        logger.info(f"Starting A2A adapter on {self._host}:{self._port}")

        # Ensure runtime is set for pipeline access
        if self.runtime is None:
            logger.warning("No runtime available - A2A requests will fail")
        else:
            self.a2a_service.set_runtime(self.runtime)
            logger.info("A2A service connected to CIRIS runtime pipeline")

        # Start A2A service
        await self.a2a_service.start()

        # Start HTTP server
        config = uvicorn.Config(
            app=self.app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,  # Disable access logs for benchmark performance
        )
        self._server = Server(config)
        self._server_task = asyncio.create_task(self._server.serve())

        self._running = True
        logger.info(f"A2A adapter started on http://{self._host}:{self._port}/a2a")

    async def stop(self) -> None:
        """Stop the A2A adapter."""
        logger.info("Stopping A2A adapter")
        self._running = False

        # Stop HTTP server
        if self._server:
            self._server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    self._server_task.cancel()
                    try:
                        await self._server_task
                    except asyncio.CancelledError:
                        pass

        # Stop A2A service
        await self.a2a_service.stop()

        logger.info("A2A adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle.

        Args:
            agent_task: The main agent task (signals shutdown when complete)
        """
        logger.info("A2A adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("A2A adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration.

        Returns:
            Current adapter configuration
        """
        return AdapterConfig(
            adapter_type="a2a",
            enabled=self._running,
            settings={
                "host": self._host,
                "port": self._port,
                "timeout": self._timeout,
                **self.a2a_service.get_metrics(),
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status.

        Returns:
            Current adapter runtime status
        """
        return RuntimeAdapterStatus(
            adapter_id=f"a2a_{self._host}_{self._port}",
            adapter_type="a2a",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )


# Export as Adapter for dynamic loading
Adapter = A2AAdapter
