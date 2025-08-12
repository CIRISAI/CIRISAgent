import base64
import logging
from abc import ABC, abstractmethod
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class STTService(ABC):
    @abstractmethod
    async def transcribe(self, audio_data: bytes, format: str = "wav") -> Optional[str]:
        pass


class OpenAISTTService(STTService):
    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.openai.com/v1/audio/transcriptions"

    async def transcribe(self, audio_data: bytes, format: str = "wav") -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            form = aiohttp.FormData()
            form.add_field("file", audio_data, filename=f"audio.{format}", content_type=f"audio/{format}")
            form.add_field("model", self.model)

            async with session.post(self.api_url, headers=headers, data=form) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get("text")
                else:
                    error = await response.text()
                    raise Exception(f"OpenAI STT error: {error}")


class GoogleSTTService(STTService):
    def __init__(self, api_key: str, language: str = "en-US"):
        # api_key is actually the path to service account JSON
        self.credentials_path = api_key
        self.language = language
        # Don't log sensitive credential paths
        logger.info("GoogleSTTService initialized")

        # Import here to avoid dependency if not using Google
        # Check if file exists
        import os

        from google.oauth2 import service_account

        if not os.path.exists(self.credentials_path):
            # Don't log sensitive paths
            logger.error("Credentials file not found")
            raise FileNotFoundError(f"Google credentials file not found: {self.credentials_path}")

        # Log file size for debugging
        file_size = os.path.getsize(self.credentials_path)
        logger.info(f"Credentials file size: {file_size} bytes")

        # Try to load and validate the JSON
        try:
            import json

            with open(self.credentials_path, "r") as f:
                creds_data = json.load(f)
                logger.info(f"Credentials loaded successfully, project_id: {creds_data.get('project_id', 'MISSING')}")
                # Check for required fields
                required_fields = ["type", "project_id", "private_key_id", "private_key", "client_email"]
                missing_fields = [field for field in required_fields if field not in creds_data]
                if missing_fields:
                    logger.error(f"Missing required fields in credentials: {missing_fields}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in credentials file: {e}")
            # Log first 200 chars of file for debugging
            with open(self.credentials_path, "r") as f:
                content = f.read(200)
                logger.error(f"First 200 chars of file: {content}")

        self.credentials = service_account.Credentials.from_service_account_file(
            self.credentials_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self.api_url = "https://speech.googleapis.com/v1/speech:recognize"

    async def transcribe(self, audio_data: bytes, format: str = "wav") -> Optional[str]:
        # Import here to avoid dependency at module level
        from google.auth.transport.requests import Request

        # Refresh token if needed or if we don't have one yet
        if not self.credentials.token or (self.credentials.expired is not None and self.credentials.expired):
            logger.info("Refreshing Google credentials token...")
            self.credentials.refresh(Request())
            logger.info(f"Token refreshed, expires at: {self.credentials.expiry}")

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.credentials.token}", "Content-Type": "application/json"}
            audio_content = base64.b64encode(audio_data).decode("utf-8")
            payload = {
                "config": {
                    "encoding": "WEBM_OPUS" if format == "webm" else "LINEAR16",
                    "sampleRateHertz": 16000,
                    "languageCode": self.language,
                },
                "audio": {"content": audio_content},
            }

            async with session.post(self.api_url, headers=headers, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    if result.get("results"):
                        return result["results"][0]["alternatives"][0]["transcript"]
                else:
                    error = await response.text()
                    raise Exception(f"Google STT error: {error}")


def create_stt_service(config) -> STTService:
    if config.provider == "openai":
        return OpenAISTTService(config.api_key, config.model)
    elif config.provider == "google":
        credentials_path = config.google_credentials_path or config.api_key
        return GoogleSTTService(credentials_path, config.google_language_code)
    else:
        raise ValueError(f"Unknown STT provider: {config.provider}")
