"""
GraphQL Schemas v1 - GraphQL operation schemas for type safety

Provides schemas for GraphQL queries, responses, and user data operations.
"""

from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict


class GraphQLVariable(BaseModel):
    """Base model for GraphQL variables"""

    model_config = ConfigDict(extra="allow")  # Allow additional fields for flexibility


class GraphQLQuery(BaseModel):
    """GraphQL query request"""

    query: str = Field(description="GraphQL query string")
    variables: GraphQLVariable = Field(default_factory=GraphQLVariable, description="Query variables")
    operation_name: Optional[str] = Field(default=None, description="Operation name for multi-operation documents")

    model_config = ConfigDict(extra="forbid")


class GraphQLUser(BaseModel):
    """User data from GraphQL response"""

    name: str = Field(description="User name")
    nick: Optional[str] = Field(default=None, description="User nickname")
    channel: Optional[str] = Field(default=None, description="User's primary channel")

    model_config = ConfigDict(extra="forbid")


class UserQueryVariables(GraphQLVariable):
    """Variables for user query"""

    names: List[str] = Field(description="List of user names to query")

    model_config = ConfigDict(extra="forbid")


class UserQueryResponse(BaseModel):
    """Response from user query"""

    users: List[GraphQLUser] = Field(default_factory=list, description="List of user data")

    model_config = ConfigDict(extra="forbid")


class GraphQLError(BaseModel):
    """GraphQL error details"""

    message: str = Field(description="Error message")
    path: Optional[List[str]] = Field(default=None, description="Path to error in query")
    extensions: Optional[JSONDict] = Field(default=None, description="Additional error details")

    model_config = ConfigDict(extra="forbid")


class GraphQLResponse(BaseModel):
    """Generic GraphQL response wrapper"""

    data: Optional[JSONDict] = Field(default=None, description="Response data")
    errors: Optional[List[GraphQLError]] = Field(default=None, description="GraphQL errors")
    extensions: Optional[JSONDict] = Field(default=None, description="Response extensions")

    model_config = ConfigDict(extra="forbid")


class UserAttribute(BaseModel):
    """User attribute key-value pair"""

    key: str = Field(description="Attribute key")
    value: str = Field(description="Attribute value")
    source: Optional[str] = Field(default=None, description="Source of attribute")

    model_config = ConfigDict(extra="forbid")


class GraphQLUserProfile(BaseModel):
    """Enriched user profile data from GraphQL"""

    nick: Optional[str] = Field(default=None, description="User nickname")
    channel: Optional[str] = Field(default=None, description="User's primary channel")
    # Additional fields from memory service
    attributes: List[UserAttribute] = Field(default_factory=list, description="Additional user attributes")
    trust_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="User trust score")
    last_seen: Optional[str] = Field(default=None, description="ISO timestamp of last activity")

    model_config = ConfigDict(extra="forbid")


class EnrichedContext(BaseModel):
    """Enriched context data"""

    user_profiles: List[Tuple[str, GraphQLUserProfile]] = Field(
        default_factory=list, description="User profiles by name"
    )
    identity_context: Optional[str] = Field(default=None, description="Identity context block")
    community_context: Optional[str] = Field(default=None, description="Community context information")

    model_config = ConfigDict(extra="forbid")


class GraphQLMutation(BaseModel):
    """GraphQL mutation request"""

    mutation: str = Field(description="GraphQL mutation string")
    variables: GraphQLVariable = Field(default_factory=GraphQLVariable, description="Mutation variables")
    operation_name: Optional[str] = Field(default=None, description="Operation name")

    model_config = ConfigDict(extra="forbid")


class GraphQLSubscription(BaseModel):
    """GraphQL subscription request"""

    subscription: str = Field(description="GraphQL subscription string")
    variables: GraphQLVariable = Field(default_factory=GraphQLVariable, description="Subscription variables")
    operation_name: Optional[str] = Field(default=None, description="Operation name")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "GraphQLVariable",
    "GraphQLQuery",
    "GraphQLUser",
    "UserQueryVariables",
    "UserQueryResponse",
    "GraphQLError",
    "GraphQLResponse",
    "UserAttribute",
    "GraphQLUserProfile",
    "EnrichedContext",
    "GraphQLMutation",
    "GraphQLSubscription",
]
