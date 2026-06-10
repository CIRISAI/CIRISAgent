"""
Fabric component versions — GET /v1/system/fabric.

Surfaces the in-process substrate crates' versions for the agent's Trust page.
Today it reports each crate's **runtime** version (the loaded Python/wheel
``__version__``). Two fields are placeholders until the upstream work lands:

- ``embedded_version`` — the version literal embedded *in the compiled cdylib*,
  read via the crate's FFI/PyO3 accessor. Gated on the embed-version issues
  (CIRISPersist#189 / CIRISEdge#77 / CIRISLensCore#38 / CIRISNodeCore#36;
  ciris-verify already embeds it). Until then: ``None``.
- ``registry_hash_status`` — whether the binary's canonical hash matches the
  registry's canonical build manifest for that version. Gated on CIRISRegistry#68.
  Until then: ``"pending"``.

When all three land, the Trust page renders the 3-way check per component:
``embedded_version == runtime_version`` (pin) ``== registry canonical`` + hash ✓.
"""

import importlib
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.responses import SuccessResponse

from ...dependencies.auth import AuthContext, require_observer

router = APIRouter()

AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]

# The in-process substrate cdylib crates, in trust-graph order. Registry is the
# verifier (it supplies registry_hash_status), not a bundled component here.
_FABRIC_CRATES = [
    ("persist", "ciris_persist"),
    ("edge", "ciris_edge"),
    ("verify", "ciris_verify"),
    ("lenscore", "ciris_lens_core"),
    ("nodecore", "ciris_node_core"),
]


class FabricComponent(BaseModel):
    """Version + trust status for one substrate cdylib crate."""

    name: str = Field(..., description="Component name (persist/edge/verify/lenscore/nodecore)")
    loaded: bool = Field(..., description="Whether the crate is loaded in this process")
    runtime_version: Optional[str] = Field(None, description="Loaded wheel __version__")
    embedded_version: Optional[str] = Field(
        None, description="Version literal embedded in the cdylib (None until the embed-version issues ship)"
    )
    registry_hash_status: str = Field(
        "pending", description="pending | verified | mismatch | unavailable (gated on CIRISRegistry#68)"
    )


class FabricVersionsResponse(BaseModel):
    """All substrate components' versions for the Trust page."""

    components: List[FabricComponent] = Field(..., description="One entry per substrate crate")
    note: str = Field(..., description="Explains which fields are still pending upstream")


def _runtime_version(module_name: str) -> tuple[bool, Optional[str]]:
    try:
        mod = importlib.import_module(module_name)
        return True, getattr(mod, "__version__", None)
    except Exception:
        return False, None


@router.get("/fabric", response_model=SuccessResponse[FabricVersionsResponse])
async def get_fabric_versions(auth: AuthObserverDep) -> SuccessResponse[FabricVersionsResponse]:
    """Substrate component versions + trust status (Trust page fabric section)."""
    components: List[FabricComponent] = []
    for name, module_name in _FABRIC_CRATES:
        loaded, runtime_version = _runtime_version(module_name)
        components.append(
            FabricComponent(
                name=name,
                loaded=loaded,
                runtime_version=runtime_version,
                # Pending upstream — see module docstring.
                embedded_version=None,
                registry_hash_status="pending",
            )
        )
    return SuccessResponse(
        data=FabricVersionsResponse(
            components=components,
            note=(
                "runtime_version is live. embedded_version (from the cdylib literal) and "
                "registry_hash_status are pending the embed-version + registry-manifest work "
                "(CIRISPersist#189 / CIRISEdge#77 / CIRISLensCore#38 / CIRISNodeCore#36 / CIRISRegistry#68)."
            ),
        )
    )
