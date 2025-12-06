"""
Schemas for registry operations.

These replace all Dict[str, Any] usage in logic/registries/base.py.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class ServiceMetadata(BaseModel):
    """Metadata for a registered service."""

    version: Optional[str] = Field(None, description="Service version")
    description: Optional[str] = Field(None, description="Service description")
    author: Optional[str] = Field(None, description="Service author")
    additional_info: JSONDict = Field(default_factory=dict, description="Additional metadata")


class ProviderInfo(BaseModel):
    """Information about a registered provider."""

    name: str = Field(..., description="Provider name")
    priority: str = Field(..., description="Priority level")
    priority_group: int = Field(0, description="Priority group")
    strategy: str = Field(..., description="Selection strategy")
    capabilities: List[str] = Field(default_factory=list, description="Provider capabilities")
    metadata: JSONDict = Field(default_factory=dict, description="Provider metadata")
    circuit_breaker_state: Optional[str] = Field(None, description="Circuit breaker state")


class ServiceTypeInfo(BaseModel):
    """Information about services of a specific type."""

    providers: List[ProviderInfo] = Field(default_factory=list, description="List of providers")


class HandlerInfo(BaseModel):
    """Information about services for a specific handler."""

    services: Dict[str, ServiceTypeInfo] = Field(default_factory=dict, description="Services by type")


class CircuitBreakerStats(BaseModel):
    """Circuit breaker statistics."""

    state: str = Field(..., description="Current state")
    failure_count: int = Field(0, description="Failure count")
    success_count: int = Field(0, description="Success count")
    last_failure_time: Optional[str] = Field(None, description="Last failure timestamp")
    last_success_time: Optional[str] = Field(None, description="Last success timestamp")


class RegistryInfo(BaseModel):
    """Complete registry information."""

    handlers: Dict[str, Dict[str, List[ProviderInfo]]] = Field(
        default_factory=dict, description="Handler-specific services"
    )
    global_services: Dict[str, List[ProviderInfo]] = Field(default_factory=dict, description="Global services")
    circuit_breaker_stats: Dict[str, CircuitBreakerStats] = Field(
        default_factory=dict, description="Circuit breaker statistics"
    )
