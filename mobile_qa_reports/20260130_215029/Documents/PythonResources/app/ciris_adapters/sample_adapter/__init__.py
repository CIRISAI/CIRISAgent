"""
Sample Adapter - Reference Implementation for CIRIS Adapter Developers.

This adapter demonstrates:
- All bus types (TOOL, COMMUNICATION, WISE_AUTHORITY)
- Interactive configuration with ConfigurableAdapterProtocol
- OAuth2 with PKCE using RFC 8252 loopback redirect
- Proper manifest structure and service registration
- BaseAdapterProtocol compliance for dynamic loading

Use this as a template when building new adapters.

Usage:
    # Load the sample adapter
    python main.py --adapter api --adapter sample_adapter

    # Run QA tests against it
    python -m tools.qa_runner adapter_config

Example importing for custom usage:
    from ciris_adapters.sample_adapter import (
        Adapter,  # BaseAdapterProtocol-compliant wrapper
        SampleToolService,
        SampleCommunicationService,
        SampleWisdomService,
        SampleConfigurableAdapter,
    )
"""

from .adapter import SampleAdapter
from .configurable import OAuthMockServer, SampleConfigurableAdapter
from .services import SampleCommunicationService, SampleToolService, SampleWisdomService

# Export as Adapter for load_adapter() compatibility
Adapter = SampleAdapter

__all__ = [
    "Adapter",  # Primary export for dynamic loading
    "SampleAdapter",
    "SampleToolService",
    "SampleCommunicationService",
    "SampleWisdomService",
    "SampleConfigurableAdapter",
    "OAuthMockServer",
]
