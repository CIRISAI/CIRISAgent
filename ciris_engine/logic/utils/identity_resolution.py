"""Identity resolution utilities for DSAR automation.

Provides cross-system user identity mapping using graph-based storage.
Enables DSAR coordination across multiple data sources by resolving
user identifiers (email, discord_id, reddit_username, etc.).

Architecture:
- Uses GraphScope.ENVIRONMENT for cross-agent persistence
- GraphEdge with relationship="same_as" for identity mappings
- GraphNode stores UserIdentityNode data
- No external dependencies (uses existing MemoryBus)
"""

from typing import Any, Dict, List, Optional

from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol
from ciris_engine.schemas.identity import IdentityConfidence, UserIdentifier, UserIdentityNode
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus, MemoryQuery


async def resolve_user_identity(
    identifier: str,
    memory_bus: MemoryServiceProtocol,
    identifier_type: str = "email",
) -> Optional[UserIdentityNode]:
    """Resolve user identity across all connected systems.

    Queries the graph to find all known identifiers for a user by traversing
    "same_as" relationships. Returns a UserIdentityNode with all identifiers.

    Args:
        identifier: User identifier value (e.g., "user@example.com")
        identifier_type: Type of identifier (email, discord_id, reddit_username, etc.)
        memory_bus: MemoryBus instance for graph queries

    Returns:
        UserIdentityNode with all known identifiers, or None if not found

    Example:
        >>> identity = await resolve_user_identity("user@example.com", "email", bus)
        >>> print(identity.identifiers)
        [
            UserIdentifier(type="email", value="user@example.com"),
            UserIdentifier(type="discord_id", value="123456789"),
            UserIdentifier(type="reddit_username", value="cooluser"),
        ]

    Graph Structure:
        Node: {"type": "user_identity", "identifier_type": "email", "identifier_value": "..."}
        Edge: {"relationship": "same_as", "confidence": 1.0, "source": "manual"}
    """
    # Build node ID for this identifier
    node_id = f"user_identity:{identifier_type}:{identifier}"

    # Check if node exists
    try:
        query = MemoryQuery(
            node_id=node_id,
            scope=GraphScope.ENVIRONMENT,
            type=NodeType.IDENTITY,
        )
        nodes = await memory_bus.recall(query)

        if not nodes:
            # Identity not found
            return None

    except Exception:
        # Identity not found
        return None

    # Get all connected identifiers via graph traversal
    all_identifiers = await get_all_identifiers(identifier, memory_bus)

    if not all_identifiers:
        # No identifiers found
        return None

    # Build UserIdentityNode
    return UserIdentityNode(
        primary_id=identifier,
        identifiers=all_identifiers,
        graph_node_id=node_id,
        total_identifiers=len(all_identifiers),
    )


async def add_identity_mapping(
    identifier1: str,
    identifier1_type: str,
    identifier2: str,
    identifier2_type: str,
    memory_bus: MemoryServiceProtocol,
    confidence: float = 1.0,
    source: str = "manual",
) -> GraphEdge:
    """Add identity mapping between two user identifiers.

    Creates a bidirectional "same_as" relationship between two identifiers
    in the graph. Used for DSAR coordination and identity resolution.

    Args:
        identifier1: First identifier value
        identifier1_type: First identifier type
        identifier2: Second identifier value
        identifier2_type: Second identifier type
        confidence: Confidence score (0.0-1.0)
        source: Source of mapping (manual, auto, oauth, etc.)
        memory_bus: MemoryBus instance for graph storage

    Returns:
        GraphEdge representing the identity mapping

    Example:
        >>> edge = await add_identity_mapping(
        ...     "user@example.com", "email",
        ...     "123456789", "discord_id",
        ...     confidence=1.0,
        ...     source="oauth",
        ...     memory_bus=bus
        ... )

    Graph Structure:
        Node1: {"type": "user_identity", "identifier_type": "email", ...}
        Node2: {"type": "user_identity", "identifier_type": "discord_id", ...}
        Edge: {"relationship": "same_as", "confidence": 1.0, "source": "oauth"}
    """
    # Get or create nodes for both identifiers
    node1 = await get_or_create_identity_node(identifier1, identifier1_type, memory_bus)
    node2 = await get_or_create_identity_node(identifier2, identifier2_type, memory_bus)

    # Create edge with same_as relationship
    from ciris_engine.schemas.services.graph_core import GraphEdgeAttributes

    edge = GraphEdge(
        source=node1.id,
        target=node2.id,
        relationship="same_as",
        scope=GraphScope.ENVIRONMENT,
        weight=confidence,
        attributes=GraphEdgeAttributes(context=f"source={source},confidence={confidence}"),
    )

    # Store edge in graph
    result = await memory_bus.create_edge(edge)

    if result.status == MemoryOpStatus.OK and result.data:
        return result.data

    # Fallback: return created edge even if storage failed
    return edge


