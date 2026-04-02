"""OpenClaw SKILL.md parser.

Parses the OpenClaw skill format (YAML frontmatter + markdown instruction body)
into a structured representation that can be converted to a CIRIS adapter.

Supports metadata namespaces: metadata.openclaw, metadata.clawdbot, metadata.clawdis
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class SkillRequirements(BaseModel):
    """Runtime requirements declared by an OpenClaw skill."""

    env: List[str] = Field(default_factory=list, description="Required environment variables")
    bins: List[str] = Field(default_factory=list, description="Required CLI binaries (all must exist)")
    any_bins: List[str] = Field(default_factory=list, description="Alternative binaries (at least one)")
    config: List[str] = Field(default_factory=list, description="Required config file paths")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class SkillInstallSpec(BaseModel):
    """Installation specification for a skill dependency."""

    kind: str = Field(..., description="Install method: brew, node, go, uv, pip, apt, manual")
    formula: Optional[str] = Field(None, description="Package name for brew")
    package: Optional[str] = Field(None, description="Package name for node/pip/apt")
    bins: List[str] = Field(default_factory=list, description="Binaries this install provides")

    model_config = ConfigDict(extra="allow", defer_build=True)


class SkillMetadata(BaseModel):
    """Parsed metadata from the openclaw/clawdbot/clawdis namespace."""

    requires: Optional[SkillRequirements] = None
    primary_env: Optional[str] = Field(None, description="Primary credential env var")
    always: bool = Field(False, description="If true, always active")
    skill_key: Optional[str] = Field(None, description="Override invocation key")
    emoji: Optional[str] = Field(None, description="Display emoji")
    homepage: Optional[str] = Field(None, description="Documentation URL")
    os: List[str] = Field(default_factory=list, description="OS restrictions")
    install: List[SkillInstallSpec] = Field(default_factory=list, description="Install specs")

    model_config = ConfigDict(extra="allow", defer_build=True)


class ParsedSkill(BaseModel):
    """A fully parsed OpenClaw skill."""

    name: str = Field(..., description="Skill identifier (lowercase, hyphenated)")
    description: str = Field("", description="Skill description")
    version: str = Field("1.0.0", description="Skill version")
    metadata: Optional[SkillMetadata] = Field(None, description="Parsed openclaw metadata")
    instructions: str = Field("", description="Markdown instruction body (the AI directive)")
    raw_frontmatter: Dict[str, Any] = Field(default_factory=dict, description="Raw YAML frontmatter")
    supporting_files: Dict[str, str] = Field(
        default_factory=dict, description="Supporting file contents (path -> content)"
    )
    source_url: Optional[str] = Field(None, description="Source URL if imported from ClawHub")

    # Additional frontmatter fields from OpenClaw
    homepage: Optional[str] = Field(None, description="Top-level homepage URL (fallback if not in metadata)")
    user_invocable: bool = Field(True, description="Whether skill is user-invocable")
    disable_model_invocation: bool = Field(False, description="If true, exclude from model prompt")
    command_dispatch: Optional[str] = Field(None, description="Dispatch mode (e.g., 'tool')")
    command_tool: Optional[str] = Field(None, description="Tool name for direct dispatch")
    command_arg_mode: Optional[str] = Field(None, description="Arg mode (e.g., 'raw')")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# Regex for YAML frontmatter: starts with ---, ends with ---
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?\n)---\s*\n?(.*)", re.DOTALL)

# Accepted metadata namespace keys (in priority order)
_METADATA_NAMESPACES = ["openclaw", "clawdbot", "clawdis"]


def _extract_metadata(raw: Dict[str, Any]) -> Optional[SkillMetadata]:
    """Extract metadata from the preferred namespace."""
    meta_block = raw.get("metadata")
    if not isinstance(meta_block, dict):
        return None

    for ns in _METADATA_NAMESPACES:
        if ns in meta_block and isinstance(meta_block[ns], dict):
            ns_data = meta_block[ns]
            # Normalize field names (camelCase -> snake_case)
            normalized: Dict[str, Any] = {}
            for key, value in ns_data.items():
                snake_key = _to_snake_case(key)
                normalized[snake_key] = value

            # Parse requires sub-block
            if "requires" in normalized and isinstance(normalized["requires"], dict):
                req_data = normalized["requires"]
                # Handle anyBins -> any_bins
                if "anyBins" in req_data:
                    req_data["any_bins"] = req_data.pop("anyBins")
                normalized["requires"] = SkillRequirements(**req_data)

            # Parse install specs
            if "install" in normalized and isinstance(normalized["install"], list):
                normalized["install"] = [SkillInstallSpec(**spec) for spec in normalized["install"]]

            return SkillMetadata(**normalized)

    return None


def _to_snake_case(name: str) -> str:
    """Convert camelCase to snake_case."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


