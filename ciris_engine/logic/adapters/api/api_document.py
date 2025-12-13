"""API Document Helper for processing PDF/DOCX documents.

Extends DocumentParser functionality for API-specific document handling.
Documents can be submitted as base64 data or URLs in the interact endpoint.
"""

import base64
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

from ciris_engine.logic.adapters.document_parser import DocumentParser
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Default media types
DEFAULT_PDF_MEDIA_TYPE = "application/pdf"
DEFAULT_DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class APIDocumentHelper:
    """
    Helper class for processing API documents.

    Converts API document payloads to extracted text using DocumentParser.
    Supports both base64-encoded documents and URL-based documents.
    """

    # Security constraints (same as DocumentParser)
    MAX_FILE_SIZE = 1024 * 1024  # 1MB
    MAX_DOCUMENTS = 3
    DOWNLOAD_TIMEOUT = 10.0  # seconds

    # Allowed formats
    ALLOWED_EXTENSIONS = {".pdf", ".docx"}
    ALLOWED_CONTENT_TYPES = {
        DEFAULT_PDF_MEDIA_TYPE,
        DEFAULT_DOCX_MEDIA_TYPE,
    }

    def __init__(self) -> None:
        """Initialize the document helper with parser."""
        self._parser = DocumentParser()

    def is_available(self) -> bool:
        """Check if document processing is available.

        Returns:
            True if at least one document format is supported
        """
        return self._parser.is_available()

    def get_status(self) -> JSONDict:
        """Get current status of document helper.

        Returns:
            Status dictionary
        """
        parser_status = self._parser.get_status()
        return {
            "available": self.is_available(),
            "max_file_size_mb": self.MAX_FILE_SIZE / 1024 / 1024,
            "max_documents": self.MAX_DOCUMENTS,
            "pdf_support": parser_status.get("pdf_support", False),
            "docx_support": parser_status.get("docx_support", False),
            "allowed_extensions": list(self.ALLOWED_EXTENSIONS),
        }

    def _get_file_extension(self, media_type: str, filename: Optional[str]) -> Optional[str]:
        """Determine file extension from media type or filename.

        Args:
            media_type: MIME type of the document
            filename: Optional filename

        Returns:
            File extension (e.g., '.pdf') or None if unsupported
        """
        # Try filename first
        if filename:
            ext = Path(filename).suffix.lower()
            if ext in self.ALLOWED_EXTENSIONS:
                return ext

        # Fall back to media type
        type_to_ext = {
            DEFAULT_PDF_MEDIA_TYPE: ".pdf",
            DEFAULT_DOCX_MEDIA_TYPE: ".docx",
        }
        return type_to_ext.get(media_type)

    def _is_valid_media_type(self, media_type: str) -> bool:
        """Check if media type is allowed."""
        return media_type in self.ALLOWED_CONTENT_TYPES

    async def process_base64_document(
        self,
        base64_data: str,
        media_type: str,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """Process a base64-encoded document and extract text.

        Args:
            base64_data: Base64-encoded document data (with or without data URL prefix)
            media_type: MIME type of the document
            filename: Optional filename

        Returns:
            Extracted text or None if processing failed
        """
        try:
            # Handle data URL format: data:application/pdf;base64,JVBERi0...
            if base64_data.startswith("data:"):
                header, data = base64_data.split(",", 1)
                if ";" in header:
                    media_type = header.split(":")[1].split(";")[0]
                base64_data = data

            # Validate media type
            if not self._is_valid_media_type(media_type):
                logger.warning(f"Unsupported document type: {media_type}")
                return None

            # Decode base64
            try:
                file_data = base64.b64decode(base64_data)
            except Exception as e:
                logger.error(f"Invalid base64 data: {e}")
                return None

            # Check size
            if len(file_data) > self.MAX_FILE_SIZE:
                logger.warning(f"Document too large: {len(file_data)} bytes (max {self.MAX_FILE_SIZE} bytes)")
                return None

            # Get file extension
            file_ext = self._get_file_extension(media_type, filename)
            if not file_ext:
                logger.warning(f"Could not determine file extension for {media_type}")
                return None

            # Extract text using parser
            return self._parser._extract_text_sync(file_data, file_ext)

        except Exception as e:
            logger.exception(f"Error processing base64 document: {e}")
            return None

    async def process_url_document(
        self,
        url: str,
        media_type: str,
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """Process a document from URL and extract text.

        Args:
            url: URL of the document
            media_type: MIME type of the document
            filename: Optional filename

        Returns:
            Extracted text or None if processing failed
        """
        try:
            # Validate media type
            if not self._is_valid_media_type(media_type):
                logger.warning(f"Unsupported document type: {media_type}")
                return None

            # Get file extension
            file_ext = self._get_file_extension(media_type, filename)
            if not file_ext:
                # Try to infer from URL
                url_path = Path(url.split("?")[0])
                if url_path.suffix.lower() in self.ALLOWED_EXTENSIONS:
                    file_ext = url_path.suffix.lower()
                else:
                    logger.warning(f"Could not determine file extension for {url}")
                    return None

            # Download document
            file_data = await self._download_document(url)
            if not file_data:
                return None

            # Extract text using parser
            return self._parser._extract_text_sync(file_data, file_ext)

        except Exception as e:
            logger.exception(f"Error processing URL document: {e}")
            return None

    async def _download_document(self, url: str) -> Optional[bytes]:
        """Download document from URL with security limits.

        Args:
            url: URL to download from

        Returns:
            Document bytes or None if download failed
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=self.DOWNLOAD_TIMEOUT)) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download document (HTTP {response.status})")
                        return None

                    # Check content length header
                    if response.headers.get("content-length"):
                        content_length = int(response.headers["content-length"])
                        if content_length > self.MAX_FILE_SIZE:
                            logger.error(f"Document too large ({content_length} bytes)")
                            return None

                    # Read with size limit
                    file_data = b""
                    async for chunk in response.content.iter_chunked(8192):
                        file_data += chunk
                        if len(file_data) > self.MAX_FILE_SIZE:
                            logger.error("Document size limit exceeded during download")
                            return None

                    return file_data

        except Exception as e:
            logger.error(f"Document download failed: {e}")
            return None

    async def process_document_payload(
        self,
        document_data: str,
        media_type: str = "application/pdf",
        filename: Optional[str] = None,
    ) -> Optional[str]:
        """Process a document payload from the API (auto-detect base64 vs URL).

        Args:
            document_data: Either base64-encoded data or a URL
            media_type: MIME type of the document
            filename: Optional filename

        Returns:
            Extracted text or None if processing failed
        """
        # Detect URL vs base64 (checking format, not making connections)
        if document_data.startswith(("http://", "https://")):  # NOSONAR - format detection only
            return await self.process_url_document(document_data, media_type, filename)
        else:
            return await self.process_base64_document(document_data, media_type, filename)

    async def process_document_list(
        self,
        documents: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Process a list of document payloads from the API.

        Each document dict should have:
        - data: base64 string or URL
        - media_type: (optional) MIME type, defaults to application/pdf
        - filename: (optional) filename

        Args:
            documents: List of document dictionaries

        Returns:
            Combined extracted text from all documents, or None if no documents processed
        """
        if not self.is_available():
            logger.warning("Document processing not available (missing libraries)")
            return None

        if not documents:
            return None

        # Limit number of documents
        if len(documents) > self.MAX_DOCUMENTS:
            logger.warning(f"Too many documents ({len(documents)}), processing first {self.MAX_DOCUMENTS}")
            documents = documents[: self.MAX_DOCUMENTS]

        extracted_texts: List[str] = []

        for doc in documents:
            if not isinstance(doc, dict):
                logger.warning(f"Invalid document entry (not a dict): {type(doc)}")
                continue

            data = doc.get("data")
            if not data:
                logger.warning("Document entry missing 'data' field")
                continue

            media_type = doc.get("media_type", "application/pdf")
            filename = doc.get("filename")

            text = await self.process_document_payload(data, media_type, filename)
            if text:
                doc_name = filename or "document"
                extracted_texts.append(f"Document '{doc_name}':\n{text}")

        if extracted_texts:
            combined = "\n\n---\n\n".join(extracted_texts)
            logger.info(f"Processed {len(extracted_texts)} documents from API payload")

            # Apply text length limit
            if len(combined) > self._parser.MAX_TEXT_LENGTH:
                logger.warning(f"Combined text too long ({len(combined)} chars), truncating")
                combined = combined[: self._parser.MAX_TEXT_LENGTH] + "\n\n[Text truncated]"

            return combined

        return None


# Singleton instance
_api_document_helper: Optional[APIDocumentHelper] = None


def get_api_document_helper() -> APIDocumentHelper:
    """Get or create the API document helper singleton."""
    global _api_document_helper
    if _api_document_helper is None:
        _api_document_helper = APIDocumentHelper()
    return _api_document_helper
