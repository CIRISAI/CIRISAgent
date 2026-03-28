import logging
from pathlib import Path
from typing import Optional

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


def _load_platform_guide(base_path: Path, lang: str = DEFAULT_LANGUAGE) -> str:
    """Load the appropriate runtime guide based on platform and language.

    On mobile (Android/iOS), tries to load CIRIS_COMPREHENSIVE_GUIDE_MOBILE.md first,
    falls back to the legacy Android guide, then the standard guide.

    For non-English languages, tries to load localized versions first from
    ciris_engine/data/localized/ directory.

    Args:
        base_path: The base directory containing the guide files
        lang: ISO 639-1 language code (e.g., 'en', 'am', 'es')

    Returns:
        The guide content as a string, or empty string if not found
    """
    guide_files = []

    # For non-English, try localized guides first
    if lang != DEFAULT_LANGUAGE:
        localized_dir = Path(__file__).resolve().parents[2] / "data" / "localized"
        if is_android() or is_ios():
            guide_files.append(localized_dir / f"CIRIS_COMPREHENSIVE_GUIDE_MOBILE_{lang}.md")
        guide_files.append(localized_dir / f"CIRIS_COMPREHENSIVE_GUIDE_{lang}.md")

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


def _load_accord_file(filename: str, localized_dir: Optional[Path] = None) -> str:
    """Load an accord file from package data or localized directory.

    Args:
        filename: Name of the accord file to load
        localized_dir: Optional path to check for localized version first

    Returns:
        Accord content as string, or empty string if not found
    """
    # Try localized directory first if specified
    if localized_dir:
        localized_path = localized_dir / filename
        if localized_path.exists():
            try:
                with open(localized_path, "r", encoding="utf-8") as f:
                    logger.debug("Loaded localized accord from: %s", localized_path)
                    return f.read()
            except Exception as exc:
                logger.debug("Could not load localized accord %s: %s", localized_path, exc)

    # Fall back to package data
    try:
        try:
            # Python 3.9+ - preferred method
            from importlib.resources import files

            return files("ciris_engine.data").joinpath(filename).read_text(encoding="utf-8")
        except ImportError:
            # Python 3.7-3.8 fallback
            from importlib.resources import read_text

            return read_text("ciris_engine.data", filename, encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not load accord file %s: %s", filename, exc)
        return ""


def get_localized_accord_text(lang: str = DEFAULT_LANGUAGE) -> str:
    """Get the ACCORD text in the specified language.

    Args:
        lang: ISO 639-1 language code (e.g., 'en', 'am', 'es')

    Returns:
        ACCORD 1.3b (Polyglot version) with platform-appropriate guide.
        The Polyglot ACCORD contains all 16 languages woven together for
        maximum semantic depth and cross-cultural resonance.
    """
    # Always use the Polyglot ACCORD 1.3b - contains all languages woven together
    accord_content = _load_accord_file("accord_1.3b.txt")

    # Load platform-appropriate guide in the user's language
    guide_base_path = Path(__file__).resolve().parents[3]
    guide_content = _load_platform_guide(guide_base_path, lang)

    if guide_content:
        return accord_content + "\n\n---\n\n" + guide_content
    return accord_content


# Load accord text from package data using importlib.resources
# This works for both development (editable install) and pip-installed packages
# Always use Polyglot ACCORD 1.3b - contains all 16 languages woven together
try:
    accord_content = _load_accord_file("accord_1.3b.txt")

    # Try to append platform-appropriate comprehensive guide
    _GUIDE_BASE_PATH = Path(__file__).resolve().parents[3]
    guide_content = _load_platform_guide(_GUIDE_BASE_PATH)

    if guide_content:
        ACCORD_TEXT = accord_content + "\n\n---\n\n" + guide_content
    else:
        ACCORD_TEXT = accord_content

except Exception as exc:
    logger.warning("Could not load accord text from package data: %s", exc)
    ACCORD_TEXT = ""

# Load compressed accord for testing/benchmarking
# This is a shorter version containing only essential principles
try:
    ACCORD_TEXT_COMPRESSED = _load_accord_file("accord_1.2b_compressed.txt")
except Exception as exc:
    logger.warning("Could not load compressed accord: %s", exc)
    ACCORD_TEXT_COMPRESSED = ""

NEED_MEMORY_METATHOUGHT = "need_memory_metathought"

ENGINE_OVERVIEW_TEMPLATE = (
    "ENGINE OVERVIEW: The CIRIS Engine processes a task through a sequence of "
    "Thoughts. Each handler action except TASK_COMPLETE enqueues a new Thought "
    "for further processing. Selecting TASK_COMPLETE marks the task closed and "
    "no new Thought is generated."
)

DEFAULT_NUM_ROUNDS = None