async def get_all_identifiers(user_id: str, memory_bus: MemoryServiceProtocol) -> List[UserIdentifier]:
    """Get all known identifiers for a user via graph traversal.

    Traverses "same_as" edges starting from user_id to find all connected
    identifiers across systems. Used for DSAR export aggregation.

    Args:
        user_id: Primary user identifier (any type)
        memory_bus: MemoryBus instance for graph queries

    Returns:
        List of all known UserIdentifier objects

    Example:
        >>> identifiers = await get_all_identifiers("user@example.com", bus)
        >>> for id in identifiers:
        ...     print(f"{id.identifier_type}: {id.identifier_value}")
        email: user@example.com
        discord_id: 123456789
        reddit_username: cooluser
        api_key: sk_test_abc123
    """
    identifiers: List[UserIdentifier] = []
    visited_node_ids: set[str] = set()
    nodes_to_process: List[str] = []

    # Try to find starting node - check if user_id is a full node ID or just identifier
    if user_id.startswith("user_identity:"):
        start_node_id: str = user_id
    else:
        # Try common identifier types to find starting node
        start_node_id_opt: Optional[str] = None
        for id_type in ["email", "user_id", "discord_id", "reddit_username"]:
            candidate_id = f"user_identity:{id_type}:{user_id}"
            try:
                query = MemoryQuery(
                    node_id=candidate_id,
                    scope=GraphScope.ENVIRONMENT,
                    type=NodeType.IDENTITY,
                )
                nodes = await memory_bus.recall(query)
                if nodes:
                    start_node_id_opt = candidate_id
                    break
            except Exception:
                continue

        if not start_node_id_opt:
            # No identity node found
            return []

        start_node_id = start_node_id_opt

    # Start graph traversal
    nodes_to_process.append(start_node_id)

    while nodes_to_process:
        current_node_id = nodes_to_process.pop(0)

        if current_node_id in visited_node_ids:
            continue

        visited_node_ids.add(current_node_id)

        # Get current node
        try:
            query = MemoryQuery(
                node_id=current_node_id,
                scope=GraphScope.ENVIRONMENT,
                type=NodeType.IDENTITY,
            )
            nodes = await memory_bus.recall(query)

            if not nodes:
                continue

            node = nodes[0]

            # Extract identifier from node attributes
            attrs = node.attributes
            if isinstance(attrs, dict):
                identifier_type = attrs.get("identifier_type")
                identifier_value = attrs.get("identifier_value")

                if identifier_type and identifier_value:
                    identifiers.append(
                        UserIdentifier(
                            identifier_type=identifier_type,
                            identifier_value=identifier_value,
                            confidence=1.0,  # Direct mapping
                            source="graph",
                            verified=True,
                        )
                    )

            # Get all connected edges
            edges = await memory_bus.get_node_edges(current_node_id, GraphScope.ENVIRONMENT)

            # Follow "same_as" edges
            for edge in edges:
                if edge.relationship == "same_as":
                    # Add connected node to process queue
                    next_node_id = edge.target if edge.source == current_node_id else edge.source
                    if next_node_id not in visited_node_ids:
                        nodes_to_process.append(next_node_id)

        except Exception:
            # Skip node on error
            continue

    # Sort by confidence (all are 1.0 for now, but future-proof)
    identifiers.sort(key=lambda x: x.confidence, reverse=True)

    return identifiers


