import logging
from pathlib import Path

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
#   - "compressed" (default): ~6KB polyglot synthesis - recommended for production
#   - "full": ~104KB full polyglot - only for special cases
#   - "none": No accord in prompts - for testing only
# ==============================================================================

# Global accord mode - set via CIRIS_ACCORD_MODE env var
# Default to "compressed" for production (saves tokens, retains cross-cultural depth)
ACCORD_MODE = get_env_var("CIRIS_ACCORD_MODE", "compressed")

# The ONLY accord file used in production
ACCORD_FILENAME = "accord_1.2b_POLYGLOT.txt"


def _load_platform_guide(base_path: Path) -> str:
    """Load the appropriate runtime guide based on platform.

    On mobile (Android/iOS), tries to load CIRIS_COMPREHENSIVE_GUIDE_MOBILE.md first,
    falls back to the legacy Android guide, then the standard guide.

    Args:
        base_path: The base directory containing the guide files

    Returns:
        The guide content as a string, or empty string if not found
    """
    guide_files = []

    # Platform-specific guide takes priority on mobile
    if is_android() or is_ios():
        guide_files.append(base_path / "CIRIS_COMPREHENSIVE_GUIDE_MOBILE.md")
        # Legacy fallback for older Android builds
        guide_files.append(base_path / "CIRIS_COMPREHENSIVE_GUIDE_ANDROID.md")
        logger.debug("Mobile platform detected, will try mobile-specific guide first")

    # Standard guide as fallback
    guide_files.append(base_path / "CIRIS_COMPREHENSIVE_GUIDE.md")

    for guide_path in guide_files:
        try:
            with open(guide_path, "r", encoding="utf-8") as f:
                logger.debug("Loaded runtime guide from: %s", guide_path)
                return f.read()
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.debug("Could not load guide from %s: %s", guide_path, exc)
            continue

    logger.debug("No comprehensive guide found (development-only file)")
    return ""


def _load_accord_file(filename: str) -> str:
    """Load an accord file from package data.

    Args:
        filename: Name of the accord file to load

    Returns:
        Accord content as string, or empty string if not found
    """
    try:
        try:
            # Python 3.9+ - preferred method
            from importlib.resources import files

            content = files("ciris_engine.data").joinpath(filename).read_text(encoding="utf-8")
            logger.info(f"[ACCORD] Loaded {filename}: {len(content)} chars")
            return content
        except ImportError:
            # Python 3.7-3.8 fallback
            from importlib.resources import read_text

            content = read_text("ciris_engine.data", filename, encoding="utf-8")
            logger.info(f"[ACCORD] Loaded {filename}: {len(content)} chars (legacy import)")
            return content
    except Exception as exc:
        logger.error(f"[ACCORD] FAILED to load {filename}: {exc}")
        return ""


# ==============================================================================
# Load ACCORD_TEXT at module initialization
# ==============================================================================
# This is the ONLY place we load the accord. All DMAs use this constant.
# ==============================================================================

try:
    _accord_content = _load_accord_file(ACCORD_FILENAME)

    if not _accord_content:
        logger.error(f"[ACCORD] CRITICAL: {ACCORD_FILENAME} loaded as empty!")
        ACCORD_TEXT = ""
    else:
        # Try to append platform-appropriate comprehensive guide
        _GUIDE_BASE_PATH = Path(__file__).resolve().parents[3]
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
    """Get ACCORD text based on mode.

    This is the SINGLE function all DMAs should use to get ACCORD text.
    Centralizes ACCORD loading logic - change here, not in 6 DMA files.

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


NEED_MEMORY_METATHOUGHT = "need_memory_metathought"

ENGINE_OVERVIEW_TEMPLATE = (
    "ENGINE OVERVIEW: The CIRIS Engine processes a task through a sequence of "
    "Thoughts. Each handler action except TASK_COMPLETE enqueues a new Thought "
    "for further processing. Selecting TASK_COMPLETE marks the task closed and "
    "no new Thought is generated."
)

DEFAULT_NUM_ROUNDS = None
