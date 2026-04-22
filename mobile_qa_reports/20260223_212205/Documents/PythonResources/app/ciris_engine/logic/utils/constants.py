import logging
from pathlib import Path

from ciris_engine.logic.config.env_utils import get_env_var
from ciris_engine.logic.utils.path_resolution import is_android

logger = logging.getLogger(__name__)

# DEFAULT_WA removed - use WA_USER_IDS for Discord user IDs instead
WA_USER_IDS = get_env_var("WA_USER_IDS", "537080239679864862")  # Comma-separated list of WA user IDs

DISCORD_CHANNEL_ID = get_env_var("DISCORD_CHANNEL_ID")
DISCORD_DEFERRAL_CHANNEL_ID = get_env_var("DISCORD_DEFERRAL_CHANNEL_ID")
API_CHANNEL_ID = get_env_var("API_CHANNEL_ID")
API_DEFERRAL_CHANNEL_ID = get_env_var("API_DEFERRAL_CHANNEL_ID")
WA_API_USER = get_env_var("WA_API_USER", "somecomputerguy")  # API username for WA


def _load_platform_guide(base_path: Path) -> str:
    """Load the appropriate runtime guide based on platform.

    On Android, tries to load CIRIS_COMPREHENSIVE_GUIDE_ANDROID.md first,
    falls back to the standard guide if not available.

    Args:
        base_path: The base directory containing the guide files

    Returns:
        The guide content as a string, or empty string if not found
    """
    guide_files = []

    # Platform-specific guide takes priority
    if is_android():
        guide_files.append(base_path / "CIRIS_COMPREHENSIVE_GUIDE_ANDROID.md")
        logger.debug("Android platform detected, will try Android-specific guide first")

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

            return files("ciris_engine.data").joinpath(filename).read_text(encoding="utf-8")
        except ImportError:
            # Python 3.7-3.8 fallback
            from importlib.resources import read_text

            return read_text("ciris_engine.data", filename, encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not load accord file %s: %s", filename, exc)
        return ""


# Load accord text from package data using importlib.resources
# This works for both development (editable install) and pip-installed packages
try:
    accord_content = _load_accord_file("accord_1.2b.txt")

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
