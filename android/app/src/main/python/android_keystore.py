"""
Android Keystore integration for secrets encryption.

Uses Chaquopy to call Kotlin's KeystoreSecretWrapper for hardware-backed
key wrapping on Android devices.
"""

import base64
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Check if running on Android
IS_ANDROID = "ANDROID_DATA" in os.environ


def _get_keystore_wrapper():
    """Get the Kotlin KeystoreSecretWrapper class via Chaquopy."""
    if not IS_ANDROID:
        return None

    try:
        from java import jclass

        return jclass("ai.ciris.mobile.security.KeystoreSecretWrapper")
    except Exception as e:
        logger.warning(f"Failed to load KeystoreSecretWrapper: {e}")
        return None


def wrap_master_key(plain_key: bytes) -> Optional[str]:
    """
    Wrap a master key using Android Keystore.

    Args:
        plain_key: The raw 32-byte master key

    Returns:
        Base64-encoded wrapped key, or None if not on Android or wrapping failed
    """
    wrapper = _get_keystore_wrapper()
    if wrapper is None:
        return None

    try:
        wrapped = wrapper.wrapKey(plain_key)
        if wrapped:
            logger.info("Master key wrapped with Android Keystore")
            return wrapped
        logger.error("Keystore wrapping returned null")
        return None
    except Exception as e:
        logger.error(f"Failed to wrap key with Android Keystore: {e}")
        return None


def unwrap_master_key(wrapped_key_base64: str) -> Optional[bytes]:
    """
    Unwrap a master key using Android Keystore.

    Args:
        wrapped_key_base64: Base64-encoded wrapped key from wrap_master_key()

    Returns:
        The raw 32-byte master key, or None if unwrapping failed
    """
    wrapper = _get_keystore_wrapper()
    if wrapper is None:
        return None

    try:
        unwrapped = wrapper.unwrapKey(wrapped_key_base64)
        if unwrapped:
            # Convert Java byte array to Python bytes
            result = bytes(unwrapped)
            logger.info("Master key unwrapped from Android Keystore")
            return result
        logger.error("Keystore unwrapping returned null")
        return None
    except Exception as e:
        logger.error(f"Failed to unwrap key with Android Keystore: {e}")
        return None


def has_keystore_wrapper_key() -> bool:
    """Check if a wrapper key exists in Android Keystore."""
    wrapper = _get_keystore_wrapper()
    if wrapper is None:
        return False

    try:
        return wrapper.hasWrapperKey()
    except Exception as e:
        logger.error(f"Failed to check keystore wrapper key: {e}")
        return False


def load_or_create_wrapped_master_key(key_file_path: Path) -> Optional[bytes]:
    """
    Load or create a master key, using Android Keystore wrapping if available.

    On Android:
    - If wrapped key file exists, unwrap it using Keystore
    - If not, generate new key, wrap it, and save

    On non-Android:
    - Falls back to plain file storage (existing behavior)

    Args:
        key_file_path: Path to the key file (will have .wrapped suffix on Android)

    Returns:
        The 32-byte master key, or None on error
    """
    import secrets as secrets_module

    if not IS_ANDROID:
        # Non-Android: use plain file (existing behavior)
        if key_file_path.exists():
            return key_file_path.read_bytes()
        else:
            new_key = secrets_module.token_bytes(32)
            key_file_path.parent.mkdir(parents=True, exist_ok=True)
            key_file_path.write_bytes(new_key)
            return new_key

    # Android: use Keystore wrapping
    wrapped_path = key_file_path.with_suffix(".wrapped")

    if wrapped_path.exists():
        # Load and unwrap existing key
        try:
            wrapped_data = wrapped_path.read_text().strip()
            master_key = unwrap_master_key(wrapped_data)
            if master_key:
                return master_key
            logger.error("Failed to unwrap existing master key - will regenerate")
        except Exception as e:
            logger.error(f"Failed to read wrapped key file: {e}")

    # Generate new key and wrap it
    new_key = secrets_module.token_bytes(32)
    wrapped = wrap_master_key(new_key)

    if wrapped:
        try:
            wrapped_path.parent.mkdir(parents=True, exist_ok=True)
            wrapped_path.write_text(wrapped)
            logger.info(f"Saved wrapped master key to {wrapped_path}")

            # Remove plain key file if it exists (migration)
            if key_file_path.exists():
                key_file_path.unlink()
                logger.info(f"Removed plain key file {key_file_path}")

            return new_key
        except Exception as e:
            logger.error(f"Failed to save wrapped key: {e}")
            return None
    else:
        # Fallback to plain storage if Keystore fails
        logger.warning("Keystore wrapping failed, falling back to plain storage")
        key_file_path.parent.mkdir(parents=True, exist_ok=True)
        key_file_path.write_bytes(new_key)
        return new_key


def migrate_plain_key_to_wrapped(key_file_path: Path) -> bool:
    """
    Migrate a plain master key file to Keystore-wrapped format.

    Args:
        key_file_path: Path to the existing plain key file

    Returns:
        True if migration succeeded or not needed, False on error
    """
    if not IS_ANDROID:
        return True  # Nothing to migrate on non-Android

    wrapped_path = key_file_path.with_suffix(".wrapped")

    if wrapped_path.exists():
        return True  # Already migrated

    if not key_file_path.exists():
        return True  # No key to migrate

    try:
        # Read plain key
        plain_key = key_file_path.read_bytes()
        if len(plain_key) != 32:
            logger.error(f"Invalid key length: {len(plain_key)} bytes")
            return False

        # Wrap with Keystore
        wrapped = wrap_master_key(plain_key)
        if not wrapped:
            logger.error("Failed to wrap key during migration")
            return False

        # Save wrapped key
        wrapped_path.write_text(wrapped)

        # Remove plain key
        key_file_path.unlink()

        logger.info(f"Migrated {key_file_path} to Keystore-wrapped format")
        return True

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False
