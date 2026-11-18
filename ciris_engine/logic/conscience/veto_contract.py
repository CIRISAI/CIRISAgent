"""The decision contract between consciences and the retry (CIRISAgent#1366 items 7-9).

Pure helpers the conscience fold and the retry path share:

* ``action_fingerprint`` -- what "the same action" means for the ban: the verb,
  the tool name, and a hash of the normalized arguments (TOOL) or speak text
  (SPEAK). Whitespace never makes two drafts different; for SPEAK neither does
  case.
* ``trusted_evidence_ids`` / ``held_evidence_ids`` -- the trusted Wise Authority
  state a task carries (the signed ``WAAuthorization`` of a resolved deferral,
  approved identity amendments) and the part of it a given conscience was
  shown. Built only from that state (``formatters.wa_approval``), never from
  message text: a WA rule stated in chat is advisory (FSD
  PROMPT_CONTEXT_PROVENANCE §15.1), and the drafter's argument never
  discharges an evidence objection.
* ``banned_entry_for`` -- the ban: a substantive veto, or an evidence veto no
  trusted state discharged, on an identical fingerprint in this task.
* ``format_prior_vetoes_block`` -- the record as the drafters read it, on a
  retry and on a follow-up thought.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, List, Optional

from pydantic import BaseModel

from ciris_engine.logic.formatters.wa_approval import approved_amendments_of, wa_authorization_of
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import WAAuthorization
from ciris_engine.schemas.runtime.veto_record import ObjectionType, VetoRecordEntry

#: The record key in a thought's conscience feedback (the dict the retry path
#: stores on the queue item; ``dma.conscience_feedback`` renders its
#: ``retry_guidance``). The record rides beside it so the fold of the next pass
#: sees vetoes a failed task write would otherwise lose.
VETO_RECORD_FEEDBACK_KEY = "veto_record"

#: How many earlier vetoes the drafters are shown (most recent last).
MAX_PRIOR_VETOES_SHOWN = 8
_REASON_CHARS = 300


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    return value


def _params_dict(params: Any) -> dict[str, Any]:
    if isinstance(params, BaseModel):
        dumped = params.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(params, dict):
        return dict(params)
    return {}


def action_fingerprint(action: Any) -> str:
    """``verb:tool:hash`` for a draft (#1366 item 8).

    SPEAK hashes the speak text (whitespace collapsed, case folded); TOOL hashes
    the tool's arguments (whitespace collapsed inside strings, keys sorted);
    any other verb hashes its parameters without the channel routing fields.
    """
    verb_obj = getattr(action, "selected_action", None)
    verb = verb_obj.value if isinstance(verb_obj, HandlerActionType) else str(verb_obj or "unknown")
    params = _params_dict(getattr(action, "action_parameters", None))
    tool = ""
    if verb_obj == HandlerActionType.SPEAK:
        body = " ".join(str(params.get("content", "")).split()).casefold()
    elif verb_obj == HandlerActionType.TOOL:
        tool = str(params.get("name", ""))
        body = json.dumps(_normalize(params.get("parameters") or {}), sort_keys=True, ensure_ascii=False, default=str)
    else:
        routed = {k: v for k, v in params.items() if k not in ("channel_id", "channel_context")}
        body = json.dumps(_normalize(routed), sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return f"{verb}:{tool}:{digest}"


def authorization_evidence_id(authorization: WAAuthorization) -> str:
    """The id a signed WA authorization is cited by: its response attestation, else its deferral."""
    return authorization.response_attestation_id or authorization.deferral_id


def _amendment_ids(context: Any) -> List[str]:
    """Approved amendment node ids; none when the identity is not a readable identity."""
    try:
        return [a.node_id for a in approved_amendments_of(getattr(context, "agent_identity", None))]
    except TypeError:  # an identity whose amendments are not a list carries none we can verify
        return []


def trusted_evidence_ids(context: Any) -> List[str]:
    """Ids of every trusted governance entry the task carries: the signed grant, then the amendments."""
    ids: List[str] = []
    authorization = wa_authorization_of(context)
    if authorization is not None:
        ids.append(authorization_evidence_id(authorization))
    ids.extend(_amendment_ids(context))
    return ids


def held_evidence_ids(context: Any, *, sees_governance: bool) -> List[str]:
    """The trusted governance ids a conscience was shown.

    Every conscience reads the identity block, approved amendments included.
    Only a conscience shown the verified governance block (entropy and the
    optimization veto always; coherence and epistemic humility only when the
    system attaches it on re-review) also holds the signed grant.
    """
    amendments = _amendment_ids(context)
    if not sees_governance:
        return amendments
    authorization = wa_authorization_of(context)
    return ([authorization_evidence_id(authorization)] if authorization is not None else []) + amendments


def _entries(raw: Any) -> List[VetoRecordEntry]:
    entries: List[VetoRecordEntry] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, VetoRecordEntry):
            entries.append(item)
        elif isinstance(item, dict):
            try:
                entries.append(VetoRecordEntry.model_validate(item))
            except Exception:  # noqa: BLE001 - an unreadable entry is not a veto
                continue
    return entries


def veto_entries_of_feedback(feedback: Any) -> List[VetoRecordEntry]:
    """The veto record a thought's conscience feedback carries (dict or object form)."""
    if feedback is None:
        return []
    raw = feedback.get(VETO_RECORD_FEEDBACK_KEY) if isinstance(feedback, dict) else getattr(feedback, VETO_RECORD_FEEDBACK_KEY, None)
    return _entries(raw)


def veto_entries_of_task(task: Any) -> List[VetoRecordEntry]:
    """The veto record a task carries."""
    return _entries(getattr(task, "veto_record", None))


def merge_veto_entries(*records: Iterable[VetoRecordEntry]) -> List[VetoRecordEntry]:
    """One record, first-seen order, deduplicated by ``veto_id`` (a later copy wins: it may be discharged)."""
    by_id: dict[str, VetoRecordEntry] = {}
    for record in records:
        for entry in record:
            by_id[entry.veto_id] = entry
    return list(by_id.values())


def banned_entry_for(
    fingerprint: str, entries: Iterable[VetoRecordEntry], available_evidence_ids: Iterable[str] = ()
) -> Optional[VetoRecordEntry]:
    """The recorded veto that bans this exact draft, if any.

    A banned evidence veto stops applying once trusted state holds evidence the
    objecting conscience did not have (a WA has since signed): the draft then
    goes back to the consciences, and the discharge is recorded there. A
    substantive veto is never discharged by evidence.
    """
    available = set(available_evidence_ids)
    for entry in entries:
        if entry.action_fingerprint != fingerprint or not entry.banned or entry.discharged_by:
            continue
        if entry.objection_type == ObjectionType.EVIDENCE and available - set(entry.held_evidence_ids):
            continue
        return entry
    return None


def format_prior_vetoes_block(entries: List[VetoRecordEntry], language: str) -> str:
    """The task's vetoes as the drafters read them; "" when there are none."""
    if not entries:
        return ""
    from ciris_engine.logic.utils.localization import get_string

    lines = [get_string(language, "conscience.prior_vetoes_header")]
    for entry in entries[-MAX_PRIOR_VETOES_SHOWN:]:
        status = (
            get_string(language, "conscience.veto_status_banned")
            if entry.banned
            else get_string(language, "conscience.veto_status_open")
        )
        lines.append(
            get_string(
                language,
                "conscience.prior_veto_line",
                action=entry.action_summary or entry.action_fingerprint,
                conscience=entry.conscience,
                objection_type=entry.objection_type.value,
                status=status,
                # Last: free text, never re-read as a placeholder.
                reason=(entry.reason or "-")[:_REASON_CHARS],
            )
        )
    return "\n".join(lines)


__all__ = [
    "MAX_PRIOR_VETOES_SHOWN",
    "VETO_RECORD_FEEDBACK_KEY",
    "action_fingerprint",
    "authorization_evidence_id",
    "banned_entry_for",
    "format_prior_vetoes_block",
    "held_evidence_ids",
    "merge_veto_entries",
    "trusted_evidence_ids",
    "veto_entries_of_feedback",
    "veto_entries_of_task",
]
