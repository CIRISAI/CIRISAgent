"""
Identity management for CIRIS Agent runtime.

Handles loading, creating, and persisting agent identity.
"""

import hashlib
import logging
from pathlib import Path
from typing import Optional

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.config.agent import AgentTemplate
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.core import AgentIdentityRoot, CoreProfile, IdentityMetadata
from ciris_engine.schemas.runtime.enums import HandlerActionType

logger = logging.getLogger(__name__)


class IdentityManager:
    """Manages agent identity lifecycle."""

    def __init__(self, config: EssentialConfig, time_service: TimeServiceProtocol) -> None:
        self.config = config
        self.time_service = time_service
        self.agent_identity: Optional[AgentIdentityRoot] = None

    async def initialize_identity(self) -> AgentIdentityRoot:
        """Initialize agent identity - create from template on first run, load from graph thereafter."""
        # Check if identity exists in graph
        identity_data = await self._get_identity_from_graph()

        if identity_data:
            # Identity exists - load it and use it
            logger.info("Loading existing agent identity from graph")
            self.agent_identity = AgentIdentityRoot.model_validate(identity_data)
        else:
            # First run - use template to create initial identity
            logger.info("No identity found, creating from template (first run only)")

            # Load template ONLY for initial identity creation
            # Use default_template from config as the template name
            template_name = getattr(self.config, "default_template", "default")
            template_path = Path(self.config.template_directory) / f"{template_name}.yaml"
            initial_template = await self._load_template(template_path)

            if not initial_template:
                logger.warning(f"Template '{template_name}' not found, using default")
                default_path = Path(self.config.template_directory) / "default.yaml"
                initial_template = await self._load_template(default_path)

            if not initial_template:
                raise RuntimeError("No template available for initial identity creation")

            # Create identity from template and save to graph
            self.agent_identity = self._create_identity_from_template(initial_template)
            await self._save_identity_to_graph(self.agent_identity)

        return self.agent_identity

    async def _load_template(self, template_path: Path) -> Optional[AgentTemplate]:
        """Load template from file."""
        from ciris_engine.logic.utils.profile_loader import load_template

        return await load_template(template_path)

    async def _get_identity_from_graph(
        self,
    ) -> Optional[dict]:  # NOSONAR: Maintains async consistency in identity chain
        """Retrieve agent identity from the persistence tier."""
        try:
            from ciris_engine.logic.persistence.models.identity import retrieve_agent_identity

            identity = retrieve_agent_identity()
            if identity:
                return identity.model_dump()

        except Exception as e:
            logger.warning(f"Failed to retrieve identity from persistence: {e}")

        return None

    async def _save_identity_to_graph(self, identity: AgentIdentityRoot) -> None:
        """Save agent identity to the persistence tier."""
        try:
            from ciris_engine.logic.persistence.models.identity import store_agent_identity

            success = store_agent_identity(identity, self.time_service)
            if success:
                logger.info("Agent identity saved to persistence tier")
            else:
                raise RuntimeError("Failed to store agent identity")

        except Exception as e:
            logger.error(f"Failed to save identity to persistence: {e}")
            raise

    def _create_identity_from_template(self, template: AgentTemplate) -> AgentIdentityRoot:
        """Create initial identity from template (first run only)."""
        # Generate deterministic identity hash
        identity_string = f"{template.name}:{template.description}:{template.role_description}"
        identity_hash = hashlib.sha256(identity_string.encode()).hexdigest()

        # Extract DSDMA configuration from template
        domain_knowledge = {}
        dsdma_prompt_template = None

        if template.dsdma_kwargs:
            # Extract domain knowledge from typed model
            if template.dsdma_kwargs.domain_specific_knowledge:
                for key, value in template.dsdma_kwargs.domain_specific_knowledge.items():
                    if isinstance(value, dict):
                        # Convert nested dicts to JSON strings
                        import json

                        domain_knowledge[key] = json.dumps(value)
                    else:
                        domain_knowledge[key] = str(value)

            # Extract prompt template
            if template.dsdma_kwargs.prompt_template:
                dsdma_prompt_template = template.dsdma_kwargs.prompt_template

        # Create identity root from template
        return AgentIdentityRoot(
            agent_id=template.name,
            identity_hash=identity_hash,
            core_profile=CoreProfile(
                description=template.description,
                role_description=template.role_description,
                domain_specific_knowledge=domain_knowledge,
                dsdma_prompt_template=dsdma_prompt_template,
                csdma_overrides={
                    k: v
                    for k, v in (template.csdma_overrides.__dict__ if template.csdma_overrides else {}).items()
                    if v is not None
                },
                action_selection_pdma_overrides={
                    k: v
                    for k, v in (
                        template.action_selection_pdma_overrides.__dict__
                        if template.action_selection_pdma_overrides
                        else {}
                    ).items()
                    if v is not None
                },
                last_shutdown_memory=None,
            ),
            identity_metadata=IdentityMetadata(
                created_at=self.time_service.now(),
                last_modified=self.time_service.now(),
                modification_count=0,
                creator_agent_id="system",
                lineage_trace=["system"],
                approval_required=True,
                approved_by=None,
                approval_timestamp=None,
                version=CIRIS_VERSION,  # Use actual CIRIS version
            ),
            permitted_actions=[
                HandlerActionType.OBSERVE,
                HandlerActionType.SPEAK,
                HandlerActionType.TOOL,
                HandlerActionType.MEMORIZE,
                HandlerActionType.RECALL,
                HandlerActionType.FORGET,
                HandlerActionType.DEFER,
                HandlerActionType.REJECT,
                HandlerActionType.PONDER,
                HandlerActionType.TASK_COMPLETE,
            ],
            restricted_capabilities=[
                "identity_change_without_approval",
                "profile_switching",
                "unauthorized_data_access",
            ],
        )

    async def verify_identity_integrity(self) -> bool:
        """Verify identity has been properly loaded."""
        if not self.agent_identity:
            logger.error("No agent identity loaded")
            return False

        # Verify core fields
        required_fields = ["agent_id", "identity_hash", "core_profile"]
        for field in required_fields:
            if not hasattr(self.agent_identity, field) or not getattr(self.agent_identity, field):
                logger.error(f"Identity missing required field: {field}")
                return False

        logger.info("✓ Agent identity verified")
        return True
