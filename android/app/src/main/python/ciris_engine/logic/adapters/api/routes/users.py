"""User management API routes."""

import logging
from datetime import datetime
from typing import Any, Dict, Generic, List, Optional, TypeVar

import aiofiles
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.api.auth import AuthContext, PermissionRequestResponse, PermissionRequestUser, UserRole
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import OAuthIdentityLink, WARole
from ciris_engine.schemas.types import JSONDict

from ..dependencies.auth import check_permissions, get_auth_context, get_auth_service
from ..services.auth_service import (
    PERMISSION_MANAGE_USER_PERMISSIONS,
    PERMISSION_USERS_DELETE,
    PERMISSION_USERS_READ,
    PERMISSION_USERS_WRITE,
    PERMISSION_WA_MINT,
    APIAuthService,
)

# Error message constants
ERROR_USER_NOT_FOUND = "User not found"
ERROR_USERNAME_EXISTS = "Username already exists"
ERROR_CREATE_USER_FAILED = "Failed to create user"
ERROR_CHANGE_PASSWORD_FAILED = "Failed to change password. Check current password."
ERROR_CANNOT_DEMOTE_SELF = "Cannot demote your own role"
ERROR_CANNOT_DEACTIVATE_SELF = "Cannot deactivate your own account"
ERROR_ONLY_ADMIN_MINT_WA = "Only ADMIN or higher can mint Wise Authorities"
ERROR_CANNOT_MINT_ROOT = "Cannot mint new ROOT authorities. ROOT is singular."
ERROR_INVALID_SIGNATURE = "Invalid ROOT signature"
ERROR_SIGNATURE_OR_KEY_REQUIRED = "Either signature or private_key_path must be provided"

router = APIRouter(prefix="/users", tags=["users"])

logger = logging.getLogger(__name__)


