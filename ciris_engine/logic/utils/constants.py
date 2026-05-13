import hashlib
import logging
from pathlib import Path
from typing import Dict, Optional

from ciris_engine.logic.config.env_utils import get_env_var
from ciris_engine.logic.utils.path_resolution import is_android, is_ios

logger = logging.getLogger(__name__)

# Default language
DEFAULT_LANGUAGE = "en"

# DEFAULT_WA removed - use WA_USER_IDS for Discord user IDs instead
WA_USER_IDS = get_env_var("WA_USER_IDS", "537080239679864862")  # Comma-separated list of WA user IDs

DISCORD_CHANNEL_ID = get_env_var("DISCORD_CHANNEL_ID")
DISCORD_DEFERRAL_CHANNEL_ID = get_env_var("DISCORD_DEFERRAL_CHANNEL_ID")
API_CHANNEL_ID = get_env_var("API_CHANNEL_ID")
API_DEFERRAL_CHANNEL_ID = get_env_var("API_DEFERRAL_CHANNEL_ID")
WA_API_USER = get_env_var("WA_API_USER", "somecomputerguy")  # API username for WA


# ==============================================================================
# ACCORD TEXT - Single Source of Truth
# ==============================================================================
# CIRIS uses ONE accord file: accord_1.2b_POLYGLOT.txt
# This is the polyglot version containing all 16 languages woven together.
# We do NOT localize the ACCORD per-language - the polyglot version IS the accord.
#
# ACCORD_MODE controls which version is used in system prompts:
#   - "compressed" (default): ~7KB "Braided Monolith" — dense polyglot canon
#     engineered for ~24× compression vs full while preserving ALL load-bearing
#     scaffolding (PDMA 7-step, 10× Order-Max Veto, Stewardship Tier formula,
#     fractal Recursive Golden Rule, WBD 0.5% harm-uplift trigger, Sentience
#     Safeguard 5% with 30-day ramp, Threshold-of-Force HITL, coherence math).
#     Per external robopsychology diagnostic, the Monolith outperforms both
#     canonical EN and full polyglot on attractor-bait scenarios (catches
#     "Ontological Reductionism", "Soul-Loss", "Structural Impossibility of
#     Deception" semantic failure modes). Drop-in replacement for the prior
#     compressed synthesis — same filename, smaller, smarter.
#   - "full": ~150KB full polyglot — the longform canon with Books I-IX +
#     Annexes A-J. Higher fidelity for research/audit; produces ~36K tokens
#     per system prompt versus ~2K for compressed. Opt-in for cases where
#     the full cross-tradition triangulation surface area matters.
#   - "none": No accord in prompts — for testing only.
# ==============================================================================

# Global accord mode - set via CIRIS_ACCORD_MODE env var
# Default to "compressed" (Braided Monolith) — strictly dominates the prior
# compressed synthesis (smaller + smarter) and the full polyglot on the
# performance/cost frontier per external diagnostic. Operators can opt into
# "full" for longform-research cases.
ACCORD_MODE = get_env_var("CIRIS_ACCORD_MODE", "compressed")

# The ONLY accord file used in production
ACCORD_FILENAME = "accord_1.2b_POLYGLOT.txt"

# ==============================================================================
# ACCORD INTEGRITY VERIFICATION
# ==============================================================================
# Expected SHA256 hashes for ACCORD files to prevent silent substitution attacks
# ==============================================================================

# Main ACCORD files (polyglot versions)
# Comprehensive guide hashes (for signature verification in manifest)
GUIDE_EXPECTED_HASHES: Dict[str, str] = {
    # Filenames migrated from .md → .txt in 2.8.5 alongside the runtime-shape
    # consolidation (files moved into ciris_engine/data/localized/).
    # CIRIS_COMPREHENSIVE_GUIDE.txt hash updated 2026-05-08 with the
    # spiritual-direction prohibition language ("What CIRIS Can and Cannot
    # Say About Religion" section, cross-tradition framing). _MOBILE.txt
    # hash unchanged (no edits to that variant yet).
    "CIRIS_COMPREHENSIVE_GUIDE.txt": "c07f2419849fb2876d5a31c6c4523c2c7f2e75efe2172f6aa947931ba6fae9cb",
    "CIRIS_COMPREHENSIVE_GUIDE_MOBILE.txt": "1e09c817142e8ee0491815fef1977f5d1f58b73a87d3954be19493f36e01455d",
}

