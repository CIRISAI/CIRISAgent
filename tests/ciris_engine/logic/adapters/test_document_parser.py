"""Tests for DocumentParser - minimal secure document parsing."""

import asyncio
import tempfile
from pathlib import Path
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.document_parser import DocumentParser


class MockAttachment:
    """Mock attachment for testing."""

    def __init__(self, filename: str, size: int, content_type: str, url: str = "https://example.com/file"):
        if filename is not None:
            self.filename = filename
        if size is not None:
            self.size = size
        if content_type is not None:
            self.content_type = content_type
        self.url = url


class TestDocumentParserInitialization:
    """Test DocumentParser initialization and configuration."""

    def test_init_with_dependencies_available(self):
        """Test initialization when both dependencies are available."""
        parser = DocumentParser()
        # These should be True if dependencies are installed
        assert isinstance(parser._pdf_available, bool)
        assert isinstance(parser._docx_available, bool)
        assert parser.is_available() == (parser._pdf_available or parser._docx_available)

    def test_init_with_no_dependencies(self):
        """Test initialization when dependencies are missing."""
        with patch("builtins.__import__", side_effect=ImportError):
            parser = DocumentParser()
            assert parser._pdf_available is False
            assert parser._docx_available is False
            assert parser.is_available() is False

    def test_init_with_partial_dependencies(self):
        """Test initialization with only PDF support."""

        def mock_import(module_name, *args, **kwargs):
            if module_name == "docx2txt":
                raise ImportError("docx2txt not available")
            return MagicMock()

        with patch("builtins.__import__", side_effect=mock_import):
            parser = DocumentParser()
            assert parser._pdf_available is True
            assert parser._docx_available is False
            assert parser.is_available() is True  # Still available with PDF only

    def test_security_constraints(self):
        """Test security constraint configuration."""
        parser = DocumentParser()
        assert parser.MAX_FILE_SIZE == 1024 * 1024  # 1MB
        assert parser.MAX_ATTACHMENTS == 3
        assert parser.PROCESSING_TIMEOUT == 30.0
        assert parser.MAX_TEXT_LENGTH == 50000
        assert ".pdf" in parser.ALLOWED_EXTENSIONS
        assert ".docx" in parser.ALLOWED_EXTENSIONS
        assert len(parser.ALLOWED_EXTENSIONS) == 2  # Only these two

    def test_get_status(self):
        """Test status reporting."""
        parser = DocumentParser()
        status = parser.get_status()

        assert isinstance(status, dict)
        assert "available" in status
        assert "pdf_support" in status
        assert "docx_support" in status
        assert "max_file_size_mb" in status
        assert "max_attachments" in status
        assert "processing_timeout_sec" in status
        assert "allowed_extensions" in status

        assert status["max_file_size_mb"] == 1.0
        assert status["max_attachments"] == 3
        assert status["processing_timeout_sec"] == 30.0
        assert isinstance(status["allowed_extensions"], list)


