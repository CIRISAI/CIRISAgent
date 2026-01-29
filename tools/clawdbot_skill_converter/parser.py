"""
SKILL.md Parser for Clawdbot skills.

Parses the YAML frontmatter and markdown body from Clawdbot SKILL.md files.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class InstallSpec:
    """Installation specification for a skill dependency."""

    id: str
    kind: str  # brew, apt, pip, npm, manual, winget, choco
    label: str
    formula: Optional[str] = None  # For brew
    package: Optional[str] = None  # For apt/pip/npm
    command: Optional[str] = None  # For manual
    url: Optional[str] = None
    binaries: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)


@dataclass
class SkillRequirements:
    """Requirements for a skill to function."""

    binaries: List[str] = field(default_factory=list)
    any_binaries: List[str] = field(default_factory=list)
    env_vars: List[str] = field(default_factory=list)
    config_keys: List[str] = field(default_factory=list)
    platforms: List[str] = field(default_factory=list)
    primary_env_var: Optional[str] = None


@dataclass
class ParsedSkill:
    """Parsed skill from a SKILL.md file."""

    # Core identity
    name: str
    description: str
    source_path: Path

    # Display
    emoji: Optional[str] = None
    homepage: Optional[str] = None

    # Requirements
    requirements: SkillRequirements = field(default_factory=SkillRequirements)

    # Installation
    install_steps: List[InstallSpec] = field(default_factory=list)

    # Documentation
    detailed_instructions: str = ""

    # Raw metadata for extension
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_adapter_name(self) -> str:
        """Convert skill name to valid Python adapter name."""
        # Replace hyphens with underscores, remove invalid chars
        name = re.sub(r"[^a-zA-Z0-9_]", "_", self.name)
        name = re.sub(r"_+", "_", name)  # Collapse multiple underscores
        name = name.strip("_").lower()
        # Prefix with 'clawdbot_' to indicate source
        return f"clawdbot_{name}"

    def to_tool_name(self) -> str:
        """Convert skill name to tool name format."""
        return self.name.replace("-", "_").lower()

    def to_class_name(self) -> str:
        """Convert skill name to PascalCase class name."""
        # Handle names starting with numbers
        name = self.name
        if name and name[0].isdigit():
            # Prefix with word for the number
            number_words = {
                "1": "One",
                "2": "Two",
                "3": "Three",
                "4": "Four",
                "5": "Five",
                "6": "Six",
                "7": "Seven",
                "8": "Eight",
                "9": "Nine",
                "0": "Zero",
            }
            name = number_words.get(name[0], "X") + name[1:]

        # Split on hyphens and underscores
        parts = re.split(r"[-_]", name)
        # Capitalize each part
        return "".join(part.capitalize() for part in parts)


class SkillParser:
    """Parser for Clawdbot SKILL.md files."""

    # Regex to extract YAML frontmatter
    FRONTMATTER_PATTERN = re.compile(
        r"^---\s*\n(.*?)\n---\s*\n(.*)$",
        re.DOTALL | re.MULTILINE,
    )

    def parse_file(self, skill_path: Path) -> ParsedSkill:
        """Parse a SKILL.md file.

        Args:
            skill_path: Path to the SKILL.md file

        Returns:
            ParsedSkill with extracted information

        Raises:
            ValueError: If file format is invalid
        """
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill file not found: {skill_path}")

        content = skill_path.read_text(encoding="utf-8")
        return self.parse_content(content, skill_path)

    def parse_content(self, content: str, source_path: Path) -> ParsedSkill:
        """Parse SKILL.md content.

        Args:
            content: Raw file content
            source_path: Path to source file (for reference)

        Returns:
            ParsedSkill with extracted information
        """
        # Extract frontmatter and body
        match = self.FRONTMATTER_PATTERN.match(content)
        if not match:
            raise ValueError(f"Invalid SKILL.md format - missing YAML frontmatter: {source_path}")

        frontmatter_yaml = match.group(1)
        body = match.group(2).strip()

        # Parse YAML frontmatter
        try:
            frontmatter = yaml.safe_load(frontmatter_yaml) or {}
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in frontmatter: {e}") from e

        # Extract core fields
        name = frontmatter.get("name", source_path.parent.name)
        description = frontmatter.get("description", "")
        homepage = frontmatter.get("homepage")

        # Extract moltbot metadata
        metadata = frontmatter.get("metadata", {}).get("moltbot", {})
        emoji = metadata.get("emoji")
        platforms = metadata.get("os", [])
        primary_env_var = metadata.get("primaryEnv")

        # Extract requirements
        requires = metadata.get("requires", {})
        requirements = SkillRequirements(
            binaries=requires.get("bins", []),
            any_binaries=requires.get("anyBins", []),
            env_vars=requires.get("env", []),
            config_keys=requires.get("config", []),
            platforms=platforms,
            primary_env_var=primary_env_var,
        )

        # Extract install steps
        install_steps = []
        for step in metadata.get("install", []):
            install_steps.append(
                InstallSpec(
                    id=step.get("id", "unknown"),
                    kind=step.get("kind", "manual"),
                    label=step.get("label", "Install"),
                    formula=step.get("formula"),
                    package=step.get("package"),
                    command=step.get("command"),
                    url=step.get("url"),
                    binaries=step.get("bins", []),
                    platforms=step.get("platforms", []),
                )
            )

        return ParsedSkill(
            name=name,
            description=description,
            source_path=source_path,
            emoji=emoji,
            homepage=homepage,
            requirements=requirements,
            install_steps=install_steps,
            detailed_instructions=body,
            raw_metadata=metadata,
        )

    def parse_directory(self, skills_dir: Path) -> List[ParsedSkill]:
        """Parse all SKILL.md files in a directory.

        Args:
            skills_dir: Directory containing skill subdirectories

        Returns:
            List of ParsedSkill objects
        """
        skills = []

        for skill_dir in skills_dir.iterdir():
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue

            try:
                skill = self.parse_file(skill_file)
                skills.append(skill)
            except (ValueError, FileNotFoundError) as e:
                print(f"Warning: Skipping {skill_dir.name}: {e}")

        return skills