# Generic models
T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response."""

    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int


# Request/Response models
class UserSummary(BaseModel):
    """Summary information about a user."""

    user_id: str
    username: str
    auth_type: str = Field(description="password, oauth, api_key")
    api_role: APIRole
    wa_role: Optional[WARole] = None
    wa_id: Optional[str] = None
    oauth_provider: Optional[str] = None
    oauth_email: Optional[str] = None
    oauth_name: Optional[str] = None  # Full name from OAuth provider
    oauth_picture: Optional[str] = None  # Profile picture URL
    permission_requested_at: Optional[datetime] = None  # Permission request timestamp
    created_at: datetime
    last_login: Optional[datetime] = None
    is_active: bool = True
    linked_oauth_accounts: List["LinkedOAuthAccount"] = Field(default_factory=list)


class UserDetail(UserSummary):
    """Detailed user information."""

    permissions: List[str]
    custom_permissions: Optional[List[str]] = None
    oauth_external_id: Optional[str] = None
    wa_parent_id: Optional[str] = None
    wa_auto_minted: bool = False
    api_keys_count: int = 0


class LinkedOAuthAccount(BaseModel):
    """Linked OAuth identity summary."""

    provider: str
    external_id: str
    account_name: Optional[str] = None
    linked_at: Optional[datetime] = None
    is_primary: bool = False
    metadata: Dict[str, str] = Field(default_factory=dict)


def _build_linked_accounts(user: Any) -> List[LinkedOAuthAccount]:
    accounts: List[LinkedOAuthAccount] = []
    seen = set()

    for link in getattr(user, "oauth_links", []) or []:
        key = (link.provider, link.external_id)
        seen.add(key)
        accounts.append(
            LinkedOAuthAccount(
                provider=link.provider,
                external_id=link.external_id,
                account_name=getattr(link, "account_name", None),
                linked_at=getattr(link, "linked_at", None),
                is_primary=getattr(link, "is_primary", False),
                metadata=getattr(link, "metadata", {}) or {},
            )
        )

    if user.oauth_provider and user.oauth_external_id:
        key = (user.oauth_provider, user.oauth_external_id)
        if key not in seen:
            accounts.append(
                LinkedOAuthAccount(
                    provider=user.oauth_provider,
                    external_id=user.oauth_external_id,
                    account_name=getattr(user, "oauth_name", None),
                    linked_at=None,
                    is_primary=True,
                    metadata={},
                )
            )

    primary_found = False
    for account in accounts:
        if account.is_primary and not primary_found:
            primary_found = True
        else:
            account.is_primary = account.is_primary and primary_found

    if accounts and not any(account.is_primary for account in accounts):
        accounts[0].is_primary = True

    return accounts


def _build_user_detail(user_id: str, user: Any, auth_service: APIAuthService) -> UserDetail:
    """Build UserDetail response from user object (DRY helper)."""
    # Use effective permissions which includes WA role inheritance
    # ROOT WA users get AUTHORITY permissions (including wa.resolve_deferral)
    permissions = auth_service.get_effective_permissions(user)
    api_keys = auth_service.list_user_api_keys(user_id)

    return UserDetail(
        user_id=user_id,
        username=user.name,
        auth_type=user.auth_type,
        api_role=user.api_role,
        wa_role=user.wa_role,
        wa_id=user.wa_id if user.wa_role else None,
        oauth_provider=user.oauth_provider,
        oauth_email=user.oauth_email,
        oauth_name=user.oauth_name,
        oauth_picture=user.oauth_picture,
        permission_requested_at=user.permission_requested_at,
        oauth_external_id=user.oauth_external_id,
        created_at=user.created_at,
        last_login=user.last_login,
        is_active=user.is_active,
        permissions=permissions,
        custom_permissions=user.custom_permissions,
        wa_parent_id=user.wa_parent_id,
        wa_auto_minted=user.wa_auto_minted,
        api_keys_count=len(api_keys),
        linked_oauth_accounts=_build_linked_accounts(user),
    )


class UpdateUserRequest(BaseModel):
    """Request to update user information."""

    api_role: Optional[APIRole] = None
    is_active: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    """Request to change user password."""

    current_password: str
    new_password: str


class LinkOAuthAccountRequest(BaseModel):
    """Request payload to link an OAuth account to a user."""

    provider: str = Field(..., description="OAuth provider identifier")
    external_id: str = Field(..., description="Provider-scoped user identifier")
    account_name: Optional[str] = Field(None, description="Display name provided by the provider")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata from the provider")
    primary: bool = Field(False, description="Promote this identity to the primary mapping")


class CreateUserRequest(BaseModel):
    """Request to create a new user."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    api_role: APIRole = APIRole.OBSERVER


class MintWARequest(BaseModel):
    """Request to mint user as Wise Authority."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"wa_role": "AUTHORITY", "signature": "base64_encoded_signature"}}
    )

    wa_role: WARole = Field(description="Role to grant: AUTHORITY or OBSERVER")
    signature: Optional[str] = Field(None, description="Ed25519 signature from ROOT private key")
    private_key_path: Optional[str] = Field(None, description="Path to ROOT private key for auto-signing")


class UpdatePermissionsRequest(BaseModel):
    """Request to update user's custom permissions."""

    model_config = ConfigDict(json_schema_extra={"example": {"permissions": ["send_messages", "custom_permission_1"]}})

    permissions: List[str] = Field(description="List of permission strings to grant")


class WAKeyCheckResponse(BaseModel):
    """Response for WA key existence check."""

    exists: bool = Field(..., description="Whether the key file exists")
    filename: str = Field(..., description="The filename that was checked")
    error: Optional[str] = Field(None, description="Error message if any")
    valid_size: Optional[bool] = Field(None, description="Whether the key has valid size (if exists)")
    size: Optional[int] = Field(None, description="File size in bytes (if exists)")


class DeactivateUserResponse(BaseModel):
    """Response for user deactivation."""

    message: str = Field(..., description="Success message")