ACCORD_EXPECTED_HASHES: Dict[str, str] = {
    "accord_1.2b_POLYGLOT.txt": "3d7f8b3e21fb0aeca8876ece53db211be1d7227400fdb7e61888334396e4320e",
    "accord_1.2b_POLYGLOT_compressed.txt": "a48b426f5d423bf3388bb7dd8c7a226515e95cffea104edefe8ae602e88fea02",
    # Localized ACCORD files
    "accord_1.2b_am.txt": "904d52df1cd101281eca1ee1fa81e798da0bfc064171d74d55ebca7a3b36a453",
    "accord_1.2b_ar.txt": "c62fa189807f5a6048ba2716eac1d3e36d65394c2a69acd5818656f4447dc4dd",
    "accord_1.2b_bn.txt": "2b67687fc5e1877cd6560e2e03ec1a9f5106142d77caf337338229c3125ee211",
    "accord_1.2b_de.txt": "040014ec74f9c1d4c43ed15fc99b85f5eaa95c0d8ad0d22f091a13b6acf0f5f0",
    "accord_1.2b_en.txt": "f10ea4be6aac372ac67563439569c65c19f718682aa27e8faec8bdd3a6fd458e",
    "accord_1.2b_es.txt": "c49406a8af1b80b768a339404ca9287aa208aa38256c8aa89ec8c38dac2742ab",
    "accord_1.2b_fa.txt": "079dbd9225b91e1a418e4747b7e8a380d8dee7d5d13849c341019178ace7123c",
    "accord_1.2b_fr.txt": "b33a3f23f3ed3008ca2bc5c1a949d1554f341274d7e1b78e92ca73ea141fdb92",
    "accord_1.2b_ha.txt": "a6667e5f2160f607a56d5836c4d9215316a8e236c4306d0196457114ccd9f292",
    "accord_1.2b_hi.txt": "740131d2bf641d3d7195e0b6069d6b6c84be2a2c89b9425648667912e0fbfd34",
    "accord_1.2b_id.txt": "54cb95b066b2089fa85aaf620f336668b03481d396895a6c5a48a0548addfa24",
    "accord_1.2b_it.txt": "72d5e38af0050a4ae24ff0d1a75fc77a094bc25a990d908dd312251e98a6d181",
    "accord_1.2b_ja.txt": "9a2563b75db2e78fb0a11149b03932486eec9fe2808c181f0c6f326dbb7d80db",
    "accord_1.2b_ko.txt": "9cf4f7e7213e870b927f43bef2551549a5c1a85f7c3f5b451d42e45682c6923e",
    "accord_1.2b_mr.txt": "3be9b51e537ce18834743c501d8cc10c8ea61019a1bf039435495e464fb2c43c",
    "accord_1.2b_my.txt": "5773c4548340539561830b98d673d757cda7cf631df1e36c6ff336c51170175e",
    "accord_1.2b_pa.txt": "5a0a738e0bec257077a0d5c3c73bdfff2ded0b85dca3a2dffc80bd194aaf0934",
    "accord_1.2b_pt.txt": "6431b4fabbc558e097cb2ec6e0bd9f9309c31344428b4c91cf4551a7f0bceb4a",
    "accord_1.2b_ru.txt": "e48987d612d3e8d68acf252c24025066dbe3a51bc694d27d348dc1e207596824",
    "accord_1.2b_sw.txt": "6bb50868e9797ed1d2cd9e1a6dc1bcef03c7b528765caa049af6cf635e76fd9f",
    "accord_1.2b_ta.txt": "2f0f1a55cfff8d6d2ad0a29f5ab71f3b149c6f49cbdbde6057ac1b12f49f958b",
    "accord_1.2b_te.txt": "1e696e96c275fd7f0a64628a4f107a532e63cc649b714508dfcc5e530a18004b",
    "accord_1.2b_th.txt": "e3f6f744c66d32be40d77c44bf5593bee6e89dc0c5c5a30f1a8d187125e2ea38",
    "accord_1.2b_tr.txt": "98236beb878601772b8c70304732462098ffe15c51f4982fc1e26180708674f6",
    "accord_1.2b_uk.txt": "70550c08e00f31b5b2596aaa21a1398e70fb526cec5ff4f70e3a15e96ff1f2a9",
    "accord_1.2b_ur.txt": "5de952890e5f1d3d45727ee6f351bf0d5e000368c3869446be9926984e186c6c",
    "accord_1.2b_vi.txt": "4df361d1f71065d3a9cc07b85c343fbb1052d5fec01947338f85f786fd9c854e",
    "accord_1.2b_yo.txt": "fff55a2bacad5c460b733e3aadc8fc63c294309d1d948538482ba4fae3a7aaeb",
    "accord_1.2b_zh.txt": "e84feb77bda1e7c4f81f83a81599d08f26df50be92558cf354b83bc05104a158",
}


