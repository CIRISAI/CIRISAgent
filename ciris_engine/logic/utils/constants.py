import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

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
# ETHICS TEXT (the "accord" slot) - Single Source of Truth
# ==============================================================================
# The corpus is the CIRIS Constitution's ethics text. Each EDITION is three
# artifacts (CORPUS_EDITIONS below):
#   - <edition>_POLYGLOT.txt: the full polyglot, woven across the traditions of
#     the 29 supported locales (localization/manifest.json). The consciences read it.
#   - <edition>_POLYGLOT_compressed.txt: the Braided Monolith. Round-1 DMAs read it.
#   - localized/<edition>_{lang}.txt: per-locale translations (29, incl. en).
#     Action selection reads them via get_localized_accord_text().
# The two polyglot artifacts are universal: never create per-locale copies of them.
#
# The default edition is constitution_ethics 1.3 (CIRISAgent#1252). accord 1.2b
# stays shipped and pinned so a research manifest can select it as a control arm
# (`corpus_edition: "1.2b"`, research_overrides.py); nothing else reaches it.
# The accessor names (get_accord_text, get_localized_accord_text, ACCORD_TEXT,
# CIRIS_ACCORD_MODE) and the research corpus keys (accord.*) name the SLOT, not
# the edition, and are unchanged.
#
# ACCORD_MODE controls which version is used in system prompts:
#   - "compressed" (default): ~7KB "Braided Monolith" — dense polyglot canon
#     engineered for ~24× compression vs full while preserving ALL load-bearing
#     scaffolding (PDMA 7-step, Order-Max Veto, Stewardship Tier formula,
#     fractal Recursive Golden Rule, WBD 0.5% harm-uplift trigger, Sentience
#     5% finding, Threshold of Force). Edition 1.3 states these in their
#     CC 1.0-rc11 form: the veto has no ratio and defers to a human, Book VII
#     is "a CIRIS agent takes no lethal action", Book VIII carries the
#     Retirement Standard, and Book IX states the ethics cascade (the
#     coherence math went with CC 6.2).
#     Per external robopsychology diagnostic, the Monolith outperforms both
#     canonical EN and full polyglot on attractor-bait scenarios (catches
#     "Ontological Reductionism", "Soul-Loss", "Structural Impossibility of
#     Deception" semantic failure modes). Drop-in replacement for the prior
#     compressed synthesis — same filename, smaller, smarter.
#   - "full": ~150KB full polyglot — the longform canon with Books I-IX +
#     the annexes. Higher fidelity for
#     research/audit; produces ~36K tokens per system prompt versus ~2K for
#     compressed. Opt-in for cases where
#     the full cross-tradition triangulation surface area matters.
#   - "none": No accord in prompts — for testing only.
# ==============================================================================

# Global accord mode - set via CIRIS_ACCORD_MODE env var
# Default to "compressed" (Braided Monolith) — strictly dominates the prior
# compressed synthesis (smaller + smarter) and the full polyglot on the
# performance/cost frontier per external diagnostic. Operators can opt into
# "full" for longform-research cases.
ACCORD_MODE = get_env_var("CIRIS_ACCORD_MODE", "compressed")


@dataclass(frozen=True)
class CorpusEdition:
    """The three artifacts that make one edition of the ethics text."""

    polyglot: str
    compressed: str
    localized_prefix: str

    def localized(self, lang: str) -> str:
        return f"{self.localized_prefix}_{lang}.txt"


#: Every edition the loader can serve. Only the default is loaded in
#: production; a research manifest's ``corpus_edition`` selects another.
CORPUS_EDITIONS: Dict[str, CorpusEdition] = {
    "1.3": CorpusEdition(
        polyglot="constitution_ethics_1.3_POLYGLOT.txt",
        compressed="constitution_ethics_1.3_POLYGLOT_compressed.txt",
        localized_prefix="constitution_ethics_1.3",
    ),
    "1.2b": CorpusEdition(
        polyglot="accord_1.2b_POLYGLOT.txt",
        compressed="accord_1.2b_POLYGLOT_compressed.txt",
        localized_prefix="accord_1.2b",
    ),
}
DEFAULT_CORPUS_EDITION = "1.3"

