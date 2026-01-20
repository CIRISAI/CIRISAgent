"""
Identity management for CIRIS Agent runtime.

Handles loading, creating, and persisting agent identity.
"""

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.config.agent import AgentTemplate
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.core import AgentIdentityRoot, CoreProfile, IdentityMetadata
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class IdentityManager:
    """Manages agent identity lifecycle."""

    def __init__(self, config: EssentialConfig, time_service: TimeServiceProtocol) -> None:
        self.config = config
        self.time_service = time_service
        self.agent_identity: Optional[AgentIdentityRoot] = None
        # NOTE: agent_template is ONLY set during first-run seeding, then never used again
        # All operational config (including tickets) should come from the graph after seeding
        self.agent_template: Optional[AgentTemplate] = None

    async def initialize_identity(self) -> AgentIdentityRoot:
        """Initialize agent identity - create from template on first run, load from graph thereafter."""
        # Check if identity exists in graph
        identity_data = await self._get_identity_from_graph()

        if identity_data:
            # Identity exists - load it from graph
            # IMPORTANT: Template is COMPLETELY IGNORED when identity already exists
            # All config (identity, operational, tickets, etc.) comes from the graph
            logger.info("Loading existing agent identity from graph (template ignored entirely)")
            self.agent_identity = AgentIdentityRoot.model_validate(identity_data)
            # self.agent_template remains None - template is not used after first run
        else:
            # First run - use template to create initial identity
            logger.info("No identity found, creating from template (first run only)")

            # Load template ONLY for initial identity creation
            # Use default_template from config as the template name
            from ciris_engine.logic.utils.path_resolution import find_template_file

            template_name = getattr(self.config, "default_template", "default")
            template_path = find_template_file(template_name)
            if template_path:
                initial_template = await self._load_template(template_path)
            else:
                initial_template = None

            if not initial_template:
                logger.warning(f"Template '{template_name}' not found, using default")
                default_path = find_template_file("default")
                if default_path:
                    initial_template = await self._load_template(default_path)

            if not initial_template:
                raise RuntimeError("No template available for initial identity creation")

            # Store template temporarily - only used during this seeding process
            # After seeding, all config comes from graph
            # NOTE: Tickets config will be migrated to graph by ciris_runtime._migrate_tickets_config_to_graph()
            self.agent_template = initial_template

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
    ) -> Optional[JSONDict]:  # NOSONAR: Maintains async consistency in identity chain
        """Retrieve agent identity from the persistence tier."""
        try:
            from ciris_engine.logic.config import get_sqlite_db_full_path
            from ciris_engine.logic.persistence.models.identity import retrieve_agent_identity

            # Get the correct db path from our config
            db_path = get_sqlite_db_full_path(self.config)
            identity = retrieve_agent_identity(db_path=db_path)
            if identity:
                return identity.model_dump()

        except Exception as e:
            logger.warning(f"Failed to retrieve identity from persistence: {e}")

        return None

    async def _save_identity_to_graph(self, identity: AgentIdentityRoot) -> None:
        """Save agent identity to the persistence tier."""
        try:
            from ciris_engine.logic.config import get_sqlite_db_full_path
            from ciris_engine.logic.persistence.models.identity import store_agent_identity

            # Get the correct db path from our config
            db_path = get_sqlite_db_full_path(self.config)
            success = store_agent_identity(identity, self.time_service, db_path=db_path)
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

    async def refresh_identity_from_template(
        self,
        template_name: str,
        updated_by: str = "admin",
    ) -> bool:
        """
        Refresh existing identity from template (admin operation).

        Used for major template updates. Requires explicit --identity-update flag.
        Uses update_agent_identity() for proper tracking and signing.

        Args:
            template_name: Name of the template to load
            updated_by: ID of the admin/system performing the update

        Returns:
            True if update successful, False otherwise
        """
        from ciris_engine.logic.config import get_sqlite_db_full_path
        from ciris_engine.logic.persistence.models.identity import update_agent_identity
        from ciris_engine.logic.utils.path_resolution import find_template_file

        logger.info(f"Refreshing identity from template '{template_name}' (admin: {updated_by})")

        # 1. Get current identity from graph (must exist)
        current_identity_data = await self._get_identity_from_graph()
        if not current_identity_data:
            logger.error("Cannot refresh identity - no existing identity found in graph")
            return False

        current_identity = AgentIdentityRoot.model_validate(current_identity_data)
        logger.info(
            f"Found existing identity: {current_identity.agent_id} (version: {current_identity.identity_metadata.modification_count})"
        )

        # 2. Load the template
        template_path = find_template_file(template_name)
        if not template_path:
            logger.error(f"Template '{template_name}' not found")
            return False

        template = await self._load_template(template_path)
        if not template:
            logger.error(f"Failed to load template '{template_name}'")
            return False

        logger.info(f"Loaded template: {template.name}")

        # 3. Create updated identity preserving creation metadata
        updated_identity = self._create_updated_identity_from_template(template, current_identity)

        # 4. Call update_agent_identity for proper tracking
        db_path = get_sqlite_db_full_path(self.config)
        success = update_agent_identity(
            updated_identity,
            updated_by=updated_by,
            time_service=self.time_service,
            db_path=db_path,
        )

        if success:
            self.agent_identity = updated_identity
            self.agent_template = template  # Store for config migration if needed
            logger.info(
                f"Identity refreshed from template '{template_name}' "
                f"(new version: {updated_identity.identity_metadata.modification_count + 1})"
            )
        else:
            logger.error("Failed to update identity in graph")

        return success

    def _extract_dsdma_config(self, template: AgentTemplate) -> tuple[Dict[str, str], Optional[str]]:
        """Extract DSDMA configuration from template."""
        import json

        domain_knowledge: Dict[str, str] = {}
        dsdma_prompt_template = None

        if not template.dsdma_kwargs:
            return domain_knowledge, dsdma_prompt_template

        if template.dsdma_kwargs.domain_specific_knowledge:
            for key, value in template.dsdma_kwargs.domain_specific_knowledge.items():
                domain_knowledge[key] = json.dumps(value) if isinstance(value, dict) else str(value)

        if template.dsdma_kwargs.prompt_template:
            dsdma_prompt_template = template.dsdma_kwargs.prompt_template

        return domain_knowledge, dsdma_prompt_template

    def _build_overrides_dict(self, overrides: Optional[Any]) -> Dict[str, Any]:
        """Build filtered overrides dict from optional overrides object."""
        if not overrides:
            return {}
        return {k: v for k, v in overrides.__dict__.items() if v is not None}

    def _get_default_permitted_actions(self) -> list[HandlerActionType]:
        """Return default permitted actions for an agent."""
        return [
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
        ]

    def _create_updated_identity_from_template(
        self,
        template: AgentTemplate,
        current_identity: AgentIdentityRoot,
    ) -> AgentIdentityRoot:
        """Create updated identity from template, preserving creation metadata."""
        # Generate new identity hash
        identity_string = f"{template.name}:{template.description}:{template.role_description}"
        identity_hash = hashlib.sha256(identity_string.encode()).hexdigest()

        # Extract DSDMA configuration from template
        domain_knowledge, dsdma_prompt_template = self._extract_dsdma_config(template)

        # Preserve lineage and add template refresh marker
        lineage = list(current_identity.identity_metadata.lineage_trace or [])
        lineage.append(f"template_refresh:{template.name}")

        # Build overrides using helper
        csdma_overrides = self._build_overrides_dict(template.csdma_overrides)
        action_pdma_overrides = self._build_overrides_dict(template.action_selection_pdma_overrides)

        # Build permitted actions list
        actions_source = template.permitted_actions or self._get_default_permitted_actions()
        permitted_actions = [
            HandlerActionType(action) if isinstance(action, str) else action
            for action in actions_source
        ]

        # Create updated identity
        return AgentIdentityRoot(
            agent_id=template.name,
            identity_hash=identity_hash,
            core_profile=CoreProfile(
                description=template.description,
                role_description=template.role_description,
                domain_specific_knowledge=domain_knowledge,
                dsdma_prompt_template=dsdma_prompt_template,
                csdma_overrides=csdma_overrides,
                action_selection_pdma_overrides=action_pdma_overrides,
                last_shutdown_memory=current_identity.core_profile.last_shutdown_memory,
            ),
            identity_metadata=IdentityMetadata(
                created_at=current_identity.identity_metadata.created_at,
                creator_agent_id=current_identity.identity_metadata.creator_agent_id,
                last_modified=self.time_service.now(),
                modification_count=current_identity.identity_metadata.modification_count + 1,
                lineage_trace=lineage,
                approval_required=current_identity.identity_metadata.approval_required,
                approved_by=current_identity.identity_metadata.approved_by,
                approval_timestamp=current_identity.identity_metadata.approval_timestamp,
                version=CIRIS_VERSION,
            ),
            permitted_actions=permitted_actions,
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
