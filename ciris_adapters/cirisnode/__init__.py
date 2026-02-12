"""
CIRISNode oversight adapter — deferral routing and trace forwarding.

Registers as WISE_AUTHORITY for:
- WBD deferral submission and resolution polling
- Covenant trace forwarding in Lens format
"""

from ciris_adapters.cirisnode.adapter import CIRISNodeAdapter
from ciris_adapters.cirisnode.client import CIRISNodeClient
from ciris_adapters.cirisnode.services import CIRISNodeService

Adapter = CIRISNodeAdapter

__all__ = ["CIRISNodeAdapter", "CIRISNodeClient", "CIRISNodeService", "Adapter"]
