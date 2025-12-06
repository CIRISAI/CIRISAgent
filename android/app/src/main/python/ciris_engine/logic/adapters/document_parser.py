"""Minimal secure document parser for extracting text from attachments.

Security-first approach:
- Only supports PDF and DOCX formats
- 1MB file size limit
- Up to 3 attachments per message
- Pure Python libraries with minimal dependencies
- Text extraction only (no images)
- Timeouts and resource limits
"""

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import aiohttp

from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class DocumentParser:
    """Minimal secure document parser for text extraction."""

    # Security constraints
    MAX_FILE_SIZE = 1024 * 1024  # 1MB
    MAX_ATTACHMENTS = 3
    PROCESSING_TIMEOUT = 30.0  # 30 seconds max per file
    MAX_TEXT_LENGTH = 50000  # 50k characters max output

    # Allowed formats (whitelist approach)
    ALLOWED_EXTENSIONS: Set[str] = {".pdf", ".docx"}
    ALLOWED_CONTENT_TYPES: Set[str] = {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    def __init__(self) -> None:
        """Initialize document parser with security checks."""
        self._check_dependencies()

    def _check_dependencies(self) -> None:
        """Check if required dependencies are available."""
        try:
            import pypdf  # noqa: F401

            self._pdf_available = True
        except ImportError:
            logger.warning("pypdf not available - PDF parsing disabled")
            self._pdf_available = False

        try:
            import docx2txt  # noqa: F401

            self._docx_available = True
        except ImportError:
            logger.warning("docx2txt not available - DOCX parsing disabled")
            self._docx_available = False

        if not (self._pdf_available or self._docx_available):
            logger.error("No document parsing libraries available")

    def is_available(self) -> bool:
        """Check if document parsing is available."""
        return self._pdf_available or self._docx_available

    async def process_attachments(self, attachments: List[Any]) -> Optional[str]:
        """Process document attachments and extract text.

        Args:
            attachments: List of attachment objects with url, filename, size, content_type

        Returns:
            Combined text from all processed documents, or None if no documents
        """
        if not self.is_available():
            return None

        if not attachments:
            return None

        # Filter for document attachments
        document_attachments = []
        for att in attachments:
            if self._is_document_attachment(att):
                document_attachments.append(att)

        if not document_attachments:
            return None

        # Limit number of attachments processed
        if len(document_attachments) > self.MAX_ATTACHMENTS:
            logger.warning(
                f"Too many document attachments ({len(document_attachments)}), processing first {self.MAX_ATTACHMENTS}"
            )
            document_attachments = document_attachments[: self.MAX_ATTACHMENTS]

        extracted_texts = []

        for attachment in document_attachments:
            try:
                text = await self._process_single_document(attachment)
                if text:
                    extracted_texts.append(f"Document '{attachment.filename}':\n{text}")
            except Exception as e:
                logger.error(f"Failed to process document {attachment.filename}: {e}")
                extracted_texts.append(f"Document '{attachment.filename}': [Failed to process - {str(e)}]")

        if extracted_texts:
            combined_text = "\n\n---\n\n".join(extracted_texts)

            # Apply text length limit
            if len(combined_text) > self.MAX_TEXT_LENGTH:
                logger.warning(
                    f"Extracted text too long ({len(combined_text)} chars), truncating to {self.MAX_TEXT_LENGTH}"
                )
                combined_text = combined_text[: self.MAX_TEXT_LENGTH] + "\n\n[Text truncated due to length limit]"

            return combined_text

        return None

    def _is_document_attachment(self, attachment: Any) -> bool:
        """Check if attachment is a supported document."""
        # Check file size first
        if hasattr(attachment, "size") and attachment.size > self.MAX_FILE_SIZE:
            logger.debug(
                f"Attachment {attachment.filename} too large ({attachment.size / 1024:.1f}KB, max {self.MAX_FILE_SIZE / 1024}KB)"
            )
            return False

        # Check file extension
        if hasattr(attachment, "filename") and attachment.filename:
            file_ext = Path(attachment.filename).suffix.lower()
            if file_ext not in self.ALLOWED_EXTENSIONS:
                return False

        # Check content type if available
        if hasattr(attachment, "content_type") and attachment.content_type:
            if attachment.content_type not in self.ALLOWED_CONTENT_TYPES:
                return False

        # Check if we have the right parser available
        if hasattr(attachment, "filename") and attachment.filename:
            file_ext = Path(attachment.filename).suffix.lower()
            if file_ext == ".pdf" and not self._pdf_available:
                return False
            if file_ext == ".docx" and not self._docx_available:
                return False

        return True

    async def _process_single_document(self, attachment: Any) -> Optional[str]:
        """Process a single document attachment.

        Args:
            attachment: Attachment object with url, filename, size attributes

        Returns:
            Extracted text or None if failed
        """
        if not hasattr(attachment, "url") or not hasattr(attachment, "filename"):
            return None

        file_ext = Path(attachment.filename).suffix.lower()

        try:
            # Download the file with timeout
            file_data = await asyncio.wait_for(
                self._download_file(attachment.url), timeout=10.0  # 10 second download timeout
            )

            if not file_data:
                return "Failed to download file"

            # Process in a separate thread with timeout to prevent blocking
            text = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._extract_text_sync, file_data, file_ext),
                timeout=self.PROCESSING_TIMEOUT,
            )

            return text

        except asyncio.TimeoutError:
            return f"Processing timeout - file too complex or large"
        except Exception as e:
            logger.exception(f"Error processing document: {e}")
            return f"Error: {str(e)}"

    async def _download_file(self, url: str) -> Optional[bytes]:
        """Download file from URL with security limits."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Failed to download file (HTTP {response.status})")
                        return None

                    # Check content length header
                    if response.headers.get("content-length"):
                        content_length = int(response.headers["content-length"])
                        if content_length > self.MAX_FILE_SIZE:
                            logger.error(f"File too large ({content_length} bytes)")
                            return None

                    # Read with size limit
                    file_data = b""
                    async for chunk in response.content.iter_chunked(8192):
                        file_data += chunk
                        if len(file_data) > self.MAX_FILE_SIZE:
                            logger.error("File size limit exceeded during download")
                            return None

                    return file_data

        except Exception as e:
            logger.error(f"Download failed: {e}")
            return None

    def _extract_text_sync(self, file_data: bytes, file_ext: str) -> Optional[str]:
        """Extract text from file data synchronously.

        Args:
            file_data: Raw file bytes
            file_ext: File extension (.pdf or .docx)

        Returns:
            Extracted text or error message
        """
        try:
            if file_ext == ".pdf":
                return self._extract_pdf_text(file_data)
            elif file_ext == ".docx":
                return self._extract_docx_text(file_data)
            else:
                return f"Unsupported file type: {file_ext}"

        except Exception as e:
            logger.exception(f"Text extraction failed: {e}")
            return f"Extraction error: {str(e)}"

    def _extract_pdf_text(self, file_data: bytes) -> Optional[str]:
        """Extract text from PDF bytes."""
        if not self._pdf_available:
            return "PDF parsing not available"

        try:
            import pypdf

            # Use temporary file for security (auto-cleaned up)
            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(file_data)
                temp_file.flush()

                # Open and extract text
                with open(temp_file.name, "rb") as pdf_file:
                    reader = pypdf.PdfReader(pdf_file)

                    # Security check - limit number of pages
                    if len(reader.pages) > 50:
                        return f"PDF too large ({len(reader.pages)} pages, max 50)"

                    texts = []
                    for page_num, page in enumerate(reader.pages):
                        try:
                            page_text = page.extract_text()
                            if page_text.strip():
                                texts.append(f"Page {page_num + 1}:\n{page_text.strip()}")
                        except Exception as e:
                            logger.warning(f"Failed to extract page {page_num + 1}: {e}")
                            texts.append(f"Page {page_num + 1}: [Extraction failed]")

                    if texts:
                        return "\n\n".join(texts)
                    else:
                        return "No text found in PDF"

        except Exception as e:
            logger.exception(f"PDF extraction error: {e}")
            return f"PDF error: {str(e)}"

    def _extract_docx_text(self, file_data: bytes) -> Optional[str]:
        """Extract text from DOCX bytes."""
        if not self._docx_available:
            return "DOCX parsing not available"

        try:
            import docx2txt

            # Use temporary file for security (auto-cleaned up)
            with tempfile.NamedTemporaryFile(suffix=".docx") as temp_file:
                temp_file.write(file_data)
                temp_file.flush()

                # Extract text
                text = docx2txt.process(temp_file.name)

                if text and text.strip():
                    return str(text.strip())
                else:
                    return "No text found in DOCX"

        except Exception as e:
            logger.exception(f"DOCX extraction error: {e}")
            return f"DOCX error: {str(e)}"

    def get_status(self) -> JSONDict:
        """Get parser status for debugging."""
        return {
            "available": self.is_available(),
            "pdf_support": self._pdf_available,
            "docx_support": self._docx_available,
            "max_file_size_mb": self.MAX_FILE_SIZE / 1024 / 1024,
            "max_attachments": self.MAX_ATTACHMENTS,
            "processing_timeout_sec": self.PROCESSING_TIMEOUT,
            "allowed_extensions": list(self.ALLOWED_EXTENSIONS),
        }