class APIKeyInfo(BaseModel):
    """Information about an API key (masked for security)."""

    key_id: str = Field(..., description="Unique key identifier")
    masked_key: str = Field(..., description="Masked version of the key (e.g., 'ciris_****')")
    created_at: datetime = Field(..., description="When the key was created")
    last_used: Optional[datetime] = Field(None, description="When the key was last used")
    is_active: bool = Field(..., description="Whether the key is currently active")
    name: Optional[str] = Field(None, description="Optional name for the key")


class UserSettingsResponse(BaseModel):
    """User's personal settings (user-modifiable preferences)."""

    user_preferred_name: Optional[str] = Field(None, description="User's preferred display name")
    location: Optional[str] = Field(None, description="User's location preference")
    interaction_preferences: Optional[str] = Field(None, description="User's custom interaction preferences")
    marketing_opt_in: bool = Field(False, description="User consent for marketing communications")
    marketing_opt_in_source: Optional[str] = Field(None, description="Source of marketing consent (read-only)")


class UpdateUserSettingsRequest(BaseModel):
    """Request to update user's personal settings."""

    user_preferred_name: Optional[str] = Field(None, description="User's preferred display name")
    location: Optional[str] = Field(None, description="User's location preference")
    interaction_preferences: Optional[str] = Field(None, description="User's custom interaction preferences")
    marketing_opt_in: Optional[bool] = Field(None, description="User consent for marketing communications")


@router.get("", response_model=PaginatedResponse[UserSummary])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    auth_type: Optional[str] = None,
    api_role: Optional[APIRole] = None,
    wa_role: Optional[WARole] = None,
    is_active: Optional[bool] = None,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
    _: None = Depends(check_permissions([PERMISSION_USERS_READ])),
) -> PaginatedResponse[UserSummary]:
    """
    List all users with optional filtering.

    Requires: users.read permission (ADMIN or higher)
    """
    # Get all WA certificates from the auth service
    users = await auth_service.list_users(
        search=search, auth_type=auth_type, api_role=api_role, wa_role=wa_role, is_active=is_active
    )

    # Paginate results
    total = len(users)
    start = (page - 1) * page_size
    end = start + page_size

    # Convert to UserSummary objects
    items = []
    for user_id, user in users[start:end]:
        items.append(
            UserSummary(
                user_id=user_id,  # Use the actual user_id key, not wa_id
                username=user.name,
                auth_type=user.auth_type,
                api_role=user.api_role,
                wa_role=user.wa_role,
                wa_id=user.wa_id if user.wa_role else None,
                oauth_provider=user.oauth_provider,
                oauth_email=user.oauth_email,
                oauth_name=user.oauth_name,
                oauth_picture=user.oauth_picture,
                permission_requested_at=user.permission_requested_at,
                created_at=user.created_at,
                last_login=user.last_login,
                is_active=user.is_active,
                linked_oauth_accounts=_build_linked_accounts(user),
            )
        )

    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, pages=(total + page_size - 1) // page_size
    )


@router.post("", response_model=UserDetail)
async def create_user(
    request: CreateUserRequest,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
    _: None = Depends(check_permissions([PERMISSION_USERS_WRITE])),
) -> UserDetail:
    """
    Create a new user account.

    Requires: users.write permission (SYSTEM_ADMIN only)
    """
    # Check if username already exists
    existing = auth_service.get_user_by_username(request.username)
    if existing:
        raise HTTPException(status_code=400, detail=ERROR_USERNAME_EXISTS)

    # Create the user
    user = await auth_service.create_user(
        username=request.username, password=request.password, api_role=request.api_role
    )

    if not user:
        raise HTTPException(status_code=500, detail=ERROR_CREATE_USER_FAILED)

    # Return the created user details
    return await get_user(user.wa_id, auth, auth_service, None)


