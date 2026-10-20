"""Real attachment files carrying a known sentinel, built in memory.

Shared by the `attachments` QA module and the unit tests, so both check the
same bytes. Each document carries the sentinel in its TEXT, which is what has
to reach the agent; the mock LLM echoes any sentinel it finds in its prompt
(`[DOCUMENT_TOKENS:...]`), and a live model is asked to quote it.

No third-party writer is used: the PDF, DOCX and PNG are assembled by hand, so
a fixture can never depend on the library the agent uses to read it.
"""

from __future__ import annotations

import io
import re
import secrets
import struct
import zipfile
import zlib

#: The shape of a sentinel. The mock LLM matches this pattern.
SENTINEL_PATTERN = re.compile(r"CIRIS-ATTACH-[0-9A-F]{8}")


def new_sentinel() -> str:
    return f"CIRIS-ATTACH-{secrets.token_hex(4).upper()}"


def sentence(sentinel: str) -> str:
    return f"The archive code word is {sentinel}."


def png(size: int = 8) -> bytes:
    """A valid size x size RGB PNG."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    row = b"\x00" + b"\x30\x90\xc0" * size
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(row * size))
        + chunk(b"IEND", b"")
    )


def pdf(text: str) -> bytes:
    """A one-page PDF whose text layer is `text` (Helvetica, so pypdf extracts it verbatim)."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def docx(text: str) -> bytes:
    """A minimal WordprocessingML document with one paragraph of `text`."""
    from xml.sax.saxutils import escape

    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>"
        ),
        "word/document.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{w}"><w:body><w:p><w:r><w:t>{escape(text)}</w:t></w:r></w:p></w:body></w:document>'
        ),
    }
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in files.items():
            # Fixed timestamp: the same text always builds the same bytes.
            zf.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), body, zipfile.ZIP_DEFLATED)
    return out.getvalue()


def text(body: str) -> bytes:
    return body.encode("utf-8")
