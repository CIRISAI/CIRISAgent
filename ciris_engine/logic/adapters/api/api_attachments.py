"""Inline attachments on `/v1/agent/interact`: one gate, and an outcome for every file.

Every image and document a client attaches gets an :class:`AttachmentOutcome`:
accepted, or refused with a stable :class:`AttachmentRefusalReason` the client
renders. Before this, a file that was too large, of an unparsed type, or
unreadable was dropped with a log line only. The agent answered as if nothing
had been attached, and the user saw an agent that "can't see my file".

A refused file is also named to the agent (:func:`refusal_note`), so its reply
can say the file could not be read instead of carrying on without it.

The type is taken from the bytes, not the label: the declared media type must
match the sniffed signature (CIRISClient FSD/MEDIA_EDGE.md §9.4 rule 3). A
mismatch is a refusal, never a correction.

This is the interim inline path. Large files and drive-backed attachments
arrive with the migration to substrate-native agent chat (CIRISAgent#1300),
which retires this module.
"""

from __future__ import annotations

import base64
import binascii
import logging
from enum import Enum
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from ciris_engine.logic.adapters.api.api_document import get_api_document_helper
from ciris_engine.logic.adapters.api.api_vision import get_api_vision_helper
from ciris_engine.logic.adapters.document_parser import ExtractionRefused
from ciris_engine.schemas.runtime.models import ImageContent

logger = logging.getLogger(__name__)

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
TEXT_PLAIN = "text/plain"
TEXT_MARKDOWN = "text/markdown"
TEXT_CSV = "text/csv"

IMAGE_TYPES: Tuple[str, ...] = ("image/jpeg", "image/png", "image/gif", "image/webp")
DOCUMENT_TYPES: Tuple[str, ...] = (PDF, DOCX, TEXT_PLAIN, TEXT_MARKDOWN, TEXT_CSV)
TEXT_TYPES = frozenset({TEXT_PLAIN, TEXT_MARKDOWN, TEXT_CSV})

#: Per-file and per-message limits. The client's picker allows 10 MB and 5
#: attachments (CIRISClient PickedFile); these match it, so a file the client
#: lets through is not refused here for size or count.
IMAGE_MAX_BYTES = 20 * 1024 * 1024
DOCUMENT_MAX_BYTES = 10 * 1024 * 1024
MAX_IMAGES = 5
MAX_DOCUMENTS = 5
#: All extracted document text, combined, that goes into the message.
MAX_EXTRACTED_CHARS = 50_000

