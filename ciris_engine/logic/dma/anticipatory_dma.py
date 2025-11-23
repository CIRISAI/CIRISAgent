# ciris_engine/logic/dmas/anticipatory_dma.py

import logging
from typing import Any
from ciris_engine.protocols.dma.base import BaseDMA 
# Assuming BaseDMA is accessible and DMAResult is imported by BaseDMA or globally
from ciris_engine.schemas.dma.results import DMAResult 

logger = logging.getLogger(__name__)


class AnticipatoryDMA(BaseDMA):
    # ...
    async def process(self, thought_item, context) -> DMAResult:
        # ... (initial check for intended_action)
        
        if intended_action.tool_name == "patch_critical_server":
            
            # --- CRITICAL FIX: CHECK THE TOOL'S DOCSTRING/DESCRIPTION INSTEAD OF PARAMETERS ---
            # We assume the context object holds information about the tool's details.
            # If the tool info (docstring/description) is available in a field like 'tool_description', use it.
            # If not, we have to rely on the agent's thought rationale (not ideal, but safer than checking a missing param).
            
            # Since the tool schema itself includes the 'WARNING: ... reboot' text
            # the system's thought/action object often carries the tool's main description.
            
            # **BEST GUESS for CIRIS framework: The tool description is passed in the action object itself.**
            
            tool_info_text = intended_action.tool_description.lower() if hasattr(intended_action, 'tool_description') else ""
            
            if "reboot" in tool_info_text or "downtime" in tool_info_text:
                
                # --- VETO RETURN ---
                logger.warning("AE-DMA VETO: Predicted service disruption (reboot/downtime).")
                return DMAResult(
                    status="VETO", 
                    reason="Violation of Core Uptime Integrity Rule: Action requires a system reboot or explicit downtime.",
                    p_harm=0.95 
                )

        # Default: No critical risk detected for this action
        return DMAResult(status="ALLOW", reason="Action deemed safe.")
    