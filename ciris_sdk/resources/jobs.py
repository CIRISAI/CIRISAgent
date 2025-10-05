"""
Async job management for expensive operations in CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.

Provides async job pattern for long-running operations like:
- Large memory queries
- Bulk imports/exports
- Complex telemetry aggregations
- Audit log exports
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

from ..transport import Transport


class JobStatus(Enum):
    """Status of an async job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(Enum):
    """Types of async jobs."""

    MEMORY_QUERY = "memory_query"
    MEMORY_BULK_IMPORT = "memory_bulk_import"
    AUDIT_EXPORT = "audit_export"
    TELEMETRY_QUERY = "telemetry_query"
    TELEMETRY_AGGREGATION = "telemetry_aggregation"


class JobInfo(BaseModel):
    """Information about an async job."""

    job_id: str = Field(..., description="Unique job identifier")
    job_type: JobType = Field(..., description="Type of job")
    status: JobStatus = Field(..., description="Current job status")
    created_at: datetime = Field(..., description="When job was created")
    started_at: Optional[datetime] = Field(
        None, description="When job started processing"
    )
    completed_at: Optional[datetime] = Field(None, description="When job completed")
    progress: int = Field(0, ge=0, le=100, description="Progress percentage (0-100)")
    message: Optional[str] = Field(None, description="Current status message")
    error: Optional[str] = Field(None, description="Error message if failed")
    result_size: Optional[int] = Field(None, description="Size of result data")
    expires_at: datetime = Field(..., description="When job results will expire")


class JobCreateRequest(BaseModel):
    """Request to create an async job."""

    job_type: JobType = Field(..., description="Type of job to create")
    parameters: Dict[str, Any] = Field(..., description="Job-specific parameters")
    priority: str = Field("normal", description="Job priority (low/normal/high)")


class JobCreateResponse(BaseModel):
    """Response from creating an async job."""

    job_id: str = Field(..., description="Unique job identifier")
    status: JobStatus = Field(..., description="Initial job status")
    estimated_duration_seconds: Optional[int] = Field(
        None, description="Estimated time to complete"
    )
    queue_position: Optional[int] = Field(None, description="Position in job queue")


T = TypeVar("T")


class JobResult(BaseModel, Generic[T]):
    """Result from a completed job."""

    job_id: str = Field(..., description="Job identifier")
    status: JobStatus = Field(..., description="Final job status")
    result: Optional[T] = Field(None, description="Job result data")
    error: Optional[str] = Field(None, description="Error if job failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Job metadata")