@router.post("/request-permissions", response_model=PermissionRequestResponse)
async def request_permissions(
    auth: AuthContext = Depends(get_auth_context), auth_service: APIAuthService = Depends(get_auth_service)
) -> PermissionRequestResponse:
    """
    Request communication permissions for the current user.

    Requires: Must be authenticated (any role)
    """
    from ciris_engine.schemas.api.auth import Permission, PermissionRequestResponse

    # Check if user already has SEND_MESSAGES permission
    if auth.has_permission(Permission.SEND_MESSAGES):
        return PermissionRequestResponse(
            success=True, status="already_granted", message="You already have communication permissions."
        )

    # Get the current user
    user = auth_service.get_user(auth.user_id)
    if not user:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    # Check if request already pending
    if user.permission_requested_at:
        return PermissionRequestResponse(
            success=True,
            status="already_requested",
            message="Your permission request is pending review.",
            requested_at=user.permission_requested_at,
        )

    # Set permission request timestamp
    user.permission_requested_at = datetime.now()
    # Store the updated user
    auth_service._users[user.wa_id] = user

    logger.info(f"Permission request submitted by user ID: {user.wa_id}")

    return PermissionRequestResponse(
        success=True,
        status="request_submitted",
        message="Your request has been submitted for review.",
        requested_at=user.permission_requested_at,
    )


@router.get("/permission-requests", response_model=List[PermissionRequestUser])
async def get_permission_requests(
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
    include_granted: bool = Query(False, description="Include users who already have permissions"),
) -> List[PermissionRequestUser]:
    """
    Get list of users who have requested permissions.

    Requires: ADMIN role or higher
    """
    from ciris_engine.schemas.api.auth import Permission, PermissionRequestUser

    logger.info(f"Permission requests called by {auth.user_id} with role {auth.role}")

    # Check permissions - require ADMIN or higher
    if auth.role not in [UserRole.ADMIN, UserRole.AUTHORITY, UserRole.SYSTEM_ADMIN]:
        logger.error(f"Insufficient permissions for user {auth.user_id} with role {auth.role}")
        raise HTTPException(status_code=403, detail="Insufficient permissions")

    permission_requests = []

    # Check all users for permission requests
    logger.info(f"Checking {len(auth_service._users)} users in _users dict")
    for user_id, user in auth_service._users.items():
        # Skip users without permission requests
        if not user.permission_requested_at:
            continue

        # Check if user has SEND_MESSAGES permission
        has_send_messages = Permission.SEND_MESSAGES.value in (user.custom_permissions or [])

        # Skip users who already have permissions unless include_granted is True
        if has_send_messages and not include_granted:
            continue

        # Add to results
        permission_requests.append(
            PermissionRequestUser(
                id=user.wa_id,
                email=user.oauth_email,
                oauth_name=user.oauth_name,
                oauth_picture=user.oauth_picture,
                role=UserRole.OBSERVER,  # OAuth users are always OBSERVER initially
                permission_requested_at=user.permission_requested_at,
                has_send_messages=has_send_messages,
            )
        )

    # Sort by request date (newest first)
    permission_requests.sort(key=lambda x: x.permission_requested_at, reverse=True)

    return permission_requests


@router.get("/me/settings", response_model=UserSettingsResponse)
async def get_my_settings(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> UserSettingsResponse:
    """
    Get the current user's personal settings.

    Requires: Must be authenticated (any role)
    """
    from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
    from ciris_engine.schemas.services.operations import MemoryQuery

    # Get the memory service from app state
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail="Memory service not available")

    try:
        # Query the user node from the graph
        user_query = MemoryQuery(
            node_id=f"user/{auth.user_id}",
            scope=GraphScope.LOCAL,
            type=NodeType.USER,
            include_edges=False,
            depth=1,
        )
        user_results = await memory_service.recall(user_query)

        if not user_results:
            # User node doesn't exist yet - return defaults
            return UserSettingsResponse()

        user_node = user_results[0]
        attrs = user_node.attributes if isinstance(user_node.attributes, dict) else {}

        # Extract user settings from node attributes
        return UserSettingsResponse(
            user_preferred_name=attrs.get("user_preferred_name"),
            location=attrs.get("location"),
            interaction_preferences=attrs.get("interaction_preferences"),
            marketing_opt_in=attrs.get("marketing_opt_in", False),
            marketing_opt_in_source=attrs.get("marketing_opt_in_source"),
        )

    except Exception as e:
        logger.error(f"Failed to retrieve user settings for {auth.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve user settings")


