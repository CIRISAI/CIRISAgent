"""Build segments and AAA carriers from the records the engine already keeps (FSD/PROMPT_CONTEXT_PROVENANCE.md §4.5).

The sender's identity comes from :class:`VerifiedSender` (built by the observer from adapter fields, never from
message text, #1366 item 5); a WA grant from :class:`WAAuthorization` (issued only on a verified signature).
"""

from typing import List

from ciris_engine.schemas.context.prompt_provenance import (
    AuthnCarrier,
    AuthzCarrier,
    GrantKind,
    PromptSegment,
    SegmentKind,
    SegmentSource,
)
from ciris_engine.schemas.runtime.models import VerifiedSender, WAAuthorization


def sender_segments(sender: VerifiedSender, *, id_prefix: str = "sender") -> List[PromptSegment]:
    """``sender_identity`` (only when something verified the id) and a separate ``display_name``."""
    segments: List[PromptSegment] = []
    if sender.user_id and sender.source != "unverified":
        segments.append(
            PromptSegment(
                segment_id=f"{id_prefix}:identity",
                kind=SegmentKind.SENDER_IDENTITY,
                source=SegmentSource.AUTH_CONTEXT if sender.role is not None else SegmentSource.ADAPTER_METADATA,
                authn=AuthnCarrier(
                    subject_id=sender.user_id,
                    role=sender.role.value if sender.role is not None else "not verified",
                    verifier=sender.source,
                ),
            )
        )
    if sender.self_chosen_display_name:
        segments.append(
            PromptSegment(
                segment_id=f"{id_prefix}:display_name",
                kind=SegmentKind.DISPLAY_NAME,
                source=SegmentSource.ADAPTER_METADATA,
                text=sender.self_chosen_display_name,
            )
        )
    return segments


def authz_from_wa_authorization(grant: WAAuthorization) -> AuthzCarrier:
    """The authz carrier of a verified WA approval (its deferral is the grant)."""
    return AuthzCarrier(
        grant_kind=GrantKind.DEFERRAL,
        grant_id=grant.deferral_id,
        authorizer_id=grant.wa_id,
        signature_verified=grant.verification == "verified",
        attestation_ids=[a for a in (grant.request_attestation_id, grant.response_attestation_id) if a],
        granted_at=grant.granted_at,
    )


__all__ = ["authz_from_wa_authorization", "sender_segments"]
