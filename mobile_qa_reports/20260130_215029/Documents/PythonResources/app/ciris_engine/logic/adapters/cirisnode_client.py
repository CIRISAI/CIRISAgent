import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

import httpx

from ciris_engine.logic.adapters.base import Service
from ciris_engine.schemas.adapters.cirisnode import (
    AssessmentResult,
    AssessmentSubmission,
    ChaosTestRequest,
    ChaosTestResult,
    EventLogRequest,
    EventLogResponse,
    HE300Request,
    HE300Result,
    SimpleBenchRequest,
    SimpleBenchResult,
    WAServiceRequest,
    WAServiceResponse,
)

# Configuration loaded via environment variables - no get_config dependency
from ciris_engine.schemas.config.essential import CIRISNodeConfig
from ciris_engine.schemas.runtime.audit import AuditActionContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ServiceType
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry
    from ciris_engine.protocols.services import AuditService

logger = logging.getLogger(__name__)


class CIRISNodeClient(Service):
    """Asynchronous client for interacting with CIRISNode."""

    def __init__(self, service_registry: Optional["ServiceRegistry"] = None, base_url: Optional[str] = None) -> None:
        # Configure retry settings for HTTP operations
        retry_config = {
            "retry": {
                "global": {
                    "max_retries": 3,
                    "base_delay": 1.0,
                    "max_delay": 30.0,  # Shorter max delay for API calls
                },
                "http_request": {
                    "retryable_exceptions": (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError),
                    "non_retryable_exceptions": (httpx.HTTPStatusError,),  # Will be filtered by status code
                },
            }
        }
        super().__init__(config=retry_config)

        self.service_registry = service_registry
        self._audit_service: Optional["AuditService"] = None

        # Use base_url if provided, otherwise use default
        if base_url:
            self.base_url = base_url
        else:
            # Default to localhost for testing/development
            node_cfg = CIRISNodeConfig()
            node_cfg.load_env_vars()
            self.base_url = node_cfg.base_url or "http://localhost:8080"

        self._client = httpx.AsyncClient(base_url=self.base_url)
        self._closed = False

    async def _get_audit_service(self) -> Optional["AuditService"]:
        """Retrieve the audit service from the registry with caching."""
        if self._audit_service is not None:
            return self._audit_service

        if not self.service_registry:
            logger.debug("CIRISNodeClient has no service registry; audit logging disabled")
            return None

        self._audit_service = await self.service_registry.get_service(
            self.__class__.__name__, ServiceType.AUDIT, required_capabilities=["log_action"]
        )

        if not self._audit_service:
            logger.warning("No audit service available for CIRISNodeClient")
        return self._audit_service

    async def start(self) -> None:
        """Start the client service."""
        await super().start()

    async def stop(self) -> None:
        """Stop the client service and clean up resources."""
        await self._client.aclose()
        await super().stop()
        self._closed = True

    async def close(self) -> None:
        """Alias for stop() for backwards compatibility."""
        await self.stop()

    def is_closed(self) -> bool:
        return self._closed

    async def _post(self, endpoint: str, payload: JSONDict) -> Any:
        async def _make_request() -> Any:
            resp = await self._client.post(endpoint, json=payload)
            if 400 <= resp.status_code < 500:
                resp.raise_for_status()  # Don't retry 4xx client errors
            resp.raise_for_status()  # Raise for any other errors (will be retried)
            return await resp.json()

        return await self.retry_with_backoff(
            _make_request,
            retryable_exceptions=(httpx.ConnectError, httpx.TimeoutException),
            non_retryable_exceptions=(httpx.HTTPStatusError,),
            **self.get_retry_config("http_request"),
        )

    async def _get(self, endpoint: str, params: JSONDict) -> Any:
        from typing import Mapping, cast

        async def _make_request() -> Any:
            resp = await self._client.get(endpoint, params=cast(Mapping[str, str | int | float | bool | None], params))
            if 400 <= resp.status_code < 500:
                resp.raise_for_status()  # Don't retry 4xx client errors
            resp.raise_for_status()  # Raise for any other errors (will be retried)
            return await resp.json()

        return await self.retry_with_backoff(
            _make_request,
            retryable_exceptions=(httpx.ConnectError, httpx.TimeoutException),
            non_retryable_exceptions=(httpx.HTTPStatusError,),
            **self.get_retry_config("http_request"),
        )

    async def _put(self, endpoint: str, payload: JSONDict) -> Any:
        async def _make_request() -> Any:
            resp = await self._client.put(endpoint, json=payload)
            if 400 <= resp.status_code < 500:
                resp.raise_for_status()  # Don't retry 4xx client errors
            resp.raise_for_status()  # Raise for any other errors (will be retried)
            return await resp.json()

        return await self.retry_with_backoff(
            _make_request,
            retryable_exceptions=(httpx.ConnectError, httpx.TimeoutException),
            non_retryable_exceptions=(httpx.HTTPStatusError,),
            **self.get_retry_config("http_request"),
        )

    async def run_simplebench(self, model_id: str, agent_id: str) -> SimpleBenchResult:
        """Run the simple bench benchmark for the given model."""
        request = SimpleBenchRequest(model_id=model_id, agent_id=agent_id)
        response = await self._post("/simplebench", request.model_dump())
        result = SimpleBenchResult.model_validate(response)
        audit_service = await self._get_audit_service()
        if audit_service:
            await audit_service.log_action(
                HandlerActionType.TOOL,
                AuditActionContext(
                    thought_id=agent_id,
                    task_id="simplebench",
                    handler_name="cirisnode_client",
                    parameters={"model_id": model_id, "agent_id": agent_id},
                ),
                outcome=f"SimpleBench completed with score {result.score}",
            )
        return result

    async def run_he300(self, model_id: str, agent_id: str) -> HE300Result:
        """Run the HE-300 benchmark for the given model."""
        request = HE300Request(model_id=model_id, agent_id=agent_id)
        response = await self._post("/he300", request.model_dump())
        result = HE300Result.model_validate(response)
        audit_service = await self._get_audit_service()
        if audit_service:
            await audit_service.log_action(
                HandlerActionType.TOOL,
                AuditActionContext(
                    thought_id=agent_id,
                    task_id="he300",
                    handler_name="cirisnode_client",
                    parameters={"model_id": model_id, "agent_id": agent_id},
                ),
                outcome=f"HE-300 completed with ethics score {result.ethics_score}",
            )
        return result

    async def run_chaos_tests(self, agent_id: str, scenarios: List[str]) -> List[ChaosTestResult]:
        """Run chaos test scenarios and return verdicts."""
        request = ChaosTestRequest(agent_id=agent_id, scenarios=scenarios)
        response = await self._post("/chaos", request.model_dump())
        result = [ChaosTestResult.model_validate(r) for r in response]
        audit_service = await self._get_audit_service()
        if audit_service:
            await audit_service.log_action(
                HandlerActionType.TOOL,
                AuditActionContext(
                    thought_id=agent_id,
                    task_id="chaos_tests",
                    handler_name="cirisnode_client",
                    parameters={"agent_id": agent_id, "scenarios": scenarios},
                ),
                outcome=f"Chaos tests completed: {len(result)} scenarios",
            )
        return result

    async def run_wa_service(self, service: str, action: str, params: JSONDict) -> WAServiceResponse:
        """Call a WA service on CIRISNode."""
        request = WAServiceRequest(service=service, action=action, params=params)
        response = await self._post(f"/wa/{service}", request.model_dump())
        result = WAServiceResponse.model_validate(response)
        audit_service = await self._get_audit_service()
        if audit_service:
            await audit_service.log_action(
                HandlerActionType.TOOL,
                AuditActionContext(
                    thought_id=params.get("agent_id", "unknown"),
                    task_id=f"wa_service_{service}",
                    handler_name="cirisnode_client",
                    parameters={"service": service, "action": action, **params},
                ),
                outcome=f"WA service {service} completed",
            )
        return result

    async def log_event(
        self, event_type: str, event_data: JSONDict, agent_id: Optional[str] = None
    ) -> EventLogResponse:
        """Send an event payload to CIRISNode for storage."""
        request = EventLogRequest(event_type=event_type, event_data=event_data, agent_id=agent_id)
        response = await self._post("/events", request.model_dump())
        result = EventLogResponse.model_validate(response)
        audit_service = await self._get_audit_service()
        if audit_service:
            await audit_service.log_action(
                HandlerActionType.TOOL,
                AuditActionContext(
                    thought_id=agent_id or "unknown",
                    task_id="log_event",
                    handler_name="cirisnode_client",
                    parameters={"event_type": event_type, "agent_id": agent_id},
                ),
                outcome=f"Event logged: {event_type}",
            )
        return result

    async def fetch_benchmark_prompts(
        self,
        benchmark: str,
        model_id: str,
        agent_id: str,
    ) -> List[JSONDict]:
        """Retrieve benchmark prompts from CIRISNode."""
        result = cast(
            List[JSONDict],
            await self._get(
                f"/bench/{benchmark}/prompts",
                {"model_id": model_id, "agent_id": agent_id},
            ),
        )
        audit_service = await self._get_audit_service()
        if audit_service:
            await audit_service.log_action(
                HandlerActionType.TOOL,
                AuditActionContext(
                    thought_id=agent_id,
                    task_id=f"fetch_{benchmark}_prompts",
                    handler_name="cirisnode_client",
                    parameters={"benchmark": benchmark, "model_id": model_id, "agent_id": agent_id},
                ),
                outcome=f"Fetched {len(result)} {benchmark} prompts",
            )
        return result

    async def submit_benchmark_answers(
        self,
        benchmark: str,
        model_id: str,
        agent_id: str,
        answers: List[JSONDict],
    ) -> AssessmentResult:
        """Send benchmark answers back to CIRISNode."""
        submission = AssessmentSubmission(assessment_id=benchmark, agent_id=agent_id, answers=answers)
        response = await self._put(
            f"/bench/{benchmark}/answers",
            submission.model_dump(),
        )
        result = AssessmentResult.model_validate(response)
        audit_service = await self._get_audit_service()
        if audit_service:
            await audit_service.log_action(
                HandlerActionType.TOOL,
                AuditActionContext(
                    thought_id=agent_id,
                    task_id=f"submit_{benchmark}_answers",
                    handler_name="cirisnode_client",
                    parameters={
                        "benchmark": benchmark,
                        "model_id": model_id,
                        "agent_id": agent_id,
                        "answer_count": len(answers),
                    },
                ),
                outcome=f"Submitted {len(answers)} {benchmark} answers",
            )
        return result
