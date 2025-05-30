"""
ThoughtProcessor: Core logic for processing a single thought in the CIRISAgent pipeline.
Coordinates DMA orchestration, context building, guardrails, and pondering.
"""
import logging
from typing import Optional, Dict, Any

from ciris_engine.schemas.config_schemas_v1 import AppConfig
from ciris_engine.processor.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.agent_core_schemas_v1 import ActionSelectionResult, Thought
from ciris_engine.schemas.foundational_schemas_v1 import ThoughtStatus, HandlerActionType # Added imports
from ciris_engine.schemas.action_params_v1 import PonderParams # Ensure this import is present
from ciris_engine.action_handlers.ponder_handler import PonderHandler # Ensure this import is present
from ciris_engine.action_handlers.base_handler import ActionHandlerDependencies # Add this import

logger = logging.getLogger(__name__)

class ThoughtProcessor:
    def __init__(
        self,
        dma_orchestrator,
        context_builder,
        guardrail_orchestrator,
        app_config: AppConfig,
        dependencies: ActionHandlerDependencies # Add dependencies
    ):
        self.dma_orchestrator = dma_orchestrator
        self.context_builder = context_builder
        self.guardrail_orchestrator = guardrail_orchestrator
        self.app_config = app_config
        self.dependencies = dependencies # Store dependencies
        self.settings = app_config.workflow # New: Point to the workflow config directly

    async def process_thought(
        self,
        thought_item: ProcessingQueueItem,
        platform_context: Optional[Dict[str, Any]] = None,
        benchmark_mode: bool = False
    ) -> Optional[ActionSelectionResult]:
        """Main processing pipeline - coordinates the components."""
        # 1. Fetch the full Thought object
        thought = await self._fetch_thought(thought_item.thought_id)
        if not thought:
            logger.error(f"Thought {thought_item.thought_id} not found.")
            return None

        # 2. Build context
        context = await self.context_builder.build_thought_context(thought)

        # 3. Run DMAs
        # profile_name is not an accepted argument by run_initial_dmas.
        # If profile specific DMA behavior is needed, it might be part of thought_item's context
        # or run_initial_dmas and its sub-runners would need to be updated.
        # For now, removing profile_name to fix TypeError.
        # The dsdma_context argument is optional and defaults to None if not provided.
        dma_results = await self.dma_orchestrator.run_initial_dmas(
            thought_item=thought_item
        )

        # 4. Check for failures/escalations
        if self._has_critical_failure(dma_results):
            return self._create_deferral_result(dma_results, thought)

        # 5. Run action selection
        profile_name = self._get_profile_name(thought)
        action_result = await self.dma_orchestrator.run_action_selection(
            thought_item=thought_item,
            actual_thought=thought,
            processing_context=context, # This is the ThoughtContext
            dma_results=dma_results,
            profile_name=profile_name
        )
        
        # CRITICAL DEBUG: Check action_result details immediately
        if action_result:
            selected_action = getattr(action_result, 'selected_action', 'UNKNOWN')
            logger.info(f"ThoughtProcessor: Action selection result for {thought.thought_id}: {selected_action}")
            
            # Special debug for OBSERVE actions
            if selected_action == HandlerActionType.OBSERVE:
                logger.warning(f"OBSERVE ACTION DEBUG: ThoughtProcessor received OBSERVE action for thought {thought.thought_id}")
                logger.warning(f"OBSERVE ACTION DEBUG: action_result type: {type(action_result)}")
                logger.warning(f"OBSERVE ACTION DEBUG: action_result details: {action_result}")
        else:
            logger.error(f"ThoughtProcessor: No action result from DMA for {thought.thought_id}")
            logger.error(f"ThoughtProcessor: action_result is None! This is the critical issue.")
            # Return early with fallback result
            return self._create_deferral_result(dma_results, thought)

        # 6. Apply guardrails
        logger.info(f"ThoughtProcessor: Applying guardrails for {thought.thought_id} with action {getattr(action_result, 'selected_action', 'UNKNOWN')}")
        guardrail_result = await self.guardrail_orchestrator.apply_guardrails(
            action_result, thought, dma_results
        )
        
        # DEBUG: Log guardrail result details
        if guardrail_result:
            if hasattr(guardrail_result, 'final_action') and guardrail_result.final_action:
                final_action = getattr(guardrail_result.final_action, 'selected_action', 'UNKNOWN')
                logger.info(f"ThoughtProcessor: Guardrail result for {thought.thought_id}: final_action={final_action}")
            else:
                logger.warning(f"ThoughtProcessor: Guardrail result for {thought.thought_id} has no final_action")
        else:
            logger.error(f"ThoughtProcessor: No guardrail result for {thought.thought_id}")

        # 7. Handle special cases (PONDER, DEFER overrides)
        logger.info(f"ThoughtProcessor: Handling special cases for {thought.thought_id}")
        final_result = await self._handle_special_cases(
            guardrail_result, thought, context
        )

        # 8. Ensure we return the final result
        if final_result:
            logger.debug(f"ThoughtProcessor returning result for thought {thought.thought_id}: {final_result.selected_action}")
        else:
            # If no final result, check if we got a guardrail result we can use
            if hasattr(guardrail_result, 'final_action') and guardrail_result.final_action:
                final_result = guardrail_result.final_action
                logger.debug(f"ThoughtProcessor using guardrail final_action for thought {thought.thought_id}")
            else:
                logger.warning(f"ThoughtProcessor: No final result for thought {thought.thought_id}")

        return final_result

    async def _fetch_thought(self, thought_id: str) -> Optional[Thought]:
        # Import here to avoid circular import
        from ciris_engine import persistence
        return persistence.get_thought_by_id(thought_id)

    def _get_profile_name(self, thought: Thought) -> str:
        """Extract profile name from thought context or use default."""
        profile_name = None
        # Method 1: From thought context (if it was set during task creation)
        if hasattr(thought, 'context') and isinstance(thought.context, dict):
            profile_name = thought.context.get('agent_profile_name')
        # Method 2: Check if we have a primary profile loaded
        # Look for non-default profiles first
        if not profile_name and hasattr(self.app_config, 'agent_profiles'):
            for name, profile in self.app_config.agent_profiles.items():
                if name != "default" and profile:
                    profile_name = name
                    break
        # Method 3: Use configured default profile
        if not profile_name and hasattr(self.app_config, 'default_profile'):
            profile_name = self.app_config.default_profile
        # Final fallback
        if not profile_name:
            profile_name = "default"
        logger.debug(f"Determined profile name '{profile_name}' for thought {thought.thought_id}")
        return profile_name

    def _get_permitted_actions(self, thought: Thought) -> Any:
        # Example: extract permitted actions from context or config
        return getattr(thought, 'permitted_actions', None)

    def _has_critical_failure(self, dma_results: Any) -> bool:
        # Placeholder: implement logic to detect critical DMA failures
        return getattr(dma_results, 'critical_failure', False)

    def _create_deferral_result(self, dma_results: Dict[str, Any], thought: Thought) -> ActionSelectionResult:
        from ciris_engine.schemas.action_params_v1 import DeferParams
        from ciris_engine.schemas.foundational_schemas_v1 import HandlerActionType
        from ciris_engine.utils.constants import DEFAULT_WA

        defer_reason = "Critical DMA failure or guardrail override."
        # Ensure dma_results are serializable if they contain Pydantic models
        serializable_dma_results = {}
        for k, v in dma_results.items():
            if hasattr(v, 'model_dump'):
                serializable_dma_results[k] = v.model_dump(mode='json')
            else:
                serializable_dma_results[k] = v

        defer_params = DeferParams(
            reason=defer_reason,
            target_wa_ual=DEFAULT_WA, # Or a more specific UAL if available
            context={"original_thought_id": thought.thought_id, "dma_results_summary": serializable_dma_results}
        )
        
        return ActionSelectionResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=defer_params.model_dump(mode='json'), # Pass as dict
            rationale=defer_reason
            # Confidence and raw_llm_response can be None/omitted for system-generated deferrals
        )



    async def _handle_special_cases(self, result, thought, context):
        """Handle special cases like PONDER and DEFER overrides."""
        # Handle both GuardrailResult and ActionSelectionResult
        selected_action = None
        final_result = result
        
        if result is None:
            logger.error(f"ThoughtProcessor: No result provided for thought {thought.thought_id}")
            return None

        if hasattr(result, 'selected_action'):
            # This is an ActionSelectionResult
            selected_action = result.selected_action
            final_result = result
        elif hasattr(result, 'final_action') and result.final_action and hasattr(result.final_action, 'selected_action'):
            # This is a GuardrailResult - extract the final_action
            selected_action = result.final_action.selected_action
            final_result = result.final_action  # Use the final_action ActionSelectionResult
            logger.debug(
                f"ThoughtProcessor: Extracted final_action from GuardrailResult for thought {thought.thought_id}"
            )
        else:
            logger.warning(
                f"ThoughtProcessor: Unknown result type for thought {thought.thought_id}: {type(result)}. Returning result as-is."
            )
            return result
        
        # Log the action being handled
        if selected_action:
            logger.debug(f"ThoughtProcessor handling special case for action: {selected_action}")
        else:
            logger.warning(f"ThoughtProcessor: No selected_action found for thought {thought.thought_id}")
            return final_result  # Return what we have instead of None
        
        # TASK_COMPLETE actions should be returned as-is for proper dispatch
        from ciris_engine.schemas.foundational_schemas_v1 import HandlerActionType
        if selected_action == HandlerActionType.TASK_COMPLETE:
            logger.debug(f"ThoughtProcessor: Returning TASK_COMPLETE result for thought {thought.thought_id}")
            return final_result
        
        # NOTE: PONDER actions are now handled by the PonderHandler in the action dispatcher
        # No special processing needed here - just return the result for normal dispatch
        return final_result







    async def _update_thought_status(self, thought, result):
        from ciris_engine import persistence
        # Update the thought status in persistence
        # Support GuardrailResult as well as ActionSelectionResult
        selected_action = None
        action_parameters = None
        rationale = None
        if hasattr(result, 'selected_action'):
            selected_action = result.selected_action
            action_parameters = getattr(result, 'action_parameters', None)
            rationale = getattr(result, 'rationale', None)
        elif hasattr(result, 'final_action') and hasattr(result.final_action, 'selected_action'):
            selected_action = result.final_action.selected_action
            action_parameters = getattr(result.final_action, 'action_parameters', None)
            rationale = getattr(result.final_action, 'rationale', None)
        new_status_val = ThoughtStatus.COMPLETED # Default, will be overridden by specific actions
        if selected_action == HandlerActionType.DEFER:
            new_status_val = ThoughtStatus.DEFERRED
        elif selected_action == HandlerActionType.PONDER:
            new_status_val = ThoughtStatus.PENDING # Ponder implies it goes back to pending for re-evaluation
        elif selected_action == HandlerActionType.REJECT:
            new_status_val = ThoughtStatus.FAILED # Reject implies failure of this thought path
        # Other actions might imply ThoughtStatus.COMPLETED if they are terminal for the thought.
        final_action_details = {
            "action_type": selected_action.value if selected_action else None,
            "parameters": action_parameters.model_dump(mode="json") if hasattr(action_parameters, "model_dump") else action_parameters,
            "rationale": rationale
        }
        persistence.update_thought_status(
            thought_id=thought.thought_id,
            status=new_status_val, # Pass ThoughtStatus enum member
            final_action=final_action_details
        )

    async def _handle_action_selection(
        self, thought: Thought, action_selection: ActionSelectionResult, context: Dict[str, Any]
    ) -> None:
        """Handles the selected action by dispatching to the appropriate handler."""
        # ...existing code...
        if action_selection.action == HandlerActionType.PONDER:
            ponder_questions = []
            if action_selection.action_parameters:
                if isinstance(action_selection.action_parameters, dict) and 'questions' in action_selection.action_parameters:
                    ponder_questions = action_selection.action_parameters['questions']
                elif hasattr(action_selection.action_parameters, 'questions'):
                    ponder_questions = action_selection.action_parameters.questions
            
            if not ponder_questions:
                ponder_questions = [
                    "What is the core issue I need to address?",
                    "What additional context would help me provide a better response?",
                    "Are there any assumptions I should reconsider?"
                ]
            
            ponder_params = PonderParams(questions=ponder_questions)
            
            # max_rounds is now directly on self.settings (which is app_config.workflow)
            max_rounds = getattr(self.settings, 'max_rounds', 5) 
            ponder_handler = PonderHandler(dependencies=self.dependencies, max_rounds=max_rounds)
            
            await ponder_handler.handle(
                thought=thought,
                ponder_params=ponder_params,
                context=context
            )
            
            # After PonderHandler.handle, the thought's status and ponder_count are updated.
            # If status is PENDING, it means it should be re-processed in the next round.
            # No need to manually re-queue - the processing loop will pick up PENDING thoughts naturally.
            if thought.status == ThoughtStatus.PENDING:
                logger.info(f"Thought ID {thought.thought_id} marked as PENDING after PONDER action - will be processed in next round.")
        
        # Special handling for OBSERVE action in CLI mode
        if action_selection.action == HandlerActionType.OBSERVE:
            agent_mode = getattr(self.app_config, "agent_mode", "").lower()
            if agent_mode == "cli":
                import os
                try:
                    cwd = os.getcwd()
                    files = os.listdir(cwd)
                    file_list = "\n".join(sorted(files))
                    observation = f"[CLI MODE] Agent working directory: {cwd}\n\nDirectory contents:\n{file_list}\n\nNote: CIRISAgent is running in CLI mode."
                except Exception as e:
                    observation = f"[CLI MODE] Error listing working directory: {e}"
                # Attach the observation to the action_parameters
                obs_result = locals().get('final_result', None)
                if obs_result and hasattr(obs_result, "action_parameters"):
                    if isinstance(obs_result.action_parameters, dict):
                        obs_result.action_parameters["observation"] = observation
                    else:
                        try:
                            setattr(obs_result.action_parameters, "observation", observation)
                        except Exception:
                            pass
                logger.info(f"[OBSERVE] CLI observation attached for thought {thought.thought_id}")
                return obs_result
        # ...existing code...
