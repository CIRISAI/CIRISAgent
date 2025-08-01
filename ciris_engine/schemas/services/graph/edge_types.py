"""
Type definitions for graph edges.

Provides typed models for edge creation and management.
"""
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


class EdgeAttributes(BaseModel):
    """Attributes for a graph edge."""
    weight: float = Field(1.0, description="Edge weight")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        extra = "allow"  # Allow additional fields for flexibility


class ParticipantData(BaseModel):
    """Data about a participant in an interaction."""
    user_id: str = Field(..., description="User identifier")
    display_name: str = Field(..., description="User display name")
    message_count: int = Field(0, description="Number of messages from this participant")
    first_seen: Optional[str] = Field(None, description="First interaction timestamp")
    last_seen: Optional[str] = Field(None, description="Last interaction timestamp")
    role: Optional[str] = Field(None, description="User role if known")
    
    class Config:
        extra = "allow"  # Allow additional fields for different platforms


class EdgeSpecification(BaseModel):
    """Specification for creating an edge."""
    source_node_id: str = Field(..., description="Source node ID")
    target_node_id: str = Field(..., description="Target node ID") 
    edge_type: str = Field(..., description="Type of relationship")
    attributes: EdgeAttributes = Field(default_factory=EdgeAttributes, description="Edge attributes")