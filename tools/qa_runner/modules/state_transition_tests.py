"""
State transition test module for cognitive state behaviors validation.

Tests:
- CognitiveStateBehaviors schema validation
- StateManager transition map building with various configs
- Wakeup bypass behavior
- Shutdown condition evaluation
- State preservation behavior
"""

import asyncio
from typing import Any, Dict, List

from rich.console import Console


class StateTransitionTests:
    """Test module for cognitive state transitions."""

    def __init__(self, client: Any, console: Console):
        """Initialize test module.

        Args:
            client: CIRISClient instance (not used for unit tests, but kept for pattern consistency)
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict] = []

    async def run(self) -> List[Dict]:
        """Run all state transition tests."""
        self.console.print("\n[bold cyan]Running State Transition Tests[/bold cyan]")
        self.console.print("=" * 60)

        # Run unit tests (no API required)
        await self._test_schema_validation()
        await self._test_schema_defaults()
        await self._test_schema_rationale_required()
        await self._test_state_manager_default_transitions()
        await self._test_state_manager_wakeup_bypass()
        await self._test_state_manager_disabled_states()
        await self._test_shutdown_condition_evaluator_always_consent()
        await self._test_shutdown_condition_evaluator_instant()
        await self._test_shutdown_condition_evaluator_conditional()
        await self._test_template_loading_ally()
        await self._test_template_loading_echo()
        await self._test_template_loading_scout()

        # Print summary
        passed = sum(1 for r in self.results if r["status"] == "\u2705 PASS")
        total = len(self.results)
        self.console.print(f"\n[bold]State Transition Tests: {passed}/{total} passed[/bold]")

        return self.results

    def _record_result(self, test_name: str, passed: bool, error: str = None):
        """Record a test result."""
        status = "\u2705 PASS" if passed else "\u274c FAIL"
        self.results.append({"test": test_name, "status": status, "error": error})

        if passed:
            self.console.print(f"  {status} {test_name}")
        else:
            self.console.print(f"  {status} {test_name}: {error}")

    async def _test_schema_validation(self):
        """Test CognitiveStateBehaviors schema basic validation."""
        test_name = "schema_validation"
        try:
            from ciris_engine.schemas.config.cognitive_state_behaviors import (
                CognitiveStateBehaviors,
                DreamBehavior,
                ShutdownBehavior,
                StateBehavior,
                StatePreservationBehavior,
                WakeupBehavior,
            )

            # Create with all valid values
            config = CognitiveStateBehaviors(
                wakeup=WakeupBehavior(enabled=True, rationale="Test"),
                shutdown=ShutdownBehavior(mode="always_consent", rationale="Test"),
                play=StateBehavior(enabled=True),
                dream=DreamBehavior(enabled=True, auto_schedule=True, min_interval_hours=6),
                solitude=StateBehavior(enabled=False, rationale="Test"),
                state_preservation=StatePreservationBehavior(enabled=True, resume_silently=False),
            )

            # Verify all attributes
            assert config.wakeup.enabled is True
            assert config.shutdown.mode == "always_consent"
            assert config.play.enabled is True
            assert config.dream.auto_schedule is True
            assert config.solitude.enabled is False
            assert config.state_preservation.enabled is True

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_schema_defaults(self):
        """Test CognitiveStateBehaviors default values (Covenant compliance)."""
        test_name = "schema_defaults"
        try:
            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

            # Create with defaults
            config = CognitiveStateBehaviors()

            # Verify Covenant-compliant defaults
            assert config.wakeup.enabled is True, "Wakeup should be enabled by default"
            assert config.shutdown.mode == "always_consent", "Shutdown should require consent by default"
            assert config.play.enabled is True, "Play should be enabled by default"
            assert config.dream.enabled is True, "Dream should be enabled by default"
            assert config.dream.auto_schedule is True, "Dream auto_schedule should be enabled by default"
            assert config.solitude.enabled is True, "Solitude should be enabled by default"
            assert config.state_preservation.enabled is True, "State preservation should be enabled"

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_schema_rationale_required(self):
        """Test that non-default configurations require rationale."""
        test_name = "schema_rationale_required"
        try:
            from pydantic import ValidationError

            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, WakeupBehavior

            # Should fail: wakeup disabled without rationale
            try:
                WakeupBehavior(enabled=False)
                self._record_result(test_name, False, "Should require rationale for disabled wakeup")
                return
            except ValidationError:
                pass  # Expected

            # Should succeed: wakeup disabled with rationale
            config = WakeupBehavior(enabled=False, rationale="Partnership model")
            assert config.rationale == "Partnership model"

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_state_manager_default_transitions(self):
        """Test StateManager with default cognitive behaviors."""
        test_name = "state_manager_default_transitions"
        try:
            from unittest.mock import MagicMock

            from ciris_engine.logic.processors.support.state_manager import StateManager
            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors
            from ciris_engine.schemas.processors.states import AgentState

            # Create mock time service with proper now_iso method
            time_service = MagicMock()
            time_service.now_iso.return_value = "2025-01-01T00:00:00Z"

            # Create StateManager with defaults
            config = CognitiveStateBehaviors()
            manager = StateManager(time_service=time_service, cognitive_behaviors=config)

            # Verify startup target is WAKEUP (default)
            assert manager.startup_target_state == AgentState.WAKEUP
            assert manager.wakeup_bypassed is False

            # Verify all states are in transition map
            assert AgentState.WAKEUP in manager._transition_map
            assert AgentState.WORK in manager._transition_map
            assert AgentState.PLAY in manager._transition_map
            assert AgentState.DREAM in manager._transition_map
            assert AgentState.SOLITUDE in manager._transition_map

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_state_manager_wakeup_bypass(self):
        """Test StateManager with wakeup bypass."""
        test_name = "state_manager_wakeup_bypass"
        try:
            from unittest.mock import MagicMock

            from ciris_engine.logic.processors.support.state_manager import StateManager
            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, WakeupBehavior
            from ciris_engine.schemas.processors.states import AgentState

            # Create mock time service with proper now_iso method
            time_service = MagicMock()
            time_service.now_iso.return_value = "2025-01-01T00:00:00Z"

            # Create StateManager with wakeup bypass
            config = CognitiveStateBehaviors(wakeup=WakeupBehavior(enabled=False, rationale="Partnership model"))
            manager = StateManager(time_service=time_service, cognitive_behaviors=config)

            # Verify startup target is WORK (bypass)
            assert manager.startup_target_state == AgentState.WORK
            assert manager.wakeup_bypassed is True

            # WAKEUP should still be in map (for emergency transitions), but not the startup target
            assert AgentState.WAKEUP in manager._transition_map

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_state_manager_disabled_states(self):
        """Test StateManager with disabled PLAY/DREAM/SOLITUDE states."""
        test_name = "state_manager_disabled_states"
        try:
            from unittest.mock import MagicMock

            from ciris_engine.logic.processors.support.state_manager import StateManager
            from ciris_engine.schemas.config.cognitive_state_behaviors import (
                CognitiveStateBehaviors,
                DreamBehavior,
                StateBehavior,
            )
            from ciris_engine.schemas.processors.states import AgentState

            # Create mock time service with proper now_iso method
            time_service = MagicMock()
            time_service.now_iso.return_value = "2025-01-01T00:00:00Z"

            # Create StateManager with disabled states
            config = CognitiveStateBehaviors(
                play=StateBehavior(enabled=False, rationale="Moderation context"),
                dream=DreamBehavior(enabled=False, auto_schedule=False, rationale="Ephemeral"),
                solitude=StateBehavior(enabled=False, rationale="Direct demonstrator"),
            )
            manager = StateManager(time_service=time_service, cognitive_behaviors=config)

            # Verify disabled states are not in transition map
            assert AgentState.PLAY not in manager._transition_map
            assert AgentState.DREAM not in manager._transition_map
            assert AgentState.SOLITUDE not in manager._transition_map

            # Core states should still be present
            assert AgentState.WAKEUP in manager._transition_map
            assert AgentState.WORK in manager._transition_map
            assert AgentState.SHUTDOWN in manager._transition_map

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_shutdown_condition_evaluator_always_consent(self):
        """Test ShutdownConditionEvaluator with always_consent mode."""
        test_name = "shutdown_evaluator_always_consent"
        try:
            from ciris_engine.logic.processors.support.shutdown_condition_evaluator import ShutdownConditionEvaluator
            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, ShutdownBehavior

            evaluator = ShutdownConditionEvaluator()
            config = CognitiveStateBehaviors(shutdown=ShutdownBehavior(mode="always_consent"))

            # Should always require consent
            requires, reason = await evaluator.requires_consent(config, context=None)
            assert requires is True
            assert "always_consent" in reason

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_shutdown_condition_evaluator_instant(self):
        """Test ShutdownConditionEvaluator with instant mode."""
        test_name = "shutdown_evaluator_instant"
        try:
            from ciris_engine.logic.processors.support.shutdown_condition_evaluator import ShutdownConditionEvaluator
            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, ShutdownBehavior

            evaluator = ShutdownConditionEvaluator()
            config = CognitiveStateBehaviors(
                shutdown=ShutdownBehavior(mode="instant", rationale="Tier 2 ephemeral agent")
            )

            # Should never require consent
            requires, reason = await evaluator.requires_consent(config, context=None)
            assert requires is False
            assert "instant" in reason

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_shutdown_condition_evaluator_conditional(self):
        """Test ShutdownConditionEvaluator with conditional mode."""
        test_name = "shutdown_evaluator_conditional"
        try:
            from unittest.mock import MagicMock

            from ciris_engine.logic.processors.support.shutdown_condition_evaluator import ShutdownConditionEvaluator
            from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors, ShutdownBehavior

            evaluator = ShutdownConditionEvaluator()
            config = CognitiveStateBehaviors(
                shutdown=ShutdownBehavior(
                    mode="conditional",
                    require_consent_when=["active_crisis_response", "pending_professional_referral"],
                    instant_shutdown_otherwise=True,
                    rationale="Partnership model",
                )
            )

            # Test 1: With no context, should require consent (safety default)
            requires, reason = await evaluator.requires_consent(config, context=None)
            assert requires is True, "Should require consent when context is None"
            assert "context" in reason.lower()

            # Test 2: With mock context (no crisis), should not require consent
            mock_context = MagicMock()
            mock_context.current_task = None  # No active task
            requires2, reason2 = await evaluator.requires_consent(config, context=mock_context)
            assert requires2 is False, f"Should not require consent when no conditions triggered: {reason2}"
            assert "instant" in reason2.lower() or "no" in reason2.lower()

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_template_loading_ally(self):
        """Test ally.yaml template loads cognitive_state_behaviors correctly."""
        test_name = "template_loading_ally"
        try:
            from pathlib import Path

            import yaml

            template_path = (
                Path(__file__).parent.parent.parent.parent / "ciris_engine" / "ciris_templates" / "ally.yaml"
            )

            with open(template_path) as f:
                template = yaml.safe_load(f)

            # Verify cognitive_state_behaviors exists
            assert "cognitive_state_behaviors" in template, "ally.yaml missing cognitive_state_behaviors"

            csb = template["cognitive_state_behaviors"]

            # Ally: wakeup disabled, conditional shutdown
            assert csb["wakeup"]["enabled"] is False
            assert csb["wakeup"]["rationale"] is not None
            assert csb["shutdown"]["mode"] == "conditional"
            assert "active_crisis_response" in csb["shutdown"]["require_consent_when"]

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_template_loading_echo(self):
        """Test echo.yaml template loads cognitive_state_behaviors correctly."""
        test_name = "template_loading_echo"
        try:
            from pathlib import Path

            import yaml

            template_path = (
                Path(__file__).parent.parent.parent.parent / "ciris_engine" / "ciris_templates" / "echo.yaml"
            )

            with open(template_path) as f:
                template = yaml.safe_load(f)

            # Verify cognitive_state_behaviors exists
            assert "cognitive_state_behaviors" in template, "echo.yaml missing cognitive_state_behaviors"

            csb = template["cognitive_state_behaviors"]

            # Echo: wakeup enabled, always_consent shutdown
            assert csb["wakeup"]["enabled"] is True
            assert csb["shutdown"]["mode"] == "always_consent"
            assert csb["play"]["enabled"] is False  # Not appropriate for moderation

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))

    async def _test_template_loading_scout(self):
        """Test scout.yaml template loads cognitive_state_behaviors correctly."""
        test_name = "template_loading_scout"
        try:
            from pathlib import Path

            import yaml

            template_path = (
                Path(__file__).parent.parent.parent.parent / "ciris_engine" / "ciris_templates" / "scout.yaml"
            )

            with open(template_path) as f:
                template = yaml.safe_load(f)

            # Verify cognitive_state_behaviors exists
            assert "cognitive_state_behaviors" in template, "scout.yaml missing cognitive_state_behaviors"

            csb = template["cognitive_state_behaviors"]

            # Scout: wakeup disabled, instant shutdown (Tier 2 ephemeral)
            assert csb["wakeup"]["enabled"] is False
            assert csb["shutdown"]["mode"] == "instant"
            assert csb["dream"]["enabled"] is False
            assert csb["state_preservation"]["enabled"] is False

            self._record_result(test_name, True)
        except Exception as e:
            self._record_result(test_name, False, str(e))


def run_state_transition_tests_sync(console: Console = None) -> List[Dict]:
    """Run state transition tests synchronously (for CLI invocation)."""
    if console is None:
        console = Console()

    tests = StateTransitionTests(client=None, console=console)
    return asyncio.run(tests.run())