@router.put("/me/settings", response_model=UserSettingsResponse)
async def update_my_settings(
    http_request: Request,
    request: UpdateUserSettingsRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> UserSettingsResponse:
    """
    Update the current user's personal settings.

    Requires: Must be authenticated (any role)

    Note: This endpoint bypasses the MANAGED_USER_ATTRIBUTES protection
    because users are allowed to modify their own settings.
    """
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
    from ciris_engine.schemas.services.operations import MemoryQuery

    # Get the memory service from app state
    memory_service = getattr(http_request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail="Memory service not available")

    try:
        # Query the user node from the graph
        user_query = MemoryQuery(
            node_id=f"user/{auth.user_id}",
            scope=GraphScope.LOCAL,
            type=NodeType.USER,
            include_edges=False,
            depth=1,
        )
        user_results = await memory_service.recall(user_query)

        # Prepare attributes to update (only include fields that were provided)
        attrs_to_update: JSONDict = {}
        if request.user_preferred_name is not None:
            attrs_to_update["user_preferred_name"] = request.user_preferred_name
        if request.location is not None:
            attrs_to_update["location"] = request.location
        if request.interaction_preferences is not None:
            attrs_to_update["interaction_preferences"] = request.interaction_preferences
        if request.marketing_opt_in is not None:
            attrs_to_update["marketing_opt_in"] = request.marketing_opt_in
            # Update marketing_opt_in_source when user changes their preference
            attrs_to_update["marketing_opt_in_source"] = "settings_api"

        if user_results:
            # User node exists - update it
            user_node = user_results[0]
            existing_attrs = user_node.attributes if isinstance(user_node.attributes, dict) else {}

            # Merge existing attributes with updates
            updated_attrs = {**existing_attrs, **attrs_to_update}

            # Create updated node
            updated_node = GraphNode(
                id=f"user/{auth.user_id}",
                type=NodeType.USER,
                scope=GraphScope.LOCAL,
                attributes=updated_attrs,
            )

            # Save the updated node directly (bypassing MANAGED_USER_ATTRIBUTES check)
            await memory_service.memorize(updated_node, handler_name="UserSettingsAPI")

        else:
            # User node doesn't exist - create it with the settings
            new_node = GraphNode(
                id=f"user/{auth.user_id}",
                type=NodeType.USER,
                scope=GraphScope.LOCAL,
                attributes=attrs_to_update,
            )

            # Save the new node
            await memory_service.memorize(new_node, handler_name="UserSettingsAPI")

        # Return the updated settings
        final_attrs = {**attrs_to_update}
        if user_results:
            user_node = user_results[0]
            existing_attrs = user_node.attributes if isinstance(user_node.attributes, dict) else {}
            final_attrs = {**existing_attrs, **attrs_to_update}

        return UserSettingsResponse(
            user_preferred_name=final_attrs.get("user_preferred_name"),
            location=final_attrs.get("location"),
            interaction_preferences=final_attrs.get("interaction_preferences"),
            marketing_opt_in=final_attrs.get("marketing_opt_in", False),
            marketing_opt_in_source=final_attrs.get("marketing_opt_in_source"),
        )

    except Exception as e:
        logger.error(f"Failed to update user settings for {auth.user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user settings")


@router.get("/{user_id}", response_model=UserDetail)
async def get_user(
    user_id: str,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
    _: None = Depends(check_permissions([PERMISSION_USERS_READ])),
) -> UserDetail:
    """
    Get detailed information about a specific user.

    Requires: users.read permission (ADMIN or higher)
    """
    user = auth_service.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    return _build_user_detail(user_id, user, auth_service)


@router.put("/{user_id}", response_model=UserDetail)
async def update_user(
    user_id: str,
    request: UpdateUserRequest,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
    _: None = Depends(check_permissions([PERMISSION_USERS_WRITE])),
) -> UserDetail:
    """
    Update user information (role, active status).

    Requires: users.write permission (SYSTEM_ADMIN only)
    """
    # Prevent self-demotion
    if user_id == auth.user_id and request.api_role:
        if request.api_role.value < auth.role.value:
            raise HTTPException(status_code=400, detail=ERROR_CANNOT_DEMOTE_SELF)

    # Update user
    user = await auth_service.update_user(user_id=user_id, api_role=request.api_role, is_active=request.is_active)

    if not user:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    # Return updated user details
    return await get_user(user_id, auth, auth_service, None)


@router.put("/{user_id}/password")
async def change_password(
    user_id: str,
    request: ChangePasswordRequest,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> Dict[str, str]:
    """
    Change user password.

    Users can change their own password.
    SYSTEM_ADMIN can change any password without knowing current.
    """
    # Check permissions
    if user_id != auth.user_id:
        # Only SYSTEM_ADMIN can change other users' passwords
        await check_permissions([PERMISSION_USERS_WRITE])(auth, auth_service)
        # SYSTEM_ADMIN doesn't need to provide current password
        success = await auth_service.change_password(
            user_id=user_id, new_password=request.new_password, skip_current_check=True
        )
    else:
        # Users changing their own password must provide current
        success = await auth_service.change_password(
            user_id=user_id, new_password=request.new_password, current_password=request.current_password
        )

    if not success:
        raise HTTPException(status_code=400, detail=ERROR_CHANGE_PASSWORD_FAILED)

    return {"message": "Password changed successfully"}


@router.post("/{user_id}/oauth-links", response_model=UserDetail)
async def link_oauth_account(
    user_id: str,
    request: LinkOAuthAccountRequest,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> UserDetail:
    """
    Link an OAuth identity to an existing user.

    Users can link accounts to themselves without special permissions.
    Only SYSTEM_ADMIN can link accounts to other users.
    """
    # Check permissions: users can link to their own account, SYSTEM_ADMIN can link to any
    if user_id != auth.user_id:
        await check_permissions([PERMISSION_USERS_WRITE])(auth, auth_service)

    user = await auth_service.link_user_oauth(
        wa_id=user_id,
        provider=request.provider,
        external_id=request.external_id,
        account_name=request.account_name,
        metadata=request.metadata,
        primary=request.primary,
    )

    if not user:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    return _build_user_detail(user_id, user, auth_service)


@router.delete("/{user_id}/oauth-links/{provider}/{external_id}", response_model=UserDetail)
async def unlink_oauth_account(
    user_id: str,
    provider: str,
    external_id: str,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> UserDetail:
    """
    Remove a linked OAuth identity from a user.

    Users can unlink accounts from themselves without special permissions.
    Only SYSTEM_ADMIN can unlink accounts from other users.
    """
    # Check permissions: users can unlink from their own account, SYSTEM_ADMIN can unlink from any
    if user_id != auth.user_id:
        await check_permissions([PERMISSION_USERS_WRITE])(auth, auth_service)

    user = await auth_service.unlink_user_oauth(user_id, provider, external_id)
    if not user:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    return _build_user_detail(user_id, user, auth_service)


@router.post("/{user_id}/mint-wa", response_model=UserDetail)
async def mint_wise_authority(
    user_id: str,
    request: MintWARequest,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> UserDetail:
    """
    Mint a user as a Wise Authority.

    Requires: ADMIN role or higher and valid Ed25519 signature from ROOT private key.

    The signature should be over the message:
    "MINT_WA:{user_id}:{wa_role}:{timestamp}"

    If no signature is provided and private_key_path is specified, will attempt
    to sign automatically using the key at that path.
    """
    # Check if user is ADMIN or higher
    if auth.role.level < APIRole.ADMIN.level:
        raise HTTPException(status_code=403, detail=ERROR_ONLY_ADMIN_MINT_WA)

    # Validate that request.wa_role is not ROOT
    if request.wa_role == WARole.ROOT:
        raise HTTPException(status_code=400, detail=ERROR_CANNOT_MINT_ROOT)

    # If no signature provided but private key path is given, try to auto-sign
    signature = request.signature
    if not signature and request.private_key_path:
        # Auto-sign using the provided private key
        import base64
        import os

        from cryptography.hazmat.primitives.asymmetric import ed25519

        try:
            # Security: Validate the private key path
            # Only allow alphanumeric characters, dots, dashes, and underscores in filename
            import re

            if not request.private_key_path:
                raise HTTPException(status_code=400, detail="Private key path is required")

            # Extract just the filename, no path components allowed
            filename = os.path.basename(request.private_key_path)
            if not re.match(r"^[a-zA-Z0-9._-]+$", filename):
                raise HTTPException(
                    status_code=400,
                    detail="Invalid key filename. Only alphanumeric characters, dots, dashes, and underscores are allowed",
                )

            # Construct the safe path - no user input in directory path
            allowed_base = os.path.expanduser("~/.ciris/wa_keys/")
            safe_path = os.path.join(allowed_base, filename)

            # Double-check with realpath to prevent any symlink attacks
            resolved_path = os.path.realpath(safe_path)
            allowed_base_resolved = os.path.realpath(allowed_base)
            if not resolved_path.startswith(allowed_base_resolved):
                raise HTTPException(status_code=403, detail="Access denied: path traversal detected")

            # Read the private key
            async with aiofiles.open(resolved_path, "rb") as f:
                private_key_bytes = await f.read()

            # Create Ed25519 private key object
            private_key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key_bytes)

            # Sign the message
            message = f"MINT_WA:{user_id}:{request.wa_role.value}"
            signature_bytes = private_key.sign(message.encode())

            # Encode to base64
            signature = base64.b64encode(signature_bytes).decode()

            logger.info(f"Auto-signed WA mint request for {user_id} using key file: {filename}")

        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=f"Private key file not found: {filename}")
        except Exception as e:
            logger.error(f"Failed to auto-sign: {e}")
            raise HTTPException(status_code=500, detail="Failed to auto-sign with provided private key")

    if not signature:
        raise HTTPException(status_code=400, detail=ERROR_SIGNATURE_OR_KEY_REQUIRED)

    # Verify the ROOT signature
    verified = await auth_service.verify_root_signature(user_id=user_id, wa_role=request.wa_role, signature=signature)

    if not verified:
        raise HTTPException(status_code=401, detail=ERROR_INVALID_SIGNATURE)

    # Mint the user as WA
    user = await auth_service.mint_wise_authority(user_id=user_id, wa_role=request.wa_role, minted_by=auth.user_id)

    if not user:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    # Return updated user details
    return await get_user(user_id, auth, auth_service, None)


@router.get("/wa/key-check", response_model=WAKeyCheckResponse)
async def check_wa_key_exists(
    path: str = Query(..., description="Filename of private key to check"),
    auth: AuthContext = Depends(get_auth_context),
    _: None = Depends(check_permissions([PERMISSION_WA_MINT])),  # SYSTEM_ADMIN only
) -> WAKeyCheckResponse:
    """
    Check if a WA private key exists at the given filename.

    Requires: wa.mint permission (SYSTEM_ADMIN only)

    This is used by the UI to determine if auto-signing is available.
    Only checks files within ~/.ciris/wa_keys/ for security.
    """
    import os
    import re

    try:
        # Security: Validate the filename
        # Extract just the filename, no path components allowed
        filename = os.path.basename(path)
        if not re.match(r"^[a-zA-Z0-9._-]+$", filename):
            return WAKeyCheckResponse(
                exists=False,
                filename=filename,
                error="Invalid filename. Only alphanumeric characters, dots, dashes, and underscores are allowed",
            )

        # Construct the safe path - no user input in directory path
        allowed_base = os.path.expanduser("~/.ciris/wa_keys/")
        safe_path = os.path.join(allowed_base, filename)

        # Double-check with realpath to prevent any symlink attacks
        resolved_path = os.path.realpath(safe_path)
        allowed_base_resolved = os.path.realpath(allowed_base)
        if not resolved_path.startswith(allowed_base_resolved):
            return WAKeyCheckResponse(exists=False, filename=filename, error="Access denied: path traversal detected")

        # Check if file exists and is readable
        exists = os.path.isfile(resolved_path) and os.access(resolved_path, os.R_OK)

        # If exists, check if it's a valid key size (32 bytes for Ed25519)
        if exists:
            file_size = os.path.getsize(resolved_path)
            valid_size = file_size == 32  # Ed25519 private key is 32 bytes

            return WAKeyCheckResponse(exists=True, valid_size=valid_size, size=file_size, filename=filename)
        else:
            return WAKeyCheckResponse(exists=False, filename=filename)

    except Exception as e:
        logger.error(f"Error checking key file {filename}: {e}")
        return WAKeyCheckResponse(exists=False, error="Failed to check key file", filename=filename)


@router.delete("/{user_id}", response_model=DeactivateUserResponse)
async def deactivate_user(
    user_id: str,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
    _: None = Depends(check_permissions([PERMISSION_USERS_DELETE])),
) -> DeactivateUserResponse:
    """
    Deactivate a user account.

    Requires: users.delete permission (SYSTEM_ADMIN only)
    """
    # Prevent self-deactivation
    if user_id == auth.user_id:
        raise HTTPException(status_code=400, detail=ERROR_CANNOT_DEACTIVATE_SELF)

    success = await auth_service.deactivate_user(user_id)

    if not success:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    return DeactivateUserResponse(message="User deactivated successfully")


@router.get("/{user_id}/api-keys", response_model=List[APIKeyInfo])
async def list_user_api_keys(
    user_id: str,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> List[APIKeyInfo]:
    """
    List API keys for a user.

    Users can view their own keys.
    ADMIN+ can view any user's keys.
    """
    # Check permissions
    if user_id != auth.user_id:
        await check_permissions([PERMISSION_USERS_READ])(auth, auth_service)

    keys = auth_service.list_user_api_keys(user_id)

    # Mask the actual key values for security
    return [
        APIKeyInfo(
            key_id=key.key_id,
            masked_key=key.key_value[:8] + "****" if len(key.key_value) > 8 else "****",
            created_at=key.created_at,
            last_used=key.last_used,
            is_active=key.is_active,
            name=getattr(key, "name", None),
        )
        for key in keys
    ]


@router.put("/{user_id}/permissions", response_model=UserDetail)
async def update_user_permissions(
    user_id: str,
    request: UpdatePermissionsRequest,
    auth: AuthContext = Depends(get_auth_context),
    auth_service: APIAuthService = Depends(get_auth_service),
    _: None = Depends(check_permissions([PERMISSION_MANAGE_USER_PERMISSIONS])),
) -> UserDetail:
    """
    Update user's custom permissions.

    Requires: users.permissions permission (AUTHORITY or higher)

    This allows granting specific permissions to users beyond their role defaults.
    For example, granting SEND_MESSAGES permission to an OBSERVER.
    """
    # Update user permissions
    user = await auth_service.update_user_permissions(user_id=user_id, permissions=request.permissions)

    if not user:
        raise HTTPException(status_code=404, detail=ERROR_USER_NOT_FOUND)

    # Return updated user details
    return await get_user(user_id, auth, auth_service, None)