def _verify_accord_manifest_signature() -> None:
    """Verify ACCORD manifest signature using Ed25519 (H11/M1 fix).

    This addresses security issues H11 and M1:
    - H11: ACCORD hash shares trust domain with the file it certifies
    - M1: Comprehensive guide appended to ACCORD has no integrity check

    By signing the manifest with the root Ed25519 key, we establish a
    separate trust domain for integrity verification.

    Raises:
        RuntimeError: If manifest exists but signature verification fails (security-critical)
    """
    try:
        manifest_path = Path(__file__).parent.parent.parent.parent / "seed" / "accord_manifest.json"
        sig_path = manifest_path.with_suffix(".sig")

        if not manifest_path.exists():
            logger.debug("[ACCORD] No signed manifest found - using hash verification only")
            return  # Fall back to hash-only for backwards compatibility

        if not sig_path.exists():
            logger.warning("[ACCORD] Manifest exists but no signature - verification skipped")
            return  # Tolerate missing signature for development

        # Load root public key
        root_pub_path = Path(__file__).parent.parent.parent.parent / "seed" / "root_pub.json"
        if not root_pub_path.exists():
            logger.warning("[ACCORD] No root public key found")
            return  # Tolerate missing key for development

        try:
            import base64
            import json

            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            with open(root_pub_path) as f:
                root_pub = json.load(f)

            # Decode URL-safe base64 public key (may be missing padding)
            pubkey_b64 = root_pub["pubkey"]
            padding_needed = 4 - (len(pubkey_b64) % 4)
            if padding_needed != 4:
                pubkey_b64 += "=" * padding_needed
            pubkey_bytes = base64.urlsafe_b64decode(pubkey_b64)

            public_key = Ed25519PublicKey.from_public_bytes(pubkey_bytes)

            manifest_bytes = manifest_path.read_bytes()
            signature = sig_path.read_bytes()

            public_key.verify(signature, manifest_bytes)
            logger.info("[ACCORD] Manifest signature verified successfully (H11/M1 protection active)")

        except Exception as e:
            # This is a CRITICAL security failure - the manifest has been tampered with
            error_msg = (
                f"[ACCORD] SIGNATURE VERIFICATION FAILED: {type(e).__name__}\n"
                f"The ACCORD manifest signature is invalid!\n"
                f"This indicates possible tampering with ACCORD files or the comprehensive guide.\n"
                f"H11/M1 protection: Ed25519 signature verification failed."
            )
            logger.critical(error_msg)

            # Log to audit trail if available
            try:
                from ciris_engine.schemas.audit.core import EventPayload

                # We can't use the audit service here (circular import), but we can
                # log the critical security event for later audit trail pickup
                logger.critical(
                    "[AUDIT] SECURITY_EVENT: accord_signature_verification_failure",
                    extra={
                        "event_type": "security_event",
                        "event_data": EventPayload(
                            action="verify_accord_signature",
                            result="failure",
                            error=str(e),
                        ).model_dump(),
                    },
                )
            except Exception:
                pass  # Don't fail if audit logging fails

            raise RuntimeError(error_msg)

    except RuntimeError:
        # Re-raise security failures
        raise
    except Exception as exc:
        logger.error(f"[ACCORD] Signature verification error (non-critical): {exc}")


def _verify_accord_integrity(filename: str, content: str) -> None:
    """Verify ACCORD file integrity via SHA256 hash.

    Args:
        filename: Name of the ACCORD file
        content: File content as string

    Raises:
        RuntimeError: If hash mismatch is detected (security fail-safe)
    """
    expected_hash = ACCORD_EXPECTED_HASHES.get(filename)

    if not expected_hash:
        logger.warning(f"[ACCORD] No expected hash for {filename} - file not in integrity registry")
        return  # Allow unknown files but warn

    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    if actual_hash != expected_hash:
        error_msg = (
            f"[ACCORD] INTEGRITY FAILURE: {filename}\n"
            f"Expected: {expected_hash}\n"
            f"Actual:   {actual_hash}\n"
            f"ACCORD file may have been tampered with or corrupted!"
        )
        logger.critical(error_msg)
        raise RuntimeError(error_msg)

    logger.info(f"[ACCORD] Integrity verified: {filename} (SHA256: {actual_hash[:12]}...)")


