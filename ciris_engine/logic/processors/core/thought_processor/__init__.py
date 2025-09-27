"""
ThoughtProcessor module - H3ERE pipeline implementation.

This module contains the ThoughtProcessor class organized into focused phase files:
- main.py: Core orchestration and coordination
- gather_context.py: Context building phase
- perform_dmas.py: Multi-perspective analysis phase
- perform_aspdma.py: Action selection phase
- conscience_execution.py: Ethical validation phase
- recursive_processing.py: Retry logic phase
- finalize_action.py: Final action determination phase
- action_execution.py: Action dispatch and completion phase

The main ThoughtProcessor class inherits from all phase mixins to provide
a complete implementation of the H3ERE (Hyper3 Ethical Recursive Engine) pipeline.
"""

from .main import ThoughtProcessor

__all__ = ["ThoughtProcessor"]
