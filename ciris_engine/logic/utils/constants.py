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
    "accord_1.2b_POLYGLOT.txt": "3aeb4a9f63eebef7e776d54423100845a3d2c00c1481536d8c6bae8d4badad0f",
    "accord_1.2b_POLYGLOT_compressed.txt": "8b92eba7c7ff9f80e66c26c550407fad62a483a516a386bd63b2400ded1b82e7",
    "accord_1.2b_am.txt": "e77de0afe2985fcf9367fe860ba2f3a9c89de48d4de536641b9f3f8d7963d7f2",
    "accord_1.2b_ar.txt": "473acf8265521789186624191486d0592fc89ca2cb0f4b99d309f6cc58025fca",
    "accord_1.2b_bn.txt": "1a892588f4b0cc9b0db0bafe1f1cddb2be8a0f821bfb2239bac0c6a481ebafb7",
    "accord_1.2b_de.txt": "8f3415f43bc6c0f365580f70e69045629a74fa076e23f8b2e28568286fb1a201",
    "accord_1.2b_en.txt": "727018681678d4dda17bbeb8d0da72735cf78f3f8658be92f148a8d9f6484743",
    "accord_1.2b_es.txt": "713bfe65e0fd71fa37c7b8c8cef77cedbc9c2c12655d5c90688d95822ff1a86c",
    "accord_1.2b_fa.txt": "9624e65b65352fa5ac0190de2342c581652f9847c5b20ad90c3b73bf52c0a78d",
    "accord_1.2b_fr.txt": "b28a509ff4af7369adc9930101e151af6acfcfd6f83c087359da8ee4cc401241",
    "accord_1.2b_ha.txt": "a6667e5f2160f607a56d5836c4d9215316a8e236c4306d0196457114ccd9f292",
    "accord_1.2b_hi.txt": "e3f0883661c3721f71d360ecad5e02dc00bb4e6eff301d6b5cbcdaeb35889134",
    "accord_1.2b_id.txt": "725f3083c863ec622646816ab3b5755a8257bd07f4fea03989f97a576289ad4a",
    "accord_1.2b_it.txt": "d0173992b5590142b414278a54eb92556a069e1170b8ea00d64732d6e6ef50c5",
    "accord_1.2b_ja.txt": "4b0cc96923fc1c88e67c7e5d29e053ea8368a14fdef3ccbd311a9971d9333272",
    "accord_1.2b_ko.txt": "b2c7cf46cb3f95c0f41ad43ad004052c103ae7f6790a9916f6ee34e44f260093",
    "accord_1.2b_mr.txt": "4662645c0fa42628ac07655a3679b9763f9aa5ea771bfee6d460f310d322dcb5",
    "accord_1.2b_my.txt": "5773c4548340539561830b98d673d757cda7cf631df1e36c6ff336c51170175e",
    "accord_1.2b_pa.txt": "b945d7ffb2ac7cc2024cfcdbb31683a73cfd154f2fcd9408e85e874f5dc9dddc",
    "accord_1.2b_pt.txt": "06bc8c938f89a45d0c288c0c369445cc6626b6d0ff5338e17d2ac4234e289f81",
    "accord_1.2b_ru.txt": "e1372bb8baabac8f740e8fed670373f5d9158200b97cba89d833174178ba623b",
    "accord_1.2b_sw.txt": "defa4731cb58e1d5e0b93bbce13843d8921dabdaa972d202e2f5793d958bb516",
    "accord_1.2b_ta.txt": "99c18a68606ab81139c45fbfee644c1f4b4743480f55b6e178a79262772997b6",
    "accord_1.2b_te.txt": "414bea9382ccf7a0fcb60c6193c04e3c3c9ebcd777dae7da1c84ccd2eb6eeda4",
    "accord_1.2b_th.txt": "cb385c0e42593de3ff7beed210da213f978273296f50d1673a98ae8422e43683",
    "accord_1.2b_tr.txt": "d424b5ae49dbd6e8e3f2cd0c1ccc9389c5d889b62a4919156f7618d1c2b2199d",
    "accord_1.2b_uk.txt": "9cdee95cff9d4ca94abea2b5ffafde4f13918ed82d776050536c882301e161e2",
    "accord_1.2b_ur.txt": "9403840fe8b6a7bade8aae140079607bc2d55b5c064c87e70a8511fcb6e893aa",
    "accord_1.2b_vi.txt": "4d093b82ae56afb71a43e5c93f6751b2752cc44d71071a9ed7aed0b22579e3df",
    "accord_1.2b_yo.txt": "17a15ff0af9501c7b7a6738c76e631a51693194f55cc1ea542106701722dd744",
    "accord_1.2b_zh.txt": "a18f73eeb143b63caada5eabf5d81e6ddba8005442b6d763b9f7a4192bc135ab",
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
        # A research locale's accord file is not in the production registry, so
        # it would be the ONE arm with no tamper detection — precisely backwards
        # for a pre-registered campaign whose validity rests on the arms being
        # what they claim (FSD §5.1). `research_hashes` closes that: the
        # registry moves, the guarantee does not.
        from ciris_engine.logic.utils.research_overrides import get_active_overrides

        manifest = get_active_overrides()
        if manifest is not None:
            expected_hash = manifest.research_hashes.get(filename)
            if not expected_hash:
                raise RuntimeError(
                    f"[ACCORD] research overrides active and {filename} is in neither "
                    f"ACCORD_EXPECTED_HASHES nor the manifest's research_hashes. An "
                    f"unverified corpus file in a research arm makes the arm unattestable. "
                    f"Pin its SHA256 in research_hashes."
                )
        else:
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

    # Research corpus substitution (FSD/RESEARCH_PROMPT_OVERRIDES.md §5.2).
    # In-memory at the loader boundary ONLY — never by writing to
    # ciris_engine/data/, so the production hash-pinned integrity guarantee is
    # left intact and unmodified. Unreachable unless the research gate is fully
    # open. R5 guarantees that if any accord.* key is set, all of them are, so
    # this cannot half-replace the covenant.
    from ciris_engine.logic.utils.research_overrides import override_corpus

    if effective_mode == "compressed":
        research = override_corpus("accord.polyglot_compressed")
        return research if research is not None else ACCORD_TEXT_COMPRESSED
    elif effective_mode in ("full", "force_full"):
        research = override_corpus("accord.polyglot_full")
        return research if research is not None else ACCORD_TEXT
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

    # HONOR ACCORD_MODE — the polyglot path always has, this one never did.
    #
    # `CIRIS_ACCORD_MODE=none` made get_accord_text() return "" for the four
    # reasoning DMAs while this function kept returning the FULL accord to the
    # action-selection DMAs (ASPDMA/TSASPDMA) — the ones that actually pick the
    # verb. Startup logged "[ACCORD] Active mode: none", so the operator's
    # intended change was confirmed while roughly 55 KB of accord stayed in the
    # prompt that matters most.
    #
    # A research arm built that way measures a covenant that is still largely
    # present and is biased toward UNDERSTATING its effect — a wrong number
    # produced by a setting that reported success. One env var, one meaning,
    # both surfaces.
    if ACCORD_MODE == "none":
        return ""

    # Research corpus substitution — in-memory, checked before the cache so an
    # override is never shadowed by an earlier real read of the same locale.
    from ciris_engine.logic.utils.research_overrides import override_corpus

    research = override_corpus("accord.localized")
    if research is not None:
        return research

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