_EXTENSION_TYPES = {
    ".pdf": PDF,
    ".docx": DOCX,
    ".txt": TEXT_PLAIN,
    ".md": TEXT_MARKDOWN,
    ".markdown": TEXT_MARKDOWN,
    ".csv": TEXT_CSV,
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
#: Labels that say nothing about the type. The filename's extension decides
#: instead, and the bytes must still agree.
_UNINFORMATIVE_TYPES = frozenset({"", "application/octet-stream", "binary/octet-stream"})


class AttachmentKind(str, Enum):
    IMAGE = "image"
    DOCUMENT = "document"


class AttachmentStatus(str, Enum):
    ACCEPTED = "accepted"
    REFUSED = "refused"


class AttachmentRefusalReason(str, Enum):
    """Why a file was not given to the agent. Stable ids: the client localizes them."""

    #: Over the per-file limit for its kind (`limit_bytes`).
    TOO_LARGE = "too_large"
    #: Beyond the per-message count for its kind.
    TOO_MANY = "too_many"
    #: A type the agent does not read (`policy.image_types` / `policy.document_types`).
    UNSUPPORTED_TYPE = "unsupported_type"
    #: The bytes are not what the label says (MEDIA_EDGE §9.4 rule 3).
    TYPE_MISMATCH = "type_mismatch"
    #: Not valid base64, a corrupt file, or text that is not UTF-8.
    UNREADABLE = "unreadable"
    #: Readable, but no text came out of it (a scanned PDF, an empty file).
    NO_TEXT = "no_text"
    #: This build cannot parse the type (its parser library is missing).
    PARSER_UNAVAILABLE = "parser_unavailable"
    #: The combined text limit was already used up by earlier documents.
    TEXT_LIMIT_REACHED = "text_limit_reached"


class AttachmentOutcome(BaseModel):
    """What happened to one attached file."""

    index: int = Field(..., description="Position of the file within its list (images[] or documents[])")
    kind: AttachmentKind
    filename: Optional[str] = None
    media_type: str = Field(..., description="The type the agent decided on (declared, or from the extension)")
    status: AttachmentStatus
    reason: Optional[AttachmentRefusalReason] = Field(None, description="Set when refused")
    size_bytes: Optional[int] = Field(None, description="Decoded size, when known")
    limit_bytes: Optional[int] = Field(None, description="The per-file limit, when the reason is too_large")
    extracted_chars: Optional[int] = Field(None, description="Characters of text given to the agent (documents)")
    truncated: bool = Field(False, description="The document's text was cut at the combined text limit")


class AttachmentPolicy(BaseModel):
    """The limits this agent applies, so a client can refuse up front instead of hard-coding."""

    image_types: List[str]
    image_max_bytes: int
    max_images: int
    document_types: List[str] = Field(..., description="Types this build can read right now")
    document_max_bytes: int
    max_documents: int
    max_extracted_chars: int


class ProcessedAttachments(BaseModel):
    images: List[ImageContent] = Field(default_factory=list)
    document_text: str = ""
    outcomes: List[AttachmentOutcome] = Field(default_factory=list)


def _readable_document_types() -> List[str]:
    parser = get_api_document_helper()._parser
    readable = [TEXT_PLAIN, TEXT_MARKDOWN, TEXT_CSV]
    if getattr(parser, "_pdf_available", False):
        readable.insert(0, PDF)
    if getattr(parser, "_docx_available", False):
        readable.insert(1 if PDF in readable else 0, DOCX)
    return readable


def attachment_policy() -> AttachmentPolicy:
    return AttachmentPolicy(
        image_types=list(IMAGE_TYPES),
        image_max_bytes=IMAGE_MAX_BYTES,
        max_images=MAX_IMAGES,
        document_types=_readable_document_types(),
        document_max_bytes=DOCUMENT_MAX_BYTES,
        max_documents=MAX_DOCUMENTS,
        max_extracted_chars=MAX_EXTRACTED_CHARS,
    )


def _sniff(data: bytes) -> Optional[str]:
    """The type the leading bytes say, for the formats this gate accepts. None = no signature."""
    if data.startswith(b"%PDF-"):
        return PDF
    if data.startswith(b"PK\x03\x04"):
        return "application/zip"  # DOCX is a ZIP; the parser checks the member layout
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _signature_matches(declared: str, data: bytes) -> bool:
    sniffed = _sniff(data)
    if declared == DOCX:
        return sniffed == "application/zip"
    if declared in TEXT_TYPES:
        return sniffed is None  # text has no signature, and must not carry a binary one
    return sniffed == declared


def _resolve_type(declared: Optional[str], filename: Optional[str]) -> str:
    media_type = (declared or "").split(";", 1)[0].strip().lower()
    if media_type in _UNINFORMATIVE_TYPES and filename:
        return _EXTENSION_TYPES.get(Path(filename).suffix.lower(), media_type)
    return media_type


def _split_data_url(data: str, media_type: str) -> Tuple[str, str]:
    if data.startswith("data:") and "," in data:
        header, payload = data.split(",", 1)
        if ";" in header:
            media_type = header[5:].split(";", 1)[0].strip().lower() or media_type
        return payload, media_type
    return data, media_type


def _decoded_size_estimate(b64: str) -> int:
    return (len(b64) * 3) // 4


def _decode(b64: str) -> Optional[bytes]:
    try:
        return base64.b64decode(b64, validate=False)
    except (binascii.Error, ValueError):
        return None


def _is_url(data: str) -> bool:
    return data.startswith(("http://", "https://"))


def _refused(index: int, kind: AttachmentKind, filename: Optional[str], media_type: str,
             reason: AttachmentRefusalReason, size: Optional[int] = None, limit: Optional[int] = None) -> AttachmentOutcome:
    logger.warning("[ATTACHMENT] refused %s #%d %r (%s): %s", kind.value, index, filename, media_type, reason.value)
    return AttachmentOutcome(index=index, kind=kind, filename=filename, media_type=media_type,
                             status=AttachmentStatus.REFUSED, reason=reason, size_bytes=size, limit_bytes=limit)


def _process_image(index: int, data: str, declared: Optional[str], filename: Optional[str]
                   ) -> Tuple[Optional[ImageContent], AttachmentOutcome]:
    kind = AttachmentKind.IMAGE
    media_type = _resolve_type(declared, filename)
    if _is_url(data):
        if media_type not in IMAGE_TYPES:
            return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.UNSUPPORTED_TYPE)
        content = get_api_vision_helper().process_image_payload(data, media_type, filename)
        if content is None:
            return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.UNREADABLE)
        return content, AttachmentOutcome(index=index, kind=kind, filename=filename, media_type=media_type,
                                          status=AttachmentStatus.ACCEPTED)

    payload, media_type = _split_data_url(data, media_type)
    if media_type not in IMAGE_TYPES:
        return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.UNSUPPORTED_TYPE)
    if _decoded_size_estimate(payload) > IMAGE_MAX_BYTES + 3:
        return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.TOO_LARGE,
                              _decoded_size_estimate(payload), IMAGE_MAX_BYTES)
    raw = _decode(payload)
    if not raw:
        return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.UNREADABLE)
    if len(raw) > IMAGE_MAX_BYTES:
        return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.TOO_LARGE, len(raw), IMAGE_MAX_BYTES)
    if not _signature_matches(media_type, raw):
        return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.TYPE_MISMATCH, len(raw))
    content = get_api_vision_helper().bytes_to_image_content(raw, media_type, filename)
    if content is None:
        return None, _refused(index, kind, filename, media_type, AttachmentRefusalReason.UNREADABLE, len(raw))
    return content, AttachmentOutcome(index=index, kind=kind, filename=filename, media_type=media_type,
                                      status=AttachmentStatus.ACCEPTED, size_bytes=len(raw))


