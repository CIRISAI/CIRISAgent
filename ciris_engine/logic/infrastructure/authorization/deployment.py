"""Deployment-scope resolution for task envelopes (CIRISAgent#938, Phase 1).

An envelope resolves from what is actually knowable when a task is created:
the environment tier, the agent's role/template, the tools this deployment
enabled, and the requester's authorization. This module answers the first two;
:mod:`.enabled_tools` answers the third; the caller supplies the fourth.

Deliberately *not* an input: the task's purpose. See the issuance correction on
CIRISAgent#938 — for an ally deployment every task is a generic assistant task,
and pre-authorizing by task type guarantees the one task that needed the ban is
the one that could not issue it.
"""

from __future__ import annotations

import logging
import os

from ciris_engine.schemas.runtime.task_envelope import DeploymentScope, EnvironmentTier

logger = logging.getLogger(__name__)

# `CIRIS_ENV` already exists in the codebase (ciris_runtime.py treats "prod" as
# production). We accept the spellings people actually use rather than
# inventing a new variable.
_TIER_ALIASES = {
    "prod": EnvironmentTier.PRODUCTION,
    "production": EnvironmentTier.PRODUCTION,
    "qa": EnvironmentTier.QA,
    "staging": EnvironmentTier.QA,
    "test": EnvironmentTier.QA,
    "dev": EnvironmentTier.DEVELOPMENT,
    "development": EnvironmentTier.DEVELOPMENT,
    "local": EnvironmentTier.LOCAL,
}

_DEFAULT_TIER = EnvironmentTier.DEVELOPMENT
"""Matches the existing ``os.environ.get("CIRIS_ENV", "dev")`` default.

An unset tier resolves to DEVELOPMENT, never PRODUCTION: an unlabelled
deployment must not silently inherit production standing.
"""


def resolve_environment_tier() -> EnvironmentTier:
    """Environment tier from ``CIRIS_ENV``, defaulting to development."""
    raw = (os.environ.get("CIRIS_ENV") or "").strip().lower()
    if not raw:
        return _DEFAULT_TIER
    tier = _TIER_ALIASES.get(raw)
    if tier is None:
        logger.warning(
            "CIRIS_ENV=%r is not a recognised environment tier; resolving to %s",
            raw,
            _DEFAULT_TIER.value,
        )
        return _DEFAULT_TIER
    return tier


def resolve_agent_id() -> str:
    """Agent identifier for this deployment."""
    return (os.environ.get("CIRIS_AGENT_ID") or "").strip() or "default"


def resolve_template() -> str:
    """Agent role/template (echo, scout, datum, ...).

    ``CIRIS_TEMPLATE`` is the same variable ``EssentialConfig`` and
    ``component_builder`` read, resolved through the same ``get_env_var``
    helper so a ``.env``-provided value is seen here too.
    """
    try:
        from ciris_engine.logic.config.env_utils import get_env_var  # local import: avoids config import cycle

        env_template = (get_env_var("CIRIS_TEMPLATE") or "").strip()
    except Exception as exc:  # pragma: no cover - defensive; env layer may not be up yet
        logger.debug("template resolution falling back to os.environ: %s", exc)
        env_template = (os.environ.get("CIRIS_TEMPLATE") or "").strip()
    return env_template or "default"


def resolve_deployment_scope(agent_occurrence_id: str = "default") -> DeploymentScope:
    """The (tier, agent, template, occurrence) coordinates of this deployment."""
    return DeploymentScope(
        environment_tier=resolve_environment_tier(),
        agent_id=resolve_agent_id(),
        template=resolve_template(),
        agent_occurrence_id=agent_occurrence_id or "default",
    )


__all__ = [
    "resolve_agent_id",
    "resolve_deployment_scope",
    "resolve_environment_tier",
    "resolve_template",
]
