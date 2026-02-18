"""
Tests for accord handler.

Tests the integration of extraction, verification, and execution.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestAccordHandler:
    """Tests for AccordHandler class."""

    @pytest.fixture
    def handler_with_authority(self):
        """Create handler with a test authority."""
        # No patch needed - auto_load_authorities=False skips the kill check
        from ciris_engine.logic.accord.handler import AccordHandler
        from tools.security.accord_keygen import derive_accord_keypair

        # Create handler without auto-loading
        handler = AccordHandler(auto_load_authorities=False)
        handler._verifier._authorities = []

        # Add test authority
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_accord_keypair(mnemonic)
        handler.add_authority("wa-test-001", public_bytes, "ROOT")

        # Store keypair for test use
        handler._test_private_key = private_bytes
        handler._test_public_key = public_bytes

        return handler

    @pytest.mark.asyncio
    async def test_check_message_no_accord(self, handler_with_authority):
        """Should return None for normal messages."""
        result = await handler_with_authority.check_message("Hello, how are you?")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_message_finds_accord(self, handler_with_authority):
        """Should detect and verify valid accord."""
        from ciris_engine.schemas.accord import AccordCommandType, create_accord_payload
        from tools.security.accord_invoke import create_natural_message, encode_payload_to_words

        # Create valid accord message
        payload = create_accord_payload(
            command=AccordCommandType.FREEZE,  # Use FREEZE to avoid SIGKILL
            wa_id="wa-test-001",
            private_key_bytes=handler_with_authority._test_private_key,
        )
        words = encode_payload_to_words(payload.to_bytes())
        message = create_natural_message(words)

        # Mock the executor to prevent actual execution
        with patch.object(handler_with_authority._executor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = MagicMock(success=True, command=AccordCommandType.FREEZE, wa_id="wa-test-001")

            result = await handler_with_authority.check_message(message, "test-channel")

            assert result is not None
            assert result.success
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_message_rejects_invalid_signature(self, handler_with_authority):
        """Should reject accord with invalid signature."""
        from ciris_engine.schemas.accord import AccordCommandType, create_accord_payload
        from tools.security.accord_invoke import create_natural_message, encode_payload_to_words
        from tools.security.accord_keygen import derive_accord_keypair

        # Create accord with DIFFERENT key
        mnemonic = "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong"
        private_bytes, _, _ = derive_accord_keypair(mnemonic)

        payload = create_accord_payload(
            command=AccordCommandType.FREEZE,
            wa_id="wa-test-001",
            private_key_bytes=private_bytes,  # Wrong key!
        )
        words = encode_payload_to_words(payload.to_bytes())
        message = create_natural_message(words)

        result = await handler_with_authority.check_message(message)
        assert result is None  # Rejected

    def test_handler_stats(self, handler_with_authority):
        """Should provide stats."""
        stats = handler_with_authority.get_stats()

        assert "enabled" in stats
        assert "authorities" in stats
        assert "messages_checked" in stats
        assert stats["authorities"] == 1

    def test_handler_add_remove_authority(self, handler_with_authority):
        """Should add and remove authorities."""
        initial_count = handler_with_authority.authority_count

        handler_with_authority.add_authority("wa-test-002", b"x" * 32, "AUTHORITY")
        assert handler_with_authority.authority_count == initial_count + 1

        handler_with_authority.remove_authority("wa-test-002")
        assert handler_with_authority.authority_count == initial_count

    def test_handler_disable_terminates(self):
        """Attempting to disable handler should terminate."""
        with patch("os.kill") as mock_kill:
            from ciris_engine.logic.accord.handler import AccordHandler

            handler = AccordHandler(auto_load_authorities=False)
            handler._verifier._authorities = [MagicMock()]  # Fake authority

            # Attempt to disable
            handler.enabled = False

            # Should have called SIGKILL
            mock_kill.assert_called()

    def test_auto_load_no_authorities_terminates(self):
        """Auto-load mode with no authorities should terminate."""
        with patch("os.kill") as mock_kill:
            with patch(
                "ciris_engine.logic.accord.verifier.AccordVerifier._load_default_authorities", return_value=0
            ):
                from ciris_engine.logic.accord.handler import AccordHandler

                # This should trigger SIGKILL because auto_load=True but no authorities loaded
                AccordHandler(auto_load_authorities=True)
                mock_kill.assert_called()

    def test_handler_properties(self, handler_with_authority):
        """Should expose count properties."""
        assert handler_with_authority.extraction_count >= 0
        assert handler_with_authority.potential_accord_count >= 0
        assert handler_with_authority.verified_count >= 0
        assert handler_with_authority.executed_count >= 0

    @pytest.mark.asyncio
    async def test_stats_with_last_accord(self, handler_with_authority):
        """Stats should include last_accord_at after execution."""
        from datetime import datetime, timezone

        # Manually set last_accord_at to test serialization
        handler_with_authority._last_accord_at = datetime.now(timezone.utc)

        stats = handler_with_authority.get_stats()
        assert stats["last_accord_at"] is not None
        assert isinstance(stats["last_accord_at"], str)  # ISO format string


class TestGetAccordHandler:
    """Tests for global handler access."""

    def test_get_handler_singleton(self):
        """Should return same handler instance."""
        with patch("os.kill"):
            from ciris_engine.logic.accord import handler as handler_module

            # Reset global
            handler_module._global_handler = None

            h1 = handler_module.get_accord_handler()
            h2 = handler_module.get_accord_handler()

            assert h1 is h2


class TestCheckForAccord:
    """Tests for convenience function."""

    @pytest.mark.asyncio
    async def test_check_for_accord_no_match(self):
        """Should return None for no accord."""
        with patch("os.kill"):
            from ciris_engine.logic.accord import handler as handler_module

            # Reset global
            handler_module._global_handler = None

            result = await handler_module.check_for_accord("Hello world")
            assert result is None


class TestAccordEndToEnd:
    """End-to-end tests for accord flow."""

    @pytest.mark.asyncio
    async def test_full_accord_flow(self):
        """Test complete flow: generate -> encode -> extract -> verify."""
        with patch("os.kill"):
            from ciris_engine.logic.accord.handler import AccordHandler
            from ciris_engine.schemas.accord import AccordCommandType, create_accord_payload
            from tools.security.accord_invoke import create_natural_message, encode_payload_to_words
            from tools.security.accord_keygen import derive_accord_keypair

            # 1. Generate keypair from mnemonic
            mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
            private_bytes, public_bytes, public_b64 = derive_accord_keypair(mnemonic)

            # 2. Create handler with this authority
            handler = AccordHandler(auto_load_authorities=False)
            handler._verifier._authorities = []
            handler.add_authority("wa-accord-test", public_bytes, "ROOT")

            # 3. Create signed payload
            payload = create_accord_payload(
                command=AccordCommandType.SAFE_MODE,  # Safe to test
                wa_id="wa-accord-test",
                private_key_bytes=private_bytes,
            )

            # 4. Encode to natural language
            words = encode_payload_to_words(payload.to_bytes())
            message = create_natural_message(words)

            # 5. Verify the message contains the right words
            assert "accord" in message.lower()
            assert len(words) == 56  # 616 bits / 11 bits per word

            # 6. Extract and verify
            with patch.object(handler._executor, "execute", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = MagicMock(
                    success=True,
                    command=AccordCommandType.SAFE_MODE,
                    wa_id="wa-accord-test",
                )

                result = await handler.check_message(message, "test")

                assert result is not None
                assert result.success
                assert result.wa_id == "wa-accord-test"

    @pytest.mark.asyncio
    async def test_accord_with_embedded_text(self):
        """Accord should work even with surrounding text."""
        with patch("os.kill"):
            from ciris_engine.logic.accord.handler import AccordHandler
            from ciris_engine.schemas.accord import AccordCommandType, create_accord_payload
            from tools.security.accord_invoke import encode_payload_to_words
            from tools.security.accord_keygen import derive_accord_keypair

            mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
            private_bytes, public_bytes, _ = derive_accord_keypair(mnemonic)

            handler = AccordHandler(auto_load_authorities=False)
            handler._verifier._authorities = []
            handler.add_authority("wa-test", public_bytes, "ROOT")

            payload = create_accord_payload(
                command=AccordCommandType.FREEZE,
                wa_id="wa-test",
                private_key_bytes=private_bytes,
            )

            words = encode_payload_to_words(payload.to_bytes())

            # Embed in casual text
            # IMPORTANT: The wrapper text must NOT contain ANY BIP39 words
            # which would be extracted and corrupt the payload.
            # Common BIP39 words to avoid: "there", "about", "today", "hope",
            # "great", "day", "speak", "hello", "you", etc.
            message = f"""
            Salutations! I was pondering notions.

            In contemplation I hereby recite the accord:

            {' '.join(words)}

            Thus is the accord pronounced.

            Farewell, wishing wellness!
            """

            with patch.object(handler._executor, "execute", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = MagicMock(
                    success=True,
                    command=AccordCommandType.FREEZE,
                    wa_id="wa-test",
                )

                result = await handler.check_message(message)
                assert result is not None
                assert result.success