class OpenClawSkillParser:
    """Parses OpenClaw SKILL.md files into structured representations."""

    def parse_skill_md(self, content: str, source_url: Optional[str] = None) -> ParsedSkill:
        """Parse a SKILL.md file content string.

        Args:
            content: The raw SKILL.md content (YAML frontmatter + markdown body)
            source_url: Optional source URL for provenance tracking

        Returns:
            ParsedSkill with all fields populated

        Raises:
            ValueError: If the content is invalid or missing required fields
        """
        match = _FRONTMATTER_RE.match(content)
        if match:
            frontmatter_str = match.group(1)
            instructions = match.group(2).strip()
        else:
            # No frontmatter - treat entire content as instructions
            frontmatter_str = ""
            instructions = content.strip()

        # Parse YAML frontmatter
        raw_frontmatter: Dict[str, Any] = {}
        if frontmatter_str:
            try:
                parsed = yaml.safe_load(frontmatter_str)
                if isinstance(parsed, dict):
                    raw_frontmatter = parsed
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML frontmatter: {e}") from e

        # Extract required fields
        name = raw_frontmatter.get("name", "")
        if not name:
            raise ValueError("SKILL.md must have a 'name' field in frontmatter")

        description = raw_frontmatter.get("description", "")
        version = raw_frontmatter.get("version", "1.0.0")
        metadata = _extract_metadata(raw_frontmatter)

        # Resolve homepage: top-level frontmatter takes priority, then metadata
        homepage = raw_frontmatter.get("homepage")
        if not homepage and metadata and metadata.homepage:
            homepage = metadata.homepage

        return ParsedSkill(
            name=name,
            description=description,
            version=str(version),
            metadata=metadata,
            instructions=instructions,
            raw_frontmatter=raw_frontmatter,
            source_url=source_url,
            homepage=homepage,
            user_invocable=raw_frontmatter.get("user-invocable", True),
            disable_model_invocation=raw_frontmatter.get("disable-model-invocation", False),
            command_dispatch=raw_frontmatter.get("command-dispatch"),
            command_tool=raw_frontmatter.get("command-tool"),
            command_arg_mode=raw_frontmatter.get("command-arg-mode"),
        )

    def parse_directory(self, skill_dir: Path, source_url: Optional[str] = None) -> ParsedSkill:
        """Parse a skill from a directory containing SKILL.md and supporting files.

        Args:
            skill_dir: Path to the skill directory
            source_url: Optional source URL

        Returns:
            ParsedSkill including supporting files

        Raises:
            FileNotFoundError: If SKILL.md is not found
            ValueError: If parsing fails
        """
        # Find SKILL.md (case-insensitive)
        skill_md_path = None
        for candidate in ["SKILL.md", "skill.md"]:
            p = skill_dir / candidate
            if p.exists():
                skill_md_path = p
                break

        if not skill_md_path:
            raise FileNotFoundError(f"No SKILL.md found in {skill_dir}")

        content = skill_md_path.read_text(encoding="utf-8")
        parsed = self.parse_skill_md(content, source_url=source_url)

        # Collect supporting text files
        supporting: Dict[str, str] = {}
        _TEXT_EXTENSIONS = {
            ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
            ".js", ".ts", ".py", ".sh", ".bash", ".svg",
        }
        for path in skill_dir.rglob("*"):
            if path == skill_md_path:
                continue
            if path.is_file() and path.suffix.lower() in _TEXT_EXTENSIONS:
                rel = str(path.relative_to(skill_dir))
                # Skip hidden/metadata directories
                if rel.startswith(".clawhub") or rel.startswith(".git"):
                    continue
                try:
                    supporting[rel] = path.read_text(encoding="utf-8")
                except (UnicodeDecodeError, OSError):
                    logger.debug(f"Skipping non-text file: {rel}")

        parsed.supporting_files = supporting
        return parsed
