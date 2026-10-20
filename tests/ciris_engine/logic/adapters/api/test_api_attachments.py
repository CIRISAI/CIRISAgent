"""The inline attachment gate: every file gets an outcome, and nothing is dropped silently.

Real bytes throughout (tools/qa_runner/attachment_fixtures.py), so a refusal is
proven against the file the client would send, not a mocked helper.
"""

from __future__ import annotations

import base64

import pytest

from ciris_adapters.mock_llm.responses_action_selection import attachment_markers
from ciris_engine.logic.adapters.api import api_attachments as gate
from ciris_engine.logic.adapters.api.api_attachments import (
    AttachmentRefusalReason as R,
)
from ciris_engine.logic.adapters.api.api_attachments import (
    AttachmentStatus,
    attachment_policy,
    process_attachments,
    refusal_note,
)
from tools.qa_runner import attachment_fixtures as fx

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


async def one_doc(data: bytes, media_type: str, filename: str = "f"):
    result = await process_attachments([], [(b64(data), media_type, filename)])
    return result, result.outcomes[0]


async def one_image(data: bytes, media_type: str, filename: str = "i"):
    result = await process_attachments([(b64(data), media_type, filename)], [])
    return result, result.outcomes[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "build,media_type,filename",
    [
        pytest.param(fx.pdf, PDF, "a.pdf", id="pdf"),
        pytest.param(fx.docx, DOCX, "a.docx", id="docx"),
        pytest.param(fx.text, "text/plain", "a.txt", id="txt"),
        pytest.param(fx.text, "text/markdown", "a.md", id="md"),
        pytest.param(fx.text, "text/csv", "a.csv", id="csv"),
        # picker label for unknown types
        pytest.param(fx.docx, "application/octet-stream", "a.docx", id="octet-docx"),
        pytest.param(fx.pdf, "", "a.pdf", id="unlabelled-pdf"),
    ],
)
async def test_document_text_reaches_the_message(build, media_type, filename):
    token = fx.new_sentinel()
    result, outcome = await one_doc(build(fx.sentence(token)), media_type, filename)
    assert outcome.status == AttachmentStatus.ACCEPTED, outcome
    assert token in result.document_text
    assert outcome.extracted_chars and outcome.extracted_chars >= len(token)


@pytest.mark.asyncio
async def test_data_url_document_and_image():
    token = fx.new_sentinel()
    result = await process_attachments(
        [(f"data:image/png;base64,{b64(fx.png())}", None, "a.png")],
        [(f"data:application/pdf;base64,{b64(fx.pdf(fx.sentence(token)))}", None, "a.pdf")],
    )
    assert [o.status for o in result.outcomes] == [AttachmentStatus.ACCEPTED] * 2
    assert len(result.images) == 1 and token in result.document_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,media_type,reason",
    [
        pytest.param(b"PK\x03\x04sheet", "application/vnd.ms-excel", R.UNSUPPORTED_TYPE, id="xlsx"),
        # no extension to go on
        pytest.param(b"hello", "application/octet-stream", R.UNSUPPORTED_TYPE, id="octet-no-ext"),
        pytest.param(fx.pdf("x"), DOCX, R.TYPE_MISMATCH, id="pdf-as-docx"),
        pytest.param(fx.docx("x"), PDF, R.TYPE_MISMATCH, id="docx-as-pdf"),
        # binary bytes labelled text
        pytest.param(fx.pdf("x"), "text/plain", R.TYPE_MISMATCH, id="pdf-as-text"),
        pytest.param(b"\xff\xfe\x00bad", "text/plain", R.UNREADABLE, id="text-not-utf8"),
        pytest.param(b"%PDF-1.4 not really a pdf", PDF, R.UNREADABLE, id="corrupt-pdf"),
        pytest.param(b"PK\x03\x04 not a docx", DOCX, R.UNREADABLE, id="corrupt-docx"),
        pytest.param(b"   \n ", "text/plain", R.NO_TEXT, id="blank-text"),
        pytest.param(b"", "text/plain", R.NO_TEXT, id="empty"),
    ],
)
async def test_document_refusals_carry_a_reason(data, media_type, reason):
    result, outcome = await one_doc(data, media_type)
    assert outcome.status == AttachmentStatus.REFUSED
    assert outcome.reason == reason, outcome
    assert result.document_text == ""


@pytest.mark.asyncio
async def test_parser_error_strings_never_become_document_text():
    """The parser's legacy string returns ("PDF error: ...") must not pass as content."""
    result, outcome = await one_doc(b"%PDF-1.4 truncated", PDF)
    assert outcome.reason == R.UNREADABLE
    assert "error" not in result.document_text.lower()


@pytest.mark.asyncio
async def test_too_large_is_refused_before_decoding(monkeypatch):
    monkeypatch.setattr(gate, "DOCUMENT_MAX_BYTES", 1000)
    _, outcome = await one_doc(b"a" * 1001, "text/plain")
    assert outcome.reason == R.TOO_LARGE and outcome.limit_bytes == 1000


