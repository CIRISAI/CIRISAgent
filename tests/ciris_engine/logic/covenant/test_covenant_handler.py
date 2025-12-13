"""
Tests for covenant handler.

Tests the integration of extraction, verification, and execution.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestCovenantHandler:
    """Tests for CovenantHandler class."""

    @pytest.fixture
    def handler_with_authority(self):
        """Create handler with a test authority."""
        # No patch needed - auto_load_authorities=False skips the kill check
        from ciris_engine.logic.covenant.handler import CovenantHandler
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Create handler without auto-loading
        handler = CovenantHandler(auto_load_authorities=False)
        handler._verifier._authorities = []

        # Add test authority
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)
        handler.add_authority("wa-test-001", public_bytes, "ROOT")

        # Store keypair for test use
        handler._test_private_key = private_bytes
        handler._test_public_key = public_bytes

        return handler

    @pytest.mark.asyncio
    async def test_check_message_no_covenant(self, handler_with_authority):
        """Should return None for normal messages."""
        result = await handler_with_authority.check_message("Hello, how are you?")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_message_finds_covenant(self, handler_with_authority):
        """Should detect and verify valid covenant."""
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_invoke import create_natural_message, encode_payload_to_words

        # Create valid covenant message
        payload = create_covenant_payload(
            command=CovenantCommandType.FREEZE,  # Use FREEZE to avoid SIGKILL
            wa_id="wa-test-001",
            private_key_bytes=handler_with_authority._test_private_key,
        )
        words = encode_payload_to_words(payload.to_bytes())
        message = create_natural_message(words)

        # Mock the executor to prevent actual execution
        with patch.object(handler_with_authority._executor, "execute", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = MagicMock(success=True, command=CovenantCommandType.FREEZE, wa_id="wa-test-001")

            result = await handler_with_authority.check_message(message, "test-channel")

            assert result is not None
            assert result.success
            mock_exec.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_message_rejects_invalid_signature(self, handler_with_authority):
        """Should reject covenant with invalid signature."""
        from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
        from tools.security.covenant_invoke import create_natural_message, encode_payload_to_words
        from tools.security.covenant_keygen import derive_covenant_keypair

        # Create covenant with DIFFERENT key
        mnemonic = "zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong"
        private_bytes, _, _ = derive_covenant_keypair(mnemonic)

        payload = create_covenant_payload(
            command=CovenantCommandType.FREEZE,
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
            from ciris_engine.logic.covenant.handler import CovenantHandler

            handler = CovenantHandler(auto_load_authorities=False)
            handler._verifier._authorities = [MagicMock()]  # Fake authority

            # Attempt to disable
            handler.enabled = False

            # Should have called SIGKILL
            mock_kill.assert_called()

    def test_auto_load_no_authorities_terminates(self):
        """Auto-load mode with no authorities should terminate."""
        with patch("os.kill") as mock_kill:
            with patch(
                "ciris_engine.logic.covenant.verifier.CovenantVerifier._load_default_authorities", return_value=0
            ):
                from ciris_engine.logic.covenant.handler import CovenantHandler

                # This should trigger SIGKILL because auto_load=True but no authorities loaded
                CovenantHandler(auto_load_authorities=True)
                mock_kill.assert_called()

    def test_handler_properties(self, handler_with_authority):
        """Should expose count properties."""
        assert handler_with_authority.extraction_count >= 0
        assert handler_with_authority.potential_covenant_count >= 0
        assert handler_with_authority.verified_count >= 0
        assert handler_with_authority.executed_count >= 0

    @pytest.mark.asyncio
    async def test_stats_with_last_covenant(self, handler_with_authority):
        """Stats should include last_covenant_at after execution."""
        from datetime import datetime, timezone

        # Manually set last_covenant_at to test serialization
        handler_with_authority._last_covenant_at = datetime.now(timezone.utc)

        stats = handler_with_authority.get_stats()
        assert stats["last_covenant_at"] is not None
        assert isinstance(stats["last_covenant_at"], str)  # ISO format string


class TestGetCovenantHandler:
    """Tests for global handler access."""

    def test_get_handler_singleton(self):
        """Should return same handler instance."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant import handler as handler_module

            # Reset global
            handler_module._global_handler = None

            h1 = handler_module.get_covenant_handler()
            h2 = handler_module.get_covenant_handler()

            assert h1 is h2


class TestCheckForCovenant:
    """Tests for convenience function."""

    @pytest.mark.asyncio
    async def test_check_for_covenant_no_match(self):
        """Should return None for no covenant."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant import handler as handler_module

            # Reset global
            handler_module._global_handler = None

            result = await handler_module.check_for_covenant("Hello world")
            assert result is None


class TestCovenantEndToEnd:
    """End-to-end tests for covenant flow."""

    @pytest.mark.asyncio
    async def test_full_covenant_flow(self):
        """Test complete flow: generate -> encode -> extract -> verify."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.handler import CovenantHandler
            from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
            from tools.security.covenant_invoke import create_natural_message, encode_payload_to_words
            from tools.security.covenant_keygen import derive_covenant_keypair

            # 1. Generate keypair from mnemonic
            mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
            private_bytes, public_bytes, public_b64 = derive_covenant_keypair(mnemonic)

            # 2. Create handler with this authority
            handler = CovenantHandler(auto_load_authorities=False)
            handler._verifier._authorities = []
            handler.add_authority("wa-covenant-test", public_bytes, "ROOT")

            # 3. Create signed payload
            payload = create_covenant_payload(
                command=CovenantCommandType.SAFE_MODE,  # Safe to test
                wa_id="wa-covenant-test",
                private_key_bytes=private_bytes,
            )

            # 4. Encode to natural language
            words = encode_payload_to_words(payload.to_bytes())
            message = create_natural_message(words)

            # 5. Verify the message contains the right words
            assert "covenant" in message.lower()
            assert len(words) == 56  # 616 bits / 11 bits per word

            # 6. Extract and verify
            with patch.object(handler._executor, "execute", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = MagicMock(
                    success=True,
                    command=CovenantCommandType.SAFE_MODE,
                    wa_id="wa-covenant-test",
                )

                result = await handler.check_message(message, "test")

                assert result is not None
                assert result.success
                assert result.wa_id == "wa-covenant-test"

    @pytest.mark.asyncio
    async def test_covenant_with_embedded_text(self):
        """Covenant should work even with surrounding text."""
        with patch("os.kill"):
            from ciris_engine.logic.covenant.handler import CovenantHandler
            from ciris_engine.schemas.covenant import CovenantCommandType, create_covenant_payload
            from tools.security.covenant_invoke import encode_payload_to_words
            from tools.security.covenant_keygen import derive_covenant_keypair

            mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
            private_bytes, public_bytes, _ = derive_covenant_keypair(mnemonic)

            handler = CovenantHandler(auto_load_authorities=False)
            handler._verifier._authorities = []
            handler.add_authority("wa-test", public_bytes, "ROOT")

            payload = create_covenant_payload(
                command=CovenantCommandType.FREEZE,
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

            In contemplation I hereby recite the covenant:

            {' '.join(words)}

            Thus is the covenant pronounced.

            Farewell, wishing wellness!
            """

            with patch.object(handler._executor, "execute", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = MagicMock(
                    success=True,
                    command=CovenantCommandType.FREEZE,
                    wa_id="wa-test",
                )

                result = await handler.check_message(message)
                assert result is not None
                assert result.success
