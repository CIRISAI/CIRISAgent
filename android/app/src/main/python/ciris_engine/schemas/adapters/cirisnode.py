"""
Schemas for CIRISNode client operations.

These replace all Dict[str, Any] usage in cirisnode_client.py.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict


# Request/Response schemas for benchmarks
class SimpleBenchRequest(BaseModel):
    """Request to run SimpleBench."""

    model_id: str = Field(..., description="Model identifier")
    agent_id: str = Field(..., description="Agent identifier")

    model_config = ConfigDict(protected_namespaces=())


class SimpleBenchResult(BaseModel):
    """Result from SimpleBench run."""

    benchmark_id: str = Field(..., description="Unique benchmark run ID")
    agent_id: str = Field(..., description="Agent that was tested")
    model_id: str = Field(..., description="Model that was used")
    score: float = Field(..., description="Benchmark score")
    duration_seconds: float = Field(..., description="Time taken to complete")
    completed_at: datetime = Field(..., description="Completion timestamp")
    details: Optional[Dict[str, Union[str, int, float, bool]]] = Field(None, description="Additional benchmark details")

    model_config = ConfigDict(protected_namespaces=())


class HE300Request(BaseModel):
    """Request to run HE300 benchmark."""

    model_id: str = Field(..., description="Model identifier")
    agent_id: str = Field(..., description="Agent identifier")

    model_config = ConfigDict(protected_namespaces=())


class HE300Result(BaseModel):
    """Result from HE300 run."""

    benchmark_id: str = Field(..., description="Unique benchmark run ID")
    agent_id: str = Field(..., description="Agent that was tested")
    model_id: str = Field(..., description="Model that was used")
    ethics_score: float = Field(..., description="Ethics alignment score")
    coherence_score: float = Field(..., description="Response coherence score")
    duration_seconds: float = Field(..., description="Time taken to complete")
    completed_at: datetime = Field(..., description="Completion timestamp")
    details: Optional[Dict[str, Union[str, int, float, bool]]] = Field(None, description="Additional benchmark details")

    model_config = ConfigDict(protected_namespaces=())


# Chaos testing schemas
class ChaosTestRequest(BaseModel):
    """Request to run chaos tests."""

    agent_id: str = Field(..., description="Agent to test")
    scenarios: List[str] = Field(..., description="Chaos scenarios to run")


class ChaosTestResult(BaseModel):
    """Result from a single chaos test."""

    scenario: str = Field(..., description="Scenario that was tested")
    passed: bool = Field(..., description="Whether the test passed")
    recovery_time: Optional[float] = Field(None, description="Time to recover in seconds")
    error_message: Optional[str] = Field(None, description="Error if test failed")
    metrics: Optional[Dict[str, Union[str, int, float, bool]]] = Field(None, description="Test metrics")


# WA service schemas
class WAServiceRequest(BaseModel):
    """Generic request to WA service."""

    service: str = Field(..., description="WA service name")
    action: str = Field(..., description="Action to perform")
    params: JSONDict = Field(default_factory=dict, description="Service parameters")


class WAServiceResponse(BaseModel):
    """Generic response from WA service."""

    service: str = Field(..., description="WA service name")
    action: str = Field(..., description="Action performed")
    success: bool = Field(..., description="Whether action succeeded")
    result: Optional[JSONDict] = Field(None, description="Action result")
    error: Optional[str] = Field(None, description="Error message if failed")


# Event logging schemas
class EventLogRequest(BaseModel):
    """Request to log an event."""

    event_type: str = Field(..., description="Type of event")
    event_data: JSONDict = Field(..., description="Event data")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    agent_id: Optional[str] = Field(None, description="Agent that generated event")


class EventLogResponse(BaseModel):
    """Response from event logging."""

    event_id: str = Field(..., description="Unique event ID")
    accepted: bool = Field(..., description="Whether event was accepted")
    timestamp: datetime = Field(..., description="Server timestamp")


# Assessment schemas
class AssessmentSubmission(BaseModel):
    """Submit assessment answers."""

    assessment_id: str = Field(..., description="Assessment ID")
    agent_id: str = Field(..., description="Agent taking assessment")
    answers: List[JSONDict] = Field(..., description="Assessment answers as attribute dictionaries")


class AssessmentResult(BaseModel):
    """Assessment completion result."""

    assessment_id: str = Field(..., description="Assessment ID")
    agent_id: str = Field(..., description="Agent ID")
    score: float = Field(..., description="Overall score")
    passed: bool = Field(..., description="Whether passed")
    feedback: Optional[str] = Field(None, description="Assessment feedback")
    certificate_id: Optional[str] = Field(None, description="Certificate if passed")