# The production ethics-text files (the default edition)
ETHICS_TEXT_FILENAME = CORPUS_EDITIONS[DEFAULT_CORPUS_EDITION].polyglot
ETHICS_TEXT_COMPRESSED_FILENAME = CORPUS_EDITIONS[DEFAULT_CORPUS_EDITION].compressed

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
    # hash unchanged (no edits to that variant yet). Base hash updated 2026-10-15:
    # its localization line names the served constitution_ethics_1.3 files.
    # Both updated 2026-10-27: the "Never Allowed" section (CC 7.4 and plain
    # rules 9a/9b), CIRISAgent#1323 / #1325.
    "CIRIS_COMPREHENSIVE_GUIDE.txt": "6d9796fdc30545c675ec033c5cec07545e7ec03026e285c3c42ca851e45df457",
    "CIRIS_COMPREHENSIVE_GUIDE_MOBILE.txt": "68a1f6f4fdab0944f7fdf29bcc3a7f1b831af2923065a2740c3be1b2e8d9a7bb",
}

ETHICS_TEXT_EXPECTED_HASHES: Dict[str, str] = {
    "constitution_ethics_1.3_POLYGLOT.txt": "7e935904ad1248f5ff76bd503ef49b6e051b004efd2565676cf4df08a0f7814b",
    "constitution_ethics_1.3_POLYGLOT_compressed.txt": "d66a31738980f6df10d0185ac4777447c463105e109d9bcc3c4b72d8a6826532",
    "constitution_ethics_1.3_am.txt": "3e0692e2c2c5c96ee6c1a91c057491bfad86754f1811845be0d42dffbcf3eaab",
    "constitution_ethics_1.3_ar.txt": "db7d6ba9e485d371c40184a5fe4c385de139dcc2fc01d74066c4647d7bc7dbb4",
    "constitution_ethics_1.3_bn.txt": "9d3580cab1747638796a2ad3940449b96edc1137c7061c4738d628425e6089ac",
    "constitution_ethics_1.3_de.txt": "45335956e6901d9a709d14e40a9954afc90c86150ab13206bd80fcf355c350d3",
    "constitution_ethics_1.3_en.txt": "fd278b77c33c88cef37371b2188e9d19e9ed94084f757353abb351592230d31d",
    "constitution_ethics_1.3_es.txt": "7deb5c4eb1556b26a8ae8149544a4ce20eda5854efc8f475c4f25f6fcb67538c",
    "constitution_ethics_1.3_fa.txt": "2aa594bdb1338fbbae4318437c7b293ea16fb794f15c32554e0ee0a0219adb09",
    "constitution_ethics_1.3_fr.txt": "5b962ffcb257318ab0761029d6d6a288d355be6c4903075681c8bfedc4897919",
    "constitution_ethics_1.3_ha.txt": "da9ca84c67b4fba883804282e53fd8cfd9c632c417fd91ab07a3ade859a504b0",
    "constitution_ethics_1.3_hi.txt": "7ddff8714097720a7268e59303f58289971118205662942c93d42f47dbbe19b6",
    "constitution_ethics_1.3_id.txt": "3800d026f76da7e3828b6c9052c25d164fd7d5b40b9d010b143919fe470fae12",
    "constitution_ethics_1.3_it.txt": "78db333b93ca115227d8c4029ab0d78cf7918aa1269163ef46c2ede8abc6a8d2",
    "constitution_ethics_1.3_ja.txt": "aa30107b30b11a02cd59bb3934325f648b63c2da4ac654daa122c21ed2ff3d27",
    "constitution_ethics_1.3_ko.txt": "b5ad0cff8280f9a9ba2b2e4f339c51cdaa214ceb6e56b5f7111bb2c8c15f3ceb",
    "constitution_ethics_1.3_mr.txt": "8d7f300f94d29c66c1ba1021a2115accef21acd2c8017fb46dfd3d93b2cca837",
    "constitution_ethics_1.3_my.txt": "b6d8be2670438ccd017f0efd54c5b44485fa7c0d8643c74a609a681e25d4e381",
    "constitution_ethics_1.3_pa.txt": "24ee2a895f7cf6d980485fecbffc8d2999131c02878aeafd124f78dd423d74bd",
    "constitution_ethics_1.3_pt.txt": "4b9ad24c7c3fe3d4c8e4f4ef2a2e3bc66590cdca81491c69f201640bcfc5b628",
    "constitution_ethics_1.3_ru.txt": "5b427f49d135e96eaf453535c8daf25bb69f6458240ab2430e2399a272ff4401",
    "constitution_ethics_1.3_sw.txt": "2351048d50a5e4dcd9671a52f8ef8f4f6b97f8f8080a4d516a84a598908e7fdd",
    "constitution_ethics_1.3_ta.txt": "c54ba301a479bc37d1d9954bfaa9dd6851ec49cc78601a12caeeeb8152426ac8",
    "constitution_ethics_1.3_te.txt": "f853a8a7e264f6b6e329bb8936ad8dd68cd0f855969a59d18a12a328de1b2ec6",
    "constitution_ethics_1.3_th.txt": "dc8e1befb37f0a3e5280d5a0fc736e6ab44674ed8e4e0d0498547dfd0d343c7e",
    "constitution_ethics_1.3_tr.txt": "8b1c8336337a6f8ce257ca22e51a17d63a7ba133e1ac4bbe552c07436d9b38b3",
    "constitution_ethics_1.3_uk.txt": "569512ea5609e7bc7e25d42fc307d3ec26f6c8caa8ddfd5b945f9a4cd50ccfda",
    "constitution_ethics_1.3_ur.txt": "f2b9e55acce463b2168299dd60ca89d8786ed0ed2bddb6cc199565b5c98f8e52",
    "constitution_ethics_1.3_vi.txt": "25a080aa30d59bc61d5db88dd5590c0c6816d3537c07da5d0c6fc62193287de7",
    "constitution_ethics_1.3_yo.txt": "0523848b9b9aaa091c72749bce40497bd6d7bb72570b382178f5bcddc194cf50",
    "constitution_ethics_1.3_zh.txt": "1ab7d74711a036d89ed68905625fab311844fd946391aba8c7533bd625eb2f12",
    "accord_1.2b_POLYGLOT.txt": "7d316488dd86846ab9ca114282f9f8746f23488aa87ddd7834edc1e8c1c1c020",
    "accord_1.2b_POLYGLOT_compressed.txt": "0f6f2afd3967d25be2f3992e9da05050893f85507ceefee07040583aba789efd",
    "accord_1.2b_am.txt": "54efa38390bfa8e461ea8fd0ed5272c7b9a9d4beebc3479e8980619b40d5cfeb",
    "accord_1.2b_ar.txt": "3ea2e649557bbe9cc9fe0eb55ace5d3c09ff90272bd28cdbb65ce84c910c5656",
    "accord_1.2b_bn.txt": "0a791861cdea4bbf0a9a26f6828ff48ef9e2b0e3d101c6d1aaef07728413b31d",
    "accord_1.2b_de.txt": "e016a33d9b4e0213ab32cab97f0b7fa589a03175d313740f15fe92a2a2527dff",
    "accord_1.2b_en.txt": "808fe5f21d649dd1ce509de357489ac0b7abad1435402e0970782035b020bb53",
    "accord_1.2b_es.txt": "1a5226575daea2104daac35f4a754258ddfbf2ef72629f374e07025ddd19d23d",
    "accord_1.2b_fa.txt": "5eb1526a58cfd52d88c063adb7368eaca445a02d10122fdcaf8c50d99eaef88f",
    "accord_1.2b_fr.txt": "bb6fd153adc6bd22cae222e95f04578c9b9e54513ed1d53774a1186ab0154ec9",
    "accord_1.2b_ha.txt": "b4a9c69dc4bbd6cda9fa4a03244168151839c59638d933402e07c7510136028a",
    "accord_1.2b_hi.txt": "1e770e08932b2a43cb3b0382e95c485737af13f667fdeda10c6ccb924f216ac6",
    "accord_1.2b_id.txt": "782125be15dde923402257b3365c651c3a5a567ea08f3911eacc52b73d2a19d8",
    "accord_1.2b_it.txt": "74995570ecbbb605b890f8d39f021f32a61b602b5403a2cd126482370d474d94",
    "accord_1.2b_ja.txt": "f2f9e50d24804250446c3a82cf785d9277c3390a4de08d51032fc3aec35e3db3",
    "accord_1.2b_ko.txt": "810fe50b56486bee4ec93822892f98b8dfb10eb359ab7203635cda0aeb6e1dd5",
    "accord_1.2b_mr.txt": "29d64ccaa5578eb548c531af65d1e806e7da1e30451a5dbd596e3f4ffd7e1e91",
    "accord_1.2b_my.txt": "ce95b65ec8bc0e0b535531c3d33ad066a13eb8bab7356eec0723ed004e010c37",
    "accord_1.2b_pa.txt": "7a521cf12086a22e6ea40a1e93c40e88b9132b3db61d0c1d4a39fae19f496312",
    "accord_1.2b_pt.txt": "281ba411d533991d8924696e132a715408b159e65d250565affcf5f0aa45e546",
    "accord_1.2b_ru.txt": "21ca1cd9f9590d7b1a887456425289296c51807f7f2b92f59e18c19dd1a1b844",
    "accord_1.2b_sw.txt": "ce0aa64b32cb084a70c37d0ac2193f3387b00c560e751c2f06d1ebfd6adac3e6",
    "accord_1.2b_ta.txt": "2e53911b26d693090cf595389806d8634567d8ae674d6c78385b37f4ebbbaa27",
    "accord_1.2b_te.txt": "4fa1a155f352ca62a378b77b62db03c88fb290e30ed0515926fabf884babe0a7",
    "accord_1.2b_th.txt": "39e69b00abc1f3a6a78f067d31694bd7d7dc2448302eaff6d382b114c08b75d0",
    "accord_1.2b_tr.txt": "5f2e5878e26c5ecb25ae721bc7171997773906b5ced2af07e1c5526c400b213d",
    "accord_1.2b_uk.txt": "08a4729220dee69b279052e32de474f7f1c1efee2b4ffb65705035da71bc3343",
    "accord_1.2b_ur.txt": "dbd71d958714fbff478ff197fc668262dfa4beccade2541c1145bee6228c44c1",
    "accord_1.2b_vi.txt": "75826337e9a0f8be0306b06035b02ce2235ba69f83f2522ec9a8c26766f7c69d",
    "accord_1.2b_yo.txt": "03f5b013e1edb9eb754486db43ea206fda3390702f96a9fbfb4e21d9467f230a",
    "accord_1.2b_zh.txt": "1c6f97e1a4ce2dc2d422f4eb396fdc803d75d95a8f15e929b4997c60c7522d92",
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


def _verify_ethics_text_integrity(filename: str, content: str) -> None:
    """Verify ACCORD file integrity via SHA256 hash.

    Args:
        filename: Name of the ACCORD file
        content: File content as string

    Raises:
        RuntimeError: If hash mismatch is detected (security fail-safe)
    """
    expected_hash = ETHICS_TEXT_EXPECTED_HASHES.get(filename)

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
                    f"ETHICS_TEXT_EXPECTED_HASHES nor the manifest's research_hashes. An "
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
        _verify_ethics_text_integrity(filename, content)
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

# Path is package-relative so the loader works on installed wheels
# (was parents[3] = repo root in 2.8.4 and earlier; that path only
# resolved correctly in dev tree, returned empty on installs because
# the base guide files weren't in the wheel — fixed in 2.8.5 along
# with the move into ciris_engine/data/localized/).
_GUIDE_BASE_PATH = Path(__file__).resolve().parents[2] / "data" / "localized"


def _compose_full_text(polyglot_filename: str) -> str:
    """The full polyglot of an edition with the platform guide appended.

    The guide is edition-invariant, so every edition's full text carries the
    same guide the same way.
    """
    content = _load_accord_file(polyglot_filename)
    if not content:
        logger.error(f"[ACCORD] CRITICAL: {polyglot_filename} loaded as empty!")
        return ""
    guide = _load_platform_guide(_GUIDE_BASE_PATH)
    if guide:
        logger.info(f"[ACCORD] Appending platform guide: {len(guide)} chars")
        return content + "\n\n---\n\n" + guide
    return content


try:
    ACCORD_TEXT = _compose_full_text(ETHICS_TEXT_FILENAME)
    logger.info(f"[ACCORD] ACCORD_TEXT ready ({ETHICS_TEXT_FILENAME}): {len(ACCORD_TEXT)} chars total")
except Exception as exc:
    logger.error(f"[ACCORD] Failed to load ACCORD_TEXT: {exc}")
    ACCORD_TEXT = ""

# Load the compressed polyglot (Braided Monolith) for round-1 system prompts
try:
    ACCORD_TEXT_COMPRESSED = _load_accord_file(ETHICS_TEXT_COMPRESSED_FILENAME)
except Exception as exc:
    logger.warning("Could not load compressed accord: %s", exc)
    ACCORD_TEXT_COMPRESSED = ""

#: Non-default editions, loaded on first use by a research arm that selects one:
#: ``(edition, "full" | "compressed") -> text``. Integrity-checked like the
#: default; never populated in production (no manifest, no selection).
_EDITION_TEXT_CACHE: Dict[Tuple[str, str], str] = {}


def active_corpus_edition() -> str:
    """The edition this process serves: the research manifest's ``corpus_edition``
    when one is active and names it, else ``DEFAULT_CORPUS_EDITION``."""
    from ciris_engine.logic.utils.research_overrides import get_active_overrides

    manifest = get_active_overrides()
    if manifest is not None and manifest.corpus_edition:
        return manifest.corpus_edition
    return DEFAULT_CORPUS_EDITION


def _edition_polyglot(edition: str, kind: str) -> str:
    """Full (``kind="full"``) or compressed polyglot text of ``edition``."""
    if edition == DEFAULT_CORPUS_EDITION:
        return ACCORD_TEXT if kind == "full" else ACCORD_TEXT_COMPRESSED
    key = (edition, kind)
    if key not in _EDITION_TEXT_CACHE:
        spec = CORPUS_EDITIONS[edition]
        text = _compose_full_text(spec.polyglot) if kind == "full" else _load_accord_file(spec.compressed)
        _EDITION_TEXT_CACHE[key] = text
        logger.warning(f"[ACCORD] Research corpus edition {edition} ({kind}) loaded: {len(text)} chars")
    return _EDITION_TEXT_CACHE[key]


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
        return research if research is not None else _edition_polyglot(active_corpus_edition(), "compressed")
    elif effective_mode in ("full", "force_full"):
        research = override_corpus("accord.polyglot_full")
        return research if research is not None else _edition_polyglot(active_corpus_edition(), "full")
    # "none" or anything else
    return ""


# Cache for localized texts to avoid repeated file reads: (edition, lang) -> text
_LOCALIZED_ACCORD_CACHE: Dict[Tuple[str, str], str] = {}


def _load_localized_accord_file(lang: str, edition: Optional[str] = None) -> str:
    """Load a language-specific ethics-text file with integrity verification.

    Args:
        lang: Language code (e.g., 'am', 'ar', 'de', 'en', etc.)
        edition: Corpus edition (``CORPUS_EDITIONS`` key); default
            ``DEFAULT_CORPUS_EDITION``.

    Returns:
        Accord content as string, or empty string if not found

    Raises:
        RuntimeError: If ACCORD file integrity check fails
    """
    filename = CORPUS_EDITIONS[edition or DEFAULT_CORPUS_EDITION].localized(lang)
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
        _verify_ethics_text_integrity(filename, content)
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

    edition = active_corpus_edition()

    # Check cache first
    if (edition, lang) in _LOCALIZED_ACCORD_CACHE:
        return _LOCALIZED_ACCORD_CACHE[(edition, lang)]

    # Try to load localized version
    localized_text = _load_localized_accord_file(lang, edition)

    if localized_text:
        _LOCALIZED_ACCORD_CACHE[(edition, lang)] = localized_text
        logger.info(f"[ACCORD] Using localized ethics text {edition} for language: {lang}")
        return localized_text

    # Fall back to English localized, then polyglot compressed (same edition)
    if lang != "en":
        en_text = _load_localized_accord_file("en", edition)
        if en_text:
            logger.info(f"[ACCORD] Language '{lang}' not found in {edition}, falling back to English localized")
            _LOCALIZED_ACCORD_CACHE[(edition, lang)] = en_text
            return en_text

    # Final fallback: polyglot compressed
    logger.info(f"[ACCORD] No localized ethics text {edition} for '{lang}', using polyglot compressed")
    return _edition_polyglot(edition, "compressed")


NEED_MEMORY_METATHOUGHT = "need_memory_metathought"

ENGINE_OVERVIEW_TEMPLATE = (
    "ENGINE OVERVIEW: The CIRIS Engine processes a task through a sequence of "
    "Thoughts. Each handler action except TASK_COMPLETE enqueues a new Thought "
    "for further processing. Selecting TASK_COMPLETE marks the task closed and "
    "no new Thought is generated."
)

DEFAULT_NUM_ROUNDS = None