@pytest.mark.asyncio
async def test_too_many_documents_and_images():
    docs = [(b64(fx.text(f"doc {i}")), "text/plain", f"{i}.txt") for i in range(gate.MAX_DOCUMENTS + 1)]
    imgs = [(b64(fx.png()), "image/png", f"{i}.png") for i in range(gate.MAX_IMAGES + 1)]
    result = await process_attachments(imgs, docs)
    refused = [(o.kind.value, o.index, o.reason) for o in result.outcomes if o.status == AttachmentStatus.REFUSED]
    assert refused == [("image", gate.MAX_IMAGES, R.TOO_MANY), ("document", gate.MAX_DOCUMENTS, R.TOO_MANY)]
    assert len(result.images) == gate.MAX_IMAGES


@pytest.mark.asyncio
async def test_text_budget_truncates_then_refuses(monkeypatch):
    monkeypatch.setattr(gate, "MAX_EXTRACTED_CHARS", 100)
    result = await process_attachments([], [(b64(b"a" * 150), "text/plain", "1.txt"), (b64(b"b"), "text/plain", "2.txt")])
    first, second = result.outcomes
    assert first.status == AttachmentStatus.ACCEPTED and first.truncated and first.extracted_chars == 100
    assert second.reason == R.TEXT_LIMIT_REACHED


@pytest.mark.asyncio
async def test_missing_parser_is_reported_and_left_out_of_the_policy(monkeypatch):
    parser = gate.get_api_document_helper()._parser
    monkeypatch.setattr(parser, "_pdf_available", False)
    _, outcome = await one_doc(fx.pdf("x"), PDF)
    assert outcome.reason == R.PARSER_UNAVAILABLE
    assert PDF not in attachment_policy().document_types
    assert "text/plain" in attachment_policy().document_types


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data,media_type,reason",
    [
        pytest.param(fx.png(), "image/jpeg", R.TYPE_MISMATCH, id="png-as-jpeg"),
        pytest.param(b"\x00\x00\x00\x18ftypheic", "image/heic", R.UNSUPPORTED_TYPE, id="heic"),
        pytest.param(b"", "image/png", R.UNREADABLE, id="empty"),
        pytest.param(fx.pdf("x"), "image/png", R.TYPE_MISMATCH, id="pdf-as-png"),
    ],
)
async def test_image_refusals_carry_a_reason(data, media_type, reason):
    result, outcome = await one_image(data, media_type)
    assert outcome.reason == reason and result.images == []


@pytest.mark.asyncio
async def test_refusal_note_names_every_refused_file():
    result = await process_attachments(
        [(b64(fx.png()), "image/jpeg", "m.jpg")], [(b64(b"x"), "application/zip", "z.zip")]
    )
    note = refusal_note(result.outcomes)
    assert "'m.jpg' (image/jpeg): type_mismatch" in note
    assert "'z.zip' (application/zip): unsupported_type" in note
    assert refusal_note([]) == ""


def test_policy_matches_the_client_picker_limits():
    """CIRISClient PickedFile allows 10 MB and 5 attachments; the agent must not refuse below that."""
    policy = attachment_policy()
    assert policy.document_max_bytes >= 10 * 1024 * 1024
    assert policy.max_documents >= 5 and policy.max_images >= 5


def test_mock_llm_markers():
    assert attachment_markers(["attached_documents:2", "attachment_tokens:CIRIS-ATTACH-0000ABCD",
                               "attachments_refused:1"]) == (
        "[DOCUMENT_DETECTED:2] [DOCUMENT_TOKENS:CIRIS-ATTACH-0000ABCD] [ATTACHMENT_REFUSED:1]"
    )
    assert attachment_markers(["multimodal_images:1"]) == ""


def test_mock_llm_sees_document_text_in_the_prompt():
    from ciris_adapters.mock_llm.responses import extract_context_from_messages

    token = fx.new_sentinel()
    content = f"hi\n\n[Document Analysis]\nDocument 'a.pdf':\n{fx.sentence(token)}"
    items = extract_context_from_messages([{"role": "user", "content": content}])
    assert "attached_documents:1" in items
    assert f"attachment_tokens:{token}" in items


@pytest.mark.asyncio
async def test_mock_llm_counts_the_refusal_notice_the_gate_writes():
    """The mock's count must parse the gate's own notice lines (CI found a regex that read 0)."""
    from ciris_adapters.mock_llm.responses import extract_context_from_messages

    result = await process_attachments(
        [(b64(fx.png()), "image/jpeg", "m.jpg"), (b64(b"x"), "image/heic", "p.heic")],
        [(b64(b"PK\x03\x04x"), "application/vnd.ms-excel", "b.xlsx")],
    )
    items = extract_context_from_messages([{"role": "user", "content": "files" + refusal_note(result.outcomes)}])
    assert "attachments_refused:3" in items

