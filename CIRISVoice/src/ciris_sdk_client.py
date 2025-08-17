"""
CIRIS SDK Client for Wyoming Voice Bridge.

Uses the official CIRIS SDK for improved reliability and features.
Configured for 58-second timeout to work with Home Assistant's 60-second pipeline.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

# Import SDK - it's installed locally in the container
try:
    import os
    import sys

    # Debug: Check if SDK directory exists
    sdk_paths = ["/app/sdk", "/app/sdk/ciris_sdk", "/app/ciris_sdk"]
    for path in sdk_paths:
        if os.path.exists(path):
            print(f"DEBUG: Found SDK at {path}")
            if os.path.isdir(path):
                print(f"DEBUG: Contents: {os.listdir(path)}")

    # Try multiple import methods
    imported = False

    # Method 1: Try as installed package (from pip install -e)
    try:
        from ciris_sdk.client import CIRISClient as SDKCIRISClient
        from ciris_sdk.exceptions import CIRISError, CIRISTimeoutError

        print("DEBUG: Successfully imported CIRIS SDK as installed package")
        imported = True
    except ImportError as e:
        print(f"DEBUG: Method 1 failed: {e}")

    # Method 2: Try direct import from /app/sdk (files are directly there)
    if not imported:
        sys.path.insert(0, "/app/sdk")
        try:
            from client import CIRISClient as SDKCIRISClient
            from exceptions import CIRISError, CIRISTimeoutError

            print("DEBUG: Successfully imported CIRIS SDK from /app/sdk directly")
            imported = True
        except ImportError as e:
            print(f"DEBUG: Method 2 failed: {e}")

    if not imported:
        raise ImportError("Could not import CIRIS SDK from any location")
except ImportError as e:
    print(f"DEBUG: Failed to import SDK: {e}")
    # Fallback for development without SDK installed
    SDKCIRISClient = None
    CIRISError = Exception
    CIRISTimeoutError = asyncio.TimeoutError

logger = logging.getLogger(__name__)


class CIRISVoiceClient:
    """CIRIS client optimized for voice interactions with extended timeout."""

    def __init__(self, config):
        """
        Initialize the CIRIS voice client.

        Args:
            config: Configuration object with api_url, api_key, channel_id, etc.
        """
        if SDKCIRISClient is None:
            raise ImportError("CIRIS SDK not installed. Please run: pip install ciris-sdk")

        # Initialize SDK client with extended timeout
        logger.debug(f"Initializing SDK with base_url={config.api_url}, api_key={'***' if config.api_key else 'None'}")
        self.client = SDKCIRISClient(
            base_url=config.api_url,
            api_key=config.api_key,
            timeout=58.0,  # 58 seconds - just under HA's 60s timeout
            max_retries=0,  # No retries for voice - we have one shot
        )

        # Voice-specific configuration
        self.channel_id = f"voice_{config.channel_id}"
        self.profile = getattr(config, "profile", "default")
        self.language = getattr(config, "language", "en-US")

        # Track session for context
        self.session_id = None
        self.conversation_start = None

        logger.info(f"CIRIS Voice Client initialized for channel: {self.channel_id}")

    async def initialize(self):
        """
        Initialize the client and authenticate if needed.

        For API key auth, this is a no-op. For username/password,
        this would handle login.
        """
        try:
            # Start the transport
            await self.client.__aenter__()

            logger.info(f"Attempting to connect to CIRIS at {self.client._transport.base_url}")

            # Check if we have username:password format
            if self.client._transport.api_key and ":" in self.client._transport.api_key:
                username, password = self.client._transport.api_key.split(":", 1)
                logger.info("Using username/password auth")

                # Login to get token
                try:
                    token = await self.client.auth.login(username, password)
                    logger.info("Successfully logged in, got access token")
                    # Update the transport with the new token
                    self.client._transport.set_api_key(token.access_token)
                except Exception as e:
                    logger.error(f"Failed to login: {e}")
                    raise
            else:
                logger.info(f"Using auth: {'API key' if self.client._transport.api_key else 'None'}")

            # Test connection and auth
            status = await self.client.agent.get_status()
            logger.info(f"Connected to CIRIS agent: {status.name} (state: {status.cognitive_state})")

            # Start new session
            self.session_id = f"voice_session_{datetime.now().timestamp()}"
            self.conversation_start = datetime.now()

        except CIRISError as e:
            logger.error(f"Failed to initialize CIRIS client: {e}")
            logger.error(f"Error details: {type(e).__name__}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error initializing CIRIS: {type(e).__name__}: {str(e)}")
            raise

    async def send_message(self, content: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Send a voice message to CIRIS and wait for response.

        Args:
            content: The transcribed user speech
            context: Optional additional context

        Returns:
            Dict with 'content' key containing the response text
        """
        try:
            # Build voice-specific context with channel_id
            voice_context = {
                "source": "wyoming_voice",
                "channel_id": self.channel_id,  # Pass channel_id in context
                "profile": self.profile,
                "language": self.language,
                "session_id": self.session_id,
                "input_method": "voice",
                "timestamp": datetime.now().isoformat(),
            }

            # Merge with provided context
            if context:
                voice_context.update(context)

            logger.info(f"Sending to CIRIS: '{content[:50]}...' on channel {self.channel_id}")

            # Use the SDK's agent interact method (without channel_id parameter)
            response = await self.client.agent.interact(message=content, context=voice_context)

            # Log response time for monitoring
            processing_time = response.processing_time_ms / 1000.0
            logger.info(f"CIRIS responded in {processing_time:.1f}s: '{response.response[:50]}...'")

            # Return in expected format
            return {
                "content": response.response,
                "message_id": response.message_id,
                "state": response.state,
                "processing_time": response.processing_time_ms,
            }

        except CIRISTimeoutError:
            # Timeout after 58 seconds
            logger.warning("CIRIS timeout after 58 seconds")
            return {
                "content": "That took too long to process. Please try again.",
                "message_id": None,
                "state": "timeout",
                "processing_time": 58000,
            }

        except CIRISError as e:
            # API errors (auth, validation, etc)
            logger.error(f"CIRIS API error: {e}")
            return {
                "content": "I'm having trouble understanding that request.",
                "message_id": None,
                "state": "error",
                "processing_time": 0,
            }

        except Exception as e:
            # Unexpected errors
            logger.exception(f"Unexpected error: {e}")
            return {
                "content": "I'm experiencing technical difficulties.",
                "message_id": None,
                "state": "error",
                "processing_time": 0,
            }

    async def get_conversation_history(self, limit: int = 10) -> Optional[list]:
        """
        Get recent conversation history for context.

        Args:
            limit: Maximum number of messages to retrieve

        Returns:
            List of recent messages or None if unavailable
        """
        try:
            history = await self.client.agent.get_history(channel_id=self.channel_id, limit=limit)

            return [
                {
                    "role": "assistant" if msg.is_agent else "user",
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                }
                for msg in history.messages
            ]

        except CIRISError as e:
            logger.warning(f"Could not retrieve history: {e}")
            return None

    async def end_session(self):
        """
        End the current voice session and clean up.
        """
        if self.session_id:
            logger.info(f"Ending voice session: {self.session_id}")

            # Log session duration
            if self.conversation_start:
                duration = (datetime.now() - self.conversation_start).total_seconds()
                logger.info(f"Session duration: {duration:.1f} seconds")

            # Reset session
            self.session_id = None
            self.conversation_start = None

    async def close(self):
        """
        Close the client and clean up resources.
        """
        try:
            await self.client.__aexit__(None, None, None)
            logger.info("CIRIS client closed successfully")
        except Exception as e:
            logger.error(f"Error closing CIRIS client: {e}")
        logger.info("CIRIS Voice Client closed")


# Backward compatibility wrapper
class CIRISClient:
    """
    Backward compatibility wrapper to match original interface.

    This allows dropping in the SDK-based client without changing
    the existing bridge code.
    """

    def __init__(self, config):
        self.voice_client = CIRISVoiceClient(config)
        self._initialized = False

    async def send_message(self, content: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send message using the new SDK client."""
        # Auto-initialize on first use
        if not self._initialized:
            await self.voice_client.initialize()
            self._initialized = True

        return await self.voice_client.send_message(content, context)

    async def get_response(self, message_id: str) -> Optional[str]:
        """
        Legacy method - not needed with SDK as responses are synchronous.

        Kept for compatibility but returns None.
        """
        return None
