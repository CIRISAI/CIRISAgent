"""Skill Builder API endpoints.

HyperCard-style skill creation: browse cards, edit schemas, build adapters.
Every endpoint works with serializable JSON - the UI just renders forms
from Pydantic JSON Schemas and sends data back.

Two modes:
- Card mode: UI renders pretty forms from JSON Schema
- Edit mode: UI shows raw JSON, user edits directly

Endpoints:
  GET  /skills/cards              - Get all card schemas (UI renders forms from this)
  GET  /skills/cards/{card_id}    - Get one card schema
  POST /skills/drafts             - Create new draft (blank or from OpenClaw import)
  GET  /skills/drafts             - List all drafts
  GET  /skills/drafts/{id}        - Get a draft
  PUT  /skills/drafts/{id}        - Update a draft (full or partial card update)
  DELETE /skills/drafts/{id}      - Delete a draft
  POST /skills/drafts/{id}/validate - Validate a draft
  POST /skills/drafts/{id}/build  - Build adapter from draft
  PUT  /skills/drafts/{id}/cards/{card_id} - Update a single card
"""

import logging
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.services.skill_import.builder import (
    CARD_DEFINITIONS,
    SkillBuilder,
    SkillDraft,
    get_all_card_schemas,
    get_card_schema,
)
from ciris_engine.schemas.api.auth import AuthContext

from ...dependencies.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()
AuthAdminDep = Annotated[AuthContext, Depends(require_admin)]

# Shared builder instance
_builder = SkillBuilder()


# ============================================================================
# Request / Response Schemas
# ============================================================================


class CreateDraftRequest(BaseModel):
    """Request to create a new skill draft."""

    from_openclaw: Optional[str] = Field(None, description="Raw SKILL.md content to import")
    source_url: Optional[str] = Field(None, description="Source URL for provenance")

    model_config = ConfigDict(extra="forbid")


class UpdateCardRequest(BaseModel):
    """Request to update a single card in a draft."""

    data: Dict[str, Any] = Field(..., description="Card data matching the card's JSON Schema")

    model_config = ConfigDict(extra="forbid")


class UpdateDraftRequest(BaseModel):
    """Request to update the entire draft or multiple cards."""

    identity: Optional[Dict[str, Any]] = None
    tools: Optional[Dict[str, Any]] = None
    requires: Optional[Dict[str, Any]] = None
    instruct: Optional[Dict[str, Any]] = None
    behavior: Optional[Dict[str, Any]] = None
    install: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")


class ValidationResult(BaseModel):
    """Result of draft validation."""

    valid: bool
    errors: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class BuildResult(BaseModel):
    """Result of building an adapter from a draft."""

    success: bool
    adapter_path: str = ""
    module_name: str = ""
    message: str = ""
    errors: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Card Schema Endpoints (read-only, no auth needed for schemas)
# ============================================================================


@router.get("/skills/cards")
async def get_cards(auth: AuthAdminDep) -> Dict[str, Any]:
    """Get all card schemas for the skill builder UI.

    Returns card metadata (title, subtitle, emoji) plus the full
    JSON Schema for each card. The UI uses this to render forms
    in card mode or JSON editors in edit mode.

    This is the single call the UI needs to bootstrap the skill builder.
    """
    return get_all_card_schemas()