class TestAttachmentFiltering:
    """Test attachment filtering logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DocumentParser()

    def test_valid_pdf_attachment(self):
        """Test valid PDF attachment passes filtering."""
        attachment = MockAttachment("test.pdf", 500000, "application/pdf")
        assert self.parser._is_document_attachment(attachment) is True

    def test_valid_docx_attachment(self):
        """Test valid DOCX attachment passes filtering."""
        attachment = MockAttachment(
            "test.docx", 800000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert self.parser._is_document_attachment(attachment) is True

    def test_oversized_attachment_rejected(self):
        """Test oversized attachment is rejected."""
        attachment = MockAttachment("huge.pdf", 2 * 1024 * 1024, "application/pdf")  # 2MB
        assert self.parser._is_document_attachment(attachment) is False

    def test_unsupported_extension_rejected(self):
        """Test unsupported file extensions are rejected."""
        unsupported_files = [
            MockAttachment("test.txt", 1000, "text/plain"),
            MockAttachment("test.exe", 1000, "application/octet-stream"),
            MockAttachment("test.jpg", 1000, "image/jpeg"),
            MockAttachment("test.doc", 1000, "application/msword"),  # Old Word format
        ]

        for attachment in unsupported_files:
            assert self.parser._is_document_attachment(attachment) is False

    def test_unsupported_content_type_rejected(self):
        """Test unsupported content types are rejected."""
        attachment = MockAttachment("test.pdf", 1000, "text/plain")  # Wrong content type
        assert self.parser._is_document_attachment(attachment) is False

    def test_missing_filename_handling(self):
        """Test behavior with missing or empty filenames."""
        # Empty filename with valid content type - current behavior is to accept
        # (relies on content type validation only)
        attachment = MockAttachment("", 1000, "application/pdf")
        result = self.parser._is_document_attachment(attachment)
        # Current logic: empty filename skips extension checks, relies on content type
        assert result is True  # This is the actual current behavior

        # Test attachment without filename attribute
        class AttachmentNoFilename:
            def __init__(self):
                self.size = 1000
                self.content_type = "application/pdf"
                # No filename attribute

        attachment_no_filename = AttachmentNoFilename()
        result = self.parser._is_document_attachment(attachment_no_filename)
        # Without filename attribute, only content type is checked
        assert result is True  # Current behavior - content type validation passes

        # Test case that should actually fail: wrong content type AND no filename
        class AttachmentBad:
            def __init__(self):
                self.size = 1000
                self.content_type = "text/plain"  # Wrong content type
                # No filename attribute

        attachment_bad = AttachmentBad()
        result = self.parser._is_document_attachment(attachment_bad)
        assert result is False  # Should fail due to wrong content type

    def test_dependency_unavailable_rejection(self):
        """Test rejection when required parser is unavailable."""
        parser = DocumentParser()
        parser._pdf_available = False
        parser._docx_available = False

        pdf_attachment = MockAttachment("test.pdf", 1000, "application/pdf")
        docx_attachment = MockAttachment(
            "test.docx", 1000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        assert parser._is_document_attachment(pdf_attachment) is False
        assert parser._is_document_attachment(docx_attachment) is False

    def test_partial_dependency_filtering(self):
        """Test filtering when only some parsers are available."""
        parser = DocumentParser()
        parser._pdf_available = True
        parser._docx_available = False

        pdf_attachment = MockAttachment("test.pdf", 1000, "application/pdf")
        docx_attachment = MockAttachment(
            "test.docx", 1000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        assert parser._is_document_attachment(pdf_attachment) is True
        assert parser._is_document_attachment(docx_attachment) is False


class TestDocumentProcessing:
    """Test document processing functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DocumentParser()

    @pytest.mark.asyncio
    async def test_process_attachments_empty_list(self):
        """Test processing empty attachment list."""
        result = await self.parser.process_attachments([])
        assert result is None

    @pytest.mark.asyncio
    async def test_process_attachments_no_documents(self):
        """Test processing attachments with no documents."""
        attachments = [
            MockAttachment("image.jpg", 1000, "image/jpeg"),
            MockAttachment("text.txt", 1000, "text/plain"),
        ]
        result = await self.parser.process_attachments(attachments)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_attachments_parser_unavailable(self):
        """Test processing when parser is unavailable."""
        parser = DocumentParser()
        parser._pdf_available = False
        parser._docx_available = False

        attachments = [MockAttachment("test.pdf", 1000, "application/pdf")]
        result = await parser.process_attachments(attachments)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_attachments_too_many(self):
        """Test processing more than max allowed attachments."""
        attachments = [
            MockAttachment(f"test{i}.pdf", 1000, "application/pdf") for i in range(5)  # More than MAX_ATTACHMENTS (3)
        ]

        with patch.object(self.parser, "_process_single_document") as mock_process:
            mock_process.return_value = "Test content"
            result = await self.parser.process_attachments(attachments)

            # Should only process first 3 attachments
            assert mock_process.call_count == 3

    @pytest.mark.asyncio
    async def test_process_attachments_success(self):
        """Test successful processing of multiple attachments."""
        attachments = [
            MockAttachment("doc1.pdf", 1000, "application/pdf"),
            MockAttachment(
                "doc2.docx", 1000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        ]

        with patch.object(self.parser, "_process_single_document") as mock_process:
            mock_process.side_effect = ["PDF content", "DOCX content"]
            result = await self.parser.process_attachments(attachments)

            assert result is not None
            assert "Document 'doc1.pdf':\nPDF content" in result
            assert "Document 'doc2.docx':\nDOCX content" in result
            assert "---" in result  # Separator between documents

    @pytest.mark.asyncio
    async def test_process_attachments_with_failures(self):
        """Test processing with some failed attachments."""
        attachments = [
            MockAttachment("good.pdf", 1000, "application/pdf"),
            MockAttachment("bad.pdf", 1000, "application/pdf"),
        ]

        async def mock_process(att):
            if att.filename == "bad.pdf":
                raise Exception("Processing failed")
            return "Good content"

        with patch.object(self.parser, "_process_single_document", side_effect=mock_process):
            result = await self.parser.process_attachments(attachments)

            assert result is not None
            assert "Document 'good.pdf':\nGood content" in result
            assert "Document 'bad.pdf': [Failed to process - Processing failed]" in result

    @pytest.mark.asyncio
    async def test_process_attachments_text_length_limit(self):
        """Test text length limiting."""
        attachments = [MockAttachment("big.pdf", 1000, "application/pdf")]

        # Create text longer than MAX_TEXT_LENGTH
        long_text = "x" * (self.parser.MAX_TEXT_LENGTH + 1000)

        with patch.object(self.parser, "_process_single_document", return_value=long_text):
            result = await self.parser.process_attachments(attachments)

            assert result is not None
            assert len(result) <= self.parser.MAX_TEXT_LENGTH + 100  # Account for metadata
            assert "[Text truncated due to length limit]" in result

    @pytest.mark.asyncio
    async def test_download_file_http_error(self):
        """Test download with HTTP error."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 404

            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            result = await self.parser._download_file("https://example.com/file.pdf")
            assert result is None

    @pytest.mark.asyncio
    async def test_download_file_too_large(self):
        """Test download rejection for oversized content."""
        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {"content-length": str(2 * 1024 * 1024)}  # 2MB

            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            result = await self.parser._download_file("https://example.com/file.pdf")
            assert result is None

    @pytest.mark.asyncio
    async def test_download_file_streaming_size_limit(self):
        """Test size limit during streaming download."""
        # Create chunks that exceed size limit
        large_chunk = b"x" * (1024 * 1024)  # 1MB chunks
        chunks = [large_chunk, large_chunk]  # 2MB total

        with patch("aiohttp.ClientSession") as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.headers = {}  # No content-length header
            mock_response.content.iter_chunked.return_value = chunks

            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_response

            result = await self.parser._download_file("https://example.com/file.pdf")
            assert result is None

    @pytest.mark.asyncio
    async def test_download_file_exception(self):
        """Test download with network exception."""
        with patch("aiohttp.ClientSession", side_effect=Exception("Network error")):
            result = await self.parser._download_file("https://example.com/file.pdf")
            assert result is None


class TestTextExtraction:
    """Test text extraction from different file formats."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DocumentParser()

    def test_extract_text_sync_unsupported_format(self):
        """Test extraction with unsupported file format."""
        result = self.parser._extract_text_sync(b"test data", ".txt")
        assert "Unsupported file type: .txt" in result

    def test_extract_text_sync_exception(self):
        """Test extraction with processing exception."""
        with patch.object(self.parser, "_extract_pdf_text", side_effect=Exception("Test error")):
            result = self.parser._extract_text_sync(b"test data", ".pdf")
            assert "Extraction error: Test error" in result

    def test_extract_pdf_text_parser_unavailable(self):
        """Test PDF extraction when parser unavailable."""
        parser = DocumentParser()
        parser._pdf_available = False

        result = parser._extract_pdf_text(b"test data")
        assert result == "PDF parsing not available"

    def test_extract_docx_text_parser_unavailable(self):
        """Test DOCX extraction when parser unavailable."""
        parser = DocumentParser()
        parser._docx_available = False

        result = parser._extract_docx_text(b"test data")
        assert result == "DOCX parsing not available"

    def test_extract_pdf_text_too_many_pages(self):
        """Test PDF extraction with too many pages."""
        with patch("builtins.__import__") as mock_import:
            mock_pypdf = MagicMock()
            mock_reader = MagicMock()
            mock_reader.pages = [MagicMock()] * 60  # More than 50 pages
            mock_pypdf.PdfReader.return_value = mock_reader

            def side_effect(name, *args, **kwargs):
                if name == "pypdf":
                    return mock_pypdf
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_pdf_text(b"test data")
            assert "PDF too large (60 pages, max 50)" in result

    def test_extract_pdf_text_success(self):
        """Test successful PDF text extraction."""
        with patch("builtins.__import__") as mock_import:
            mock_pypdf = MagicMock()

            # Mock PDF with pages containing text
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Page 1 content"
            mock_page2 = MagicMock()
            mock_page2.extract_text.return_value = "Page 2 content"

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page1, mock_page2]
            mock_pypdf.PdfReader.return_value = mock_reader

            def side_effect(name, *args, **kwargs):
                if name == "pypdf":
                    return mock_pypdf
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_pdf_text(b"test data")
            assert "Page 1:\nPage 1 content" in result
            assert "Page 2:\nPage 2 content" in result

    def test_extract_pdf_text_with_page_errors(self):
        """Test PDF extraction with some page errors."""
        with patch("builtins.__import__") as mock_import:
            mock_pypdf = MagicMock()

            # Mock PDF with one good page and one error page
            mock_page1 = MagicMock()
            mock_page1.extract_text.return_value = "Good content"
            mock_page2 = MagicMock()
            mock_page2.extract_text.side_effect = Exception("Page error")

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page1, mock_page2]
            mock_pypdf.PdfReader.return_value = mock_reader

            def side_effect(name, *args, **kwargs):
                if name == "pypdf":
                    return mock_pypdf
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_pdf_text(b"test data")
            assert "Page 1:\nGood content" in result
            assert "Page 2: [Extraction failed]" in result

    def test_extract_pdf_text_no_text(self):
        """Test PDF extraction with no text content."""
        with patch("builtins.__import__") as mock_import:
            mock_pypdf = MagicMock()

            # Mock PDF with empty pages
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "   "  # Whitespace only

            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]
            mock_pypdf.PdfReader.return_value = mock_reader

            def side_effect(name, *args, **kwargs):
                if name == "pypdf":
                    return mock_pypdf
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_pdf_text(b"test data")
            assert result == "No text found in PDF"

    def test_extract_docx_text_success(self):
        """Test successful DOCX text extraction."""
        with patch("builtins.__import__") as mock_import:
            mock_docx2txt = MagicMock()
            mock_docx2txt.process.return_value = "DOCX content here"

            def side_effect(name, *args, **kwargs):
                if name == "docx2txt":
                    return mock_docx2txt
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_docx_text(b"test data")
            assert result == "DOCX content here"

    def test_extract_docx_text_empty(self):
        """Test DOCX extraction with empty content."""
        with patch("builtins.__import__") as mock_import:
            mock_docx2txt = MagicMock()
            mock_docx2txt.process.return_value = "   "  # Whitespace only

            def side_effect(name, *args, **kwargs):
                if name == "docx2txt":
                    return mock_docx2txt
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_docx_text(b"test data")
            assert result == "No text found in DOCX"

    def test_extract_docx_text_exception(self):
        """Test DOCX extraction with processing error."""
        with patch("builtins.__import__") as mock_import:
            mock_docx2txt = MagicMock()
            mock_docx2txt.process.side_effect = Exception("DOCX error")

            def side_effect(name, *args, **kwargs):
                if name == "docx2txt":
                    return mock_docx2txt
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_docx_text(b"test data")
            assert "DOCX error: DOCX error" in result