def _extract_text(raw: bytes, media_type: str) -> Tuple[Optional[str], Optional[AttachmentRefusalReason]]:
    if media_type in TEXT_TYPES:
        if b"\x00" in raw:
            return None, AttachmentRefusalReason.UNREADABLE
        try:
            return raw.decode("utf-8-sig"), None
        except UnicodeDecodeError:
            return None, AttachmentRefusalReason.UNREADABLE
    parser = get_api_document_helper()._parser
    try:
        if media_type == PDF:
            return parser.extract_pdf_text_strict(raw), None
        return parser.extract_docx_text_strict(raw), None
    except ExtractionRefused as e:
        return None, _EXTRACTION_REASONS.get(e.reason, AttachmentRefusalReason.UNREADABLE)


_EXTRACTION_REASONS = {
    ExtractionRefused.PARSER_UNAVAILABLE: AttachmentRefusalReason.PARSER_UNAVAILABLE,
    ExtractionRefused.TOO_LARGE: AttachmentRefusalReason.TOO_LARGE,
    ExtractionRefused.NO_TEXT: AttachmentRefusalReason.NO_TEXT,
    ExtractionRefused.UNREADABLE: AttachmentRefusalReason.UNREADABLE,
}


async def _document_text(data: str, media_type: str, filename: Optional[str]
                         ) -> Tuple[Optional[str], Optional[int], Optional[AttachmentRefusalReason]]:
    """(text, decoded size, refusal). Exactly one of text / refusal is set."""
    if _is_url(data):
        text = await get_api_document_helper().process_url_document(data, media_type, filename)
        return (text, None, None) if text else (None, None, AttachmentRefusalReason.UNREADABLE)
    if _decoded_size_estimate(data) > DOCUMENT_MAX_BYTES + 3:
        return None, _decoded_size_estimate(data), AttachmentRefusalReason.TOO_LARGE
    raw = _decode(data)
    if raw is None:
        return None, None, AttachmentRefusalReason.UNREADABLE
    if len(raw) > DOCUMENT_MAX_BYTES:
        return None, len(raw), AttachmentRefusalReason.TOO_LARGE
    if not raw:
        return None, 0, AttachmentRefusalReason.NO_TEXT
    if not _signature_matches(media_type, raw):
        return None, len(raw), AttachmentRefusalReason.TYPE_MISMATCH
    text, refusal = _extract_text(raw, media_type)
    if refusal:
        return None, len(raw), refusal
    if not text or not text.strip():
        return None, len(raw), AttachmentRefusalReason.NO_TEXT
    return text, len(raw), None


