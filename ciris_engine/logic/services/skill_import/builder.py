"""Skill Builder service.

HyperCard-inspired skill creation: every skill is a stack of schema cards.
Each card is a Pydantic model section that can be rendered as a form (card mode)
or edited as raw JSON (edit mode).

Cards:
  1. identity  - Name, description, emoji, version, homepage
  2. tools     - Tool definitions (name, description, parameters)
  3. requires  - Environment vars, binaries, platforms
  4. instruct  - The AI directive (what the skill tells the agent to do)
  5. behavior  - DMA guidance, approval requirements, context enrichment
  6. install   - Installation steps for dependencies

All data is stored as a SkillDraft (serializable JSON) that can be
converted to a full CIRIS adapter at any time.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.adapters.tools import (
    InstallStep,
    ToolDMAGuidance,
    ToolDocumentation,
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
)

logger = logging.getLogger(__name__)

# Directory for skill drafts
_DRAFTS_DIR = Path.home() / ".ciris" / "skill_drafts"


# ============================================================================
# Card Schemas - Each card is a section of the skill
# ============================================================================


class IdentityCard(BaseModel):
    """Card 1: Skill identity."""

    name: str = Field("", description="Skill name (lowercase, hyphenated, e.g. 'my-cool-skill')")
    description: str = Field("", description="What does this skill do? One sentence.")
    version: str = Field("1.0.0", description="Skill version (semver)")
    emoji: Optional[str] = Field(None, description="Display emoji (e.g. '🔧')")
    homepage: Optional[str] = Field(None, description="Documentation or homepage URL")
    author: str = Field("", description="Who made this skill?")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolParameter(BaseModel):
    """A single parameter for a tool."""

    name: str = Field(..., description="Parameter name")
    type: str = Field("string", description="Type: string, integer, number, boolean, object, array")
    description: str = Field("", description="What is this parameter for?")
    required: bool = Field(False, description="Is this parameter required?")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class ToolCard(BaseModel):
    """A single tool definition within the skill."""

    name: str = Field("", description="Tool name (e.g. 'search', 'create-task')")
    description: str = Field("", description="What does this tool do?")
    parameters: List[ToolParameter] = Field(default_factory=list, description="Tool parameters")
    when_to_use: Optional[str] = Field(None, description="When should the agent use this tool?")
    category: str = Field("general", description="Tool category")
    cost: float = Field(0.0, description="Cost to execute (0 = free)")

    model_config = ConfigDict(extra="forbid", defer_build=True)

    def to_tool_parameter_schema(self) -> ToolParameterSchema:
        """Convert to CIRIS ToolParameterSchema."""
        properties: Dict[str, Any] = {}
        required: List[str] = []
        for p in self.parameters:
            properties[p.name] = {"type": p.type, "description": p.description}
            if p.required:
                required.append(p.name)
        return ToolParameterSchema(type="object", properties=properties, required=required)


class ToolsCard(BaseModel):
    """Card 2: Tool definitions."""

    tools: List[ToolCard] = Field(default_factory=list, description="Tools this skill provides")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class RequiresCard(BaseModel):
    """Card 3: Runtime requirements."""

    env_vars: List[str] = Field(
        default_factory=list, description="Required environment variables (e.g. 'TODOIST_API_KEY')"
    )
    binaries: List[str] = Field(default_factory=list, description="Required CLI binaries (e.g. 'curl', 'jq')")
    platforms: List[str] = Field(
        default_factory=list, description="Supported platforms (empty = all). Options: linux, darwin, win32"
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class InstructCard(BaseModel):
    """Card 4: AI instructions."""

    instructions: str = Field(
        "",
        description="What should the agent do with this skill? "
        "Write clear step-by-step instructions. "
        "This is the 'brain' of the skill - it tells the AI how to behave.",
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class BehaviorCard(BaseModel):
    """Card 5: Agent behavior configuration."""

    requires_approval: bool = Field(
        True,
        description="Require human approval before executing? "
        "Recommended for skills that modify data or cost money.",
    )
    min_confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Minimum confidence (0-1) before the agent will use this skill. "
        "Higher = agent must be more sure this is the right tool.",
    )
    always_active: bool = Field(
        False,
        description="Always inject this skill's context into the agent's prompt? "
        "Use for skills that provide situational awareness.",
    )
    ethical_considerations: Optional[str] = Field(
        None, description="Any ethical concerns the agent should consider before using this skill?"
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class InstallCard(BaseModel):
    """Card 6: Installation steps for dependencies."""

    steps: List[InstallStep] = Field(default_factory=list, description="How to install missing dependencies")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# SkillDraft - The complete skill as a stack of cards
# ============================================================================


class SkillDraft(BaseModel):
    """A complete skill draft - a stack of cards that can be edited and converted to an adapter."""

    draft_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique draft ID")
    identity: IdentityCard = Field(default_factory=IdentityCard)
    tools: ToolsCard = Field(default_factory=ToolsCard)
    requires: RequiresCard = Field(default_factory=RequiresCard)
    instruct: InstructCard = Field(default_factory=InstructCard)
    behavior: BehaviorCard = Field(default_factory=BehaviorCard)
    install: InstallCard = Field(default_factory=InstallCard)

    # Import provenance
    imported_from: Optional[str] = Field(None, description="Source: 'openclaw', 'manual', etc.")
    source_url: Optional[str] = Field(None, description="Original source URL")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ============================================================================
# Card Schema Introspection
# ============================================================================

# Card metadata for the UI
CARD_DEFINITIONS = [
    {
        "id": "identity",
        "title": "Identity",
        "subtitle": "Name & describe your skill",
        "emoji": "🏷️",
        "schema_class": "IdentityCard",
    },
    {"id": "tools", "title": "Tools", "subtitle": "What can it do?", "emoji": "🔧", "schema_class": "ToolsCard"},
    {
        "id": "requires",
        "title": "Requirements",
        "subtitle": "What does it need?",
        "emoji": "📦",
        "schema_class": "RequiresCard",
    },
    {
        "id": "instruct",
        "title": "Instructions",
        "subtitle": "How should the agent behave?",
        "emoji": "📝",
        "schema_class": "InstructCard",
    },
    {
        "id": "behavior",
        "title": "Behavior",
        "subtitle": "Safety & approval settings",
        "emoji": "🛡️",
        "schema_class": "BehaviorCard",
    },
    {
        "id": "install",
        "title": "Install",
        "subtitle": "Dependency installation",
        "emoji": "⚙️",
        "schema_class": "InstallCard",
    },
]

_CARD_CLASSES: Dict[str, type[BaseModel]] = {
    "identity": IdentityCard,
    "tools": ToolsCard,
    "requires": RequiresCard,
    "instruct": InstructCard,
    "behavior": BehaviorCard,
    "install": InstallCard,
}


def get_card_schema(card_id: str) -> Dict[str, Any]:
    """Get the JSON Schema for a card, suitable for rendering as a form.

    Returns the full Pydantic JSON Schema with field descriptions,
    types, defaults, and constraints - everything the UI needs to
    render a form or a raw JSON editor.
    """
    cls = _CARD_CLASSES.get(card_id)
    if not cls:
        raise ValueError(f"Unknown card: {card_id}")
    return cls.model_json_schema()


def get_all_card_schemas() -> Dict[str, Any]:
    """Get schemas for all cards plus card metadata.

    This is the single API call the UI needs to render the entire
    skill builder. Returns card metadata (title, subtitle, emoji)
    plus the JSON Schema for each card.
    """
    cards = []
    for card_def in CARD_DEFINITIONS:
        card_id = card_def["id"]
        schema = get_card_schema(card_id)
        cards.append(
            {
                **card_def,
                "schema": schema,
            }
        )
    return {"cards": cards, "draft_schema": SkillDraft.model_json_schema()}


# ============================================================================
# SkillBuilder - Creates, validates, and converts skill drafts
# ============================================================================


class SkillBuilder:
    """Creates and manages skill drafts.

    The builder is the bridge between the card-based UI and the
    adapter converter. It handles:
    - Creating new drafts (blank or from OpenClaw import)
    - Validating card data against schemas
    - Saving/loading drafts to disk
    - Converting drafts to full CIRIS adapters
    """

    def __init__(self, drafts_dir: Optional[Path] = None):
        self.drafts_dir = drafts_dir or _DRAFTS_DIR

    def create_draft(self) -> SkillDraft:
        """Create a new blank skill draft."""
        return SkillDraft()

    def create_from_openclaw(self, skill_md_content: str, source_url: Optional[str] = None) -> SkillDraft:
        """Create a draft from an OpenClaw SKILL.md.

        Parses the skill and maps it onto cards. The user can then
        review and edit each card before creating the adapter.
        """
        from .parser import OpenClawSkillParser

        parser = OpenClawSkillParser()
        parsed = parser.parse_skill_md(skill_md_content, source_url=source_url)

        # Map parsed fields to cards
        identity = IdentityCard(
            name=parsed.name,
            description=parsed.description,
            version=parsed.version,
            emoji=parsed.metadata.emoji if parsed.metadata else None,
            homepage=parsed.homepage,
            author="OpenClaw Import",
        )

        # Build tool cards from the skill
        tool_cards: List[ToolCard] = []
        tool_cards.append(
            ToolCard(
                name=parsed.name,
                description=parsed.description or f"Execute the {parsed.name} skill",
                parameters=[
                    ToolParameter(name="input", type="string", description="Input to pass to the skill", required=True),
                    ToolParameter(name="args", type="object", description="Additional arguments", required=False),
                ],
                when_to_use=parsed.description,
            )
        )

        tools = ToolsCard(tools=tool_cards)

        # Requirements
        requires = RequiresCard()
        if parsed.metadata and parsed.metadata.requires:
            requires.env_vars = parsed.metadata.requires.env
            requires.binaries = parsed.metadata.requires.bins
        if parsed.metadata and parsed.metadata.os:
            requires.platforms = parsed.metadata.os

        # Instructions
        instruct = InstructCard(instructions=parsed.instructions)

        # Behavior - default to requiring approval for imported skills
        behavior = BehaviorCard(
            requires_approval=True,
            always_active=bool(parsed.metadata and parsed.metadata.always),
        )

        # Install steps
        install = InstallCard()
        if parsed.metadata and parsed.metadata.install:
            from .converter import _build_install_steps

            step_dicts = _build_install_steps(parsed.metadata.install)
            install.steps = [InstallStep(**s) for s in step_dicts]

        return SkillDraft(
            identity=identity,
            tools=tools,
            requires=requires,
            instruct=instruct,
            behavior=behavior,
            install=install,
            imported_from="openclaw",
            source_url=source_url,
        )

    def validate_card(self, card_id: str, data: Dict[str, Any]) -> List[str]:
        """Validate card data against its schema.

        Returns a list of validation errors (empty = valid).
        """
        cls = _CARD_CLASSES.get(card_id)
        if not cls:
            return [f"Unknown card: {card_id}"]

        try:
            cls.model_validate(data)
            return []
        except Exception as e:
            return [str(e)]

    def validate_draft(self, draft: SkillDraft) -> List[str]:
        """Validate the entire draft for completeness."""
        errors = []

        if not draft.identity.name:
            errors.append("Skill name is required")
        elif not re.match(r"^[a-z0-9][a-z0-9-]*$", draft.identity.name):
            errors.append("Skill name must be lowercase alphanumeric with hyphens")

        if not draft.identity.description:
            errors.append("Description is required")

        if not draft.tools.tools:
            errors.append("At least one tool is required")

        for i, tool in enumerate(draft.tools.tools):
            if not tool.name:
                errors.append(f"Tool {i + 1}: name is required")
            if not tool.description:
                errors.append(f"Tool {i + 1}: description is required")

        return errors

    def save_draft(self, draft: SkillDraft) -> Path:
        """Save a draft to disk as JSON."""
        self.drafts_dir.mkdir(parents=True, exist_ok=True)
        path = self.drafts_dir / f"{draft.draft_id}.json"
        path.write_text(draft.model_dump_json(indent=2), encoding="utf-8")
        logger.info(f"Saved draft {draft.draft_id} to {path}")
        return path

    def load_draft(self, draft_id: str) -> Optional[SkillDraft]:
        """Load a draft from disk."""
        path = self.drafts_dir / f"{draft_id}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return SkillDraft.model_validate(data)
        except Exception as e:
            logger.error(f"Failed to load draft {draft_id}: {e}")
            return None

    def list_drafts(self) -> List[SkillDraft]:
        """List all saved drafts."""
        if not self.drafts_dir.exists():
            return []
        drafts = []
        for path in self.drafts_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                drafts.append(SkillDraft.model_validate(data))
            except Exception as e:
                logger.debug(f"Skipping invalid draft {path}: {e}")
        return drafts

    def delete_draft(self, draft_id: str) -> bool:
        """Delete a draft from disk."""
        path = self.drafts_dir / f"{draft_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def build_adapter(self, draft: SkillDraft) -> Path:
        """Convert a draft to a full CIRIS adapter directory.

        This is the "Create" step - takes the validated draft and
        generates all the adapter files.
        """
        from .converter import SkillToAdapterConverter
        from .parser import ParsedSkill, SkillInstallSpec, SkillMetadata, SkillRequirements

        # Validate first
        errors = self.validate_draft(draft)
        if errors:
            raise ValueError(f"Draft has validation errors: {'; '.join(errors)}")

        # Convert draft cards back to ParsedSkill for the converter
        metadata = SkillMetadata(
            requires=(
                SkillRequirements(
                    env=draft.requires.env_vars,
                    bins=draft.requires.binaries,
                )
                if (draft.requires.env_vars or draft.requires.binaries)
                else None
            ),
            primary_env=draft.requires.env_vars[0] if draft.requires.env_vars else None,
            always=draft.behavior.always_active,
            emoji=draft.identity.emoji,
            homepage=draft.identity.homepage,
            os=draft.requires.platforms,
            skill_key=None,
            install=[
                SkillInstallSpec(
                    kind=step.kind,
                    formula=step.formula,
                    package=step.package,
                    bins=step.provides_binaries,
                )
                for step in draft.install.steps
            ],
        )

        parsed = ParsedSkill(
            name=draft.identity.name,
            description=draft.identity.description,
            version=draft.identity.version,
            metadata=metadata,
            instructions=draft.instruct.instructions,
            homepage=draft.identity.homepage,
            source_url=draft.source_url,
            disable_model_invocation=False,
        )

        converter = SkillToAdapterConverter()
        adapter_path = converter.convert(parsed)

        # Overlay DMA guidance from behavior card onto generated services.py
        # (The converter handles basic fields; we patch in the full guidance)
        self._patch_dma_guidance(adapter_path, draft)

        logger.info(f"Built adapter from draft '{draft.identity.name}' at {adapter_path}")
        return adapter_path

    def _patch_dma_guidance(self, adapter_path: Path, draft: SkillDraft) -> None:
        """Patch DMA guidance into the generated services.py.

        Adds requires_approval, min_confidence, and ethical_considerations
        from the behavior card.
        """
        services_path = adapter_path / "services.py"
        if not services_path.exists():
            return

        content = services_path.read_text(encoding="utf-8")

        # Add DMA guidance import if not present
        if "ToolDMAGuidance" not in content:
            content = content.replace(
                "from ciris_engine.schemas.adapters.tools import (",
                "from ciris_engine.schemas.adapters.tools import (\n    ToolDMAGuidance,",
            )

        # Add dma_guidance to the main tool definition
        guidance_block = (
            f"dma_guidance=ToolDMAGuidance(\n"
            f"                            requires_approval={draft.behavior.requires_approval},\n"
            f"                            min_confidence={draft.behavior.min_confidence},\n"
            f"                            ethical_considerations={repr(draft.behavior.ethical_considerations)},\n"
            f"                        ),"
        )

        # Insert before the closing paren of the first ToolInfo
        # Find the pattern: tags=[...], and insert after it
        tag_pattern = r"(tags=\[.*?\],)"
        match = re.search(tag_pattern, content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + "\n                        " + guidance_block + content[insert_pos:]
            services_path.write_text(content, encoding="utf-8")