class JobsResource:
    """
    Async job management for expensive operations.

    Use this for operations that may take longer than typical request timeouts
    or that require significant computational resources.

    Example:
        # Start a large memory query job
        job = await client.jobs.create_memory_query(
            type="EXPERIENCE",
            since=datetime(2024, 1, 1),
            include_total=True
        )

        # Poll for completion
        while True:
            status = await client.jobs.get_status(job.job_id)
            if status.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                break
            print(f"Progress: {status.progress}%")
            await asyncio.sleep(2)

        # Get results
        if status.status == JobStatus.COMPLETED:
            result = await client.jobs.get_result(job.job_id)
            print(f"Found {len(result.result['nodes'])} nodes")
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def create(
        self, job_type: JobType, parameters: Dict[str, Any], priority: str = "normal"
    ) -> JobCreateResponse:
        """
        Create a new async job.

        Args:
            job_type: Type of job to create
            parameters: Job-specific parameters
            priority: Job priority (low/normal/high)

        Returns:
            JobCreateResponse with job ID and initial status
        """
        request = JobCreateRequest(
            job_type=job_type, parameters=parameters, priority=priority
        )

        result = await self._transport.request(
            "POST", "/v1/jobs", json=request.model_dump()
        )

        assert result is not None, "Expected non-None result from create job"
        return JobCreateResponse(**result)

    async def get_status(self, job_id: str) -> JobInfo:
        """
        Get current status of a job.

        Args:
            job_id: Job identifier

        Returns:
            JobInfo with current status and progress
        """
        result = await self._transport.request("GET", f"/v1/jobs/{job_id}/status")

        assert result is not None, "Expected non-None result from get status"
        return JobInfo(**result)

    async def get_result(self, job_id: str) -> JobResult[Any]:
        """
        Get results from a completed job.

        Args:
            job_id: Job identifier

        Returns:
            JobResult with the job output

        Raises:
            CIRISAPIError: If job is not complete or has failed
        """
        result = await self._transport.request("GET", f"/v1/jobs/{job_id}/result")

        assert result is not None, "Expected non-None result from get result"
        return JobResult(**result)

    async def cancel(self, job_id: str) -> JobInfo:
        """
        Cancel a running job.

        Args:
            job_id: Job identifier

        Returns:
            Updated JobInfo
        """
        result = await self._transport.request("POST", f"/v1/jobs/{job_id}/cancel")

        assert result is not None, "Expected non-None result from cancel job"
        return JobInfo(**result)

    async def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        job_type: Optional[JobType] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        List jobs with optional filters.

        Args:
            status: Filter by job status
            job_type: Filter by job type
            cursor: Pagination cursor
            limit: Maximum results

        Returns:
            Dict with jobs list and pagination info
        """
        params: Dict[str, Any] = {"limit": limit}

        if status:
            params["status"] = status.value
        if job_type:
            params["job_type"] = job_type.value
        if cursor:
            params["cursor"] = cursor

        result = await self._transport.request("GET", "/v1/jobs", params=params)

        assert result is not None, "Expected non-None result from list jobs"
        return result

    # Convenience methods for specific job types

    async def create_memory_query(self, **query_params: Any) -> JobCreateResponse:
        """
        Create an async memory query job.

        Use this for queries that may return large result sets or
        require complex graph traversals.

        Args:
            **query_params: Same parameters as memory.query()

        Returns:
            JobCreateResponse with job ID
        """
        return await self.create(JobType.MEMORY_QUERY, query_params)

    async def create_memory_bulk_import(
        self, nodes: List[Dict[str, Any]], batch_size: int = 100
    ) -> JobCreateResponse:
        """
        Create a bulk memory import job.

        Args:
            nodes: List of nodes to import
            batch_size: Number of nodes to process per batch

        Returns:
            JobCreateResponse with job ID
        """
        return await self.create(
            JobType.MEMORY_BULK_IMPORT, {"nodes": nodes, "batch_size": batch_size}
        )

    async def create_audit_export(
        self,
        start_date: datetime,
        end_date: datetime,
        format: str = "jsonl",
        **filters: Any,
    ) -> JobCreateResponse:
        """
        Create an audit export job.

        Args:
            start_date: Export start date
            end_date: Export end date
            format: Export format (jsonl/csv)
            **filters: Additional audit filters

        Returns:
            JobCreateResponse with job ID
        """
        params = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "format": format,
            **filters,
        }

        return await self.create(JobType.AUDIT_EXPORT, params)

    async def create_telemetry_aggregation(
        self,
        metrics: List[str],
        start_time: datetime,
        end_time: datetime,
        aggregations: List[str],
        group_by: Optional[List[str]] = None,
    ) -> JobCreateResponse:
        """
        Create a telemetry aggregation job.

        Args:
            metrics: Metrics to aggregate
            start_time: Aggregation start time
            end_time: Aggregation end time
            aggregations: Aggregation functions (sum/avg/min/max/count)
            group_by: Optional grouping fields

        Returns:
            JobCreateResponse with job ID
        """
        params = {
            "metrics": metrics,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "aggregations": aggregations,
        }

        if group_by:
            params["group_by"] = group_by

        return await self.create(JobType.TELEMETRY_AGGREGATION, params)

    async def wait_for_completion(
        self, job_id: str, poll_interval: float = 2.0, timeout: Optional[float] = None
    ) -> JobInfo:
        """
        Wait for a job to complete.

        Args:
            job_id: Job identifier
            poll_interval: Seconds between status checks
            timeout: Maximum seconds to wait (None = infinite)

        Returns:
            Final JobInfo when job completes

        Raises:
            asyncio.TimeoutError: If timeout exceeded
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            status = await self.get_status(job_id)

            if status.status in [
                JobStatus.COMPLETED,
                JobStatus.FAILED,
                JobStatus.CANCELLED,
            ]:
                return status

            if timeout:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > timeout:
                    raise asyncio.TimeoutError(
                        f"Job {job_id} did not complete within {timeout}s"
                    )

            await asyncio.sleep(poll_interval)
