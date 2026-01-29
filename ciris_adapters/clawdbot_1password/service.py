"""
Onepassword Tool Service for CIRIS.

Converted from Clawdbot skill: 1password
Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.

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


class OnepasswordToolService(SkillToolService):
    """
    Onepassword tool service providing skill-based guidance.

    Original skill: 1password
    Description: Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.
    """

    def _build_tool_info(self) -> ToolInfo:
        """Build the ToolInfo with all skill documentation."""
        return ToolInfo(
            name="1password",
            description="""Set up and use 1Password CLI (op). Use when installing the CLI, enabling desktop app integration, signing in (single or multi-account), or reading/injecting/running secrets via op.""",
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
            when_to_use="""When you need to set up and use 1password cli (op). use when installing the cli, enabling desktop app integration, si...""",
            requirements=ToolRequirements(
                binaries=[
                    BinaryRequirement(name="op"),
                ],
            ),
            install_steps=[
                InstallStep(
                    id="brew",
                    kind="brew",
                    label="Install 1Password CLI (brew)",
                    formula="1password-cli",
                    provides_binaries=["op"],
                    platforms=["darwin"],
                ),
            ],
            documentation=ToolDocumentation(
                quick_start="Follow the official CLI get-started steps. Don't guess install commands.",
                detailed_instructions="""# 1Password CLI\n\nFollow the official CLI get-started steps. Don't guess install commands.\n\n## References\n\n- `references/get-started.md` (install + app integration + sign-in flow)\n- `references/cli-examples.md` (real `op` examples)\n\n## Workflow\n\n1. Check OS + shell.\n2. Verify CLI present: `op --version`.\n3. Confirm desktop app integration is enabled (per get-started) and the app is unlocked.\n4. REQUIRED: create a fresh tmux session for all `op` commands (no direct `op` calls outside tmux).\n5. Sign in / authorize inside tmux: `op signin` (expect app prompt).\n6. Verify access inside tmux: `op whoami` (must succeed before any secret read).\n7. If multiple accounts: use `--account` or `OP_ACCOUNT`.\n\n## REQUIRED tmux session (T-Max)\n\nThe shell tool uses a fresh TTY per command. To avoid re-prompts and failures, always run `op` inside a dedicated tmux session with a fresh socket/session name.\n\nExample (see `tmux` skill for socket conventions, do not reuse old session names):\n\n```bash\nSOCKET_DIR=\"${CLAWDBOT_TMUX_SOCKET_DIR:-${TMPDIR:-/tmp}/moltbot-tmux-sockets}\"\nmkdir -p \"$SOCKET_DIR\"\nSOCKET=\"$SOCKET_DIR/moltbot-op.sock\"\nSESSION=\"op-auth-$(date +%Y%m%d-%H%M%S)\"\n\ntmux -S \"$SOCKET\" new -d -s \"$SESSION\" -n shell\ntmux -S \"$SOCKET\" send-keys -t \"$SESSION\":0.0 -- \"op signin --account my.1password.com\" Enter\ntmux -S \"$SOCKET\" send-keys -t \"$SESSION\":0.0 -- \"op whoami\" Enter\ntmux -S \"$SOCKET\" send-keys -t \"$SESSION\":0.0 -- \"op vault list\" Enter\ntmux -S \"$SOCKET\" capture-pane -p -J -t \"$SESSION\":0.0 -S -200\ntmux -S \"$SOCKET\" kill-session -t \"$SESSION\"\n```\n\n## Guardrails\n\n- Never paste secrets into logs, chat, or code.\n- Prefer `op run` / `op inject` over writing secrets to disk.\n- If sign-in without app integration is needed, use `op account add`.\n- If a command returns \"account is not signed in\", re-run `op signin` inside tmux and authorize in the app.\n- Do not run `op` outside tmux; stop and ask if tmux is unavailable.""",
                examples=[],
                gotchas=[],
                homepage="https://developer.1password.com/docs/cli/get-started/",
            ),
            dma_guidance=ToolDMAGuidance(
                requires_approval=False,
            ),
            tags=["skill", "clawdbot", "1password", "cli"],
            version="1.0.0",
        )
