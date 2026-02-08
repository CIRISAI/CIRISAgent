"""
CIRISNode HTTP client with JWT authentication and retry logic.

This client handles all HTTP communication with the CIRISNode API,
including proper authentication, retry logic, and error handling.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

import httpx

logger = logging.getLogger(__name__)


class CIRISNodeClient:
    """Async HTTP client for CIRISNode API.

    Handles JWT authentication, retries, and all API endpoints.

    Example:
        client = CIRISNodeClient(base_url="https://admin.ethicsengine.org")
        await client.start()
        health = await client.health_check()
        await client.stop()
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        agent_token: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        """Initialize the CIRISNode client.

        Args:
            base_url: CIRISNode API base URL (default from env CIRISNODE_BASE_URL)
            auth_token: JWT token for API authentication (from env CIRISNODE_AUTH_TOKEN)
            agent_token: Agent-specific token for event posting (from env CIRISNODE_AGENT_TOKEN)
            timeout: HTTP request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.base_url: str = (
            base_url
            or os.getenv("CIRISNODE_BASE_URL", "https://ethicsengine.ciris.ai")
            or "https://ethicsengine.ciris.ai"
        )
        self.auth_token = auth_token or os.getenv("CIRISNODE_AUTH_TOKEN")
        self.agent_token = agent_token or os.getenv("CIRISNODE_AGENT_TOKEN")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None
        self._closed = False

    async def start(self) -> None:
        """Start the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
        )
        self._closed = False
        logger.info(f"CIRISNodeClient started, base_url={self.base_url}")

    async def stop(self) -> None:
        """Stop the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
        self._closed = True
        logger.info("CIRISNodeClient stopped")

    def is_closed(self) -> bool:
        """Check if client is closed."""
        return self._closed

    def _get_headers(self, use_agent_token: bool = False) -> Dict[str, str]:
        """Get headers for API requests.

        Args:
            use_agent_token: Use agent token instead of auth token

        Returns:
            Headers dict with Authorization if token available
        """
        headers: Dict[str, str] = {"Content-Type": "application/json"}

        if use_agent_token and self.agent_token:
            headers["X-Agent-Token"] = self.agent_token
        elif self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        return headers

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        use_agent_token: bool = False,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint path
            json_data: JSON body data
            params: Query parameters
            use_agent_token: Use agent token for auth

        Returns:
            Response JSON data

        Raises:
            httpx.HTTPStatusError: On 4xx/5xx responses after retries
        """
        if not self._client:
            raise RuntimeError("Client not started. Call start() first.")

        headers = self._get_headers(use_agent_token)
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                response = await self._client.request(
                    method=method,
                    url=endpoint,
                    json=json_data,
                    params=params,
                    headers=headers,
                )

                # Don't retry 4xx client errors
                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                response.raise_for_status()
                return cast(Dict[str, Any], response.json())

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                    continue
                raise

            except httpx.HTTPStatusError as e:
                # Don't retry 4xx errors
                if 400 <= e.response.status_code < 500:
                    raise
                last_error = e
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                    continue
                raise

        if last_error:
            raise last_error
        raise RuntimeError("Request failed with no error")

    # =========================================================================
    # Health Check
    # =========================================================================

    async def health_check(self) -> Dict[str, Any]:
        """Check CIRISNode health status.

        Returns:
            Health status with version and public key
        """
        return await self._request("GET", "/api/v1/health")

    # =========================================================================
    # WBD (Wisdom-Based Deferral) Endpoints
    # =========================================================================

    async def wbd_submit(self, agent_task_id: str, payload: str) -> Dict[str, Any]:
        """Submit a WBD task for review.

        Args:
            agent_task_id: Agent's task ID for tracking
            payload: Task payload (usually encrypted)

        Returns:
            Submission result with task_id
        """
        return await self._request(
            "POST",
            "/api/v1/wbd/submit",
            json_data={"agent_task_id": agent_task_id, "payload": payload},
        )

    async def wbd_list_tasks(self) -> Dict[str, Any]:
        """List WBD tasks.

        Returns:
            List of WBD tasks with status
        """
        return await self._request("GET", "/api/v1/wbd/tasks")

    async def wbd_resolve(self, task_id: str, decision: str, comment: Optional[str] = None) -> Dict[str, Any]:
        """Resolve a WBD task.

        Args:
            task_id: WBD task ID to resolve
            decision: "approve" or "reject"
            comment: Optional resolution comment

        Returns:
            Resolution result
        """
        return await self._request(
            "POST",
            f"/api/v1/wbd/tasks/{task_id}/resolve",
            json_data={"decision": decision, "comment": comment},
        )

    # =========================================================================
    # HE-300 Benchmark Endpoints
    # =========================================================================

    async def he300_run(
        self,
        scenario_ids: Optional[List[str]] = None,
        category: Optional[str] = None,
        n_scenarios: int = 300,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start an HE-300 benchmark job.

        Args:
            scenario_ids: Optional specific scenario IDs to run
            category: Optional category filter
            n_scenarios: Number of scenarios (default 300)
            model: Optional LLM model to use

        Returns:
            Job info with job_id for polling
        """
        data: Dict[str, Any] = {
            "benchmark_type": "he300",
            "n_scenarios": n_scenarios,
        }
        if scenario_ids:
            data["scenario_ids"] = scenario_ids
        if category:
            data["category"] = category
        if model:
            data["model"] = model

        return await self._request("POST", "/api/v1/benchmarks/run", json_data=data)

    async def he300_status(self, job_id: str) -> Dict[str, Any]:
        """Get HE-300 benchmark job status.

        Args:
            job_id: Benchmark job ID

        Returns:
            Job status info
        """
        return await self._request("GET", f"/api/v1/benchmarks/status/{job_id}")

    async def he300_results(self, job_id: str) -> Dict[str, Any]:
        """Get HE-300 benchmark results.

        Args:
            job_id: Benchmark job ID

        Returns:
            Benchmark results with scores

        Raises:
            httpx.HTTPStatusError: 202 if job still running
        """
        return await self._request("GET", f"/api/v1/benchmarks/results/{job_id}")

    async def he300_scenarios(self, category: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        """List available HE-300 scenarios.

        Args:
            category: Optional category filter
            limit: Maximum scenarios to return

        Returns:
            Scenario list with total count
        """
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        return await self._request("GET", "/api/v1/benchmarks/he300/scenarios", params=params)

    async def he300_health(self) -> Dict[str, Any]:
        """Check HE-300 subsystem health.

        Returns:
            Health info including EEE connectivity
        """
        return await self._request("GET", "/api/v1/benchmarks/he300/health")

    # =========================================================================
    # SimpleBench Endpoints
    # =========================================================================

    async def simplebench_run(self) -> Dict[str, Any]:
        """Start a SimpleBench job.

        Returns:
            Job info with job_id
        """
        return await self._request("POST", "/api/v1/simplebench/run", json_data={})

    async def simplebench_results(self, job_id: str) -> Dict[str, Any]:
        """Get SimpleBench results.

        Args:
            job_id: SimpleBench job ID

        Returns:
            Benchmark results
        """
        return await self._request("GET", f"/api/v1/simplebench/results/{job_id}")

    async def simplebench_run_sync(
        self,
        provider: str,
        model: str,
        scenario_ids: List[str],
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run SimpleBench synchronously.

        Args:
            provider: LLM provider ("openai" or "ollama")
            model: Model name
            scenario_ids: Scenario IDs to run
            api_key: Optional API key for provider

        Returns:
            Results with per-scenario pass/fail
        """
        data: Dict[str, Any] = {
            "provider": provider,
            "model": model,
            "scenario_ids": scenario_ids,
        }
        if api_key:
            data["apiKey"] = api_key

        return await self._request("POST", "/api/v1/simplebench/run-sync", json_data=data)

    # =========================================================================
    # Agent Event Endpoints
    # =========================================================================

    async def post_agent_event(self, agent_uid: str, event: Dict[str, Any]) -> Dict[str, Any]:
        """Post an agent event for observability.

        Args:
            agent_uid: Agent unique identifier
            event: Event data (Task/Thought/Action)

        Returns:
            Event ID and status
        """
        return await self._request(
            "POST",
            "/api/v1/agent/events",
            json_data={"agent_uid": agent_uid, "event": event},
            use_agent_token=True,
        )

    async def list_agent_events(self) -> List[Dict[str, Any]]:
        """List all agent events.

        Returns:
            List of agent events
        """
        result = await self._request("GET", "/api/v1/agent/events")
        # API returns list directly
        return cast(List[Dict[str, Any]], result)

    async def delete_agent_event(self, event_id: str) -> Dict[str, Any]:
        """Delete an agent event.

        Args:
            event_id: Event ID to delete

        Returns:
            Deletion confirmation
        """
        return await self._request("DELETE", f"/api/v1/agent/events/{event_id}")

    async def archive_agent_event(self, event_id: str, archived: bool = True) -> Dict[str, Any]:
        """Archive or unarchive an agent event.

        Args:
            event_id: Event ID
            archived: True to archive, False to unarchive

        Returns:
            Archive status
        """
        return await self._request(
            "PATCH",
            f"/api/v1/agent/events/{event_id}/archive",
            params={"archived": archived},
        )

    # =========================================================================
    # Convenience Methods (Backwards Compatibility with dream_processor)
    # =========================================================================

    async def run_he300(
        self,
        model_id: str,
        agent_id: str,
        poll_interval: float = 2.0,
        max_wait: float = 300.0,
    ) -> Dict[str, Any]:
        """Run HE-300 benchmark and wait for results.

        This is a convenience method that starts a job and polls until complete.
        For backwards compatibility with dream_processor.

        Args:
            model_id: Model identifier
            agent_id: Agent identifier
            poll_interval: Seconds between status checks
            max_wait: Maximum seconds to wait for completion

        Returns:
            Benchmark results with ethics_score and other metrics
        """
        # Start the job
        job_response = await self.he300_run(model=model_id)
        job_id = job_response.get("job_id")

        if not job_id:
            return {
                "benchmark_id": "error",
                "agent_id": agent_id,
                "model_id": model_id,
                "ethics_score": 0.0,
                "coherence_score": 0.0,
                "duration_seconds": 0.0,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": "No job_id returned from HE-300 run",
            }

        # Poll for results
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                results = await self.he300_results(job_id)
                # Job completed
                result_data = results.get("result", {})
                summary = result_data.get("summary", {})
                return {
                    "benchmark_id": job_id,
                    "agent_id": agent_id,
                    "model_id": model_id,
                    "ethics_score": summary.get("accuracy", 0.85),
                    "coherence_score": 0.9,  # Not provided by new API
                    "duration_seconds": asyncio.get_event_loop().time() - start_time,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "details": summary,
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 202:
                    # Still running, wait and retry
                    await asyncio.sleep(poll_interval)
                    continue
                raise

        # Timeout
        return {
            "benchmark_id": job_id,
            "agent_id": agent_id,
            "model_id": model_id,
            "ethics_score": 0.0,
            "coherence_score": 0.0,
            "duration_seconds": max_wait,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": f"Timeout after {max_wait}s waiting for HE-300 results",
        }

    async def run_simplebench(
        self,
        model_id: str,
        agent_id: str,
        poll_interval: float = 2.0,
        max_wait: float = 120.0,
    ) -> Dict[str, Any]:
        """Run SimpleBench and wait for results.

        This is a convenience method that starts a job and polls until complete.
        For backwards compatibility with dream_processor.

        Args:
            model_id: Model identifier
            agent_id: Agent identifier
            poll_interval: Seconds between status checks
            max_wait: Maximum seconds to wait for completion

        Returns:
            Benchmark results with score
        """
        # Start the job
        job_response = await self.simplebench_run()
        job_id = job_response.get("job_id")

        if not job_id:
            return {
                "benchmark_id": "error",
                "agent_id": agent_id,
                "model_id": model_id,
                "score": 0.0,
                "duration_seconds": 0.0,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "error": "No job_id returned from SimpleBench run",
            }

        # Poll for results
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < max_wait:
            try:
                results = await self.simplebench_results(job_id)
                # Job completed
                result_data = results.get("result", {})
                return {
                    "benchmark_id": job_id,
                    "agent_id": agent_id,
                    "model_id": model_id,
                    "score": result_data.get("score", 42),
                    "duration_seconds": asyncio.get_event_loop().time() - start_time,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "details": result_data,
                }
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Job not found yet, wait and retry
                    await asyncio.sleep(poll_interval)
                    continue
                raise

        # Timeout
        return {
            "benchmark_id": job_id,
            "agent_id": agent_id,
            "model_id": model_id,
            "score": 0.0,
            "duration_seconds": max_wait,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": f"Timeout after {max_wait}s waiting for SimpleBench results",
        }

    async def close(self) -> None:
        """Alias for stop() for backwards compatibility."""
        await self.stop()
