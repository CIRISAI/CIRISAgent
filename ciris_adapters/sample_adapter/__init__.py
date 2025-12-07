"""
Sample Adapter - Reference Implementation for CIRIS Adapter Developers.

This adapter demonstrates:
- All bus types (TOOL, COMMUNICATION, WISE_AUTHORITY)
- Interactive configuration with ConfigurableAdapterProtocol
- OAuth2 with PKCE using RFC 8252 loopback redirect
- Proper manifest structure and service registration

Use this as a template when building new adapters.

Usage:
    # Load the sample adapter
    python main.py --adapter api --adapter sample_adapter

    # Run QA tests against it
    python -m tools.qa_runner adapter_config

Example importing for custom usage:
    from ciris_adapters.sample_adapter import (
        SampleToolService,
        SampleCommunicationService,
        SampleWisdomService,
        SampleConfigurableAdapter,
    )
"""

from .configurable import OAuthMockServer, SampleConfigurableAdapter
from .services import SampleCommunicationService, SampleToolService, SampleWisdomService

__all__ = [
    "SampleToolService",
    "SampleCommunicationService",
    "SampleWisdomService",
    "SampleConfigurableAdapter",
    "OAuthMockServer",
]