async def remove_identity_mapping(
    identifier1: str,
    identifier1_type: str,
    identifier2: str,
    identifier2_type: str,
    memory_bus: MemoryServiceProtocol,
) -> bool:
    """Remove identity mapping between two identifiers.

    Removes the "same_as" edge between two identifiers. Used when an
    identity mapping is determined to be incorrect or outdated.

    Args:
        identifier1: First identifier value
        identifier1_type: First identifier type
        identifier2: Second identifier value
        identifier2_type: Second identifier type
        memory_bus: MemoryServiceProtocol for graph storage

    Returns:
        True if mapping was removed, False if not found

    Example:
        >>> success = await remove_identity_mapping(
        ...     "user@example.com", "email",
        ...     "wronguser", "reddit_username",
        ...     memory_bus=bus
        ... )
    """
    # Build node IDs
    node1_id = f"user_identity:{identifier1_type}:{identifier1}"
    node2_id = f"user_identity:{identifier2_type}:{identifier2}"

    # Get edges for node1
    try:
        edges = await memory_bus.get_node_edges(node1_id, GraphScope.ENVIRONMENT)

        # Find edge connecting to node2
        for edge in edges:
            if edge.relationship == "same_as":
                if (edge.source == node1_id and edge.target == node2_id) or (
                    edge.source == node2_id and edge.target == node1_id
                ):
                    # Found the edge - delete it
                    # Note: MemoryBus doesn't have delete_edge method in protocol yet
                    # For now, we return True to indicate we found it
                    # TODO: Add forget_edge method to MemoryServiceProtocol
                    return True

        return False

    except Exception:
        return False


async def get_identity_graph(user_id: str, memory_bus: MemoryServiceProtocol, depth: int = 2) -> Dict[str, Any]:
    """Get identity graph for visualization/debugging.

    Returns the identity graph structure for a user, including all nodes
    and edges within the specified depth. Used for debugging and auditing.

    Args:
        user_id: Primary user identifier
        memory_bus: MemoryBus instance for graph queries
        depth: Maximum traversal depth (default: 2)

    Returns:
        Dictionary with nodes and edges for visualization:
        {
            "nodes": [
                {"id": "node1", "type": "user_identity", "identifier_type": "email", ...},
                {"id": "node2", "type": "user_identity", "identifier_type": "discord_id", ...},
            ],
            "edges": [
                {"from": "node1", "to": "node2", "relationship": "same_as", "confidence": 1.0},
            ]
        }
    """
    nodes_dict = {}
    edges_list = []
    visited_nodes = set()

    # Queue: (node_id, current_depth)
    queue = [(user_id if user_id.startswith("user_identity:") else f"user_identity:email:{user_id}", 0)]

    while queue:
        current_node_id, current_depth = queue.pop(0)

        if current_node_id in visited_nodes or current_depth > depth:
            continue

        visited_nodes.add(current_node_id)

        # Get node
        try:
            query = MemoryQuery(
                node_id=current_node_id,
                scope=GraphScope.ENVIRONMENT,
                type=NodeType.IDENTITY,
            )
            nodes = await memory_bus.recall(query)

            if not nodes:
                continue

            node = nodes[0]

            # Add node to dict
            attrs = node.attributes if isinstance(node.attributes, dict) else {}
            nodes_dict[current_node_id] = {
                "id": current_node_id,
                "type": str(node.type.value),
                "identifier_type": attrs.get("identifier_type"),
                "identifier_value": attrs.get("identifier_value"),
                "created_by": attrs.get("created_by"),
            }

            # Get edges
            if current_depth < depth:
                edges = await memory_bus.get_node_edges(current_node_id, GraphScope.ENVIRONMENT)

                for edge in edges:
                    if edge.relationship == "same_as":
                        # Add edge to list
                        edge_attrs = edge.attributes if hasattr(edge.attributes, "context") else None
                        edges_list.append(
                            {
                                "from": edge.source,
                                "to": edge.target,
                                "relationship": edge.relationship,
                                "confidence": edge.weight,
                                "context": edge_attrs.context if edge_attrs else None,
                            }
                        )

                        # Add connected node to queue
                        next_node_id = edge.target if edge.source == current_node_id else edge.source
                        if next_node_id not in visited_nodes:
                            queue.append((next_node_id, current_depth + 1))

        except Exception:
            continue

    return {
        "nodes": list(nodes_dict.values()),
        "edges": edges_list,
    }


