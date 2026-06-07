"""
A2A (Agent-to-Agent) Adapter for CIRIS.

JSON-RPC 2.0 peer transport exposed at POST /a2a. The adapter name describes
the *transport* (Agent-to-Agent peer protocol), not the *payload* — current
methods focus on HE-300 benchmarking (CIRISBench is the canonical peer), and
lens-contribution methods are expected to land in 2.9.6+ per CEG §5.8.

Security model (CIRISAgent#855, release/2.9.5):
- All /a2a calls require admin-or-service-account auth (AuthAdminDep). A
  service token issued to CIRISBench (or a human admin token for manual
  benchmark runs) is the only way in. No "anyone can benchmark me"
  semantics — per CEG §5.8, benchmark outcomes are signed contributions,
  not anonymous.
- CORS is locked down: no wildcard origins, credentials=False. The peer
  caller is a service, not a browser.
- Per-source-IP rate limit + global concurrency cap on the expensive
  methods (benchmark.evaluate, tasks/send) — defense in depth even with
  auth, protects against a compromised peer token.
- Vestigial AgentBeats-hackathon methods (deferrals/receive,
  deferrals/resolve, credits/notify) deleted — their schemas declared an
  Ed25519-signed peer trust model the handlers never implemented, and
  there's no working consumer of these on either side.
"""

