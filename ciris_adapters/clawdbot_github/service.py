"""
Github Tool Service for CIRIS.

Converted from Clawdbot skill: github
Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries.

This service provides skill-based guidance for using external tools/CLIs.
The detailed instructions from the original SKILL.md are embedded in the
ToolInfo.documentation field for DMA-aware tool selection.
"""

import logging
from typing import Any, Dict, List, Optional

from ciris_adapters.skill_base import SkillToolService
from ciris_engine.schemas.adapters.tools import (
    BinaryRequirement,
    InstallStep,
    ToolDMAGuidance,
    ToolDocumentation,
    ToolInfo,
    ToolParameterSchema,
    ToolRequirements,
)

logger = logging.getLogger(__name__)


class GithubToolService(SkillToolService):
    """
    Github tool service providing skill-based guidance.

    Original skill: github
    Description: Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries.
    """

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="github",
            description="""Interact with GitHub using the `gh` CLI. Use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues, PRs, CI runs, and advanced queries.""",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "command": {
                        "type": "string",
                        "description": "The command to execute (will be validated against skill guidance)",
                    },
                    "working_dir": {
                        "type": "string",
                        "description": "Working directory for command execution (optional)",
                    },
                },
                required=["command"],
            ),
            category="skill",
            when_to_use="""When you need to interact with github using the `gh` cli. use `gh issue`, `gh pr`, `gh run`, and `gh api` for issues,...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="gh"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install GitHub CLI (brew)",
                    formula="gh",
                    provides_binaries=["gh"],
                    platforms=["darwin"],
                ),
                InstallStep(
                    id="apt",
                    kind="apt",
                    label="Install GitHub CLI (apt)",
                    package="gh",
                    provides_binaries=["gh"],
                    platforms=["linux"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Use the `gh` CLI to interact with GitHub. Always specify `--repo owner/repo` when not in a git directory, or use URLs directly.",
                detailed_instructions="""# GitHub Skill\n\nUse the `gh` CLI to interact with GitHub. Always specify `--repo owner/repo` when not in a git directory, or use URLs directly.\n\n## Pull Requests\n\nCheck CI status on a PR:\n```bash\ngh pr checks 55 --repo owner/repo\n```\n\nList recent workflow runs:\n```bash\ngh run list --repo owner/repo --limit 10\n```\n\nView a run and see which steps failed:\n```bash\ngh run view <run-id> --repo owner/repo\n```\n\nView logs for failed steps only:\n```bash\ngh run view <run-id> --repo owner/repo --log-failed\n```\n\n## API for Advanced Queries\n\nThe `gh api` command is useful for accessing data not available through other subcommands.\n\nGet PR with specific fields:\n```bash\ngh api repos/owner/repo/pulls/55 --jq '.title, .state, .user.login'\n```\n\n## JSON Output\n\nMost commands support `--json` for structured output.  You can use `--jq` to filter:\n\n```bash\ngh issue list --repo owner/repo --json number,title --jq '.[] | \"\\(.number): \\(.title)\"'\n```""",
                examples=[],
                gotchas=[],
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "github", "cli"],
            version="1.0.0",
        )
