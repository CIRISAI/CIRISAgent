"""Unit tests for API document processing functionality."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.api_document import APIDocumentHelper, get_api_document_helper


class TestAPIDocumentHelper:
    """Tests for APIDocumentHelper class."""

    @pytest.fixture
    def helper(self):
        """Create helper with mocked parser."""
        with patch("ciris_engine.logic.adapters.api.api_document.DocumentParser") as mock_parser:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            mock_instance._extract_text_sync.return_value = "Extracted text"
            mock_instance.MAX_TEXT_LENGTH = 50000
            mock_parser.return_value = mock_instance
            helper = APIDocumentHelper()
            return helper

    @pytest.fixture
    def unavailable_helper(self):
        """Create helper with unavailable parser."""
        with patch("ciris_engine.logic.adapters.api.api_document.DocumentParser") as mock_parser:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = False
            mock_parser.return_value = mock_instance
            helper = APIDocumentHelper()
            return helper

    def test_is_available(self, helper):
        """Test availability check."""
        assert helper.is_available() is True

    def test_is_not_available(self, unavailable_helper):
        """Test unavailability check."""
        assert unavailable_helper.is_available() is False

    def test_get_status(self, helper):
        """Test status dictionary."""
        status = helper.get_status()
        assert "available" in status
        assert "max_file_size_mb" in status
        assert "max_documents" in status
        assert "allowed_extensions" in status
        assert ".pdf" in status["allowed_extensions"]
        assert ".docx" in status["allowed_extensions"]

    def test_get_file_extension_from_filename(self, helper):
        """Test file extension detection from filename."""
        ext = helper._get_file_extension("application/octet-stream", "document.pdf")
        assert ext == ".pdf"

        ext = helper._get_file_extension("application/octet-stream", "report.docx")
        assert ext == ".docx"

    def test_get_file_extension_from_media_type(self, helper):
        """Test file extension detection from media type."""
        ext = helper._get_file_extension("application/pdf", None)
        assert ext == ".pdf"

        ext = helper._get_file_extension(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document", None
        )
        assert ext == ".docx"

    def test_get_file_extension_unsupported(self, helper):
        """Test file extension detection for unsupported types."""
        ext = helper._get_file_extension("text/plain", "file.txt")
        assert ext is None

    def test_is_valid_media_type(self, helper):
        """Test media type validation."""
        assert helper._is_valid_media_type("application/pdf") is True
        assert (
            helper._is_valid_media_type("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            is True
        )
        assert helper._is_valid_media_type("text/plain") is False
        assert helper._is_valid_media_type("image/jpeg") is False

    @pytest.mark.asyncio
    async def test_process_base64_document(self, helper):
        """Test processing base64-encoded document."""
        # Create valid base64 data (represents PDF header)
        pdf_header = b"%PDF-1.4"
        base64_data = base64.b64encode(pdf_header).decode("utf-8")

        result = await helper.process_base64_document(base64_data, "application/pdf", "test.pdf")
        assert result == "Extracted text"

    @pytest.mark.asyncio
    async def test_process_base64_document_with_data_url(self, helper):
        """Test processing base64 with data URL prefix."""
        pdf_header = b"%PDF-1.4"
        base64_data = base64.b64encode(pdf_header).decode("utf-8")
        data_url = f"data:application/pdf;base64,{base64_data}"

        result = await helper.process_base64_document(data_url, "text/plain")  # type will be overridden
        assert result == "Extracted text"

    @pytest.mark.asyncio
    async def test_process_base64_document_invalid_type(self, helper):
        """Test processing base64 with invalid media type."""
        base64_data = base64.b64encode(b"data").decode("utf-8")
        result = await helper.process_base64_document(base64_data, "text/plain")
        assert result is None

    @pytest.mark.asyncio
    async def test_process_base64_document_too_large(self, helper):
        """Test processing base64 document that's too large."""
        # Create data larger than MAX_FILE_SIZE (1MB)
        large_data = b"x" * (1024 * 1024 + 1)
        base64_data = base64.b64encode(large_data).decode("utf-8")

        result = await helper.process_base64_document(base64_data, "application/pdf")
        assert result is None

    @pytest.mark.asyncio
    async def test_process_base64_document_invalid_base64(self, helper):
        """Test processing invalid base64 data."""
        result = await helper.process_base64_document("not-valid-base64!!!", "application/pdf")
        assert result is None

    @pytest.mark.asyncio
    async def test_process_url_document(self, helper):
        """Test processing document from URL."""
        pdf_data = b"%PDF-1.4"

        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = pdf_data

            result = await helper.process_url_document("https://example.com/doc.pdf", "application/pdf", "doc.pdf")
            assert result == "Extracted text"

    @pytest.mark.asyncio
    async def test_process_url_document_download_fails(self, helper):
        """Test handling download failure."""
        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = None

            result = await helper.process_url_document("https://example.com/doc.pdf", "application/pdf")
            assert result is None

    @pytest.mark.asyncio
    async def test_process_document_payload_detects_url(self, helper):
        """Test auto-detection of URL vs base64."""
        with patch.object(helper, "process_url_document", new_callable=AsyncMock) as mock_url:
            mock_url.return_value = "URL text"

            result = await helper.process_document_payload("https://example.com/doc.pdf", "application/pdf")
            mock_url.assert_called_once()
            assert result == "URL text"

    @pytest.mark.asyncio
    async def test_process_document_payload_detects_base64(self, helper):
        """Test auto-detection of base64 data."""
        with patch.object(helper, "process_base64_document", new_callable=AsyncMock) as mock_b64:
            mock_b64.return_value = "Base64 text"

            result = await helper.process_document_payload("JVBERi0xLjQ=", "application/pdf")  # %PDF-1.4 in base64
            mock_b64.assert_called_once()
            assert result == "Base64 text"

    @pytest.mark.asyncio
    async def test_process_document_list(self, helper):
        """Test processing multiple documents."""
        with patch.object(helper, "process_document_payload", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "Document text"

            documents = [
                {"data": "data1", "media_type": "application/pdf", "filename": "doc1.pdf"},
                {"data": "data2", "media_type": "application/pdf", "filename": "doc2.pdf"},
            ]

            result = await helper.process_document_list(documents)
            assert result is not None
            assert "doc1.pdf" in result
            assert "doc2.pdf" in result
            assert mock_proc.call_count == 2

    @pytest.mark.asyncio
    async def test_process_document_list_empty(self, helper):
        """Test processing empty document list."""
        result = await helper.process_document_list([])
        assert result is None

    @pytest.mark.asyncio
    async def test_process_document_list_unavailable(self, unavailable_helper):
        """Test processing when parser unavailable."""
        documents = [{"data": "data", "media_type": "application/pdf"}]
        result = await unavailable_helper.process_document_list(documents)
        assert result is None

    @pytest.mark.asyncio
    async def test_process_document_list_max_limit(self, helper):
        """Test document list respects max limit."""
        with patch.object(helper, "process_document_payload", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "text"

            # Create 5 documents (more than MAX_DOCUMENTS=3)
            documents = [{"data": f"data{i}", "media_type": "application/pdf"} for i in range(5)]

            await helper.process_document_list(documents)
            # Should only process MAX_DOCUMENTS (3)
            assert mock_proc.call_count == 3

    @pytest.mark.asyncio
    async def test_process_document_list_invalid_entry(self, helper):
        """Test handling invalid entries in document list."""
        with patch.object(helper, "process_document_payload", new_callable=AsyncMock) as mock_proc:
            mock_proc.return_value = "text"

            documents = [
                "not a dict",  # Invalid
                {"no_data": "missing data field"},  # Invalid
                {"data": "valid", "media_type": "application/pdf"},  # Valid
            ]

            await helper.process_document_list(documents)
            # Should only process the one valid entry
            assert mock_proc.call_count == 1


class TestProcessUrlDocumentEdgeCases:
    """Additional tests for URL document processing edge cases."""

    @pytest.fixture
    def helper(self):
        """Create helper with mocked parser."""
        with patch("ciris_engine.logic.adapters.api.api_document.DocumentParser") as mock_parser:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            mock_instance._extract_text_sync.return_value = "Extracted text"
            mock_instance.MAX_TEXT_LENGTH = 50000
            mock_parser.return_value = mock_instance
            helper = APIDocumentHelper()
            return helper

    @pytest.mark.asyncio
    async def test_process_url_invalid_media_type(self, helper):
        """Test processing URL with invalid media type."""
        result = await helper.process_url_document("https://example.com/file.txt", "text/plain")
        assert result is None

    @pytest.mark.asyncio
    async def test_process_url_infer_extension_from_url(self, helper):
        """Test inferring extension from URL path."""
        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = b"%PDF-1.4"

            # No filename provided, extension should be inferred from URL
            result = await helper.process_url_document(
                "https://example.com/documents/report.pdf",
                "application/pdf",
            )
            assert result == "Extracted text"

    @pytest.mark.asyncio
    async def test_process_url_infer_extension_from_url_path(self, helper):
        """Test inferring extension from URL when media type doesn't help."""
        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_download:
            mock_download.return_value = b"DOCX content"

            # Use octet-stream type, should infer from URL
            result = await helper.process_url_document(
                "https://example.com/report.docx?token=abc",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
            assert result == "Extracted text"

    @pytest.mark.asyncio
    async def test_process_url_cannot_infer_extension(self, helper):
        """Test URL where extension cannot be inferred."""
        result = await helper.process_url_document(
            "https://example.com/api/document/12345",  # No extension in URL
            "application/octet-stream",  # Unknown type
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_process_url_exception(self, helper):
        """Test exception handling in URL processing."""
        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_download:
            mock_download.side_effect = Exception("Unexpected error")
            result = await helper.process_url_document("https://example.com/doc.pdf", "application/pdf")
            assert result is None


class TestDownloadDocumentEdgeCases:
    """Tests for download document edge cases - tested via process_url_document."""

    @pytest.fixture
    def helper(self):
        """Create helper with mocked parser."""
        with patch("ciris_engine.logic.adapters.api.api_document.DocumentParser") as mock_parser:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            mock_instance._extract_text_sync.return_value = "Extracted"
            mock_parser.return_value = mock_instance
            helper = APIDocumentHelper()
            return helper

    @pytest.mark.asyncio
    async def test_url_processing_with_download_mock(self, helper):
        """Test URL processing when download returns data."""
        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = b"PDF content"
            result = await helper.process_url_document("https://example.com/doc.pdf", "application/pdf", "doc.pdf")
            assert result == "Extracted"
            mock_dl.assert_called_once()

    @pytest.mark.asyncio
    async def test_url_processing_download_fails(self, helper):
        """Test URL processing when download returns None."""
        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_dl:
            mock_dl.return_value = None
            result = await helper.process_url_document("https://example.com/doc.pdf", "application/pdf")
            assert result is None

    @pytest.mark.asyncio
    async def test_url_processing_download_exception(self, helper):
        """Test URL processing when download raises exception."""
        with patch.object(helper, "_download_document", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = Exception("Network error")
            result = await helper.process_url_document("https://example.com/doc.pdf", "application/pdf")
            assert result is None


class TestProcessBase64EdgeCases:
    """Additional tests for base64 document processing edge cases."""

    @pytest.fixture
    def helper(self):
        """Create helper with mocked parser."""
        with patch("ciris_engine.logic.adapters.api.api_document.DocumentParser") as mock_parser:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            mock_instance._extract_text_sync.return_value = "Extracted text"
            mock_instance.MAX_TEXT_LENGTH = 50000
            mock_parser.return_value = mock_instance
            helper = APIDocumentHelper()
            return helper

    @pytest.mark.asyncio
    async def test_no_file_extension_determined(self, helper):
        """Test when file extension cannot be determined."""
        pdf_data = base64.b64encode(b"%PDF-1.4").decode("utf-8")
        result = await helper.process_base64_document(pdf_data, "application/octet-stream")
        assert result is None

    @pytest.mark.asyncio
    async def test_exception_during_processing(self, helper):
        """Test exception during text extraction."""
        helper._parser._extract_text_sync.side_effect = Exception("Parser error")
        pdf_data = base64.b64encode(b"%PDF-1.4").decode("utf-8")
        result = await helper.process_base64_document(pdf_data, "application/pdf")
        assert result is None


class TestDocumentListTruncation:
    """Tests for text truncation in document list processing."""

    @pytest.mark.asyncio
    async def test_text_truncation(self):
        """Test that combined text is truncated when too long."""
        with patch("ciris_engine.logic.adapters.api.api_document.DocumentParser") as mock_parser:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            # Return very long text
            mock_instance._extract_text_sync.return_value = "x" * 60000
            mock_instance.MAX_TEXT_LENGTH = 50000
            mock_parser.return_value = mock_instance

            helper = APIDocumentHelper()

            with patch.object(helper, "process_document_payload", new_callable=AsyncMock) as mock_proc:
                # Return text longer than MAX_TEXT_LENGTH
                mock_proc.return_value = "y" * 60000

                documents = [{"data": "data1", "media_type": "application/pdf", "filename": "doc.pdf"}]
                result = await helper.process_document_list(documents)

                assert result is not None
                assert len(result) <= helper._parser.MAX_TEXT_LENGTH + 50  # Allow for truncation marker
                assert "[Text truncated]" in result


class TestGetAPIDocumentHelper:
    """Tests for singleton getter."""

    def test_get_api_document_helper_returns_singleton(self):
        """Test that getter returns same instance."""
        # Reset singleton for test
        import ciris_engine.logic.adapters.api.api_document as module

        module._api_document_helper = None

        with patch.object(module, "DocumentParser"):
            helper1 = get_api_document_helper()
            helper2 = get_api_document_helper()
            assert helper1 is helper2


class TestDocumentPayloadSchema:
    """Tests for DocumentPayload schema."""

    def test_document_payload_defaults(self):
        """Test DocumentPayload default values."""
        from ciris_engine.logic.adapters.api.routes.agent import DocumentPayload

        payload = DocumentPayload(data="test")
        assert payload.data == "test"
        assert payload.media_type == "application/pdf"
        assert payload.filename is None

    def test_document_payload_with_values(self):
        """Test DocumentPayload with all values."""
        from ciris_engine.logic.adapters.api.routes.agent import DocumentPayload

        payload = DocumentPayload(
            data="base64data",
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="report.docx",
        )
        assert payload.data == "base64data"
        assert "wordprocessingml" in payload.media_type
        assert payload.filename == "report.docx"


class TestInteractRequestWithDocuments:
    """Tests for InteractRequest with documents field."""

    def test_interact_request_without_documents(self):
        """Test InteractRequest without documents."""
        from ciris_engine.logic.adapters.api.routes.agent import InteractRequest

        request = InteractRequest(message="Hello")
        assert request.documents is None

    def test_interact_request_with_documents(self):
        """Test InteractRequest with documents."""
        from ciris_engine.logic.adapters.api.routes.agent import DocumentPayload, InteractRequest

        docs = [
            DocumentPayload(data="pdf_data", filename="report.pdf"),
            DocumentPayload(
                data="docx_data",
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename="doc.docx",
            ),
        ]
        request = InteractRequest(message="Analyze these", documents=docs)
        assert request.documents is not None
        assert len(request.documents) == 2
        assert request.documents[0].filename == "report.pdf"


class TestTaskCompleteParamsWithPersistImages:
    """Tests for TaskCompleteParams persist_images field."""

    def test_persist_images_defaults_false(self):
        """Test persist_images defaults to False."""
        from ciris_engine.schemas.actions.parameters import TaskCompleteParams

        params = TaskCompleteParams()
        assert params.persist_images is False

    def test_persist_images_can_be_true(self):
        """Test persist_images can be set to True."""
        from ciris_engine.schemas.actions.parameters import TaskCompleteParams

        params = TaskCompleteParams(persist_images=True)
        assert params.persist_images is True

    def test_persist_images_in_model_dump(self):
        """Test persist_images appears in serialization."""
        from ciris_engine.schemas.actions.parameters import TaskCompleteParams

        params = TaskCompleteParams(completion_reason="Done", persist_images=True)
        data = params.model_dump()
        assert "persist_images" in data
        assert data["persist_images"] is True


class TestClearTaskImages:
    """Tests for clear_task_images persistence function."""

    def test_clear_task_images_success(self):
        """Test clearing task images."""
        from unittest.mock import MagicMock

        from ciris_engine.logic.persistence.models.tasks import clear_task_images

        mock_time = MagicMock()
        mock_time.now_iso.return_value = "2025-01-01T00:00:00Z"

        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.rowcount = 1
            mock_conn.execute.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = clear_task_images("task-123", "default", mock_time)
            assert result is True

    def test_clear_task_images_not_found(self):
        """Test clearing images for non-existent task."""
        from unittest.mock import MagicMock

        from ciris_engine.logic.persistence.models.tasks import clear_task_images

        mock_time = MagicMock()
        mock_time.now_iso.return_value = "2025-01-01T00:00:00Z"

        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_db:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.rowcount = 0
            mock_conn.execute.return_value = mock_cursor
            mock_db.return_value.__enter__.return_value = mock_conn

            result = clear_task_images("nonexistent", "default", mock_time)
            assert result is False