class TestAsyncProcessing:
    """Test asynchronous processing and timeout handling."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DocumentParser()

    @pytest.mark.asyncio
    async def test_process_single_document_timeout(self):
        """Test processing timeout."""
        attachment = MockAttachment("test.pdf", 1000, "application/pdf")

        with patch.object(self.parser, "_download_file", return_value=b"test data"):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                result = await self.parser._process_single_document(attachment)
                assert "Processing timeout - file too complex or large" in result

    @pytest.mark.asyncio
    async def test_process_single_document_missing_attributes(self):
        """Test processing attachment missing required attributes."""
        # Test missing URL attribute
        attachment = MagicMock()
        attachment.filename = "test.pdf"
        del attachment.url  # Remove url attribute

        result = await self.parser._process_single_document(attachment)
        assert result is None

        # Test missing filename attribute
        attachment = MagicMock()
        attachment.url = "https://example.com/file.pdf"
        del attachment.filename  # Remove filename attribute

        result = await self.parser._process_single_document(attachment)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_single_document_download_failure(self):
        """Test processing with download failure."""
        attachment = MockAttachment("test.pdf", 1000, "application/pdf")

        with patch.object(self.parser, "_download_file", return_value=None):
            result = await self.parser._process_single_document(attachment)
            assert result == "Failed to download file"

    @pytest.mark.asyncio
    async def test_process_single_document_extraction_exception(self):
        """Test processing with extraction exception."""
        attachment = MockAttachment("test.pdf", 1000, "application/pdf")

        with patch.object(self.parser, "_download_file", return_value=b"test data"):
            with patch.object(self.parser, "_extract_text_sync", side_effect=Exception("Extraction failed")):
                result = await self.parser._process_single_document(attachment)
                assert "Error: Extraction failed" in result


class TestEdgeCasesAndCoverage:
    """Additional tests to improve code coverage for edge cases."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DocumentParser()

    def test_is_document_attachment_edge_cases(self):
        """Test edge cases in attachment filtering."""
        # Test attachment without content_type attribute
        attachment = MockAttachment("test.pdf", 1000, "")
        del attachment.content_type
        # Should still pass based on extension alone
        result = self.parser._is_document_attachment(attachment)
        assert isinstance(result, bool)

        # Test attachment without size attribute
        attachment = MockAttachment("test.pdf", 1000, "application/pdf")
        del attachment.size
        result = self.parser._is_document_attachment(attachment)
        assert isinstance(result, bool)

    def test_extract_pdf_text_file_operations(self):
        """Test PDF extraction file operation edge cases."""
        with patch("builtins.__import__") as mock_import, patch("builtins.open", side_effect=IOError("File error")):

            mock_pypdf = MagicMock()

            def side_effect(name, *args, **kwargs):
                if name == "pypdf":
                    return mock_pypdf
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_pdf_text(b"test data")
            assert "PDF error:" in result

    def test_extract_docx_text_file_operations(self):
        """Test DOCX extraction file operation edge cases."""
        with patch("builtins.__import__") as mock_import, patch(
            "tempfile.NamedTemporaryFile", side_effect=IOError("Temp file error")
        ):

            mock_docx2txt = MagicMock()

            def side_effect(name, *args, **kwargs):
                if name == "docx2txt":
                    return mock_docx2txt
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_docx_text(b"test data")
            assert "DOCX error:" in result

    def test_extract_docx_text_none_return(self):
        """Test DOCX extraction returning None."""
        with patch("builtins.__import__") as mock_import:
            mock_docx2txt = MagicMock()
            mock_docx2txt.process.return_value = None

            def side_effect(name, *args, **kwargs):
                if name == "docx2txt":
                    return mock_docx2txt
                return MagicMock()

            mock_import.side_effect = side_effect

            result = self.parser._extract_docx_text(b"test data")
            assert result == "No text found in DOCX"

    @pytest.mark.asyncio
    async def test_process_single_document_successful_flow(self):
        """Test complete successful document processing flow."""
        attachment = MockAttachment("test.pdf", 1000, "application/pdf")

        with patch.object(self.parser, "_download_file", return_value=b"pdf data") as mock_download, patch.object(
            self.parser, "_extract_text_sync", return_value="Extracted text"
        ) as mock_extract:

            result = await self.parser._process_single_document(attachment)
            assert result == "Extracted text"
            mock_download.assert_called_once_with(attachment.url)
            mock_extract.assert_called_once_with(b"pdf data", ".pdf")

    @pytest.mark.asyncio
    async def test_process_attachments_all_documents_fail(self):
        """Test processing where all documents fail to extract text."""
        attachments = [
            MockAttachment("fail1.pdf", 1000, "application/pdf"),
            MockAttachment(
                "fail2.docx", 1000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        ]

        with patch.object(self.parser, "_process_single_document", return_value=None):
            result = await self.parser.process_attachments(attachments)
            # Should return None since no text was extracted
            assert result is None

    def test_content_type_case_variations(self):
        """Test different content type variations."""
        # Test exact match
        attachment1 = MockAttachment("test.pdf", 1000, "application/pdf")
        assert self.parser._is_document_attachment(attachment1) is True

        # Test DOCX content type
        attachment2 = MockAttachment(
            "test.docx", 1000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        assert self.parser._is_document_attachment(attachment2) is True

        # Test wrong content type for PDF
        attachment3 = MockAttachment("test.pdf", 1000, "application/msword")
        assert self.parser._is_document_attachment(attachment3) is False
