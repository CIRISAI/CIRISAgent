"""Carry a call's PromptManifest to the LLM bus, and finish it there (FSD/PROMPT_CONTEXT_PROVENANCE.md §8, §10).

A stage that built its messages with ``PromptAssembler`` sends them inside ``prompt_manifest_scope(manifest)``.
The bus reads the manifest when it emits the ``llm_call`` reasoning event and attaches it as the event's
``context_manifest`` sidecar, finished with what only the bus knows:

- ``sent_messages_match``: whether the messages it sent are exactly the assembled ones (the differential check:
  a manifest that misdescribes its prompt, or a call that bypassed the assembler inside the scope, shows here);
- ``max_tokens_sent``;
- the provider library's own additions (#1363): instructor's JSON modes append a schema block to the first
  message after the bus hands the messages over, so the trace's ``prompt`` never contained it. It is reproduced
  here by running instructor's own request preparation on a copy of the messages, and recorded as
  ``schema_instruction`` segments with source ``provider_lib``.

A ContextVar, like ``buses/llm_call_context``: each asyncio task has its own, so concurrent stages never see
each other's manifest, and no LLM call signature changes.
"""

import copy
import hashlib
import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, List, Optional, Sequence, Tuple, Type

from pydantic import BaseModel

from ciris_engine.schemas.context.prompt_provenance import (
    Lifecycle,
    PromptManifest,
    ProviderCapture,
    SegmentKind,
    SegmentRecord,
    SegmentSource,
    TrustLevel,
)
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

_current_manifest: ContextVar[Optional[PromptManifest]] = ContextVar("_current_prompt_manifest", default=None)


def messages_text(messages: Sequence[JSONDict]) -> str:
    """The messages as the LLM bus serializes them for ``prompt`` / ``prompt_hash`` (llm_bus._safe_messages_to_text)."""
    try:
        return json.dumps(list(messages), ensure_ascii=False, sort_keys=False)
    except (TypeError, ValueError):
        return repr(list(messages))


def messages_sha256(messages: Sequence[JSONDict]) -> str:
    """The bus's ``prompt_hash`` of a messages list."""
    return hashlib.sha256(messages_text(messages).encode("utf-8")).hexdigest()


@contextmanager
def prompt_manifest_scope(manifest: PromptManifest) -> Iterator[None]:
    """Bind ``manifest`` to every LLM call issued inside the block."""
    token = _current_manifest.set(manifest)
    try:
        yield
    finally:
        _current_manifest.reset(token)


def current_prompt_manifest() -> Optional[PromptManifest]:
    """The manifest bound by the innermost ``prompt_manifest_scope``, or None."""
    return _current_manifest.get()


#: instructor modes whose request preparation only edits the OpenAI-style ``messages`` list (or adds kwargs).
_OPENAI_FAMILY_MODES = frozenset({"json_mode", "markdown_json_mode", "json_schema_mode", "tool_call", "tools_strict"})


def _content_text(message: JSONDict) -> Optional[str]:
    content = message.get("content")
    return content if isinstance(content, str) else None


def _diff_messages(
    before: List[JSONDict], after: List[JSONDict]
) -> Optional[List[Tuple[int, int, int, str]]]:
    """(message_index, start, end, text) for each addition; None if the change is not a pure addition."""
    additions: List[Tuple[int, int, int, str]] = []
    offset = 0
    if len(after) == len(before) + 1 and after[1:] == before:
        added = _content_text(after[0])
        if added is None:
            return None
        additions.append((0, 0, len(added), added))
        offset = 1
    elif len(after) < len(before):
        return None
    for i, old in enumerate(before):
        new = after[i + offset]
        if new == old:
            continue
        old_text, new_text = _content_text(old), _content_text(new)
        if old_text is None or new_text is None or not new_text.startswith(old_text):
            return None
        if {k: v for k, v in new.items() if k != "content"} != {k: v for k, v in old.items() if k != "content"}:
            return None
        additions.append((i + offset, len(old_text), len(new_text), new_text[len(old_text) :]))
    for j in range(len(before) + offset, len(after)):
        added = _content_text(after[j])
        if added is None:
            return None
        additions.append((j, 0, len(added), added))
    return additions


def _instructor_mode(selected_service: Any) -> Optional[Any]:
    client = getattr(selected_service, "instruct_client", None)
    return getattr(client, "mode", None)


def capture_provider_additions(
    messages: List[JSONDict], response_model: Type[BaseModel], mode: Any
) -> Tuple[ProviderCapture, List[SegmentRecord], List[str]]:
    """What instructor adds to a request in ``mode``: (capture status, schema_instruction records, added kwargs)."""
    mode_value = getattr(mode, "value", None)
    if mode_value not in _OPENAI_FAMILY_MODES:
        return ProviderCapture.UNSUPPORTED_MODE, [], []
    try:
        from instructor.processing.response import handle_response_model
    except ImportError:
        return ProviderCapture.UNAVAILABLE, [], []
    before = copy.deepcopy(messages)
    _, prepared = handle_response_model(response_model, mode, messages=copy.deepcopy(messages))
    after = prepared.get("messages", before)
    kwargs_added = sorted(k for k in prepared if k != "messages")
    if after == before:
        return ProviderCapture.NO_MESSAGE_CHANGE, [], kwargs_added
    additions = _diff_messages(before, after)
    if additions is None:
        return ProviderCapture.UNRECOGNIZED_CHANGE, [], kwargs_added
    records = [
        SegmentRecord(
            segment_id=f"provider_lib:{mode_value}:{n}",
            kind=SegmentKind.SCHEMA_INSTRUCTION,
            source=SegmentSource.PROVIDER_LIB,
            trust=TrustLevel.SYSTEM,
            lifecycle=Lifecycle.PER_CALL,
            message_index=index,
            span_start=start,
            span_end=end,
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
        for n, (index, start, end, text) in enumerate(additions)
    ]
    return ProviderCapture.CAPTURED, records, kwargs_added


def finalize_manifest_for_call(
    manifest: PromptManifest,
    *,
    messages: List[JSONDict],
    response_model: Type[BaseModel],
    selected_service: Any,
    max_tokens_sent: Optional[int],
) -> PromptManifest:
    """The manifest as sent: the bus's differential check, max_tokens and the provider library's additions."""
    update: dict[str, object] = {
        "sent_messages_match": messages_sha256(messages) == manifest.messages_sha256
        and response_model.__name__ == manifest.response_model,
        "max_tokens_sent": max_tokens_sent,
    }
    mode = _instructor_mode(selected_service)
    if mode is None:
        update["provider_capture"] = ProviderCapture.UNAVAILABLE
    else:
        update["provider_mode"] = str(getattr(mode, "value", mode))
        try:
            status, records, kwargs_added = capture_provider_additions(messages, response_model, mode)
        except Exception as exc:  # noqa: BLE001 - the trace must never break the call
            logger.warning("[PROMPT-MANIFEST] provider capture failed: %r", exc)
            status, records, kwargs_added = ProviderCapture.UNAVAILABLE, [], []
        update["provider_capture"] = status
        update["provider_kwargs_added"] = kwargs_added
        update["segments"] = list(manifest.segments) + records
    return manifest.model_copy(update=update)


__all__ = [
    "capture_provider_additions",
    "current_prompt_manifest",
    "finalize_manifest_for_call",
    "messages_sha256",
    "messages_text",
    "prompt_manifest_scope",
]