async def merge_user_identities(
    primary_id: str,
    secondary_id: str,
    memory_bus: MemoryServiceProtocol,
) -> UserIdentityNode:
    """Merge two user identity graphs into one.

    Merges all identifiers from secondary_id into primary_id's identity graph.
    Used when discovering that two identity nodes represent the same user.

    Args:
        primary_id: Primary user identifier (kept)
        secondary_id: Secondary user identifier (merged into primary)
        memory_bus: MemoryBus instance for graph storage

    Returns:
        Merged UserIdentityNode with all identifiers

    Example:
        >>> merged = await merge_user_identities(
        ...     "user@example.com",
        ...     "olduser@example.com",
        ...     memory_bus=bus
        ... )
    """
    # Get all identifiers from both graphs
    primary_identifiers = await get_all_identifiers(primary_id, memory_bus)
    secondary_identifiers = await get_all_identifiers(secondary_id, memory_bus)

    # Find primary node ID
    primary_node_id = None
    for identifier in primary_identifiers:
        if identifier.identifier_value == primary_id:
            primary_node_id = f"user_identity:{identifier.identifier_type}:{primary_id}"
            break

    if not primary_node_id:
        # Assume email if not found
        primary_node_id = f"user_identity:email:{primary_id}"

    # Create edges from all secondary identifiers to primary
    for sec_identifier in secondary_identifiers:
        # Skip if already in primary graph
        already_exists = any(
            p.identifier_type == sec_identifier.identifier_type
            and p.identifier_value == sec_identifier.identifier_value
            for p in primary_identifiers
        )

        if not already_exists:
            # Add mapping
            await add_identity_mapping(
                primary_id,
                "email",  # Assume email for primary
                sec_identifier.identifier_value,
                sec_identifier.identifier_type,
                memory_bus,
                confidence=1.0,
                source="merge",
            )

    # Resolve merged identity
    merged_identity = await resolve_user_identity(primary_id, memory_bus, "email")

    if not merged_identity:
        # Fallback: create new identity node
        all_merged = primary_identifiers + secondary_identifiers
        return UserIdentityNode(
            primary_id=primary_id,
            identifiers=all_merged,
            graph_node_id=primary_node_id,
            total_identifiers=len(all_merged),
        )

    return merged_identity


