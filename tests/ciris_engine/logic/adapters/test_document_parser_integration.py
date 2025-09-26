"""Integration tests for DocumentParser to improve coverage."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from ciris_engine.logic.adapters.document_parser import DocumentParser


class MockAttachment:
    """Mock attachment for integration testing."""

    def __init__(self, filename: str, size: int, content_type: str, url: str = "https://example.com/file"):
        self.filename = filename
        self.size = size
        self.content_type = content_type
        self.url = url


class TestDocumentParserIntegration:
    """Integration tests exercising main processing paths."""

    def setup_method(self):
        """Set up test fixtures."""
        self.parser = DocumentParser()

    @pytest.mark.asyncio
    async def test_complete_pdf_processing_pipeline(self):
        """Test complete PDF processing from attachment to text."""
        attachment = MockAttachment("test.pdf", 100000, "application/pdf")

        # Mock successful download
        with patch.object(self.parser, '_download_file') as mock_download:
            mock_download.return_value = b'fake_pdf_data'

            # Mock PDF extraction
            with patch('builtins.__import__') as mock_import:
                mock_pypdf = MagicMock()
                mock_page = MagicMock()
                mock_page.extract_text.return_value = "PDF content from page"
                mock_reader = MagicMock()
                mock_reader.pages = [mock_page]
                mock_pypdf.PdfReader.return_value = mock_reader

                def side_effect(name, *args, **kwargs):
                    if name == 'pypdf':
                        return mock_pypdf
                    return MagicMock()
                mock_import.side_effect = side_effect

                # Test the complete pipeline
                result = await self.parser.process_attachments([attachment])

                assert result is not None
                assert "Document 'test.pdf':" in result
                assert "PDF content from page" in result
                mock_download.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_docx_processing_pipeline(self):
        """Test complete DOCX processing from attachment to text."""
        attachment = MockAttachment("test.docx", 80000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

        # Mock successful download
        with patch.object(self.parser, '_download_file') as mock_download:
            mock_download.return_value = b'fake_docx_data'

            # Mock DOCX extraction
            with patch('builtins.__import__') as mock_import:
                mock_docx2txt = MagicMock()
                mock_docx2txt.process.return_value = "DOCX content from document"

                def side_effect(name, *args, **kwargs):
                    if name == 'docx2txt':
                        return mock_docx2txt
                    return MagicMock()
                mock_import.side_effect = side_effect

                # Test the complete pipeline
                result = await self.parser.process_attachments([attachment])

                assert result is not None
                assert "Document 'test.docx':" in result
                assert "DOCX content from document" in result
                mock_download.assert_called_once()

    @pytest.mark.asyncio
    async def test_mixed_document_processing(self):
        """Test processing multiple document types together."""
        attachments = [
            MockAttachment("doc1.pdf", 50000, "application/pdf"),
            MockAttachment("doc2.docx", 60000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            MockAttachment("image.jpg", 40000, "image/jpeg"),  # Should be ignored
        ]

        with patch.object(self.parser, '_download_file') as mock_download:
            mock_download.return_value = b'fake_file_data'

            with patch('builtins.__import__') as mock_import:
                mock_pypdf = MagicMock()
                mock_docx2txt = MagicMock()

                # PDF mock
                mock_pdf_page = MagicMock()
                mock_pdf_page.extract_text.return_value = "PDF text content"
                mock_pdf_reader = MagicMock()
                mock_pdf_reader.pages = [mock_pdf_page]
                mock_pypdf.PdfReader.return_value = mock_pdf_reader

                # DOCX mock
                mock_docx2txt.process.return_value = "DOCX text content"

                def side_effect(name, *args, **kwargs):
                    if name == 'pypdf':
                        return mock_pypdf
                    elif name == 'docx2txt':
                        return mock_docx2txt
                    return MagicMock()
                mock_import.side_effect = side_effect

                result = await self.parser.process_attachments(attachments)

                assert result is not None
                assert "Document 'doc1.pdf':" in result
                assert "Document 'doc2.docx':" in result
                assert "PDF text content" in result
                assert "DOCX text content" in result
                # Should process 2 documents (PDF + DOCX), ignore image
                assert mock_download.call_count == 2


    def test_attachment_filtering_comprehensive(self):
        """Test comprehensive attachment filtering scenarios."""
        test_cases = [
            # Valid cases
            (MockAttachment("doc.pdf", 500000, "application/pdf"), True),
            (MockAttachment("doc.docx", 800000, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"), True),

            # Invalid cases
            (MockAttachment("doc.pdf", 2000000, "application/pdf"), False),  # Too large
            (MockAttachment("doc.txt", 50000, "text/plain"), False),  # Wrong extension
            (MockAttachment("doc.pdf", 50000, "text/plain"), False),  # Wrong content type
            # Note: Empty filename test covered separately in main test suite
        ]

        for attachment, expected in test_cases:
            result = self.parser._is_document_attachment(attachment)
            filename = getattr(attachment, 'filename', '<missing>')
            size = getattr(attachment, 'size', '<missing>')
            assert result == expected, f"Failed for filename='{filename}' with size={size}"

    def test_text_extraction_error_handling(self):
        """Test error handling in text extraction."""
        # Test PDF extraction when parser is unavailable (simpler approach)
        parser = DocumentParser()
        parser._pdf_available = False
        result = parser._extract_pdf_text(b"test data")
        assert "PDF parsing not available" in result

        # Test DOCX extraction when parser is unavailable
        parser = DocumentParser()
        parser._docx_available = False
        result = parser._extract_docx_text(b"test data")
        assert "DOCX parsing not available" in result

    @pytest.mark.asyncio
    async def test_processing_timeout_scenarios(self):
        """Test timeout scenarios in document processing."""
        attachment = MockAttachment("slow.pdf", 50000, "application/pdf")

        with patch.object(self.parser, '_download_file') as mock_download:
            # Test download timeout
            mock_download.side_effect = asyncio.TimeoutError("Download timeout")

            result = await self.parser._process_single_document(attachment)
            assert "Processing timeout - file too complex or large" in result

        # Test extraction timeout
        with patch.object(self.parser, '_download_file', return_value=b"data"):
            with patch('asyncio.wait_for', side_effect=asyncio.TimeoutError):
                result = await self.parser._process_single_document(attachment)
                assert "Processing timeout - file too complex or large" in result

    def test_security_constraints_validation(self):
        """Test that all security constraints are properly configured."""
        assert self.parser.MAX_FILE_SIZE == 1024 * 1024  # 1MB
        assert self.parser.MAX_ATTACHMENTS == 3
        assert self.parser.PROCESSING_TIMEOUT == 30.0
        assert self.parser.MAX_TEXT_LENGTH == 50000

        # Test extensions whitelist
        assert len(self.parser.ALLOWED_EXTENSIONS) == 2
        assert '.pdf' in self.parser.ALLOWED_EXTENSIONS
        assert '.docx' in self.parser.ALLOWED_EXTENSIONS

        # Test content types whitelist
        assert len(self.parser.ALLOWED_CONTENT_TYPES) == 2
        assert 'application/pdf' in self.parser.ALLOWED_CONTENT_TYPES
        assert 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in self.parser.ALLOWED_CONTENT_TYPES