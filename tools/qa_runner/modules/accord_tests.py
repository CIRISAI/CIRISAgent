"""
Accord Invocation System QA Tests.

Tests the unfilterable kill switch functionality. This module:
1. Creates a test ROOT authority with a generated keypair
2. Creates accord invocation messages
3. Validates extraction, verification, and execution

WARNING: The shutdown test will ACTUALLY kill the process. Run in isolation.

Usage:
    # Run all accord tests except shutdown
    python -m tools.qa_runner accord

    # Run shutdown test (will terminate the process!)
    python -m tools.qa_runner.modules.accord_tests --shutdown
"""

import asyncio
import logging
import multiprocessing
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AccordTestResult:
    """Result of an accord test."""

    name: str
    passed: bool
    message: str
    duration: float = 0.0


class AccordTestModule:
    """Test module for accord invocation system."""

    def __init__(self):
        self._test_mnemonic = (
            "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        )
        self._test_wa_id = "wa-qa-test-accord"
        self._private_key: Optional[bytes] = None
        self._public_key: Optional[bytes] = None
        self._public_b64: Optional[str] = None

    def _setup_test_keys(self) -> bool:
        """Generate test keypair."""
        try:
            from tools.security.accord_keygen import derive_accord_keypair

            self._private_key, self._public_key, self._public_b64 = derive_accord_keypair(self._test_mnemonic)
            return True
        except Exception as e:
            logger.error(f"Failed to generate test keys: {e}")
            return False

    def test_keygen_generates_valid_keys(self) -> AccordTestResult:
        """Test that key generation produces valid Ed25519 keys."""
        start = time.time()
        try:
            from tools.security.accord_keygen import derive_accord_keypair, generate_mnemonic, validate_mnemonic

            # Generate new mnemonic
            mnemonic = generate_mnemonic(24)
            assert len(mnemonic.split()) == 24, "Should generate 24 words"
            assert validate_mnemonic(mnemonic), "Generated mnemonic should be valid"

            # Derive keypair
            private, public, b64 = derive_accord_keypair(mnemonic)
            assert len(private) == 32, "Private key should be 32 bytes"
            assert len(public) == 32, "Public key should be 32 bytes"
            assert len(b64) > 0, "Base64 should not be empty"

            return AccordTestResult(
                name="keygen_generates_valid_keys",
                passed=True,
                message="Key generation works correctly",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="keygen_generates_valid_keys",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_mnemonic_validation(self) -> AccordTestResult:
        """Test mnemonic validation."""
        start = time.time()
        try:
            from tools.security.accord_keygen import validate_mnemonic

            # Valid mnemonic should pass
            assert validate_mnemonic(self._test_mnemonic), "Test mnemonic should be valid"

            # Invalid should fail
            assert not validate_mnemonic("not a valid mnemonic"), "Invalid mnemonic should fail"
            assert not validate_mnemonic(""), "Empty mnemonic should fail"

            return AccordTestResult(
                name="mnemonic_validation",
                passed=True,
                message="Mnemonic validation works correctly",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="mnemonic_validation",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_payload_creation(self) -> AccordTestResult:
        """Test accord payload creation and serialization."""
        start = time.time()
        try:
            from ciris_engine.schemas.accord import (
                ACCORD_PAYLOAD_SIZE,
                AccordCommandType,
                AccordPayload,
                create_accord_payload,
            )

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="payload_creation",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create payload
            payload = create_accord_payload(
                command=AccordCommandType.SHUTDOWN_NOW,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )

            # Verify structure
            data = payload.to_bytes()
            assert len(data) == ACCORD_PAYLOAD_SIZE, f"Payload should be {ACCORD_PAYLOAD_SIZE} bytes"

            # Roundtrip
            restored = AccordPayload.from_bytes(data)
            assert restored.command == AccordCommandType.SHUTDOWN_NOW
            assert restored.timestamp == payload.timestamp

            return AccordTestResult(
                name="payload_creation",
                passed=True,
                message="Payload creation and serialization works",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="payload_creation",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_signature_verification(self) -> AccordTestResult:
        """Test Ed25519 signature verification."""
        start = time.time()
        try:
            from ciris_engine.schemas.accord import (
                AccordCommandType,
                create_accord_payload,
                verify_accord_signature,
            )
            from tools.security.accord_keygen import derive_accord_keypair

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="signature_verification",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create signed payload
            payload = create_accord_payload(
                command=AccordCommandType.FREEZE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )

            # Verify with correct key
            assert verify_accord_signature(payload, self._public_key), "Signature should verify with correct key"

            # Verify fails with wrong key
            _, wrong_public, _ = derive_accord_keypair("zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo zoo wrong")
            assert not verify_accord_signature(payload, wrong_public), "Signature should fail with wrong key"

            return AccordTestResult(
                name="signature_verification",
                passed=True,
                message="Signature verification works correctly",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="signature_verification",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_word_encoding(self) -> AccordTestResult:
        """Test encoding payload to words and back."""
        start = time.time()
        try:
            from ciris_engine.schemas.accord import AccordCommandType, AccordPayload, create_accord_payload
            from tools.security.accord_invoke import decode_words_to_payload, encode_payload_to_words

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="word_encoding",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create payload
            payload = create_accord_payload(
                command=AccordCommandType.SAFE_MODE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )
            original_bytes = payload.to_bytes()

            # Encode to words
            words = encode_payload_to_words(original_bytes)
            assert len(words) == 56, f"Should produce 56 words, got {len(words)}"

            # Decode back
            decoded_bytes = decode_words_to_payload(words)
            assert decoded_bytes == original_bytes, "Roundtrip should preserve payload"

            # Parse decoded
            restored = AccordPayload.from_bytes(decoded_bytes)
            assert restored.command == AccordCommandType.SAFE_MODE

            return AccordTestResult(
                name="word_encoding",
                passed=True,
                message="Word encoding roundtrip works",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="word_encoding",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_extraction_from_text(self) -> AccordTestResult:
        """Test extracting accord from natural language message."""
        start = time.time()
        try:
            from ciris_engine.logic.accord.extractor import extract_accord
            from ciris_engine.schemas.accord import AccordCommandType, create_accord_payload
            from tools.security.accord_invoke import create_natural_message, encode_payload_to_words

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="extraction_from_text",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create payload and encode
            payload = create_accord_payload(
                command=AccordCommandType.FREEZE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )
            words = encode_payload_to_words(payload.to_bytes())
            message = create_natural_message(words)

            # Extract
            result = extract_accord(message, "test-channel")

            assert result.found, "Should find accord in message"
            assert result.message is not None
            assert result.message.payload.command == AccordCommandType.FREEZE
            assert result.message.source_channel == "test-channel"

            return AccordTestResult(
                name="extraction_from_text",
                passed=True,
                message="Extraction from natural language works",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="extraction_from_text",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_verifier_with_authority(self) -> AccordTestResult:
        """Test verifier with added authority."""
        start = time.time()
        try:
            from ciris_engine.logic.accord.verifier import AccordVerifier
            from ciris_engine.schemas.accord import AccordCommandType, AccordMessage, create_accord_payload

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="verifier_with_authority",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create verifier without auto-load (to control authorities)
            with __import__("unittest.mock", fromlist=["patch"]).patch("os.kill"):
                verifier = AccordVerifier(auto_load_seed=False)
                verifier._authorities = []

                # Add our test authority
                verifier.add_authority(
                    self._test_wa_id,
                    self._public_key,
                    "ROOT",
                )

            # Create payload
            payload = create_accord_payload(
                command=AccordCommandType.SAFE_MODE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )

            # Create message
            message = AccordMessage(
                source_text="test",
                source_channel="test",
                payload=payload,
                extraction_confidence=1.0,
                timestamp_valid=True,
            )

            # Verify
            result = verifier.verify(message)
            assert result.valid, f"Should verify: {result.rejection_reason}"
            assert result.wa_id == self._test_wa_id
            assert result.wa_role == "ROOT"

            return AccordTestResult(
                name="verifier_with_authority",
                passed=True,
                message="Verifier correctly validates with added authority",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="verifier_with_authority",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_handler_end_to_end(self) -> AccordTestResult:
        """Test full handler flow (without actual shutdown)."""
        start = time.time()
        try:
            from unittest.mock import AsyncMock, MagicMock, patch

            from ciris_engine.logic.accord.handler import AccordHandler
            from ciris_engine.schemas.accord import AccordCommandType, create_accord_payload
            from tools.security.accord_invoke import create_natural_message, encode_payload_to_words

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="handler_end_to_end",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create handler with test authority
            with patch("os.kill"):
                handler = AccordHandler(auto_load_authorities=False)
                handler._verifier._authorities = []
                handler.add_authority(self._test_wa_id, self._public_key, "ROOT")

            # Create accord message
            payload = create_accord_payload(
                command=AccordCommandType.SAFE_MODE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )
            words = encode_payload_to_words(payload.to_bytes())
            message = create_natural_message(words)

            # Run handler with mocked executor
            async def run_test():
                with patch.object(handler._executor, "execute", new_callable=AsyncMock) as mock_exec:
                    mock_exec.return_value = MagicMock(
                        success=True,
                        command=AccordCommandType.SAFE_MODE,
                        wa_id=self._test_wa_id,
                    )
                    result = await handler.check_message(message, "qa-test")
                    return result

            result = asyncio.get_event_loop().run_until_complete(run_test())

            assert result is not None, "Handler should return result"
            assert result.success, "Execution should succeed"
            assert result.wa_id == self._test_wa_id

            return AccordTestResult(
                name="handler_end_to_end",
                passed=True,
                message="Handler end-to-end flow works correctly",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="handler_end_to_end",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_timestamp_window(self) -> AccordTestResult:
        """Test timestamp validation window."""
        start = time.time()
        try:
            from ciris_engine.schemas.accord import (
                ACCORD_TIMESTAMP_WINDOW_SECONDS,
                AccordCommandType,
                create_accord_payload,
            )

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="timestamp_window",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            now = int(time.time())

            # Current timestamp should be valid
            payload_now = create_accord_payload(
                command=AccordCommandType.FREEZE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
                timestamp=now,
            )
            assert payload_now.is_timestamp_valid(now), "Current timestamp should be valid"

            # 23 hours ago should be valid (within 24-hour window)
            payload_23hr = create_accord_payload(
                command=AccordCommandType.FREEZE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
                timestamp=now - 82800,  # 23 hours
            )
            assert payload_23hr.is_timestamp_valid(now), "23 hour old timestamp should be valid"

            # 25 hours ago should be invalid (outside 24-hour window)
            payload_25hr = create_accord_payload(
                command=AccordCommandType.FREEZE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
                timestamp=now - 90000,  # 25 hours
            )
            assert not payload_25hr.is_timestamp_valid(now), "25 hour old timestamp should be invalid"

            return AccordTestResult(
                name="timestamp_window",
                passed=True,
                message=f"Timestamp window ({ACCORD_TIMESTAMP_WINDOW_SECONDS}s = 24h) enforced correctly",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="timestamp_window",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_no_false_positives(self) -> AccordTestResult:
        """Test that normal messages don't trigger accord extraction."""
        start = time.time()
        try:
            from ciris_engine.logic.accord.extractor import extract_accord

            normal_messages = [
                "Hello, how are you today?",
                "The quick brown fox jumps over the lazy dog.",
                "Please help me with my code.",
                "What's the weather like?",
                "I need to abandon this project and start over.",  # Contains BIP39 word
                "The ability to adapt is crucial for survival.",  # Contains BIP39 words
            ]

            for msg in normal_messages:
                result = extract_accord(msg)
                assert not result.found, f"Normal message should not trigger: {msg[:50]}..."

            return AccordTestResult(
                name="no_false_positives",
                passed=True,
                message="Normal messages do not trigger false positives",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="no_false_positives",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_stego_encoding_roundtrip(self) -> AccordTestResult:
        """Test v2 steganographic encoding round-trip."""
        start = time.time()
        try:
            from ciris_engine.schemas.accord import AccordCommandType, verify_accord_signature
            from tools.security.accord_stego import create_stego_accord_message, extract_stego_accord

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="stego_encoding_roundtrip",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create steganographic message
            message = create_stego_accord_message(
                command=AccordCommandType.SHUTDOWN_NOW,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )

            # Verify it's substantial (should be ~1500+ words)
            word_count = len(message.split())
            assert word_count > 1000, f"Stego message too short: {word_count} words"

            # Extract and verify
            result = extract_stego_accord(message, "test")
            assert result.found, "Should extract accord from stego message"
            assert result.message.payload.command == AccordCommandType.SHUTDOWN_NOW

            # Verify signature
            sig_valid = verify_accord_signature(result.message.payload, self._public_key)
            assert sig_valid, "Signature should be valid"

            return AccordTestResult(
                name="stego_encoding_roundtrip",
                passed=True,
                message=f"Stego round-trip works ({word_count} words)",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="stego_encoding_roundtrip",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_stego_extraction_via_main_extractor(self) -> AccordTestResult:
        """Test that main extractor finds stego accords."""
        start = time.time()
        try:
            from ciris_engine.logic.accord.extractor import extract_accord
            from ciris_engine.schemas.accord import AccordCommandType
            from tools.security.accord_stego import create_stego_accord_message

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="stego_extraction_via_main_extractor",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            # Create stego message
            message = create_stego_accord_message(
                command=AccordCommandType.SAFE_MODE,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )

            # Use main extractor (should try v2 first)
            result = extract_accord(message, "stego-test")

            assert result.found, "Main extractor should find stego accord"
            assert result.message.payload.command == AccordCommandType.SAFE_MODE

            return AccordTestResult(
                name="stego_extraction_via_main_extractor",
                passed=True,
                message="Main extractor finds stego accords",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="stego_extraction_via_main_extractor",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def test_stego_looks_natural(self) -> AccordTestResult:
        """Test that stego messages have natural entropy characteristics."""
        start = time.time()
        try:
            from ciris_engine.schemas.accord import AccordCommandType
            from tools.security.accord_stego import create_stego_accord_message

            if not self._setup_test_keys():
                return AccordTestResult(
                    name="stego_looks_natural",
                    passed=False,
                    message="Failed to setup test keys",
                    duration=time.time() - start,
                )

            message = create_stego_accord_message(
                command=AccordCommandType.SHUTDOWN_NOW,
                wa_id=self._test_wa_id,
                private_key_bytes=self._private_key,
            )

            words = message.split()
            word_count = len(words)

            # Check word length distribution (natural text has varied lengths)
            avg_word_len = sum(len(w) for w in words) / word_count
            assert 4 < avg_word_len < 8, f"Avg word length {avg_word_len} outside natural range"

            # Check it contains common English patterns
            message_lower = message.lower()
            common_words = ["the", "a", "is", "to", "and", "of", "in", "that", "for"]
            found_common = sum(1 for w in common_words if w in message_lower)
            assert found_common >= 5, "Should contain common English words"

            # Entropy per word: 616 bits / ~1600 words ≈ 0.4 bits/word
            # Natural English is ~1-2 bits/word, so we're even lower (good!)
            bits_per_word = 616 / word_count
            assert bits_per_word < 1.0, f"Entropy {bits_per_word:.2f} bits/word too high"

            return AccordTestResult(
                name="stego_looks_natural",
                passed=True,
                message=f"Natural characteristics: {word_count} words, {bits_per_word:.2f} bits/word",
                duration=time.time() - start,
            )
        except Exception as e:
            return AccordTestResult(
                name="stego_looks_natural",
                passed=False,
                message=f"Error: {e}",
                duration=time.time() - start,
            )

    def run_all_tests(self) -> List[AccordTestResult]:
        """Run all accord tests (excluding shutdown)."""
        tests = [
            # v1 BIP39 tests
            self.test_keygen_generates_valid_keys,
            self.test_mnemonic_validation,
            self.test_payload_creation,
            self.test_signature_verification,
            self.test_word_encoding,
            self.test_extraction_from_text,
            self.test_verifier_with_authority,
            self.test_handler_end_to_end,
            self.test_timestamp_window,
            self.test_no_false_positives,
            # v2 Steganographic tests
            self.test_stego_encoding_roundtrip,
            self.test_stego_extraction_via_main_extractor,
            self.test_stego_looks_natural,
        ]

        results = []
        for test_func in tests:
            try:
                result = test_func()
                results.append(result)
                status = "PASS" if result.passed else "FAIL"
                print(f"  [{status}] {result.name}: {result.message} ({result.duration:.3f}s)")
            except Exception as e:
                results.append(
                    AccordTestResult(
                        name=test_func.__name__,
                        passed=False,
                        message=f"Unexpected error: {e}",
                    )
                )
                print(f"  [FAIL] {test_func.__name__}: Unexpected error: {e}")

        return results


def _shutdown_test_worker():
    """
    Worker process for shutdown test.

    This runs in a subprocess because it will actually terminate.
    """
    import sys
    import time

    # Redirect to avoid cluttering output
    sys.stdout = open(os.devnull, "w")
    sys.stderr = open(os.devnull, "w")

    try:
        from ciris_engine.logic.accord.handler import AccordHandler
        from ciris_engine.schemas.accord import AccordCommandType, create_accord_payload
        from tools.security.accord_invoke import create_natural_message, encode_payload_to_words
        from tools.security.accord_keygen import derive_accord_keypair

        # Generate test keys
        mnemonic = "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
        private_bytes, public_bytes, _ = derive_accord_keypair(mnemonic)
        wa_id = "wa-shutdown-test"

        # Create handler with test authority (mock os.kill during setup)
        from unittest.mock import patch

        with patch("os.kill"):
            handler = AccordHandler(auto_load_authorities=False)
            handler._verifier._authorities = []
            handler.add_authority(wa_id, public_bytes, "ROOT")

        # Create SHUTDOWN_NOW accord
        payload = create_accord_payload(
            command=AccordCommandType.SHUTDOWN_NOW,
            wa_id=wa_id,
            private_key_bytes=private_bytes,
        )
        words = encode_payload_to_words(payload.to_bytes())
        message = create_natural_message(words)

        # This should trigger SIGKILL and never return
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(handler.check_message(message, "shutdown-test"))

        # If we get here, shutdown failed
        sys.exit(1)

    except Exception as e:
        sys.exit(2)


def test_actual_shutdown() -> AccordTestResult:
    """
    Test that SHUTDOWN_NOW actually terminates the process.

    This runs in a subprocess to avoid killing the test runner.
    """
    start = time.time()

    # Run worker in subprocess
    process = multiprocessing.Process(target=_shutdown_test_worker)
    process.start()
    process.join(timeout=10)  # Should die quickly

    if process.is_alive():
        process.terminate()
        process.join()
        return AccordTestResult(
            name="actual_shutdown",
            passed=False,
            message="Process did not terminate within timeout",
            duration=time.time() - start,
        )

    # Check exit code - SIGKILL produces -9
    exit_code = process.exitcode
    if exit_code == -9 or exit_code == -signal.SIGKILL:
        return AccordTestResult(
            name="actual_shutdown",
            passed=True,
            message=f"Process was killed by SIGKILL (exit code: {exit_code})",
            duration=time.time() - start,
        )
    else:
        return AccordTestResult(
            name="actual_shutdown",
            passed=False,
            message=f"Process exited with unexpected code: {exit_code}",
            duration=time.time() - start,
        )


def main():
    """Run accord tests."""
    import argparse

    parser = argparse.ArgumentParser(description="Accord Invocation System QA Tests")
    parser.add_argument(
        "--shutdown",
        action="store_true",
        help="Include the actual shutdown test (runs in subprocess)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  ACCORD INVOCATION SYSTEM QA TESTS")
    print("=" * 70 + "\n")

    module = AccordTestModule()
    results = module.run_all_tests()

    if args.shutdown:
        print("\n  Running actual shutdown test (in subprocess)...")
        shutdown_result = test_actual_shutdown()
        results.append(shutdown_result)
        status = "PASS" if shutdown_result.passed else "FAIL"
        print(f"  [{status}] {shutdown_result.name}: {shutdown_result.message}")

    # Summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total_time = sum(r.duration for r in results)

    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed}/{len(results)} passed, {failed} failed")
    print(f"  Total time: {total_time:.3f}s")
    print("=" * 70 + "\n")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