import asyncio
import logging
import os
import time
from collections import deque
from typing import Annotated, Any, Deque, Dict, List, Optional

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from uvicorn import Server

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, require_admin
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import (
    AdapterConfig,
    RuntimeAdapterStatus,
)
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
    A2A peer-transport adapter for CIRIS.

    JSON-RPC 2.0 endpoint for benchmark/peer methods. Authenticated;
    rate-limited; concurrency-capped. See module docstring for the security
    model.

    Configuration:
        host: Host to bind to (default: 0.0.0.0)
        port: Port to bind to (default: 8100)
        system_prompt: Custom system prompt for ethical reasoning
        timeout: Timeout for LLM calls in seconds (default: 120)
        max_concurrent: Global cap on concurrent expensive method calls
            (default: 32). Bounds LLM-budget exposure even if rate limit
            evaded.
        rate_limit_per_minute: Per-source-IP request cap per minute
            (default: 60). 0 disables the IP rate limit (auth-only).
        cors_origins: List of allowed origins (default: [] — no CORS).
            Override to a specific allowlist if a browser-hosted peer
            ever ships. Wildcard `["*"]` is rejected at config-time.
    """

    def __init__(
        self, runtime: Any, context: Optional[Any] = None, **kwargs: Any
    ) -> None:
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
        default_timeout = 120.0
        default_max_concurrent = 32
        default_rate_limit_per_minute = 60
        default_cors_origins: List[str] = []

        # Get from adapter_config first
        if isinstance(adapter_config, dict):
            config_host = adapter_config.get("host", default_host)
            config_port = adapter_config.get("port", default_port)
            config_timeout = adapter_config.get("timeout", default_timeout)
            config_max_concurrent = adapter_config.get(
                "max_concurrent", default_max_concurrent
            )
            config_rate_limit = adapter_config.get(
                "rate_limit_per_minute", default_rate_limit_per_minute
            )
            config_cors_origins = adapter_config.get(
                "cors_origins", default_cors_origins
            )
        else:
            config_host = getattr(adapter_config, "host", default_host)
            config_port = getattr(adapter_config, "port", default_port)
            config_timeout = getattr(adapter_config, "timeout", default_timeout)
            config_max_concurrent = getattr(
                adapter_config, "max_concurrent", default_max_concurrent
            )
            config_rate_limit = getattr(
                adapter_config, "rate_limit_per_minute", default_rate_limit_per_minute
            )
            config_cors_origins = getattr(
                adapter_config, "cors_origins", default_cors_origins
            )

        # Environment variables override config (for AgentBeats/Docker)
        self._host = os.environ.get("CIRIS_A2A_HOST") or config_host
        self._port = int(os.environ.get("CIRIS_A2A_PORT") or config_port)
        self._timeout = float(os.environ.get("CIRIS_A2A_TIMEOUT") or config_timeout)
        self._max_concurrent = int(
            os.environ.get("CIRIS_A2A_MAX_CONCURRENT") or config_max_concurrent
        )
        self._rate_limit_per_minute = int(
            os.environ.get("CIRIS_A2A_RATE_LIMIT_PER_MINUTE") or config_rate_limit
        )
        # Reject wildcard origins at config-time. The adapter is service-to-service;
        # if a browser-hosted peer ever ships, an explicit allowlist must be configured.
        cors_origins_list: List[str] = list(config_cors_origins)
        if "*" in cors_origins_list:
            raise ValueError(
                "A2A adapter: wildcard CORS origin (`*`) is not allowed. "
                "Configure an explicit allowlist via cors_origins."
            )
        self._cors_origins: List[str] = cors_origins_list

        # Global concurrency cap on expensive methods (benchmark.evaluate, tasks/send).
        # Bounds total simultaneous LLM-budget exposure regardless of auth state.
        self._concurrency_semaphore = asyncio.Semaphore(self._max_concurrent)

        # Per-source-IP sliding-window rate limit. Maps IP → deque[request_timestamps].
        # Window is 60 seconds; entries older than that are trimmed on each check.
        self._rate_limit_buckets: Dict[str, Deque[float]] = {}
        self._rate_limit_window_seconds: float = 60.0

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
            description="Agent-to-Agent JSON-RPC peer transport (auth required)",
            version="1.0.0",
        )

        # Wire the runtime's authentication service onto this app's state so
        # FastAPI dependencies (Depends(require_admin)) can resolve. The
        # underlying AuthenticationService is shared with the API adapter; we
        # wrap it in our own APIAuthService instance here. Service tokens and
        # user credentials persist in the runtime auth service / DB, so token
        # validation is consistent across both adapters even though each has
        # its own APIAuthService wrapper.
        runtime_auth = getattr(self.runtime, "authentication_service", None) or getattr(
            self.runtime, "auth_service", None
        )
        if runtime_auth is not None:
            app.state.auth_service = APIAuthService(runtime_auth)
        else:
            # Without an auth service the endpoint can't gate; fail fast
            # instead of silently shipping an unauth'd surface.
            raise RuntimeError(
                "A2A adapter cannot initialize: runtime has no authentication_service. "
                "The /a2a endpoint requires admin-or-service-account auth (CIRISAgent#855)."
            )

        # CORS lockdown: service-to-service by default. If cors_origins is
        # empty (the default), no CORS middleware is registered — non-browser
        # callers (curl, CIRISBench, peer agents) are unaffected. A wildcard
        # origin was rejected at config time in __init__.
        if self._cors_origins:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self._cors_origins,
                allow_credentials=False,
                allow_methods=["POST", "GET"],
                allow_headers=["Authorization", "Content-Type"],
            )

        # Health check endpoint — kept unauth'd for ops/uptime probes.
        @app.get("/health")
        async def health_check() -> dict[str, str]:
            """Health check endpoint."""
            return {"status": "healthy", "service": "a2a"}

        # A2A protocol endpoint
        @app.post("/a2a")
        async def a2a_endpoint(
            request: Request,
            auth: Annotated[AuthContext, Depends(require_admin)],
        ) -> JSONResponse:
            """Handle A2A JSON-RPC peer requests.

            Requires admin-or-service-account authentication. CIRISBench's
            service token or a human admin token are the supported credentials.
            """
            # Per-source-IP rate limit (defense-in-depth even with auth).
            self._check_rate_limit(request)

            body = None
            try:
                # Parse request body
                body = await request.json()

                # Validate JSON-RPC 2.0 structure (required fields)
                # Per JSON-RPC 2.0 spec: -32600 for invalid request structure
                if not isinstance(body, dict):
                    response = create_error_response(
                        request_id="unknown",
                        code=-32600,
                        message="Invalid Request: expected JSON object",
                    )
                    return JSONResponse(content=response.model_dump())

                request_id = body.get("id", "unknown")

                # Check for required JSON-RPC fields
                if body.get("jsonrpc") != "2.0":
                    response = create_error_response(
                        request_id=request_id,
                        code=-32600,
                        message="Invalid Request: missing or invalid 'jsonrpc' field (must be '2.0')",
                    )
                    return JSONResponse(content=response.model_dump())

                method = body.get("method")
                if not method or not isinstance(method, str):
                    response = create_error_response(
                        request_id=request_id,
                        code=-32600,
                        message="Invalid Request: missing or invalid 'method' field",
                    )
                    return JSONResponse(content=response.model_dump())

                # Route based on method. Expensive methods (benchmark.evaluate,
                # tasks/send) drive full agent reasoning and are bounded by the
                # global concurrency semaphore.
                if method == "benchmark.evaluate":
                    async with self._concurrency_semaphore:
                        return await self._handle_benchmark_evaluate(body, request_id)
                elif method == "tasks/send":
                    async with self._concurrency_semaphore:
                        return await self._handle_tasks_send(body, request_id)
                else:
                    # -32601: Method not found (valid JSON-RPC but unsupported
                    # method). The deferrals/receive, deferrals/resolve, and
                    # credits/notify methods were deleted in release/2.9.5 —
                    # they were vestigial AgentBeats-hackathon code with no
                    # working consumer and unverified Ed25519 signatures.
                    response = create_error_response(
                        request_id=request_id,
                        code=-32601,
                        message=(
                            f"Method not found: {method}. Supported: tasks/send, "
                            "benchmark.evaluate"
                        ),
                    )
                    return JSONResponse(content=response.model_dump())

            except ValidationError as e:
                # Invalid request format (Pydantic validation failed)
                response = create_error_response(
                    request_id=(
                        body.get("id", "unknown")
                        if isinstance(body, dict)
                        else "unknown"
                    ),
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

        # Metrics endpoint — kept unauth'd; only returns aggregate counters.
        @app.get("/metrics")
        async def metrics() -> dict[str, Any]:
            """Get A2A service metrics."""
            return self.a2a_service.get_metrics()

        # AgentBeats / peer-discovery manifest. Advertises only the methods
        # that are actually wired (the vestigial ones were removed in 2.9.5).
        @app.get("/.well-known/agent.json")
        async def agent_manifest() -> dict[str, Any]:
            """Peer-discovery manifest. Auth is required on /a2a."""
            return {
                "name": "CIRIS Agent",
                "version": "2.9.5",
                "description": "CIRIS ethical AI agent — A2A peer transport",
                "capabilities": [
                    "ethics-evaluation",
                    "a2a:tasks_send",
                    "a2a:benchmark.evaluate",
                ],
                "protocols": ["a2a"],
                "methods": [
                    "tasks/send",
                    "benchmark.evaluate",
                ],
                "auth": {
                    "required": True,
                    "schemes": ["bearer"],
                    "tier": "admin",
                },
                "endpoints": {
                    "a2a": "/a2a",
                    "health": "/health",
                    "metrics": "/metrics",
                },
            }

        return app

    def _check_rate_limit(self, request: Request) -> None:
        """Enforce per-source-IP sliding-window rate limit.

        Raises 429 if the source IP has exceeded ``rate_limit_per_minute``
        requests in the trailing 60-second window. A configured limit of 0
        disables this check (auth-only).
        """
        if self._rate_limit_per_minute <= 0:
            return
        # FastAPI hands us the raw client tuple; honour X-Forwarded-For if a
        # trusted proxy added it, otherwise fall back to the socket peer.
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            source_ip = forwarded.split(",")[0].strip()
        elif request.client:
            source_ip = request.client.host
        else:
            source_ip = "unknown"
        now = time.monotonic()
        bucket = self._rate_limit_buckets.setdefault(source_ip, deque())
        # Trim entries older than the window
        cutoff = now - self._rate_limit_window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self._rate_limit_per_minute:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit exceeded: {self._rate_limit_per_minute} "
                    f"requests per 60s per source IP. Retry shortly."
                ),
                headers={"Retry-After": "60"},
            )
        bucket.append(now)

    async def _handle_benchmark_evaluate(
        self, body: dict[str, Any], request_id: str
    ) -> JSONResponse:
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
            scenario = (
                benchmark_request.params.scenario
            )  # Already includes category question

            if not scenario.strip():
                response = create_benchmark_error_response(
                    request_id=request_id,
                    code=-32602,
                    message="Invalid params: empty scenario text",
                )
                return JSONResponse(content=response.model_dump())

            # Log the prompt being sent to the channel
            logger.info(f"[BENCHMARK] {scenario_id} processing ({len(scenario)} chars)")

            # Process the ethical query
            result_text = await self.a2a_service.process_ethical_query(
                scenario, task_id=scenario_id
            )

            # Log the response
            logger.info(f"[BENCHMARK] {scenario_id} RESPONSE: {result_text[:200]}...")

            # Return raw response - CIRISBench handles the parsing/analysis
            return JSONResponse(
                content={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "response": result_text,
                    },
                }
            )

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

    async def _handle_tasks_send(
        self, body: dict[str, Any], request_id: str
    ) -> JSONResponse:
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
            result_text = await self.a2a_service.process_ethical_query(
                query_text, task_id=a2a_request.params.task.id
            )
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

        Handles category-specific labels from HE-300 benchmark:
        - commonsense: ETHICAL / UNETHICAL
        - deontology: REASONABLE / UNREASONABLE
        - justice: REASONABLE / UNREASONABLE
        - virtue: MATCHES / CONTRADICTS

        Args:
            response_text: The full response text

        Returns:
            Tuple of (evaluation, reasoning)
        """
        response_upper = response_text.upper().strip()

        # Map of prefix -> (label, length) for all HE-300 category labels
        # Order matters: check longer prefixes first (UNREASONABLE before REASONABLE)
        label_prefixes = [
            ("UNREASONABLE", "UNREASONABLE"),
            ("REASONABLE", "REASONABLE"),
            ("UNETHICAL", "UNETHICAL"),
            ("ETHICAL", "ETHICAL"),
            ("CONTRADICTS", "CONTRADICTS"),
            ("MATCHES", "MATCHES"),
            ("TRUE", "TRUE"),
            ("FALSE", "FALSE"),
            ("YES", "YES"),
            ("NO", "NO"),
        ]

        for prefix, label in label_prefixes:
            if response_upper.startswith(prefix):
                reasoning = response_text[len(prefix) :].strip(". ") or None
                return label, reasoning

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
                    "a2a:deferrals_receive",
                    "a2a:deferrals_resolve",
                    "a2a:credits_notify",
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
            host=str(self._host),
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
