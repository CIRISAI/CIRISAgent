"""Shared dependencies for CIRIS setup routes.

This module contains FastAPI dependencies used across setup endpoints.
"""

from fastapi import Depends, HTTPException, status

from ciris_engine.logic.setup.first_run import is_first_run


def require_setup_mode() -> None:
    """Dependency that ensures setup routes are only accessible during first-run setup.

    After setup is complete, these routes return 403 Forbidden.
    Use /v1/auth/attestation for cached attestation after setup.

    Raises:
        HTTPException: 403 if setup is already complete
    """
    if not is_first_run():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Setup routes are only available during first-run setup. "
            "Use /v1/auth/attestation for attestation status after setup.",
        )


# Type alias for the dependency
SetupOnlyDep = Depends(require_setup_mode)
