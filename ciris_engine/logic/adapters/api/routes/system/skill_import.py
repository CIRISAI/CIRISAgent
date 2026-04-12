"""Skill import endpoint.

Provides UI/API endpoint for importing OpenClaw skills as CIRIS adapters.
Supports importing from:
- Raw SKILL.md content (paste in UI)
- ClawHub URL (fetched server-side)
- Local file path (for CLI/desktop use)
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.services.skill_import.converter import SkillToAdapterConverter
from ciris_engine.logic.services.skill_import.parser import OpenClawSkillParser, ParsedSkill
from ciris_engine.schemas.api.auth import AuthContext

from ...dependencies.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()

# Annotated type alias for FastAPI dependency injection
AuthAdminDep = Annotated[AuthContext, Depends(require_admin)]


# ============================================================================
# Request / Response Schemas
# ============================================================================


class SkillImportRequest(BaseModel):
    """Request to import an OpenClaw skill."""

    skill_md_content: Optional[str] = Field(None, description="Raw SKILL.md content to import (paste from clipboard)")
    source_url: Optional[str] = Field(None, description="ClawHub or GitHub URL to fetch the skill from")
    local_path: Optional[str] = Field(None, description="Local filesystem path to a skill directory or SKILL.md file")
    output_dir: Optional[str] = Field(None, description="Override output directory (default: ~/ciris/adapters/)")
    auto_load: bool = Field(True, description="Whether to automatically load the adapter after import")

    model_config = ConfigDict(extra="forbid")


class SecurityFindingResponse(BaseModel):
    """A single security finding."""

    severity: str = Field(..., description="critical, high, medium, low, or info")
    category: str = Field(..., description="Type of issue")
    title: str = Field(..., description="Short plain English title")
    description: str = Field(..., description="What we found")
    evidence: Optional[str] = Field(None, description="The triggering text")
    recommendation: str = Field("", description="What to do")

    model_config = ConfigDict(extra="forbid")


class SecurityReportResponse(BaseModel):
    """Security scan results for a skill."""

    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    safe_to_import: bool = True
    summary: str = ""
    findings: List[SecurityFindingResponse] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SkillPreviewResponse(BaseModel):
    """Preview of what will be imported before committing."""

    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Skill description")
    version: str = Field(..., description="Skill version")
    module_name: str = Field(..., description="Generated CIRIS module name")
    tools: List[str] = Field(default_factory=list, description="Tools that will be created")
    required_env_vars: List[str] = Field(default_factory=list, description="Required environment variables")
    required_binaries: List[str] = Field(default_factory=list, description="Required binaries")
    has_supporting_files: bool = Field(False, description="Whether supporting files are included")
    source_url: Optional[str] = Field(None, description="Source URL")
    instructions_preview: str = Field("", description="First 500 chars of skill instructions")
    security: Optional[SecurityReportResponse] = Field(None, description="Security scan results")

    model_config = ConfigDict(extra="forbid")


class SkillImportResponse(BaseModel):
    """Response from a skill import operation."""

    success: bool = Field(..., description="Whether import succeeded")
    module_name: str = Field("", description="Generated adapter module name")
    adapter_path: str = Field("", description="Path where adapter was created")
    tools_created: List[str] = Field(default_factory=list, description="Tool names created")
    message: str = Field("", description="Human-readable result message")
    auto_loaded: bool = Field(False, description="Whether adapter was auto-loaded into runtime")
    preview: Optional[SkillPreviewResponse] = Field(None, description="Skill preview details")

    model_config = ConfigDict(extra="forbid")


class ImportedSkillInfo(BaseModel):
    """Info about a previously imported skill."""

    module_name: str
    original_skill_name: str
    version: str
    description: str
    adapter_path: str
    source_url: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ImportedSkillsListResponse(BaseModel):
    """List of all imported skills."""

    skills: List[ImportedSkillInfo]
    total: int

    model_config = ConfigDict(extra="forbid")


# ============================================================================
# Helper Functions
# ============================================================================

# Sensitive paths that should never be accessed via skill import
_SENSITIVE_PATTERNS = frozenset([".ssh", ".gnupg", ".aws", ".config/gcloud", "credentials"])

# Dangerous path components that indicate traversal or escape attempts
_DANGEROUS_PATH_COMPONENTS = frozenset([
    "..",      # Parent directory traversal
    "...",     # Triple dot (some systems)
    "....",    # Quad dot variations
])


# Allowed base directories (lazy-evaluated to handle test environments)
def _get_allowed_bases() -> list[Path]:
    """Get allowed base directories from trusted sources only."""
    return [Path.home(), Path.cwd(), Path(tempfile.gettempdir())]


def _validate_path_string(local_path: str) -> None:
    """Validate raw path string before any path operations.

    Raises ValueError if path is invalid or contains dangerous patterns.
    """
    if not local_path or not isinstance(local_path, str):
        raise ValueError("Path must be a non-empty string")
    if "\x00" in local_path:
        raise ValueError("Path contains null bytes")
    if len(local_path) > 4096:
        raise ValueError("Path exceeds maximum length")


def _check_path_traversal(local_path: str) -> None:
    """Check for path traversal attempts in raw string.

    Raises ValueError if dangerous patterns are found in path components.
    """
    raw_parts = local_path.replace("\\", "/").split("/")
    for part in raw_parts:
        if part in _DANGEROUS_PATH_COMPONENTS:
            raise ValueError(f"Path traversal using '{part}' is not allowed")


def _check_sensitive_paths(local_path: str) -> None:
    """Block access to sensitive directories.

    Raises ValueError if path contains sensitive patterns.
    """
    path_lower = local_path.lower()
    for pattern in _SENSITIVE_PATTERNS:
        if pattern in path_lower:
            raise ValueError(f"Access to paths containing '{pattern}' is not allowed for security reasons.")


def _resolve_to_allowed_path(local_path: str) -> Path:
    """Resolve a validated path string to an allowed Path.

    SECURITY: This function constructs paths ONLY from trusted base directories,
    never directly from user input. User input is only used to select which
    trusted base to use and to extract validated path components.

    Raises ValueError if resolved path is outside allowed directories.
    """
    allowed_bases = _get_allowed_bases()

    # Handle tilde by constructing from trusted home directory
    if local_path.startswith("~"):
        # Extract suffix and split into components for validation
        suffix = local_path[1:].lstrip("/\\")
        # Construct path from trusted base + validated components
        resolved = Path.home()
        for component in suffix.replace("\\", "/").split("/"):
            if component and component not in (".", ""):
                resolved = resolved / component
        resolved = resolved.resolve()
        # Verify still within home
        try:
            resolved.relative_to(Path.home())
            return resolved
        except ValueError:
            pass  # Fall through to error
    else:
        # For absolute/relative paths: find matching trusted base and construct from it
        # Split user path into components (already validated for traversal)
        path_components = local_path.replace("\\", "/").split("/")

        # Try each trusted base directory
        for base in allowed_bases:
            base_resolved = base.resolve()
            base_str = str(base_resolved)

            # Check if user path starts with or is relative to this base
            if local_path.startswith(base_str):
                # Absolute path within this base - extract suffix
                suffix = local_path[len(base_str):].lstrip("/\\")
                resolved = base_resolved
                for component in suffix.split("/"):
                    if component and component not in (".", ""):
                        resolved = resolved / component
                resolved = resolved.resolve()
                # Verify still within base after resolution
                try:
                    resolved.relative_to(base_resolved)
                    return resolved
                except ValueError:
                    continue  # Escaped base via symlinks, try next
            elif not local_path.startswith("/"):
                # Relative path - resolve against this base (cwd)
                resolved = base_resolved
                for component in path_components:
                    if component and component not in (".", ""):
                        resolved = resolved / component
                resolved = resolved.resolve()
                # Verify within an allowed base
                for check_base in allowed_bases:
                    try:
                        resolved.relative_to(check_base.resolve())
                        return resolved
                    except ValueError:
                        continue

    raise ValueError(
        f"Path '{local_path}' is outside allowed directories. "
        f"Local imports are restricted to your home directory, "
        f"current working directory, or /tmp."
    )


def _validate_local_path(local_path: str) -> Path:
    """Validate and sanitize a local path to prevent path traversal attacks.

    Only allows paths within:
    - User's home directory
    - Current working directory
    - /tmp directory

    Raises ValueError if the path is outside allowed directories or invalid.

    Security: Validates path string components BEFORE constructing Path objects
    to prevent filesystem oracle attacks (SonarCloud S6549).
    """
    # Step 1: Validate raw string format
    _validate_path_string(local_path)

    # Step 2: Check for path traversal attempts
    _check_path_traversal(local_path)

    # Step 3: Block sensitive directories
    _check_sensitive_paths(local_path)

    # Step 4: Resolve to allowed path (constructs Path from trusted sources)
    return _resolve_to_allowed_path(local_path)


def _parse_skill_from_request(req: SkillImportRequest) -> ParsedSkill:
    """Parse a skill from the request, handling all input modes."""
    parser = OpenClawSkillParser()

    if req.skill_md_content:
        return parser.parse_skill_md(req.skill_md_content, source_url=req.source_url)

    if req.local_path:
        # Validate path to prevent traversal attacks
        path = _validate_local_path(req.local_path)
        if path.is_dir():
            return parser.parse_directory(path, source_url=req.source_url)
        elif path.is_file():
            content = path.read_text(encoding="utf-8")
            return parser.parse_skill_md(content, source_url=req.source_url)
        else:
            raise ValueError(f"Path does not exist: {req.local_path}")

    if req.source_url:
        raise ValueError(
            "URL-based import requires skill_md_content. "
            "Fetch the SKILL.md content client-side and pass it as skill_md_content."
        )

    raise ValueError("Must provide one of: skill_md_content, local_path, or source_url with content")


def _build_preview(skill: ParsedSkill, module_name: str) -> SkillPreviewResponse:
    """Build a preview response from a parsed skill, including security scan."""
    from ciris_engine.logic.services.skill_import.scanner import SkillSecurityScanner

    env_vars: List[str] = []
    binaries: List[str] = []
    if skill.metadata and skill.metadata.requires:
        env_vars = skill.metadata.requires.env
        binaries = skill.metadata.requires.bins

    # Run security scan
    scanner = SkillSecurityScanner()
    report = scanner.scan(skill)
    security = SecurityReportResponse(
        total_findings=report.total_findings,
        critical_count=report.critical_count,
        high_count=report.high_count,
        medium_count=report.medium_count,
        low_count=report.low_count,
        safe_to_import=report.safe_to_import,
        summary=report.summary,
        findings=[
            SecurityFindingResponse(
                severity=f.severity.value,
                category=f.category,
                title=f.title,
                description=f.description,
                evidence=f.evidence,
                recommendation=f.recommendation,
            )
            for f in report.findings
        ],
    )

    return SkillPreviewResponse(
        name=skill.name,
        description=skill.description,
        version=skill.version,
        module_name=module_name,
        tools=[f"skill:{skill.name}", f"skill:{skill.name}:info"],
        required_env_vars=env_vars,
        required_binaries=binaries,
        has_supporting_files=bool(skill.supporting_files),
        source_url=skill.source_url,
        instructions_preview=skill.instructions[:500] if skill.instructions else "",
        security=security,
    )


async def _try_auto_load(request: Request, module_name: str) -> bool:
    """Attempt to load the imported adapter into the running runtime."""
    try:
        adapter_manager = getattr(request.app.state, "adapter_manager", None)
        if not adapter_manager:
            return False

        result = await adapter_manager.load_adapter(
            adapter_type=module_name,
            adapter_id=f"{module_name}_imported",
        )
        return getattr(result, "success", False)
    except Exception as e:
        logger.warning(f"Auto-load of imported skill adapter failed: {e}")
        return False


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/adapters/import-skill/preview",
    responses={
        400: {"description": "Invalid skill content"},
        500: {"description": "Server error"},
    },
)
async def preview_skill_import(
    request: Request,
    auth: AuthAdminDep,
    body: Annotated[SkillImportRequest, Body()],
) -> SkillPreviewResponse:
    """Preview what an imported skill will look like before committing.

    Parse and validate the skill content, returning a preview of the
    adapter that would be created without actually writing any files.

    Requires ADMIN role.
    """
    try:
        skill = _parse_skill_from_request(body)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error parsing skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse skill: {e}")

    import re

    sanitized = re.sub(r"[^a-z0-9_]", "_", skill.name.lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    module_name = f"imported_{sanitized}"

    return _build_preview(skill, module_name)


@router.post(
    "/adapters/import-skill",
    responses={
        400: {"description": "Invalid skill content"},
        409: {"description": "Skill already imported"},
        500: {"description": "Server error"},
    },
)
async def import_skill(
    request: Request,
    auth: AuthAdminDep,
    body: Annotated[SkillImportRequest, Body()],
) -> SkillImportResponse:
    """Import an OpenClaw skill as a CIRIS adapter.

    Parses the SKILL.md content, generates a full CIRIS adapter directory,
    and optionally loads it into the running runtime.

    The adapter is created in ~/ciris/adapters/ by default, which is
    automatically discovered by the AdapterDiscoveryService.

    Requires ADMIN role.
    """
    try:
        skill = _parse_skill_from_request(body)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error parsing skill: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to parse skill: {e}")

    # Security scan - block skills with critical findings
    from ciris_engine.logic.services.skill_import.scanner import SkillSecurityScanner

    scanner = SkillSecurityScanner()
    security_report = scanner.scan(skill)
    if not security_report.safe_to_import:
        raise HTTPException(
            status_code=400,
            detail={
                "message": security_report.summary,
                "findings": [
                    {"severity": f.severity.value, "title": f.title, "description": f.description}
                    for f in security_report.findings
                    if f.severity.value in ("critical", "high")
                ],
            },
        )

    # Convert to adapter
    output_dir = Path(body.output_dir) if body.output_dir else None
    converter = SkillToAdapterConverter(output_dir=output_dir)

    try:
        adapter_path = converter.convert(skill)
    except Exception as e:
        logger.error(f"Error converting skill to adapter: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to convert skill: {e}")

    module_name = adapter_path.name
    tools_created = [f"skill:{skill.name}", f"skill:{skill.name}:info"]

    # Auto-load if requested
    auto_loaded = False
    if body.auto_load:
        auto_loaded = await _try_auto_load(request, module_name)

    preview = _build_preview(skill, module_name)

    load_msg = " and loaded into runtime" if auto_loaded else " (restart to activate)"
    return SkillImportResponse(
        success=True,
        module_name=module_name,
        adapter_path=str(adapter_path),
        tools_created=tools_created,
        message=f"Skill '{skill.name}' imported as adapter '{module_name}'{load_msg}",
        auto_loaded=auto_loaded,
        preview=preview,
    )


@router.get(
    "/adapters/imported-skills",
    responses={500: {"description": "Server error"}},
)
async def list_imported_skills(
    request: Request,
    auth: Annotated[AuthContext, Depends(require_admin)],
) -> ImportedSkillsListResponse:
    """List all previously imported skills.

    Scans the user adapter directory for adapters created by the skill
    import process (identified by the 'imported_' prefix and metadata).

    Requires ADMIN role.
    """
    import json

    user_adapters_dir = Path.home() / "ciris" / "adapters"
    skills: List[ImportedSkillInfo] = []

    if not user_adapters_dir.exists():
        return ImportedSkillsListResponse(skills=[], total=0)

    for adapter_dir in user_adapters_dir.iterdir():
        if not adapter_dir.is_dir() or not adapter_dir.name.startswith("imported_"):
            continue

        manifest_path = adapter_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            module_info = manifest.get("module", {})
            metadata = manifest.get("metadata", {})

            if metadata.get("imported_from") != "openclaw":
                continue

            skills.append(
                ImportedSkillInfo(
                    module_name=module_info.get("name", adapter_dir.name),
                    original_skill_name=metadata.get("original_skill_name", ""),
                    version=module_info.get("version", "unknown"),
                    description=module_info.get("description", ""),
                    adapter_path=str(adapter_dir),
                    source_url=metadata.get("source_url"),
                )
            )
        except (json.JSONDecodeError, OSError) as e:
            logger.debug(f"Skipping invalid imported adapter {adapter_dir}: {e}")

    return ImportedSkillsListResponse(skills=skills, total=len(skills))


@router.delete(
    "/adapters/imported-skills/{module_name}",
    responses={
        404: {"description": "Imported skill not found"},
        500: {"description": "Server error"},
    },
)
async def delete_imported_skill(
    request: Request,
    module_name: str,
    auth: AuthAdminDep,
) -> Dict[str, Any]:
    """Delete a previously imported skill adapter.

    Removes the adapter directory from ~/ciris/adapters/.
    If the adapter is currently loaded, it will be unloaded first.

    Requires ADMIN role.
    """
    import shutil

    user_adapters_dir = Path.home() / "ciris" / "adapters"
    adapter_dir = user_adapters_dir / module_name

    if not adapter_dir.exists() or not module_name.startswith("imported_"):
        raise HTTPException(status_code=404, detail=f"Imported skill '{module_name}' not found")

    # Try to unload from runtime first
    try:
        adapter_manager = getattr(request.app.state, "adapter_manager", None)
        if adapter_manager:
            await adapter_manager.unload_adapter(f"{module_name}_imported")
    except Exception as e:
        logger.debug(f"Could not unload adapter {module_name}: {e}")

    try:
        shutil.rmtree(adapter_dir)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")

    return {
        "success": True,
        "message": f"Imported skill '{module_name}' deleted",
        "module_name": module_name,
    }
