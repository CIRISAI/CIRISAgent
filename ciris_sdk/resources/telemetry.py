"""
Telemetry resource for CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field

from ..transport import Transport
from ..telemetry_models import (
    ResourceUsage, ResourceLimits, ResourceHealth, ResourceHistoryPoint,
    MetricData, MetricAggregate, MetricTrend,
    QueryFilter, QueryFilters,
    ThoughtData, LineageInfo, ProcessorStateData, ConfigurationData,
    ServiceMetadata, InteractionContext, AuditContext, DeferralContext,
    VerificationResult
)
from ..telemetry_responses import (
    TelemetryOverviewResponse, TelemetryMetricsResponse, TelemetryTracesResponse,
    TelemetryLogsResponse, MetricsQueryResult, TracesQueryResult, LogsQueryResult,
    IncidentsQueryResult, InsightsQueryResult
)


class TelemetryOverview(BaseModel):
    """System telemetry overview."""
    uptime_seconds: float = Field(..., description="System uptime")
    cognitive_state: str = Field(..., description="Current cognitive state")
    messages_processed_24h: int = Field(default=0, description="Messages in last 24h")
    healthy_services: int = Field(default=0, description="Number of healthy services")
    
    class Config:
        extra = "allow"  # Allow additional fields


class TelemetryMetrics(BaseModel):
    """Telemetry metrics response."""
    metrics: List[MetricData] = Field(..., description="List of metrics")
    
    class Config:
        extra = "allow"


class TelemetryMetricDetail(BaseModel):
    """Detailed metric information."""
    metric_name: str = Field(..., description="Metric name")  
    current: float = Field(..., description="Current value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    
    class Config:
        extra = "allow"


class TelemetryResources(BaseModel):
    """Resource telemetry."""
    current: ResourceUsage = Field(..., description="Current usage")
    limits: ResourceLimits = Field(..., description="Resource limits")
    health: Union[str, ResourceHealth] = Field(..., description="Health status")
    
    class Config:
        extra = "allow"


class TelemetryResourcesHistory(BaseModel):
    """Historical resource data."""
    period: Optional[str] = Field(None, description="Time period")
    cpu: List[ResourceHistoryPoint] = Field(..., description="CPU history")
    memory: List[ResourceHistoryPoint] = Field(..., description="Memory history")
    
    class Config:
        extra = "allow"
        
    @classmethod
    def from_api_response(cls, data: dict) -> "TelemetryResourcesHistory":
        """Convert API response to model."""
        # Handle SuccessResponse wrapper
        if "data" in data and isinstance(data["data"], dict):
            data = data["data"]
            
        # Extract period from nested data if needed
        period = data.get("period")
        if isinstance(period, dict):
            # Period is a dict with start, end, hours
            if "start" in period and "end" in period:
                period = f"{period['start']} to {period['end']}"
            elif "hours" in period:
                period = f"Last {period['hours']} hours"
            else:
                period = "Recent"
        elif not period:
            # Create a period string from available data
            if "start" in data and "end" in data:
                period = f"{data['start']} to {data['end']}"
            elif "hours" in data:
                period = f"Last {data['hours']} hours"
            else:
                period = "Recent"
            
        # Extract CPU and memory data
        cpu = data.get("cpu", [])
        if isinstance(cpu, dict):
            if "data" in cpu:
                cpu = cpu["data"]
            else:
                # Keep the whole dict if no data field
                cpu = cpu
            
        memory = data.get("memory", [])
        if isinstance(memory, dict):
            if "data" in memory:
                memory = memory["data"]
            else:
                # Keep the whole dict if no data field
                memory = memory
            
        # If cpu/memory are not present, try history field
        if not cpu and not memory and "history" in data:
            history = data["history"]
            cpu = []
            memory = []
            for entry in history:
                timestamp = entry.get("timestamp")
                if "cpu_percent" in entry:
                    cpu.append(ResourceHistoryPoint(
                    timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp,
                    value=entry["cpu_percent"],
                    unit="percent"
                ))
                if "memory_mb" in entry:
                    memory.append(ResourceHistoryPoint(
                        timestamp=datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp,
                        value=entry["memory_mb"],
                        unit="MB"
                    ))
            
        return cls(period=period, cpu=cpu, memory=memory)


class TelemetryResource:
    def __init__(self, transport: Transport):
        self._transport = transport

    async def get_overview(self) -> TelemetryOverviewResponse:
        """
        Get system metrics summary.

        Returns comprehensive overview combining telemetry, visibility, incidents, and resource usage.
        """
        data = await self._transport.request("GET", "/v1/telemetry/overview")
        return TelemetryOverviewResponse(**data)

    async def get_metrics(self) -> TelemetryMetricsResponse:
        """
        Get detailed metrics.

        Returns detailed metrics with trends and breakdowns by service.
        """
        data = await self._transport.request("GET", "/v1/telemetry/metrics")
        return TelemetryMetricsResponse(**data)

    async def get_traces(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> TelemetryTracesResponse:
        """
        Get reasoning traces.

        Returns reasoning traces showing agent thought processes and decision-making.
        """
        params = {"limit": str(limit)}
        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()

        data = await self._transport.request("GET", "/v1/telemetry/traces", params=params)
        return TelemetryTracesResponse(**data)

    async def get_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: Optional[str] = None,
        service: Optional[str] = None,
        limit: int = 100
    ) -> TelemetryLogsResponse:
        """
        Get system logs.

        Returns system logs from all services with filtering capabilities.
        """
        params = {"limit": str(limit)}
        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()
        if level:
            params["level"] = level
        if service:
            params["service"] = service

        data = await self._transport.request("GET", "/v1/telemetry/logs", params=params)
        return TelemetryLogsResponse(**data)

    async def query(
        self,
        query_type: str,
        filters: Optional[QueryFilters] = None,
        aggregations: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> Union[MetricsQueryResult, TracesQueryResult, LogsQueryResult, IncidentsQueryResult, InsightsQueryResult]:
        """
        Execute custom telemetry queries.

        Query types: metrics, traces, logs, incidents, insights
        Requires ADMIN role.
        """
        # Convert filters to dict format for API
        filters_dict = {}
        if filters:
            filters_dict = {
                "filters": [{
                    "field": f.field,
                    "operator": f.operator,
                    "value": f.value
                } for f in filters.filters],
                "logic": filters.logic
            }
        
        payload = {
            "query_type": query_type,
            "filters": filters_dict,
            "limit": limit
        }

        if aggregations:
            payload["aggregations"] = aggregations
        if start_time:
            payload["start_time"] = start_time.isoformat()
        if end_time:
            payload["end_time"] = end_time.isoformat()

        data = await self._transport.request("POST", "/v1/telemetry/query", json=payload)
        
        # Return appropriate response type based on query_type
        if query_type == "metrics":
            return MetricsQueryResult(**data)
        elif query_type == "traces":
            return TracesQueryResult(**data)
        elif query_type == "logs":
            return LogsQueryResult(**data)
        elif query_type == "incidents":
            return IncidentsQueryResult(**data)
        elif query_type == "insights":
            return InsightsQueryResult(**data)
        else:
            # For unknown query types, return the most generic result
            return MetricsQueryResult(**data)

    # Legacy compatibility methods (will be deprecated)
    async def get_observability_overview(self) -> TelemetryOverviewResponse:
        """
        DEPRECATED: Use get_overview() instead.
        Get unified observability overview.
        """
        return await self.get_overview()

    async def get_observability_metrics(self) -> TelemetryMetricsResponse:
        """
        DEPRECATED: Use get_metrics() instead.
        Get detailed system metrics.
        """
        return await self.get_metrics()

    async def get_observability_traces(
        self,
        limit: int = 10,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> TelemetryTracesResponse:
        """
        DEPRECATED: Use get_traces() instead.
        Get reasoning traces.
        """
        return await self.get_traces(limit=limit, start_time=start_time, end_time=end_time)

    async def get_observability_logs(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: Optional[str] = None,
        service: Optional[str] = None,
        limit: int = 100
    ) -> TelemetryLogsResponse:
        """
        DEPRECATED: Use get_logs() instead.
        Get system logs.
        """
        return await self.get_logs(
            start_time=start_time,
            end_time=end_time,
            level=level,
            service=service,
            limit=limit
        )

    async def query_observability(
        self,
        query_type: str,
        filters: Optional[Dict[str, Any]] = None,
        aggregations: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> Union[MetricsQueryResult, TracesQueryResult, LogsQueryResult, IncidentsQueryResult, InsightsQueryResult]:
        """
        DEPRECATED: Use query() instead.
        Execute custom observability queries.
        """
        # Convert dict filters to QueryFilters if provided
        query_filters = None
        if filters:
            filter_list = []
            for field, value in filters.items():
                # Simple conversion - assumes equality operator
                filter_list.append(QueryFilter(field=field, operator="eq", value=value))
            query_filters = QueryFilters(filters=filter_list)
        
        return await self.query(
            query_type=query_type,
            filters=query_filters,
            aggregations=aggregations,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
    
    # Aliases for backward compatibility with tests
    async def overview(self) -> TelemetryOverview:
        """Alias for get_overview()."""
        data = await self.get_overview()
        # Convert response model to simpler model
        return TelemetryOverview(
            uptime_seconds=data.uptime_seconds,
            cognitive_state=data.cognitive_state,
            messages_processed_24h=data.messages_processed_24h,
            healthy_services=data.healthy_services
        )
    
    async def metrics(self) -> TelemetryMetrics:
        """Alias for get_metrics()."""
        data = await self.get_metrics()
        # Convert detailed metrics to simple metric data list
        metric_list = []
        for metric in data.metrics:
            for point in metric.recent_data:
                metric_list.append(point)
        return TelemetryMetrics(metrics=metric_list)
    
    async def metric_detail(self, metric_name: str) -> TelemetryMetricDetail:
        """Get detailed information about a specific metric."""
        data = await self._transport.request("GET", f"/v1/telemetry/metrics/{metric_name}")
        # Handle both direct response and data wrapped response
        if "metric_name" not in data and "name" in data:
            data["metric_name"] = data["name"]
        if "current" not in data and "current_value" in data:
            data["current"] = data["current_value"]
        return TelemetryMetricDetail(**data)
    
    async def resources(self) -> TelemetryResources:
        """Get resource usage telemetry."""
        data = await self._transport.request("GET", "/v1/telemetry/resources")
        # Parse the response data into proper models
        current = ResourceUsage(**data.get("current", {}))
        limits = ResourceLimits(**data.get("limits", {}))
        health_data = data.get("health", "unknown")
        if isinstance(health_data, dict):
            health = ResourceHealth(**health_data)
        else:
            health = health_data
        return TelemetryResources(current=current, limits=limits, health=health)
    
    async def resources_history(self, hours: int = 24) -> TelemetryResourcesHistory:
        """Get historical resource usage."""
        params = {"hours": str(hours)}
        data = await self._transport.request("GET", "/v1/telemetry/resources/history", params=params)
        return TelemetryResourcesHistory.from_api_response(data)