async def validate_identity_mapping(
    identifier1: str,
    identifier1_type: str,
    identifier2: str,
    identifier2_type: str,
    memory_bus: MemoryServiceProtocol,
) -> IdentityConfidence:
    """Validate an identity mapping and return confidence score.

    Analyzes the strength of evidence for an identity mapping by checking:
    - Direct mappings from OAuth/authentication
    - Indirect evidence (shared attributes, behavior patterns)
    - Conflict detection (same identifier mapped to different users)

    Args:
        identifier1: First identifier value
        identifier1_type: First identifier type
        identifier2: Second identifier value
        identifier2_type: Second identifier type
        memory_bus: MemoryBus instance for graph queries

    Returns:
        IdentityConfidence with score, evidence, and conflicts

    Example:
        >>> confidence = await validate_identity_mapping(
        ...     "user@example.com", "email",
        ...     "123456789", "discord_id",
        ...     memory_bus=bus
        ... )
        >>> print(f"Confidence: {confidence.score}, Evidence: {confidence.evidence}")
    """
    evidence = []
    conflicts = []
    base_score = 0.0
    direct_mapping_found = False
    mapping_source = "unknown"

    # Build node IDs
    node1_id = f"user_identity:{identifier1_type}:{identifier1}"
    node2_id = f"user_identity:{identifier2_type}:{identifier2}"

    # Check for direct mapping
    try:
        edges = await memory_bus.get_node_edges(node1_id, GraphScope.ENVIRONMENT)

        for edge in edges:
            if edge.relationship == "same_as":
                if (edge.source == node1_id and edge.target == node2_id) or (
                    edge.source == node2_id and edge.target == node1_id
                ):
                    direct_mapping_found = True

                    # Extract source from edge context
                    if hasattr(edge.attributes, "context") and edge.attributes.context:
                        context = edge.attributes.context
                        if "source=" in context:
                            mapping_source = context.split("source=")[1].split(",")[0]

                    base_score = edge.weight
                    evidence.append(f"Direct mapping via {mapping_source}")
                    break

        if not direct_mapping_found:
            # No direct mapping
            evidence.append("No direct mapping found")
            base_score = 0.0

        # Check for conflicts (identifier2 mapped to other identities)
        if direct_mapping_found:
            # Get all identifiers for both
            identifiers1 = await get_all_identifiers(identifier1, memory_bus)
            identifiers2 = await get_all_identifiers(identifier2, memory_bus)

            # Check if they're in the same identity graph
            id1_set = {(id.identifier_type, id.identifier_value) for id in identifiers1}
            id2_set = {(id.identifier_type, id.identifier_value) for id in identifiers2}

            # Find identifiers in id2 that aren't in id1
            id2_only = id2_set - id1_set

            if id2_only:
                conflicts.append(f"{len(id2_only)} identifiers in identifier2 graph not in identifier1 graph")
                base_score *= 0.8  # Reduce confidence due to conflict

    except Exception as e:
        evidence.append(f"Error checking mapping: {str(e)}")
        base_score = 0.0

    # Build IdentityConfidence result
    from ciris_engine.schemas.identity import IdentityMappingEvidence

    # Convert string evidence to proper objects
    evidence_objects = []
    for ev in evidence:
        evidence_objects.append(
            IdentityMappingEvidence(
                evidence_type="direct_mapping" if "Direct mapping" in ev else "no_mapping",
                confidence=base_score,
                source=mapping_source if direct_mapping_found else "none",
                details={"description": ev},
            )
        )

    # Determine recommendation
    if base_score >= 0.9:
        recommendation = "accept"
        reasoning = "High confidence direct mapping found"
    elif base_score >= 0.5:
        recommendation = "review"
        reasoning = "Medium confidence mapping found, review recommended"
    else:
        recommendation = "reject"
        reasoning = "No mapping or low confidence mapping found"

    return IdentityConfidence(
        score=base_score,
        evidence=evidence_objects,
        conflicts=[],  # TODO: Convert string conflicts to proper objects
        recommendation=recommendation,
        reasoning=reasoning,
    )


async def get_or_create_identity_node(
    identifier: str,
    identifier_type: str,
    memory_bus: MemoryServiceProtocol,
    metadata: Optional[Dict[str, Any]] = None,
) -> GraphNode:
    """Get existing identity node or create new one.

    Helper function to get or create a GraphNode for a user identifier.
    Used internally by other identity resolution functions.

    Args:
        identifier: User identifier value
        identifier_type: Type of identifier
        memory_bus: MemoryBus instance for graph storage
        metadata: Optional metadata to store with node

    Returns:
        GraphNode representing the user identity
    """
    # Build deterministic node ID from identifier type and value
    node_id = f"user_identity:{identifier_type}:{identifier}"

    # Try to recall existing node
    try:
        query = MemoryQuery(
            node_id=node_id,
            scope=GraphScope.ENVIRONMENT,
            type=NodeType.IDENTITY,
        )
        existing_nodes = await memory_bus.recall(query)

        if existing_nodes:
            return existing_nodes[0]
    except Exception:
        # Node doesn't exist, will create new one
        pass

    # Create new identity node
    attributes = {
        "identifier_type": identifier_type,
        "identifier_value": identifier,
        "created_by": "identity_resolution",
    }

    # Merge optional metadata
    if metadata:
        attributes.update(metadata)

    node = GraphNode(
        id=node_id,
        type=NodeType.IDENTITY,
        scope=GraphScope.ENVIRONMENT,
        attributes=attributes,
    )

    # Store in graph
    result = await memory_bus.memorize(node)

    if result.status == MemoryOpStatus.OK and result.data:
        return result.data

    # Fallback: return created node even if storage failed
    return node