@router.get("/skills/cards/{card_id}", responses={404: {"description": "Card not found"}})
async def get_card(card_id: str, auth: AuthAdminDep) -> Dict[str, Any]:
    """Get the JSON Schema for a single card."""
    try:
        return {"card_id": card_id, "schema": get_card_schema(card_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Draft CRUD
# ============================================================================


@router.post(
    "/skills/drafts",
    status_code=201,
    responses={400: {"description": "Invalid input"}, 500: {"description": "Server error"}},
)
async def create_draft(
    auth: AuthAdminDep,
    body: Annotated[CreateDraftRequest, Body()] = CreateDraftRequest(),
) -> Dict[str, Any]:
    """Create a new skill draft.

    If from_openclaw is provided, imports and maps the SKILL.md onto
    cards for review. Otherwise creates a blank draft.
    """
    try:
        if body.from_openclaw:
            draft = _builder.create_from_openclaw(body.from_openclaw, body.source_url)
        else:
            draft = _builder.create_draft()

        _builder.save_draft(draft)
        return {"draft_id": draft.draft_id, "draft": draft.model_dump()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create draft: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skills/drafts")
async def list_drafts(auth: AuthAdminDep) -> Dict[str, Any]:
    """List all saved skill drafts."""
    drafts = _builder.list_drafts()
    return {
        "drafts": [d.model_dump() for d in drafts],
        "total": len(drafts),
    }


@router.get("/skills/drafts/{draft_id}", responses={404: {"description": "Draft not found"}})
async def get_draft(draft_id: str, auth: AuthAdminDep) -> Dict[str, Any]:
    """Get a specific draft."""
    draft = _builder.load_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft '{draft_id}' not found")
    return {"draft": draft.model_dump()}


@router.put(
    "/skills/drafts/{draft_id}",
    responses={404: {"description": "Draft not found"}, 400: {"description": "Validation errors"}},
)
async def update_draft(
    draft_id: str,
    auth: AuthAdminDep,
    body: Annotated[UpdateDraftRequest, Body()],
) -> Dict[str, Any]:
    """Update a draft with new card data.

    Supports partial updates - only include the cards you want to change.
    Each card's data is validated against its schema before saving.
    """
    draft = _builder.load_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft '{draft_id}' not found")

    errors: List[str] = []

    # Apply each card update
    for card_id in ["identity", "tools", "requires", "instruct", "behavior", "install"]:
        card_data = getattr(body, card_id, None)
        if card_data is not None:
            card_errors = _builder.validate_card(card_id, card_data)
            if card_errors:
                errors.extend([f"{card_id}: {e}" for e in card_errors])
            else:
                setattr(draft, card_id, type(getattr(draft, card_id)).model_validate(card_data))

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})

    _builder.save_draft(draft)
    return {"draft": draft.model_dump()}


@router.put(
    "/skills/drafts/{draft_id}/cards/{card_id}",
    responses={404: {"description": "Draft or card not found"}, 400: {"description": "Validation errors"}},
)
async def update_card(
    draft_id: str,
    card_id: str,
    auth: AuthAdminDep,
    body: Annotated[UpdateCardRequest, Body()],
) -> Dict[str, Any]:
    """Update a single card in a draft.

    This is the card-level edit endpoint. The UI sends the card data
    (from either form mode or raw JSON edit mode) and the backend
    validates it against the card's schema.
    """
    draft = _builder.load_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft '{draft_id}' not found")

    # Validate
    errors = _builder.validate_card(card_id, body.data)
    if errors:
        raise HTTPException(status_code=400, detail={"card_id": card_id, "errors": errors})

    # Apply
    try:
        card_class = type(getattr(draft, card_id))
        setattr(draft, card_id, card_class.model_validate(body.data))
    except AttributeError:
        raise HTTPException(status_code=404, detail=f"Unknown card: {card_id}")

    _builder.save_draft(draft)
    return {"card_id": card_id, "data": getattr(draft, card_id).model_dump()}


@router.delete("/skills/drafts/{draft_id}", responses={404: {"description": "Draft not found"}})
async def delete_draft(draft_id: str, auth: AuthAdminDep) -> Dict[str, Any]:
    """Delete a draft."""
    if _builder.delete_draft(draft_id):
        return {"success": True, "draft_id": draft_id}
    raise HTTPException(status_code=404, detail=f"Draft '{draft_id}' not found")


# ============================================================================
# Validation & Build
# ============================================================================


@router.post("/skills/drafts/{draft_id}/validate", responses={404: {"description": "Draft not found"}})
async def validate_draft(draft_id: str, auth: AuthAdminDep) -> ValidationResult:
    """Validate a draft for completeness before building."""
    draft = _builder.load_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft '{draft_id}' not found")

    errors = _builder.validate_draft(draft)
    return ValidationResult(valid=len(errors) == 0, errors=errors)


@router.post("/skills/drafts/{draft_id}/build", responses={404: {"description": "Draft not found"}})
async def build_adapter(
    draft_id: str,
    request: Request,
    auth: AuthAdminDep,
) -> BuildResult:
    """Build a CIRIS adapter from a validated draft.

    This is the 'Create' step - takes the draft and generates all
    adapter files in ~/.ciris/adapters/. Optionally auto-loads the
    adapter into the running runtime.
    """
    draft = _builder.load_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft '{draft_id}' not found")

    # Validate first
    errors = _builder.validate_draft(draft)
    if errors:
        return BuildResult(success=False, errors=errors, message="Draft has validation errors")

    try:
        adapter_path = _builder.build_adapter(draft)
        module_name = adapter_path.name

        # Try auto-load
        auto_loaded = False
        try:
            adapter_manager = getattr(request.app.state, "adapter_manager", None)
            if adapter_manager:
                result = await adapter_manager.load_adapter(
                    adapter_type=module_name,
                    adapter_id=f"{module_name}_skill",
                )
                auto_loaded = getattr(result, "success", False)
        except Exception as e:
            logger.warning(f"Auto-load failed: {e}")

        load_msg = " and loaded" if auto_loaded else " (restart to activate)"
        return BuildResult(
            success=True,
            adapter_path=str(adapter_path),
            module_name=module_name,
            message=f"Skill '{draft.identity.name}' built{load_msg}",
        )
    except ValueError as e:
        return BuildResult(success=False, errors=[str(e)], message="Build failed")
    except Exception as e:
        logger.error(f"Build failed: {e}", exc_info=True)
        return BuildResult(success=False, errors=[str(e)], message="Build failed")