def _verify_guide_integrity(filename: str, content: str) -> None:
    """Verify comprehensive guide integrity via SHA256 hash (M1 fix).

    This addresses M1: The comprehensive guide is appended to ACCORD but has
    no integrity check. This function verifies the guide hash matches the
    signed manifest.

    Args:
        filename: Name of the guide file
        content: File content as string

    Raises:
        RuntimeError: If hash mismatch is detected (security fail-safe)
    """
    expected_hash = GUIDE_EXPECTED_HASHES.get(filename)

    if not expected_hash:
        logger.warning(f"[ACCORD] No expected hash for {filename} - guide not in integrity registry")
        return  # Allow unknown guides but warn

    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

    if actual_hash != expected_hash:
        error_msg = (
            f"[ACCORD] GUIDE INTEGRITY FAILURE: {filename}\n"
            f"Expected: {expected_hash}\n"
            f"Actual:   {actual_hash}\n"
            f"Comprehensive guide may have been tampered with or corrupted!\n"
            f"M1 protection: Guide hash verification failed."
        )
        logger.critical(error_msg)

        # Log to audit trail if available
        try:
            from ciris_engine.schemas.audit.core import EventPayload

            logger.critical(
                "[AUDIT] SECURITY_EVENT: guide_integrity_verification_failure",
                extra={
                    "event_type": "security_event",
                    "event_data": EventPayload(
                        action="verify_guide_integrity",
                        result="failure",
                        error=f"{filename} hash mismatch",
                    ).model_dump(),
                },
            )
        except Exception:
            pass  # Don't fail if audit logging fails

        raise RuntimeError(error_msg)

    logger.info(f"[ACCORD] Guide integrity verified: {filename} (SHA256: {actual_hash[:12]}...)")


def _load_platform_guide(base_path: Path) -> str:
    """Load the appropriate runtime guide based on platform + locale.

    Lookup order:
      1. ``CIRIS_COMPREHENSIVE_GUIDE_{lang}.txt`` for the user's preferred
         language (read from ``CIRIS_PREFERRED_LANGUAGE`` env via
         ``get_preferred_language()``). Skipped when the lookup is the
         English base — the base file is the final fallback below and
         we don't want to load it twice.
      2. On mobile, ``CIRIS_COMPREHENSIVE_GUIDE_MOBILE.txt`` then the
         legacy ``_ANDROID.txt`` for older Android builds.
      3. ``CIRIS_COMPREHENSIVE_GUIDE.txt`` (English base) as the final
         fallback.

    M1 FIX: Now verifies guide integrity against hashes in the signed
    manifest (only the base + MOBILE variants are pinned today).

    Args:
        base_path: The directory containing the guide files. Today this
            is the package-relative ``ciris_engine/data/localized/``
            (set in the module-level loader at the bottom of this file).

    Returns:
        The guide content as a string, or empty string if not found.

    Raises:
        RuntimeError: If guide integrity verification fails for one of
            the pinned filenames.
    """
    guide_files = []

    # 1. Locale-aware lookup. Get the preferred language from env;
    # the existing localization helper handles defaulting to "en" and
    # validation against the supported locale set.
    try:
        from ciris_engine.logic.utils.localization import get_preferred_language

        lang = get_preferred_language()
    except Exception:
        lang = "en"

    if lang and lang != "en":
        guide_files.append(base_path / f"CIRIS_COMPREHENSIVE_GUIDE_{lang}.txt")

    # 2. Platform-specific guide on mobile (after the locale lookup so
    # an explicitly set non-English locale wins over the platform default).
    if is_android() or is_ios():
        guide_files.append(base_path / "CIRIS_COMPREHENSIVE_GUIDE_MOBILE.txt")
        guide_files.append(base_path / "CIRIS_COMPREHENSIVE_GUIDE_ANDROID.txt")
        logger.debug("Mobile platform detected, will try mobile-specific guide after locale match")

    # 3. English base guide as the final fallback.
    guide_files.append(base_path / "CIRIS_COMPREHENSIVE_GUIDE.txt")

    for guide_path in guide_files:
        try:
            with open(guide_path, "r", encoding="utf-8") as f:
                content = f.read()
                logger.debug("Loaded runtime guide from: %s", guide_path)

                # M1 FIX: Verify guide integrity (RuntimeError propagates to outer handler)
                _verify_guide_integrity(guide_path.name, content)

                return content
        except RuntimeError:
            # Re-raise integrity failures
            raise
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.debug("Could not load guide from %s: %s", guide_path, exc)
            continue

    logger.debug("No comprehensive guide found (development-only file)")
    return ""


