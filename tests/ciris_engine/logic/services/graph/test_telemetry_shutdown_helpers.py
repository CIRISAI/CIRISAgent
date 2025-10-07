"""Test shutdown consent and reason extraction helpers."""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock

def test_extract_shutdown_reason_from_dict():
    """Test extracting shutdown reason from dict attributes."""
    from ciris_engine.logic.services.graph.telemetry_service.helpers import _extract_shutdown_reason_from_node
    
    # Create mock node with dict attributes
    node = Mock()
    node.attributes = {
        "reason": "Signal 15",
        "created_by": "runtime_shutdown",
        "tags": ["shutdown"]
    }
    
    reason = _extract_shutdown_reason_from_node(node)
    assert reason == "Signal 15"

def test_extract_shutdown_reason_from_object():
    """Test extracting shutdown reason from object attributes."""
    from ciris_engine.logic.services.graph.telemetry_service.helpers import _extract_shutdown_reason_from_node
    
    # Create mock node with object attributes
    node = Mock()
    attrs = Mock()
    attrs.reason = "Graceful shutdown"
    node.attributes = attrs
    
    reason = _extract_shutdown_reason_from_node(node)
    assert reason == "Graceful shutdown"

def test_extract_shutdown_reason_none():
    """Test extracting shutdown reason when not present."""
    from ciris_engine.logic.services.graph.telemetry_service.helpers import _extract_shutdown_reason_from_node
    
    # No attributes
    node_no_attrs = Mock(spec=[])
    assert _extract_shutdown_reason_from_node(node_no_attrs) is None
    
    # Dict without reason
    node_dict = Mock()
    node_dict.attributes = {"created_by": "runtime"}
    assert _extract_shutdown_reason_from_node(node_dict) is None

def test_extract_shutdown_consent_from_dict():
    """Test extracting consent status from dict attributes."""
    from ciris_engine.logic.services.graph.telemetry_service.helpers import _extract_shutdown_consent_from_node
    
    for status in ["accepted", "rejected", "manual"]:
        node = Mock()
        node.attributes = {"consent_status": status}
        
        consent = _extract_shutdown_consent_from_node(node)
        assert consent == status

def test_extract_shutdown_consent_from_object():
    """Test extracting consent status from object attributes."""
    from ciris_engine.logic.services.graph.telemetry_service.helpers import _extract_shutdown_consent_from_node
    
    node = Mock()
    attrs = Mock()
    attrs.consent_status = "accepted"
    node.attributes = attrs
    
    consent = _extract_shutdown_consent_from_node(node)
    assert consent == "accepted"

def test_extract_shutdown_consent_none():
    """Test extracting consent status when not present."""
    from ciris_engine.logic.services.graph.telemetry_service.helpers import _extract_shutdown_consent_from_node
    
    # No attributes
    node_no_attrs = Mock(spec=[])
    assert _extract_shutdown_consent_from_node(node_no_attrs) is None
    
    # Dict without consent_status
    node_dict = Mock()
    node_dict.attributes = {"reason": "test"}
    assert _extract_shutdown_consent_from_node(node_dict) is None
