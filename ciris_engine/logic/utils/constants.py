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

_COVENANT_PATH = Path(__file__).resolve().parents[3] / "covenant_1.0b.txt"
_COMPREHENSIVE_GUIDE_PATH = Path(__file__).resolve().parents[3] / "CIRIS_COMPREHENSIVE_GUIDE.md"

try:
    with open(_COVENANT_PATH, "r", encoding="utf-8") as f:
        covenant_content = f.read()

    # Append comprehensive guide after covenant
    try:
        with open(_COMPREHENSIVE_GUIDE_PATH, "r", encoding="utf-8") as f:
            guide_content = f.read()
        COVENANT_TEXT = covenant_content + "\n\n---\n\n" + guide_content
    except Exception as exc:
        logger.warning("Could not load comprehensive guide from %s: %s", _COMPREHENSIVE_GUIDE_PATH, exc)
        COVENANT_TEXT = covenant_content

except Exception as exc:
    logger.warning("Could not load covenant text from %s: %s", _COVENANT_PATH, exc)
    COVENANT_TEXT = ""

NEED_MEMORY_METATHOUGHT = "need_memory_metathought"

ENGINE_OVERVIEW_TEMPLATE = (
    "ENGINE OVERVIEW: The CIRIS Engine processes a task through a sequence of "
    "Thoughts. Each handler action except TASK_COMPLETE enqueues a new Thought "
    "for further processing. Selecting TASK_COMPLETE marks the task closed and "
    "no new Thought is generated."
)

DEFAULT_NUM_ROUNDS = None
