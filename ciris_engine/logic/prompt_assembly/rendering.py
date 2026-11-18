"""Localized rendering of the segments the assembler builds from carriers (FSD/PROMPT_CONTEXT_PROVENANCE.md §6).

``sender_identity`` carries no text: its bytes are built here from the ``authn`` carrier alone, through the same
formatter lines the VERIFIED SENDER block has always used, so a migrated prompt is byte-identical to its legacy
form. ``display_name`` renders as the block's labelled self-chosen line.
"""

from typing import Optional

from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.context.prompt_provenance import AuthnCarrier
from ciris_engine.schemas.runtime.models import VerifiedSender

#: The role an authn carrier states when the adapter verified an id but no role.
ROLE_NOT_VERIFIED = "not verified"


def sender_from_authn(authn: AuthnCarrier) -> VerifiedSender:
    """The VerifiedSender an authn carrier was built from (``carriers.sender_identity_authn``)."""
    role: Optional[UserRole] = None
    if authn.role != ROLE_NOT_VERIFIED:
        role = UserRole(authn.role)
    user_id = None if authn.subject_id == "unknown" else authn.subject_id
    return VerifiedSender(user_id=user_id, role=role, source=authn.verifier)


def render_sender_identity_lines(authn: Optional[AuthnCarrier], language: str) -> str:
    """The VERIFIED SENDER header, id, role and source lines, from the carrier alone."""
    from ciris_engine.logic.formatters.verified_sender import sender_identity_lines

    if authn is None:  # the guard strips a sender_identity without authn before rendering
        return ""
    # From the carrier's own values, so a system sender (role SYSTEM, not a UserRole) renders as stated.
    user_id = None if authn.subject_id == "unknown" else authn.subject_id
    role = None if authn.role == ROLE_NOT_VERIFIED else authn.role
    return "\n".join(sender_identity_lines(user_id, role, authn.verifier, language))


def render_display_name_line(display_name: str, language: str) -> str:
    """The display name, sanitised and labelled as self-chosen, not identity."""
    from ciris_engine.logic.formatters.verified_sender import verified_sender_display_name_line

    return verified_sender_display_name_line(display_name, language)


__all__ = ["ROLE_NOT_VERIFIED", "render_display_name_line", "render_sender_identity_lines", "sender_from_authn"]
