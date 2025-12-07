import logging
from pathlib import Path

from ciris_engine.logic.config.env_utils import get_env_var

logger = logging.getLogger(__name__)

# DEFAULT_WA removed - use WA_USER_IDS for Discord user IDs instead
WA_USER_IDS = get_env_var("WA_USER_IDS", "537080239679864862")  # Comma-separated list of WA user IDs

DISCORD_CHANNEL_ID = get_env_var("DISCORD_CHANNEL_ID")
DISCORD_DEFERRAL_CHANNEL_ID = get_env_var("DISCORD_DEFERRAL_CHANNEL_ID")
API_CHANNEL_ID = get_env_var("API_CHANNEL_ID")
API_DEFERRAL_CHANNEL_ID = get_env_var("API_DEFERRAL_CHANNEL_ID")
WA_API_USER = get_env_var("WA_API_USER", "somecomputerguy")  # API username for WA

# Load covenant text from package data using importlib.resources
# This works for both development (editable install) and pip-installed packages
try:
    try:
        # Python 3.9+ - preferred method
        from importlib.resources import files

        covenant_content = files("ciris_engine.data").joinpath("covenant_1.0b.txt").read_text(encoding="utf-8")
    except ImportError:
        # Python 3.7-3.8 fallback
        from importlib.resources import read_text

        covenant_content = read_text("ciris_engine.data", "covenant_1.0b.txt", encoding="utf-8")

    # Try to append comprehensive guide if available
    _COMPREHENSIVE_GUIDE_PATH = Path(__file__).resolve().parents[3] / "CIRIS_COMPREHENSIVE_GUIDE.md"
    try:
        with open(_COMPREHENSIVE_GUIDE_PATH, "r", encoding="utf-8") as f:
            guide_content = f.read()
        COVENANT_TEXT = covenant_content + "\n\n---\n\n" + guide_content
    except Exception as exc:
        logger.debug("Comprehensive guide not available (development-only file): %s", exc)
        COVENANT_TEXT = covenant_content

except Exception as exc:
    logger.warning("Could not load covenant text from package data: %s", exc)
    COVENANT_TEXT = ""

NEED_MEMORY_METATHOUGHT = "need_memory_metathought"

ENGINE_OVERVIEW_TEMPLATE = (
    "ENGINE OVERVIEW: The CIRIS Engine processes a task through a sequence of "
    "Thoughts. Each handler action except TASK_COMPLETE enqueues a new Thought "
    "for further processing. Selecting TASK_COMPLETE marks the task closed and "
    "no new Thought is generated."
)

DEFAULT_NUM_ROUNDS = None