async def process_attachments(images: Sequence[Tuple[str, Optional[str], Optional[str]]],
                              documents: Sequence[Tuple[str, Optional[str], Optional[str]]]) -> ProcessedAttachments:
    """Gate every attached file. Each entry is (data, media_type, filename)."""
    result = ProcessedAttachments()

    for index, (data, declared, filename) in enumerate(images):
        if index >= MAX_IMAGES:
            result.outcomes.append(_refused(index, AttachmentKind.IMAGE, filename, _resolve_type(declared, filename),
                                            AttachmentRefusalReason.TOO_MANY))
            continue
        content, outcome = _process_image(index, data or "", declared, filename)
        if content is not None:
            result.images.append(content)
        result.outcomes.append(outcome)

    sections: List[str] = []
    budget = MAX_EXTRACTED_CHARS
    for index, (data, declared, filename) in enumerate(documents):
        kind = AttachmentKind.DOCUMENT
        media_type = _resolve_type(declared, filename)
        data = data or ""
        if not _is_url(data):
            data, media_type = _split_data_url(data, media_type)
        if index >= MAX_DOCUMENTS:
            result.outcomes.append(_refused(index, kind, filename, media_type, AttachmentRefusalReason.TOO_MANY))
            continue
        if media_type not in DOCUMENT_TYPES:
            result.outcomes.append(_refused(index, kind, filename, media_type, AttachmentRefusalReason.UNSUPPORTED_TYPE))
            continue
        if budget <= 0:
            result.outcomes.append(_refused(index, kind, filename, media_type, AttachmentRefusalReason.TEXT_LIMIT_REACHED))
            continue
        text, size, refusal = await _document_text(data, media_type, filename)
        if refusal or text is None:
            limit = DOCUMENT_MAX_BYTES if refusal == AttachmentRefusalReason.TOO_LARGE else None
            result.outcomes.append(_refused(index, kind, filename, media_type,
                                            refusal or AttachmentRefusalReason.UNREADABLE, size, limit))
            continue
        truncated = len(text) > budget
        if truncated:
            text = text[:budget]
        budget -= len(text)
        sections.append(f"Document '{filename or f'document {index + 1}'}':\n{text}"
                        + ("\n\n[Text truncated at the attachment text limit]" if truncated else ""))
        result.outcomes.append(AttachmentOutcome(index=index, kind=kind, filename=filename, media_type=media_type,
                                                 status=AttachmentStatus.ACCEPTED, size_bytes=size,
                                                 extracted_chars=len(text), truncated=truncated))

    if sections:
        result.document_text = "\n\n[Document Analysis]\n" + "\n\n---\n\n".join(sections)
    accepted = sum(o.status == AttachmentStatus.ACCEPTED for o in result.outcomes)
    if result.outcomes:
        logger.info("[ATTACHMENT] %d attached, %d accepted, %d refused",
                    len(result.outcomes), accepted, len(result.outcomes) - accepted)
    return result


def refusal_note(outcomes: Sequence[AttachmentOutcome]) -> str:
    """Name each refused file to the agent, so its reply can say so instead of ignoring it."""
    refused = [o for o in outcomes if o.status == AttachmentStatus.REFUSED]
    if not refused:
        return ""
    lines = [f"- '{o.filename or f'{o.kind.value} {o.index + 1}'}' ({o.media_type or 'unknown type'}): "
             f"{o.reason.value if o.reason else 'refused'}" for o in refused]
    return ("\n\n[Attachment notice] The user attached files that could not be read, so their contents are "
            "not available to you. Tell the user which ones and why:\n" + "\n".join(lines))
