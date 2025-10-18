"""
Pytest configuration and fixtures for consent tests.

Imports fixtures from the shared fixtures directory.
"""

# Import all consent service fixtures
from tests.fixtures.consent_service import (
    # Basic mocks
    mock_time_service,
    mock_memory_bus,
    # Services
    consent_service_with_mocks,
    consent_service_without_memory_bus,
    dsar_automation_service,
    decay_protocol_manager,
    partnership_manager,
    air_service,
    metrics_collector,
    # Consent statuses
    sample_temporary_consent,
    sample_permanent_consent,
    sample_decaying_consent,
    expired_temporary_consent,
    mixed_consent_cache,
    populated_consent_service,
    # Graph nodes
    sample_consent_node_temporary,
    sample_consent_node_permanent,
    sample_consent_node_expired,
    mixed_consent_nodes,
    sample_user_interaction_nodes,
    sample_user_contribution_nodes,
    sample_audit_nodes,
    malformed_consent_nodes,
    # Decay fixtures
    sample_decay_status,
    sample_decay_identity_severed,
    sample_decay_completed,
    # Partnership fixtures
    sample_partnership_request,
    sample_partnership_outcome_approved,
    sample_partnership_outcome_rejected,
    sample_partnership_outcome_deferred,
    pending_partnership_data,
    # DSAR fixtures
    sample_conversation_summary_node,
    sample_conversation_summary_nodes_multiple,
    # AIR fixtures
    sample_air_interaction_session,
    sample_air_high_engagement,
    # Metrics fixtures
    sample_partnership_counters,
    sample_decay_counters,
    sample_operational_counters,
    comprehensive_counters,
)

__all__ = [
    "mock_time_service",
    "mock_memory_bus",
    "consent_service_with_mocks",
    "consent_service_without_memory_bus",
    "dsar_automation_service",
    "decay_protocol_manager",
    "partnership_manager",
    "air_service",
    "metrics_collector",
    "sample_temporary_consent",
    "sample_permanent_consent",
    "sample_decaying_consent",
    "expired_temporary_consent",
    "mixed_consent_cache",
    "populated_consent_service",
    "sample_consent_node_temporary",
    "sample_consent_node_permanent",
    "sample_consent_node_expired",
    "mixed_consent_nodes",
    "sample_user_interaction_nodes",
    "sample_user_contribution_nodes",
    "sample_audit_nodes",
    "malformed_consent_nodes",
    "sample_decay_status",
    "sample_decay_identity_severed",
    "sample_decay_completed",
    "sample_partnership_request",
    "sample_partnership_outcome_approved",
    "sample_partnership_outcome_rejected",
    "sample_partnership_outcome_deferred",
    "pending_partnership_data",
    "sample_conversation_summary_node",
    "sample_conversation_summary_nodes_multiple",
    "sample_air_interaction_session",
    "sample_air_high_engagement",
    "sample_partnership_counters",
    "sample_decay_counters",
    "sample_operational_counters",
    "comprehensive_counters",
]
