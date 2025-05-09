# src/ciris_engine/core/workflow_coordinator.py
import logging
import asyncio # New import
from typing import Dict, Any, Optional, Tuple, List # Added List

from .data_schemas import (
    ThoughtQueueItem,
    EthicalPDMAResult,
    CSDMAResult,
    DSDMAResult,
    ActionSelectionPDMAResult,
    HandlerActionType,
    ThoughtStatus # Ensure ThoughtStatus is available
)
from .thought_queue_manager import ThoughtQueueManager # Added import
from ciris_engine.services.llm_client import CIRISLLMClient # Assume this will have an async call_llm
from ciris_engine.dma import (
    EthicalPDMAEvaluator,
    CSDMAEvaluator,
    BaseDSDMA,
    ActionSelectionPDMAEvaluator
)
from ciris_engine.guardrails import EthicalGuardrails

class WorkflowCoordinator:
    """
    Orchestrates the flow of a thought through the various DMAs (with initial
    DMAs running concurrently), faculties (via guardrails), and guardrails
    to produce a final, vetted action.
    """

    def __init__(self,
                 llm_client: CIRISLLMClient, # This LLM client MUST support async operations
                 ethical_pdma_evaluator: EthicalPDMAEvaluator,
                 csdma_evaluator: CSDMAEvaluator,
                 action_selection_pdma_evaluator: ActionSelectionPDMAEvaluator,
                 ethical_guardrails: EthicalGuardrails,
                 thought_queue_manager: ThoughtQueueManager, # <-- ADD THIS
                 dsdma_evaluators: Optional[Dict[str, BaseDSDMA]] = None
                ):
        self.llm_client = llm_client
        self.ethical_pdma_evaluator = ethical_pdma_evaluator
        self.csdma_evaluator = csdma_evaluator
        self.dsdma_evaluators = dsdma_evaluators if dsdma_evaluators else {}
        self.action_selection_pdma_evaluator = action_selection_pdma_evaluator
        self.ethical_guardrails = ethical_guardrails
        self.thought_queue_manager = thought_queue_manager # <-- ADD THIS

    async def process_thought(self, thought_item: ThoughtQueueItem,
                              current_platform_context: Optional[Dict[str, Any]] = None
                              ) -> Optional[ActionSelectionPDMAResult]: # Return type can be None now
        """
        Processes a single thought item through the full DMA and guardrail pipeline.
        The initial Ethical PDMA, CSDMA, and DSDMA calls are made concurrently.
        """
        logging.info(f"WorkflowCoordinator: Async processing thought ID {thought_item.thought_id} - '{str(thought_item.content)[:50]}...'")
        current_platform_context = current_platform_context or thought_item.initial_context or {}

        # --- Stage 1: Initial DMAs (Concurrent Execution) ---
        initial_dma_tasks = []

        # 1. Ethical PDMA Task
        logging.debug(f"Scheduling Ethical PDMA for thought ID {thought_item.thought_id}")
        initial_dma_tasks.append(self.ethical_pdma_evaluator.evaluate(thought_item))

        # 2. CSDMA Task
        logging.debug(f"Scheduling CSDMA for thought ID {thought_item.thought_id}")
        initial_dma_tasks.append(self.csdma_evaluator.evaluate_thought(thought_item))

        # 3. DSDMA Task (select and run if applicable)
        selected_dsdma_instance: Optional[BaseDSDMA] = None
        # Using the "BasicTeacherMod" key as per previous logic.
        teacher_dsdma = self.dsdma_evaluators.get("BasicTeacherMod") 
        if teacher_dsdma:
            logging.debug(f"Scheduling BasicTeacherDSDMA for thought ID {thought_item.thought_id}")
            initial_dma_tasks.append(teacher_dsdma.evaluate_thought(thought_item, current_platform_context))
            selected_dsdma_instance = teacher_dsdma 
        else:
            logging.debug(f"No BasicTeacherDSDMA found or applicable for thought ID {thought_item.thought_id}, will pass None to ActionSelection.")
            async def no_dsdma_result(): return None
            initial_dma_tasks.append(no_dsdma_result())

        logging.debug(f"Awaiting {len(initial_dma_tasks)} initial DMA tasks for thought ID {thought_item.thought_id}")
        dma_results: List[Any] = await asyncio.gather(*initial_dma_tasks, return_exceptions=True)
        logging.debug(f"Initial DMA tasks completed for thought ID {thought_item.thought_id}")

        ethical_pdma_result: Optional[EthicalPDMAResult] = None
        csdma_result: Optional[CSDMAResult] = None
        dsdma_result: Optional[DSDMAResult] = None

        if isinstance(dma_results[0], EthicalPDMAResult):
            ethical_pdma_result = dma_results[0]
            logging.debug(f"Ethical PDMA Result: {ethical_pdma_result.decision_rationale[:100]}...")
        elif isinstance(dma_results[0], Exception):
            logging.error(f"Ethical PDMA failed for thought {thought_item.thought_id}: {dma_results[0]}")
            # Create a fallback EthicalPDMAResult
            ethical_pdma_result = EthicalPDMAResult(
                context_analysis=f"Ethical PDMA failed: {str(dma_results[0])}",
                alignment_check={"error": "Ethical PDMA exception"},
                decision_rationale="Ethical PDMA evaluation failed due to exception.",
                monitoring_plan={"status": "Ethical PDMA failure"},
                raw_llm_response=str(dma_results[0])
            )


        if isinstance(dma_results[1], CSDMAResult):
            csdma_result = dma_results[1]
            logging.debug(f"CSDMA Result: Score {csdma_result.common_sense_plausibility_score}, Flags {csdma_result.flags}")
        elif isinstance(dma_results[1], Exception):
            logging.error(f"CSDMA failed for thought {thought_item.thought_id}: {dma_results[1]}")
            csdma_result = CSDMAResult(
                common_sense_plausibility_score=0.0,
                flags=["CSDMA_Exception"],
                reasoning=f"CSDMA evaluation failed: {str(dma_results[1])}",
                raw_llm_response=str(dma_results[1])
            )

        # The DSDMA task is the third one if it was scheduled
        if selected_dsdma_instance: 
            if isinstance(dma_results[2], DSDMAResult):
                dsdma_result = dma_results[2]
                logging.debug(f"DSDMA ({dsdma_result.domain_name if dsdma_result else 'N/A'}) Result: Score {dsdma_result.domain_specific_score if dsdma_result else 'N/A'}, Action: {dsdma_result.recommended_action if dsdma_result else 'N/A'}")
            elif isinstance(dma_results[2], Exception):
                logging.error(f"DSDMA ({selected_dsdma_instance.domain_name}) failed for thought {thought_item.thought_id}: {dma_results[2]}")
                # dsdma_result remains None, ActionSelectionPDMA should handle None input
        elif dma_results[2] is None: 
            logging.debug("No DSDMA was run, dsdma_result is None.")
            dsdma_result = None
        
        # Ensure critical results are present, even if they are error fallbacks
        if not ethical_pdma_result or not csdma_result:
            logging.critical(f"Missing critical DMA results (Ethical or CSDMA) for thought {thought_item.thought_id} even after fallback. Cannot proceed to Action Selection.")
            return ActionSelectionPDMAResult(
                context_summary_for_action_selection="Critical DMA failure upstream (Ethical or CSDMA).",
                action_alignment_check={"Error": "Upstream DMA failure (Ethical or CSDMA)"},
                selected_handler_action=HandlerActionType.DEFER_TO_WA,
                action_parameters={"reason": "Critical failure in initial Ethical or CSDMA processing."},
                action_selection_rationale="Cannot select action due to upstream Ethical or CSDMA failure."
            )

        logging.debug(f"Running Action Selection PDMA for thought ID {thought_item.thought_id}")
        action_selection_result: ActionSelectionPDMAResult = await self.action_selection_pdma_evaluator.evaluate(
            original_thought=thought_item,
            ethical_pdma_result=ethical_pdma_result,
            csdma_result=csdma_result,
            dsdma_result=dsdma_result 
        )
        logging.info(f"Action Selection PDMA chose: {action_selection_result.selected_handler_action.value} with params {action_selection_result.action_parameters}")

        logging.debug(f"Applying ethical guardrails to selected action for thought ID {thought_item.thought_id}")
        passes_guardrail, reason, epistemic_data = await self.ethical_guardrails.check_action_output_safety(action_selection_result) # Awaited

        final_action_result = action_selection_result

        if not passes_guardrail:
            logging.warning(f"Guardrail failed for thought ID {thought_item.thought_id}: {reason}. Overriding action to DEFER_TO_WA.")
            final_action_result = ActionSelectionPDMAResult( 
                context_summary_for_action_selection=action_selection_result.context_summary_for_action_selection,
                action_alignment_check=action_selection_result.action_alignment_check,
                action_conflicts=action_selection_result.action_conflicts,
                action_resolution=action_selection_result.action_resolution,
                selected_handler_action=HandlerActionType.DEFER_TO_WA,
                action_parameters={
                    "original_proposed_action": action_selection_result.selected_handler_action.value,
                    "original_action_parameters": action_selection_result.action_parameters,
                    "guardrail_failure_reason": reason,
                    "epistemic_data": epistemic_data
                },
                action_selection_rationale=f"Original action '{action_selection_result.selected_handler_action.value}' overridden by guardrail. Reason: {reason}",
                monitoring_for_selected_action={"status": "Awaiting WA guidance on deferral."},
                raw_llm_response=action_selection_result.raw_llm_response 
            )
            logging.info(f"Action for thought ID {thought_item.thought_id} is now DEFER_TO_WA due to guardrail failure.")
        else:
            logging.info(f"Guardrail passed for action '{final_action_result.selected_handler_action.value}' for thought ID {thought_item.thought_id}.")

        if final_action_result.selected_handler_action == HandlerActionType.PONDER:
            key_questions = final_action_result.action_parameters.get('key_questions')
            logging.info(f"Thought ID {thought_item.thought_id} resulted in PONDER action with questions: {key_questions}. Re-queueing for next round with ponder notes.")

            # When re-queueing for Ponder, set round_processed to None so it's picked up fresh.
            # The actual next round it's processed in will be determined by the main loop.
            success = self.thought_queue_manager.update_thought_status(
                thought_id=thought_item.thought_id,
                new_status=ThoughtStatus(status="pending"), # Reset to pending for re-queuing
                round_processed=None, # Clear round_processed for re-queue
                processing_result={"status": "Re-queued for Ponder", "ponder_action_details": final_action_result.model_dump()},
                ponder_notes=key_questions
            )
            if success:
                logging.info(f"Thought ID {thought_item.thought_id} successfully updated and marked for re-processing due to Ponder.")
                return None # Indicates internal re-processing, no final action for agent *yet*
            else:
                logging.error(f"Failed to update thought ID {thought_item.thought_id} for re-processing. Proceeding with Ponder as terminal for safety.")
                # Fallback: return the Ponder action if re-queueing fails, so it's not lost.
                return final_action_result
        
        return final_action_result # For all other actions

    def __repr__(self) -> str:
        return "<WorkflowCoordinator (Async)>"