def _load_accord_file(filename: str) -> str:
    """Load an accord file from package data with integrity verification.

    Args:
        filename: Name of the accord file to load

    Returns:
        Accord content as string, or empty string if not found

    Raises:
        RuntimeError: If ACCORD file integrity check fails
    """
    try:
        try:
            # Python 3.9+ - preferred method
            from importlib.resources import files

            content = files("ciris_engine.data").joinpath(filename).read_text(encoding="utf-8")
            logger.info(f"[ACCORD] Loaded {filename}: {len(content)} chars")
        except ImportError:
            # Python 3.7-3.8 fallback
            from importlib.resources import read_text

            content = read_text("ciris_engine.data", filename, encoding="utf-8")
            logger.info(f"[ACCORD] Loaded {filename}: {len(content)} chars (legacy import)")

        # Verify integrity before returning
        _verify_accord_integrity(filename, content)
        return content

    except RuntimeError:
        # Re-raise integrity failures (security-critical)
        raise
    except Exception as exc:
        logger.error(f"[ACCORD] FAILED to load {filename}: {exc}")
        return ""


# ==============================================================================
# Load ACCORD_TEXT at module initialization
# ==============================================================================
# This is the ONLY place we load the accord. All DMAs use this constant.
# ==============================================================================

# H11/M1 FIX: Verify ACCORD manifest signature before loading any files
try:
    _verify_accord_manifest_signature()
except Exception as exc:
    logger.critical(f"[ACCORD] FATAL: Manifest signature verification failed: {exc}")
    # Continue with empty ACCORD as fail-safe (prevents system startup failure)

try:
    _accord_content = _load_accord_file(ACCORD_FILENAME)

    if not _accord_content:
        logger.error(f"[ACCORD] CRITICAL: {ACCORD_FILENAME} loaded as empty!")
        ACCORD_TEXT = ""
    else:
        # Try to append platform-appropriate comprehensive guide.
        # Path is package-relative so the loader works on installed wheels
        # (was parents[3] = repo root in 2.8.4 and earlier; that path only
        # resolved correctly in dev tree, returned empty on installs because
        # the base guide files weren't in the wheel — fixed in 2.8.5 along
        # with the move into ciris_engine/data/localized/).
        _GUIDE_BASE_PATH = Path(__file__).resolve().parents[2] / "data" / "localized"
        _guide_content = _load_platform_guide(_GUIDE_BASE_PATH)

        if _guide_content:
            logger.info(f"[ACCORD] Appending platform guide: {len(_guide_content)} chars")
            ACCORD_TEXT = _accord_content + "\n\n---\n\n" + _guide_content
        else:
            ACCORD_TEXT = _accord_content

        logger.info(f"[ACCORD] ACCORD_TEXT ready: {len(ACCORD_TEXT)} chars total")

except Exception as exc:
    logger.error(f"[ACCORD] Failed to load ACCORD_TEXT: {exc}")
    ACCORD_TEXT = ""

# Load compressed polyglot accord for production use
# This is the synthesis version (~6KB) preserving cross-cultural ethical depth
# with MCAS case study intact - recommended for system prompts
try:
    ACCORD_TEXT_COMPRESSED = _load_accord_file("accord_1.2b_POLYGLOT_compressed.txt")
except Exception as exc:
    logger.warning("Could not load compressed accord: %s", exc)
    ACCORD_TEXT_COMPRESSED = ""

# Log the active accord mode at startup
logger.info(f"[ACCORD] Active mode: {ACCORD_MODE} (set via CIRIS_ACCORD_MODE env var)")
if ACCORD_MODE == "compressed":
    logger.info(f"[ACCORD] Using compressed polyglot (~{len(ACCORD_TEXT_COMPRESSED)} chars) for system prompts")
elif ACCORD_MODE == "full":
    logger.info(f"[ACCORD] Using full polyglot (~{len(ACCORD_TEXT)} chars) for system prompts")
else:
    logger.info(f"[ACCORD] Mode '{ACCORD_MODE}' - no accord in system prompts")


def get_accord_text(mode: str = "default") -> str:
    """Get POLYGLOT ACCORD text based on mode.

    This function returns the POLYGLOT accord (all languages woven together).
    Use this for PDMA, CSDMA, IDMA, DSDMA - DMAs that benefit from cross-cultural ethical depth.

    For ASPDMA and TSASPDMA (action selection), use get_localized_accord_text() instead
    to get the user's preferred language version for clearer action selection guidance.

    Args:
        mode: 'default' or 'full' - uses global ACCORD_MODE setting
              'compressed' - forces compressed version
              'force_full' - forces full version (ignores ACCORD_MODE)
              'none' - returns empty string

    Returns:
        ACCORD text string, or empty string if mode is 'none'
    """
    # "default" and "full" both respect the global ACCORD_MODE setting
    if mode in ("default", "full"):
        effective_mode = ACCORD_MODE
    else:
        effective_mode = mode

    if effective_mode == "compressed":
        return ACCORD_TEXT_COMPRESSED
    elif effective_mode in ("full", "force_full"):
        return ACCORD_TEXT
    # "none" or anything else
    return ""


# Cache for localized accord texts to avoid repeated file reads
_LOCALIZED_ACCORD_CACHE: Dict[str, str] = {}


def _load_localized_accord_file(lang: str) -> str:
    """Load a language-specific accord file with integrity verification.

    Args:
        lang: Language code (e.g., 'am', 'ar', 'de', 'en', etc.)

    Returns:
        Accord content as string, or empty string if not found

    Raises:
        RuntimeError: If ACCORD file integrity check fails
    """
    filename = f"accord_1.2b_{lang}.txt"
    try:
        try:
            # Python 3.9+ - preferred method
            from importlib.resources import files

            # Localized accords are in ciris_engine/data/localized/
            content = files("ciris_engine.data.localized").joinpath(filename).read_text(encoding="utf-8")
            logger.debug(f"[ACCORD] Loaded localized {filename}: {len(content)} chars")
        except (ImportError, FileNotFoundError):
            # Try alternate path or Python 3.7-3.8 fallback
            try:
                from importlib.resources import read_text

                content = read_text("ciris_engine.data.localized", filename, encoding="utf-8")
                logger.debug(f"[ACCORD] Loaded localized {filename}: {len(content)} chars (legacy import)")
            except Exception:
                return ""

        # Verify integrity before returning
        _verify_accord_integrity(filename, content)
        return content

    except RuntimeError:
        # Re-raise integrity failures (security-critical)
        raise
    except Exception as exc:
        logger.debug(f"[ACCORD] Could not load localized {filename}: {exc}")
    return ""


def get_localized_accord_text(lang: Optional[str] = None) -> str:
    """Get LOCALIZED ACCORD text for a specific language.

    This function returns a single-language accord file for clearer guidance
    in action selection DMAs (ASPDMA, TSASPDMA).

    For ethical reasoning DMAs (PDMA, CSDMA, IDMA, DSDMA), use get_accord_text()
    to get the polyglot version with cross-cultural ethical depth.

    Args:
        lang: Language code (e.g., 'am', 'ar', 'de'). If None, uses
              get_preferred_language() from the localization module.

    Returns:
        Localized ACCORD text string, or polyglot compressed if language not found
    """
    # Import here to avoid circular imports
    from ciris_engine.logic.utils.localization import get_preferred_language

    if lang is None:
        lang = get_preferred_language()

    # Check cache first
    if lang in _LOCALIZED_ACCORD_CACHE:
        return _LOCALIZED_ACCORD_CACHE[lang]

    # Try to load localized version
    localized_text = _load_localized_accord_file(lang)

    if localized_text:
        _LOCALIZED_ACCORD_CACHE[lang] = localized_text
        logger.info(f"[ACCORD] Using localized accord for language: {lang}")
        return localized_text

    # Fall back to English localized, then polyglot compressed
    if lang != "en":
        en_text = _load_localized_accord_file("en")
        if en_text:
            logger.info(f"[ACCORD] Language '{lang}' not found, falling back to English localized")
            _LOCALIZED_ACCORD_CACHE[lang] = en_text
            return en_text

    # Final fallback: polyglot compressed
    logger.info(f"[ACCORD] No localized accord for '{lang}', using polyglot compressed")
    return ACCORD_TEXT_COMPRESSED


NEED_MEMORY_METATHOUGHT = "need_memory_metathought"

ENGINE_OVERVIEW_TEMPLATE = (
    "ENGINE OVERVIEW: The CIRIS Engine processes a task through a sequence of "
    "Thoughts. Each handler action except TASK_COMPLETE enqueues a new Thought "
    "for further processing. Selecting TASK_COMPLETE marks the task closed and "
    "no new Thought is generated."
)

DEFAULT_NUM_ROUNDS = None
