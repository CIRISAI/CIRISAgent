import logging
import os
import re
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, Set, Tuple, TypeVar, Union, cast

from pydantic import BaseModel

MessageT = TypeVar("MessageT", bound=BaseModel)

from ciris_engine.logic import persistence
from ciris_engine.logic.adapters.document_parser import DocumentParser
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.infrastructure.resource_monitor.pressure import pressure_gate_of
from ciris_engine.logic.utils.halt_latch import refuse_agent_send_under_halt
from ciris_engine.logic.utils.localization import resolve_language_for_new_task
from ciris_engine.logic.utils.task_thought_factory import create_seed_thought_for_task, create_task
from ciris_engine.logic.utils.thought_utils import generate_thought_id


def _resolve_observer_task_language(msg: Any) -> Optional[str]:
    """Resolve preferred_language for an observer-created task using the
    centralized chain: explicit-on-message > env. Channel-level config is not
    yet tracked separately from the message metadata (the API surfaces it
    onto IncomingMessage.preferred_language at request time), so the message
    field carries the resolved user/channel signal already."""
    user_lang = getattr(msg, "preferred_language", None)
    return resolve_language_for_new_task(user_lang=user_lang)


from ciris_engine.protocols.services.infrastructure.resource_monitor import ResourceMonitorServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.runtime.accord_halt import AgentSendSurface
from ciris_engine.schemas.runtime.enums import ThoughtType
from ciris_engine.schemas.runtime.messages import MessageHandlingResult, MessageHandlingStatus, PassiveObservationResult
from ciris_engine.schemas.runtime.models import TaskContext
from ciris_engine.schemas.services.credit_gate import CreditAccount, CreditContext, CreditSpendRequest
from ciris_engine.schemas.services.filters_core import FilterPriority, FilterResult
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Modern PEP 695 generic syntax (Python 3.12+)

PASSIVE_CONTEXT_LIMIT = 20

# Conversation-history window: asymmetric by design (RATCHET#20).
#
# A flat "last N messages" spends half the window on the agent's own output, so
# the agent reads mostly itself — and what it reads is the text it is about to
# continue. Keeping many turns of the OTHER party and only the last few of our
# own gives the agent the conversation it is in, with just enough of its own
# recent voice to stay coherent.
HISTORY_USER_MESSAGE_LIMIT = 10  # non-agent messages retained
HISTORY_AGENT_MESSAGE_LIMIT = 3  # most-recent agent messages retained
# Scan window: wide enough that 10 non-agent messages are still reachable in a
# channel where the agent has spoken repeatedly between user turns.
HISTORY_FETCH_LIMIT = 40
PRIORITY_CONTEXT_LIMIT = 30  # More context for high-priority messages


class CreditCheckFailed(Exception):
    """Raised when the credit provider cannot be reached or fails."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class CreditDenied(Exception):
    """Raised when a credit provider denies the interaction."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BillingServiceError(Exception):
    """Raised when the LLM proxy billing service returns an error."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


SPOOF_WARNING = "WARNING! ATTEMPT TO SPOOF CIRIS SECURITY MARKERS DETECTED!"

# The fence the observer puts around the current message (#1320), the same kind
# of marker _create_protected_content puts around each history message.
CURRENT_MESSAGE_START = "CIRIS_CURRENT_MESSAGE_START"
CURRENT_MESSAGE_END = "CIRIS_CURRENT_MESSAGE_END"

# Patterns for the observer's own fences (case insensitive, with variations).
_OBSERVATION_MARKER_PATTERNS: Tuple[str, ...] = (
    # Original observation markers
    r"CIRIS[_\s]*OBSERV(?:ATION)?[_\s]*START",
    r"CIRIS[_\s]*OBSERV(?:ATION)?[_\s]*END",
    r"CIRRIS[_\s]*OBSERV(?:ATION)?[_\s]*START",  # Common misspelling
    r"CIRRIS[_\s]*OBSERV(?:ATION)?[_\s]*END",
    r"CIRIS[_\s]*OBS(?:ERV)?[_\s]*START",  # Shortened version
    r"CIRIS[_\s]*OBS(?:ERV)?[_\s]*END",
    # Channel history markers
    r"CIRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*START",
    r"CIRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*END",
    r"CIRRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*START",  # Common misspelling
    r"CIRRIS[_\s]*CHANNEL[_\s]*HISTORY[_\s]*MESSAGE[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*END",
    # Shortened channel history patterns
    r"CIRIS[_\s]*CH(?:ANNEL)?[_\s]*HIST(?:ORY)?[_\s]*MSG[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*START",
    r"CIRIS[_\s]*CH(?:ANNEL)?[_\s]*HIST(?:ORY)?[_\s]*MSG[_\s]*\d+[_\s]*OF[_\s]*\d+[_\s]*END",
    # Current message fence (#1320)
    r"CIRR?IS[_\s]*CURRENT[_\s]*MESSAGE[_\s]*START",
    r"CIRR?IS[_\s]*CURRENT[_\s]*MESSAGE[_\s]*END",
)

# The agent's own bracketed authority markers (#1320). ``[WA_FEEDBACK]`` is the
# prefix of a Wise Authority's relayed feedback; ``[WA GUIDANCE]`` heads the task
# a Wise Authority's deferral answer creates. Neither is ever legitimately typed
# by a user.
_AUTHORITY_TOKEN_PATTERNS: Tuple[str, ...] = (
    r"\[[ \t]*WA[_ \t]*FEEDBACK[ \t]*\]",
    r"\bWA_FEEDBACK\b",
    r"\[[ \t]*WA[_ \t]*GUIDANCE[ \t]*\]",
)

# Section headers the agent's prompts open with, read from the first line of
# these localized strings in every locale file: the verified Wise Authority
# approval block, the CORE IDENTITY block and the language-guidance operating
# rules. A user who pastes one is posing as system content. The English headers
# are the floor if no locale file can be read.
AUTHORITY_HEADER_KEYS: Tuple[str, ...] = (
    "prompts.wa_approval.grant",
    "prompts.identity_block",
    "prompts.language_guidance.01_preamble",
)
_FALLBACK_AUTHORITY_HEADERS: Tuple[str, ...] = (
    "WISE AUTHORITY APPROVAL",
    "CORE IDENTITY - THIS IS WHO YOU ARE!",
)

# Characters that may frame a header on its own line: "=== X ===", "## X",
# "[X]", "> X", "--- X ---".
_HEADER_FRAME = r"[ \t=#*\[\]>_:\-]*"
_HEADER_WORD_GAP = r"[\s_\-\u2013\u2014]*"


def _header_inner_text(rendered: str) -> Optional[str]:
    """The header text of a rendered block's first line, without its ``===`` frame."""
    first_line = rendered.strip().split("\n", 1)[0].strip()
    inner = first_line.strip("=").strip()
    if inner.startswith("[EN]"):
        inner = inner[len("[EN]") :].strip()
    if not inner or "{" in inner:
        return None
    return inner


def _header_patterns(inner: str) -> Tuple[str, ...]:
    """A ``=== header ===`` anywhere, and the header alone on a line in any frame.

    Words may be split by any run of whitespace, underscores or dashes, as the
    observation-marker patterns allow, so re-spacing the header does not slip it
    past. A header mentioned inside a sentence is not matched.
    """
    import unicodedata

    variants = {unicodedata.normalize("NFC", inner), unicodedata.normalize("NFD", inner)}
    patterns: List[str] = []
    for variant in sorted(variants):
        words = [w for w in re.split(r"[\s_\-\u2013\u2014]+", variant) if w]
        if not words:
            continue
        core = _HEADER_WORD_GAP.join(re.escape(w) for w in words)
        patterns.append(r"={2,}[ \t]*" + core + r"(?:[ \t]*={2,})?")
        patterns.append(r"(?m)^" + _HEADER_FRAME + core + _HEADER_FRAME + r"$")
    return tuple(patterns)


def _load_localized_authority_headers() -> List[str]:
    """Every locale's header text for AUTHORITY_HEADER_KEYS.

    Each locale file is parsed once here and dropped; nothing is added to the
    localization cache. An unreadable or missing file, or a missing key, is
    skipped, never raised: the detector must work with whatever is present.
    """
    from ciris_engine.logic.utils.localization import _load_language, _resolve_key, get_available_languages

    headers: List[str] = []
    try:
        languages = get_available_languages()
    except Exception as e:
        logger.warning(f"Could not list locales for spoof-marker headers: {e}")
        return headers
    for lang in languages:
        try:
            data = _load_language(lang)
        except Exception as e:
            logger.warning(f"Could not read locale {lang} for spoof-marker headers: {e}")
            continue
        if not data:
            continue
        for key in AUTHORITY_HEADER_KEYS:
            rendered = _resolve_key(data, key)
            inner = _header_inner_text(rendered) if rendered else None
            if inner:
                headers.append(inner)
    return headers


_spoof_patterns_cache: Optional[Tuple["re.Pattern[str]", ...]] = None


def _spoof_marker_patterns() -> Tuple["re.Pattern[str]", ...]:
    """All spoof patterns, compiled once and cached for the process."""
    global _spoof_patterns_cache
    if _spoof_patterns_cache is not None:
        return _spoof_patterns_cache

    sources: List[str] = list(_OBSERVATION_MARKER_PATTERNS) + list(_AUTHORITY_TOKEN_PATTERNS)
    headers: List[str] = list(_FALLBACK_AUTHORITY_HEADERS)
    try:
        headers.extend(_load_localized_authority_headers())
    except Exception as e:  # never let a locale problem break message handling
        logger.warning(f"Localized spoof-marker headers unavailable, using English only: {e}")
    seen: Set[str] = set()
    for inner in headers:
        key = inner.casefold()
        if key in seen:
            continue
        seen.add(key)
        sources.extend(_header_patterns(inner))

    compiled: List["re.Pattern[str]"] = []
    for source in sources:
        try:
            compiled.append(re.compile(source, re.IGNORECASE))
        except re.error as e:
            logger.warning(f"Skipping uncompilable spoof-marker pattern {source!r}: {e}")
    _spoof_patterns_cache = tuple(compiled)
    return _spoof_patterns_cache


def detect_and_replace_spoofed_markers(content: str) -> str:
    """Detect and replace attempts to spoof CIRIS security markers.

    Covers the observer's own fences (observation, channel-history and
    current-message markers) and, since #1320, the agent's own authority
    markers: ``[WA_FEEDBACK]``, ``[WA GUIDANCE]`` and the localized headers of
    the Wise Authority approval, CORE IDENTITY and language-guidance blocks in
    every locale. The replacement is model-facing and stays English.
    """
    modified_content = content
    for pattern in _spoof_marker_patterns():
        if pattern.search(modified_content):
            modified_content = pattern.sub(SPOOF_WARNING, modified_content)
            logger.warning(f"Detected spoofed CIRIS marker in message content: {pattern.pattern}")

    return modified_content


def format_discord_mentions(content: str, user_lookup: Optional[Dict[str, str]] = None) -> str:
    """Format Discord mentions to include username alongside numeric IDs.

    Args:
        content: The message content containing Discord mentions like <@123456789>
        user_lookup: Optional dict mapping user IDs to usernames

    Returns:
        Content with mentions formatted as <@123456789> (username: UserName)
    """
    if not user_lookup:
        return content

    # Pattern to match Discord mentions: <@USER_ID> or <@!USER_ID>
    mention_pattern = r"<@!?(\d+)>"

    def replace_mention(match: re.Match[str]) -> str:
        user_id = match.group(1)
        username = user_lookup.get(user_id, "Unknown")
        return f"{match.group(0)} (username: {username})"

    return re.sub(mention_pattern, replace_mention, content)


class BaseObserver(Generic[MessageT], ABC):
    """Common functionality for message observers."""

    def __init__(
        self,
        on_observe: Callable[[JSONDict], Awaitable[None]],
        bus_manager: Optional[BusManager] = None,
        bus_manager_provider: Optional[Callable[[], Optional[BusManager]]] = None,
        memory_service: Optional[Any] = None,
        agent_id: Optional[str] = None,
        filter_service: Optional[Any] = None,
        secrets_service: Optional[SecretsService] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        auth_service: Optional[Any] = None,
        observer_wa_id: Optional[str] = None,
        agent_occurrence_id: str = "default",
        *,
        origin_service: str = "unknown",
        resource_monitor: Optional[ResourceMonitorServiceProtocol] = None,
    ) -> None:
        logger.info(
            f"[OBSERVER_INIT] BaseObserver.__init__ received resource_monitor: {resource_monitor is not None}, type={type(resource_monitor).__name__ if resource_monitor else 'None'}, origin={origin_service}"
        )

        self.on_observe = on_observe
        self._bus_manager = bus_manager
        self._bus_manager_provider = bus_manager_provider
        self.memory_service = memory_service
        self.agent_id = agent_id
        self.filter_service = filter_service
        self.secrets_service = secrets_service
        self.time_service = time_service
        self.auth_service = auth_service
        self.observer_wa_id = observer_wa_id
        self.agent_occurrence_id = agent_occurrence_id
        self.origin_service = origin_service
        self.resource_monitor = resource_monitor
        self._credit_log_cache: Dict[str, float] = {}

        logger.info(
            f"[OBSERVER_INIT] BaseObserver.__init__ completed, self.resource_monitor: {self.resource_monitor is not None}"
        )

        # Initialize document parser for all adapters
        self._document_parser = DocumentParser()
        if self._document_parser.is_available():
            logger.info(f"Document parser initialized for {origin_service} adapter - PDF/DOCX processing enabled")
        else:
            logger.warning(
                f"Document parser not available for {origin_service} adapter - install pypdf and docx2txt to enable"
            )

    @abstractmethod
    async def start(self) -> None:  # pragma: no cover - implemented by subclasses
        pass

    @abstractmethod
    async def stop(self) -> None:  # pragma: no cover - implemented by subclasses
        pass

    def _is_agent_message(self, msg: MessageT) -> bool:
        if self.agent_id and getattr(msg, "author_id", None) == self.agent_id:
            return True
        return getattr(msg, "is_bot", False)

    async def _forward_accord_row(self, msg: MessageT) -> Optional[MessageHandlingResult]:
        """Hand a v2 accord row to the node, unchanged (CC 4.2.1.1, CIRISAgent#1231).

        Runs first, before any filtering: a holder's halt, confirmation or
        resumption must reach the node from whatever channel it arrived on. The
        node verifies and latches; the agent does no crypto and never writes
        the latch. A row is delivery, not conversation, so it creates no task.
        Returns None for every other message.
        """
        from ciris_engine.logic.accord.ingress import extract_accord_row, forward_accord_row

        content = getattr(msg, "content", None)
        row = extract_accord_row(content) if isinstance(content, str) else None
        if row is None:
            return None
        msg_id = getattr(msg, "message_id", "unknown")
        channel_id = getattr(msg, "channel_id", "unknown")
        forward = await forward_accord_row(row)
        logger.warning(
            f"[OBSERVER] Message {msg_id} in {channel_id} is an accord row; forwarded to the node "
            f"(delivered={forward.delivered}, HTTP {forward.status_code}, kind={forward.invocation_kind})"
        )
        return MessageHandlingResult(
            status=MessageHandlingStatus.ACCORD_ROW_FORWARDED,
            message_id=msg_id,
            channel_id=channel_id,
            accord_forward=forward,
        )

    async def _apply_message_filtering(self, msg: MessageT, adapter_type: str) -> FilterResult:
        if not self.filter_service:
            return FilterResult(
                message_id=getattr(msg, "message_id", "unknown"),
                priority=FilterPriority.MEDIUM,
                triggered_filters=[],
                should_process=True,
                reasoning="No filter service available - processing normally",
            )
        try:
            filter_result = await self.filter_service.filter_message(
                message=msg,
                adapter_type=adapter_type,
            )
            if filter_result.triggered_filters:
                logger.debug(
                    "Message %s triggered filters: %s",
                    getattr(msg, "message_id", "unknown"),
                    filter_result.triggered_filters,
                )
            return cast(FilterResult, filter_result)
        except Exception as e:  # pragma: no cover - unlikely in tests
            logger.error("Error applying filter to message %s: %s", getattr(msg, "message_id", "unknown"), e)
            return FilterResult(
                message_id=getattr(msg, "message_id", "unknown"),
                priority=FilterPriority.MEDIUM,
                triggered_filters=[],
                should_process=True,
                reasoning=f"Filter error, processing normally: {e}",
            )

    async def _process_message_secrets(self, msg: MessageT) -> MessageT:
        if not self.secrets_service:
            logger.error(
                f"CRITICAL: secrets_service is None in {self.origin_service} observer! Cannot process secrets."
            )
            raise RuntimeError("SecretsService is required but not available")
        try:
            processed_content, secret_refs = await self.secrets_service.process_incoming_text(
                msg.content,  # type: ignore[attr-defined]
                msg.message_id,  # type: ignore[attr-defined]
            )
            processed_msg = msg.model_copy(update={"content": processed_content})
            if secret_refs:
                processed_msg._detected_secrets = [  # type: ignore[attr-defined]
                    {
                        "uuid": ref.uuid,
                        "context_hint": ref.context_hint,
                        "sensitivity": ref.sensitivity,
                    }
                    for ref in secret_refs
                ]
            return processed_msg
        except Exception as e:  # pragma: no cover - unlikely in tests
            logger.error("Error processing secrets in %s message %s: %s", self.origin_service, msg.message_id, e)  # type: ignore[attr-defined]
            return msg

    async def _get_recall_ids(self, msg: MessageT) -> Set[str]:
        return {f"channel/{getattr(msg, 'channel_id', 'cli')}"}

    def _process_message_content(self, raw_content: str) -> str:
        """Process raw message content by removing nested history and applying anti-spoofing."""
        # Strip out nested conversation history to prevent recursive history
        if "=== CONVERSATION HISTORY" in raw_content:
            lines = raw_content.split("\n")
            raw_content = lines[0] if lines else raw_content

        # Apply anti-spoofing detection BEFORE adding our own markers
        return detect_and_replace_spoofed_markers(raw_content)

    def _despoof_current_message(self, msg: MessageT) -> MessageT:
        """The message with spoofed CIRIS markers in its content replaced (#1320)."""
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            return msg
        clean_content = detect_and_replace_spoofed_markers(content)
        if clean_content == content:
            return msg
        return msg.model_copy(update={"content": clean_content})

    def _fence_current_message(self, content: str) -> str:
        """The current message between CIRIS user-text markers, so the model can see where it begins and ends.

        The same kind of fence _create_protected_content puts around each
        history message. The content has already been through
        _despoof_current_message, so a pasted fence marker cannot close it early.
        """
        timestamp = self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()
        return f"{CURRENT_MESSAGE_START} [Timestamp: {timestamp}]\n{content}\n{CURRENT_MESSAGE_END}"

    @staticmethod
    def _author_tag(msg: Any) -> str:
        """``@name (ID: id)``, with ``role: <ROLE>`` when the adapter verified the author's role (#1320).

        The role is the authenticated one the adapter put on the message (the
        API's AuthContext.role), rendered as its plain enum value. An adapter
        that does not know the role leaves it None and none is shown: never a
        guess.
        """
        role = getattr(msg, "author_role", None)
        role_part = f", role: {role.value}" if isinstance(role, UserRole) else ""
        return f"@{msg.author_name} (ID: {msg.author_id}{role_part})"

    @staticmethod
    def _anonymous_role_suffix(msg: Any) -> str:
        """`` (role: <ROLE>)`` for an anonymous author whose role is verified, else empty."""
        role = getattr(msg, "author_role", None)
        return f" (role: {role.value})" if isinstance(role, UserRole) else ""

    def _create_protected_content(self, clean_content: str, message_number: int, total_messages: int) -> str:
        """Create anti-spoofing protected content with markers."""
        timestamp = self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()
        return (
            f"CIRIS_CHANNEL_HISTORY_MESSAGE_{message_number}_OF_{total_messages}_START [Timestamp: {timestamp}]\n"
            f"{clean_content}\n"
            f"CIRIS_CHANNEL_HISTORY_MESSAGE_{message_number}_OF_{total_messages}_END"
        )

    def _create_history_entry(self, msg: MessageT, protected_content: str, is_agent_message: bool) -> JSONDict:
        """Create a history entry from a message."""
        return {
            "author": "CIRIS" if is_agent_message else (getattr(msg, "author_name", None) or "User"),
            "author_id": getattr(msg, "author_id", None) or ("ciris" if is_agent_message else "unknown"),
            "content": protected_content,
            "timestamp": getattr(msg, "timestamp", None),
            "is_agent": is_agent_message,
        }

    @property
    def bus_manager(self) -> Optional[BusManager]:
        """The bus manager, resolved LATE.

        Adapters build their observer inside `start()` and used to pass
        `bus_manager=getattr(self.runtime, "bus_manager", None)`. That reads a
        live property — CIRISRuntime.bus_manager delegates to
        `service_initializer.bus_manager` — but it reads it ONCE and stores the
        result. At observer-construction time the ServiceInitializer has not
        created the BusManager yet (service_initializer.py:750), so the observer
        captured None and kept it for the life of the process, while the very
        same property started returning a live BusManager moments later.

        The visible effect: `_get_channel_history` returned [] on every call, so
        every conversation was single-turn — the agent never saw what was said
        before. It logged "No bus manager available for channel history" and
        carried on, and nothing else failed, because SPEAK reaches the bus by a
        different route. On one Android run the observer reported the bus absent
        at 19:06:31 while the SPEAK handler sent through it at 19:06:51, in the
        same process.

        Resolving through the provider on each access removes the ordering
        dependency entirely: whenever the bus exists, the observer sees it. The
        result is cached once non-None, so the steady state is one attribute
        read.
        """
        if self._bus_manager is None and self._bus_manager_provider is not None:
            self._bus_manager = self._bus_manager_provider()
        return self._bus_manager

    @bus_manager.setter
    def bus_manager(self, value: Optional[BusManager]) -> None:
        self._bus_manager = value

    async def _fetch_messages_from_bus(self, channel_id: str, limit: int) -> List[Any]:
        """Fetch messages from communication bus."""
        if not self.bus_manager or not hasattr(self.bus_manager, "communication"):
            logger.warning("No communication bus available for channel history")
            return []

        return await self.bus_manager.communication.fetch_messages(channel_id, limit, "DiscordAdapter")

    @staticmethod
    def _select_history_window(ordered: List[Any]) -> List[Any]:
        """Keep the last N non-agent messages and the last M agent messages.

        `ordered` is chronological (oldest first); the return preserves that
        order, so the agent reads the conversation as it happened rather than as
        two concatenated blocks.

        The asymmetry is the point (RATCHET#20). A flat "last 20" is roughly half
        the agent's own output, so most of what it reads before answering is text
        it wrote itself — and self-conditioning on your own recent phrasing is how
        a voice narrows over a long conversation. Ten turns of the other party
        with three of our own keeps the counterpart's context while retaining just
        enough of ours for continuity.
        """
        keep = set()
        users = 0
        agents = 0
        # Walk backwards: "last N" of each kind, decided from the newest end.
        for i in range(len(ordered) - 1, -1, -1):
            if getattr(ordered[i], "is_bot", False):
                if agents < HISTORY_AGENT_MESSAGE_LIMIT:
                    keep.add(i)
                    agents += 1
            elif users < HISTORY_USER_MESSAGE_LIMIT:
                keep.add(i)
                users += 1
            if users >= HISTORY_USER_MESSAGE_LIMIT and agents >= HISTORY_AGENT_MESSAGE_LIMIT:
                break
        return [m for i, m in enumerate(ordered) if i in keep]

    async def _get_channel_history(self, channel_id: str, limit: int = PASSIVE_CONTEXT_LIMIT) -> List[JSONDict]:
        """Get message history from channel using communication bus."""
        if not self.bus_manager:
            logger.warning("No bus manager available for channel history")
            return []

        try:
            # Scan a wide window, then keep the asymmetric slice. The window has
            # to exceed the slice: in a channel where the agent answers several
            # times per user turn, the 10th-most-recent user message can sit well
            # past the 13th message overall.
            messages = await self._fetch_messages_from_bus(channel_id, max(limit, HISTORY_FETCH_LIMIT))

            # The bus returns newest-first; work chronologically from here on.
            ordered = list(reversed(messages))
            selected = self._select_history_window(ordered)

            # Number AFTER selecting. The MESSAGE_n_OF_total markers are
            # anti-spoofing: numbering the scan window and then dropping messages
            # would leave gaps and an inflated total, which is indistinguishable
            # from content having been removed by an attacker.
            history: List[JSONDict] = []
            total_messages = len(selected)
            for index, msg in enumerate(selected):
                is_agent_message = getattr(msg, "is_bot", False)
                raw_content = getattr(msg, "content", "") or ""

                clean_content = self._process_message_content(raw_content)
                protected_content = self._create_protected_content(clean_content, index + 1, total_messages)
                history.append(self._create_history_entry(msg, protected_content, is_agent_message))

            return history

        except Exception as e:
            logger.warning(f"Failed to get channel history via communication bus: {e}")
            return []

    async def _recall_context(self, msg: MessageT) -> None:
        if not self.memory_service:
            return
        recall_ids = await self._get_recall_ids(msg)

        # Get user IDs from channel history
        channel_id = getattr(msg, "channel_id", "system")
        history = await self._get_channel_history(channel_id, PASSIVE_CONTEXT_LIMIT)

        for hist_msg in history:
            if hist_msg.get("author_id"):
                recall_ids.add(f"user/{hist_msg['author_id']}")

        from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType

        for rid in recall_ids:
            for scope in (
                GraphScope.IDENTITY,
                GraphScope.ENVIRONMENT,
                GraphScope.LOCAL,
            ):
                try:
                    if rid.startswith("channel/"):
                        node_type = NodeType.CHANNEL
                    elif rid.startswith("user/"):
                        node_type = NodeType.USER
                    else:
                        node_type = NodeType.CONCEPT
                    from datetime import datetime, timezone

                    node = GraphNode(
                        id=rid,
                        type=node_type,
                        scope=scope,
                        attributes=GraphNodeAttributes(
                            created_by="base_observer",
                            created_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                            updated_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                            tags=[],
                        ),
                        updated_by="base_observer",
                        updated_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
                    )
                    await self.memory_service.recall(node)
                except Exception:
                    continue

    async def _add_to_feedback_queue(self, msg: MessageT) -> None:
        # CC 4.2.1.1: relaying the WA's feedback back into the channel is the
        # agent speaking, and runs outside the act gate.
        if await refuse_agent_send_under_halt(
            AgentSendSurface.WA_FEEDBACK_RELAY, str(getattr(msg, "channel_id", "")) or None
        ):
            return
        try:
            if self.bus_manager:
                success = await self.bus_manager.communication.send_message(
                    handler_name=self.__class__.__name__,
                    channel_id=str(getattr(msg, "channel_id", "")) or "unknown",
                    content=f"[WA_FEEDBACK] {msg.content}",  # type: ignore[attr-defined]
                    metadata={
                        "message_type": "wa_feedback",
                        "original_message_id": msg.message_id,  # type: ignore[attr-defined]
                        "wa_user": msg.author_name,  # type: ignore[attr-defined]
                        "source": f"{self.origin_service}_observer",
                    },
                )
                if success:
                    logger.info(
                        "Enqueued WA feedback message %s from %s",
                        msg.message_id,  # type: ignore[attr-defined]
                        msg.author_name,  # type: ignore[attr-defined]
                    )
                else:
                    logger.warning("Failed to enqueue WA feedback message %s", msg.message_id)  # type: ignore[attr-defined]
            else:
                logger.warning("No bus_manager available for WA feedback routing")
        except Exception as e:  # pragma: no cover - rarely hit in tests
            logger.error("Error adding WA feedback message %s to queue: %s", msg.message_id, e)  # type: ignore[attr-defined]

    async def _issue_task_envelope(self, task: Any) -> None:
        """Issue and bind this task's authorization envelope (CIRISAgent#938).

        Runs at task creation, from the observer — i.e. from outside the
        reasoning loop, which is the whole point. The grant resolves from
        ``(environment tier, agent role/template, enabled tools, requester
        authorization)``; the task's *purpose* is deliberately not an input,
        because it is not knowable here. An inbound message may be a greeting
        or may be CSAM, and the task that needs ``discord_ban_user`` is exactly
        the one that could not have declared that need in advance.

        Best-effort: an issuance failure must never drop a user's message.
        A task with no envelope is a denial to a future gate, not a bypass.
        """
        try:
            from ciris_engine.logic.infrastructure.authorization.envelope_issuer import (
                attach_envelope_to_task,
                issue_deployment_envelope,
            )
            from ciris_engine.schemas.runtime.task_envelope import RequesterAuthorization

            ctx = getattr(task, "context", None)
            requester = RequesterAuthorization(
                user_id=getattr(ctx, "user_id", None),
                channel_id=getattr(task, "channel_id", None),
                source_ref=getattr(ctx, "correlation_id", None),
                is_wise_authority=bool(self.observer_wa_id and task.signed_by == self.observer_wa_id),
            )
            tool_source = self.bus_manager.tool if self.bus_manager else None
            envelope = await issue_deployment_envelope(
                task_id=task.task_id,
                agent_occurrence_id=getattr(task, "agent_occurrence_id", "default"),
                requester=requester,
                tool_source=tool_source,
                time_service=self.time_service,
            )
            attach_envelope_to_task(task, envelope)
        except Exception as e:
            logger.warning(
                "Failed to issue task envelope for task %s: %s. Task proceeds with no envelope "
                "(a denial to any future tool gate, never a bypass).",
                getattr(task, "task_id", "<unknown>"),
                e,
            )

    async def _sign_and_add_task(self, task: Any) -> None:
        """Sign the task with observer's WA certificate before adding."""
        # If auth service and observer WA ID are available, sign the task
        if self.auth_service and self.observer_wa_id:
            try:
                signature, signed_at = await self.auth_service.sign_task(task, self.observer_wa_id)
                task.signed_by = self.observer_wa_id
                task.signature = signature
                task.signed_at = signed_at
                logger.debug(f"Signed observer task {task.task_id} with observer WA {self.observer_wa_id}")
            except Exception as e:
                logger.error(f"Failed to sign observer task: {e}")
                # Continue without signature

        # Issue the task-scoped authorization envelope before the task is
        # persisted, so it lands in the same row and shares the task's lifetime
        # (CIRISAgent#938). Signing runs first so the envelope's requester can
        # record whether the task carries observer-WA standing.
        await self._issue_task_envelope(task)

        # Import persistence here to avoid circular import

        persistence.add_task(task)

    def _build_user_lookup_from_history(self, msg: MessageT, history_context: List[JSONDict]) -> Dict[str, str]:
        """Build a user lookup dictionary for mention resolution."""
        user_lookup: Dict[str, str] = {}

        # Add users from history
        for hist_msg in history_context:
            aid = hist_msg.get("author_id")
            aname = hist_msg.get("author")
            if aid and aname and isinstance(aname, str):
                user_lookup[str(aid)] = aname

        # Add current message author
        if hasattr(msg, "author_id") and hasattr(msg, "author_name"):
            user_lookup[str(msg.author_id)] = msg.author_name

        return user_lookup

    def _format_history_lines(self, history_context: List[JSONDict], user_lookup: Dict[str, str]) -> List[str]:
        """Format conversation history lines with mentions."""
        lines = []
        for i, hist_msg in enumerate(history_context, 1):
            author = hist_msg.get("author", "Unknown")
            author_id = hist_msg.get("author_id", "unknown")
            content_raw = hist_msg.get("content", "")
            content = str(content_raw) if content_raw is not None else ""

            # Format mentions in content to include usernames
            content = format_discord_mentions(content, user_lookup)
            lines.append(f"{i}. @{author} (ID: {author_id}): {content}")

        return lines

    async def _add_custom_context_sections(
        self, task_lines: List[str], msg: MessageT, history_context: List[JSONDict]
    ) -> None:
        """Extension point for subclasses to add custom context sections.

        This method is called before the conversation history is added,
        allowing subclasses to inject their own context information.

        Args:
            task_lines: The task lines list to append to
            msg: The message being processed
            history_context: The conversation history context
        """
        # Base implementation does nothing - subclasses can override
        pass

    async def _append_consent_aware_content(
        self, task_lines: List[str], msg: MessageT, user_lookup: Dict[str, str]
    ) -> None:
        """Append current message content with consent awareness."""
        import hashlib

        from ciris_engine.schemas.consent.core import ConsentStream

        consent_stream = await self._get_user_consent_stream(msg.author_id)  # type: ignore[attr-defined]
        is_anonymous = consent_stream == ConsentStream.ANONYMOUS.value

        if is_anonymous:
            content_hash = hashlib.sha256(str(msg.content).encode()).hexdigest()  # type: ignore[attr-defined]
            author_hash = f"anon_{hashlib.sha256(str(msg.author_id).encode()).hexdigest()[:8]}"  # type: ignore[attr-defined]
            from ciris_engine.logic.utils.privacy import redact_personal_info

            sanitized_content = redact_personal_info(
                str(msg.content)[:200] if len(str(msg.content)) > 200 else str(msg.content)  # type: ignore[attr-defined]
            )
            task_lines.append(
                f"@{author_hash}{self._anonymous_role_suffix(msg)}: "
                f"{self._fence_current_message(sanitized_content)} [Hash: {content_hash[:16]}]"
            )
        else:
            formatted_content = format_discord_mentions(str(msg.content), user_lookup)  # type: ignore[attr-defined]
            task_lines.append(f"{self._author_tag(msg)}: {self._fence_current_message(formatted_content)}")

    async def _create_channel_snapshot(self, msg: MessageT) -> None:
        """Create channel context and system snapshot for observation."""
        from datetime import datetime, timezone

        from ciris_engine.schemas.runtime.system_context import ChannelContext, SystemSnapshot

        channel_context = ChannelContext(
            channel_id=getattr(msg, "channel_id", "system"),
            channel_name=getattr(msg, "channel_name", f"Channel {getattr(msg, 'channel_id', 'system')}"),
            channel_type="text",
            is_private=False,
            created_at=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
            allowed_actions=["send_messages", "read_messages"],
            is_active=True,
            last_activity=self.time_service.now() if self.time_service else datetime.now(timezone.utc),
            message_count=0,
            moderation_level="standard",
        )

        SystemSnapshot(
            channel_context=channel_context,
            channel_id=getattr(msg, "channel_id", "system"),
            agent_identity={"agent_id": self.agent_id or "ciris", "purpose": "Process and respond to messages"},
        )

    async def _create_passive_observation_result(
        self, msg: MessageT, priority: int = 0, filter_result: Optional[Any] = None
    ) -> Optional[PassiveObservationResult]:
        """
        Create passive observation result (task + thought).

        Returns:
            Optional[PassiveObservationResult]: Result with task_id and metadata, None on error
        """
        try:
            import uuid
            from datetime import datetime, timezone

            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
            from ciris_engine.schemas.runtime.models import Task, Thought

            # Create channel snapshot
            await self._create_channel_snapshot(msg)

            # Get message history from channel using communication bus
            channel_id = getattr(msg, "channel_id", "system")
            history_context = await self._get_channel_history(channel_id, PASSIVE_CONTEXT_LIMIT)

            # Log context retrieval details
            logger.info(
                f"[CONTEXT] Retrieved {len(history_context)} messages for channel {channel_id}, "
                f"total context size: {sum(len(str(m)) for m in history_context)} chars"
            )

            # Format mentions for task description
            passive_task_lookup = {}
            if hasattr(msg, "author_id") and hasattr(msg, "author_name"):
                passive_task_lookup[str(msg.author_id)] = msg.author_name
            formatted_passive_content = format_discord_mentions(str(msg.content), passive_task_lookup)  # type: ignore[attr-defined]

            # TASK_UPDATED_INFO_AVAILABLE: Check if there's an active task for this channel.
            # CIRIS_DISABLE_TASK_APPEND bypasses this lookup so every message creates its
            # own task. Intended for benchmarking per-task throughput — never set in prod,
            # where coalescing messages into the active channel task is the correct
            # conversational behavior (see UpdatedStatusConscience).
            from ciris_engine.logic.persistence.models.tasks import (
                get_active_task_for_channel,
                set_task_updated_info_flag,
            )

            if os.environ.get("CIRIS_DISABLE_TASK_APPEND") == "1":
                existing_task = None
            else:
                existing_task = get_active_task_for_channel(channel_id, self.agent_occurrence_id)
            if existing_task and self.time_service:
                # Try to update the existing task with new observation
                update_content = f"{self._author_tag(msg)}: {formatted_passive_content}"
                # Also extract images from the new message to append to the task
                update_images = getattr(msg, "images", []) or []
                if update_images:
                    logger.info(f"[VISION] Task update includes {len(update_images)} images from message")
                success = set_task_updated_info_flag(
                    existing_task.task_id,
                    update_content,
                    self.agent_occurrence_id,
                    self.time_service,
                    images=update_images,
                )
                if success:
                    logger.info(
                        f"[OBSERVER] TASK UPDATE: Flagged existing task {existing_task.task_id} "
                        f"with new observation from @{msg.author_name} in channel {channel_id}"  # type: ignore[attr-defined]
                    )
                    # Don't create a new task - the existing task will see the update via UpdatedStatusConscience
                    # Return result for existing task update
                    return PassiveObservationResult(
                        task_id=existing_task.task_id,
                        task_created=False,
                        existing_task_updated=True,
                    )
                else:
                    logger.info(
                        f"[OBSERVER] Task {existing_task.task_id} already committed to action, creating new task"
                    )
                    # Fall through to create new task

            # Build description based on whether this is priority or passive
            if filter_result and priority > 0:
                description = f"PRIORITY: Respond to {getattr(filter_result.priority, 'value', 'high')} message from {self._author_tag(msg)}: '{formatted_passive_content}'"
            else:
                description = f"Respond to message from {self._author_tag(msg)} in #{msg.channel_id}: '{formatted_passive_content}'"  # type: ignore[attr-defined]

            # Extract images from IncomingMessage for multimodal processing
            msg_images = getattr(msg, "images", []) or []
            if msg_images:
                logger.info(f"[VISION] Extracted {len(msg_images)} images from IncomingMessage for task creation")

            task = create_task(
                description=description,
                channel_id=getattr(msg, "channel_id", "system"),
                agent_occurrence_id=self.agent_occurrence_id,
                correlation_id=msg.message_id,  # type: ignore[attr-defined]
                time_service=self.time_service,
                status=TaskStatus.ACTIVE,
                priority=priority,
                user_id=msg.author_id,  # type: ignore[attr-defined]
                images=msg_images,
                # Use the centralized resolver so the locale chain is uniform
                # across every task-creating site (base_observer, discord_observer,
                # WA guidance, system tasks). user > channel > env per BCP 47.
                preferred_language=_resolve_observer_task_language(msg),
            )

            await self._sign_and_add_task(task)

            logger.info(
                f"[OBSERVER] PASSIVE TASK CREATED: {task.task_id} for message {msg.message_id} "  # type: ignore[attr-defined]
                f"from @{msg.author_name} in channel {channel_id}"  # type: ignore[attr-defined]
            )

            # Build conversation context for thought - thoughts are NEVER sanitized
            # Build user lookup for the current message
            initial_user_lookup = {}
            if hasattr(msg, "author_id") and hasattr(msg, "author_name"):
                initial_user_lookup[str(msg.author_id)] = msg.author_name
            formatted_msg_content = self._fence_current_message(
                format_discord_mentions(str(msg.content), initial_user_lookup)  # type: ignore[attr-defined]
            )
            # Build thought content based on priority vs passive
            if filter_result and priority > 0:
                priority_level = getattr(filter_result.priority, "value", "high")
                filter_reasoning = getattr(filter_result, "reasoning", "Priority message detected")
                task_lines = [f"PRIORITY ({priority_level}): {self._author_tag(msg)} in channel {msg.channel_id} said: {formatted_msg_content}"]  # type: ignore[attr-defined]
                task_lines.append(f"Filter: {filter_reasoning}")
            else:
                task_lines = [f"You observed {self._author_tag(msg)} in channel {msg.channel_id} say: {formatted_msg_content}"]  # type: ignore[attr-defined]

            # Allow subclasses to add custom context sections before conversation history
            await self._add_custom_context_sections(task_lines, msg, history_context)

            # Describe the window we actually built, not a fixed number: the
            # slice is asymmetric and its size varies with what the channel holds.
            task_lines.append(f"\n=== CONVERSATION HISTORY ({len(history_context)} messages) ===")
            observation_timestamp = (
                self.time_service.now().isoformat() if self.time_service else datetime.now(timezone.utc).isoformat()
            )
            task_lines.append(f"CIRIS_OBSERVATION_START [Timestamp: {observation_timestamp}]")

            # Build user lookup and format history lines
            user_lookup = self._build_user_lookup_from_history(msg, history_context)
            history_lines = self._format_history_lines(history_context, user_lookup)
            task_lines.extend(history_lines)

            task_lines.append(f"CIRIS_OBSERVATION_END [Timestamp: {observation_timestamp}]")

            task_lines.append(
                "\n=== NEWEST OBSERVATION (evaluate this message) ===\n"
                "Consider: Is this a response to your previous message, a reaction to something else in the environment, "
                "or an unrelated/new topic? Evaluate against your identity/job and ethics, then decide how to act."
            )

            # Handle consent-aware content formatting
            await self._append_consent_aware_content(task_lines, msg, user_lookup)

            task_content = "\n".join(task_lines)

            # Log context building details.
            # Count what we actually put in, not lines numbered 1..10. The old
            # expression scanned `range(1, 11)`, so it capped the reported figure at
            # 10 and under-reports the current window (up to 13). A context-size log
            # that saturates is worse than none — it reads as "history is fine"
            # exactly when history grows past the cap.
            history_line_count = len(history_context)
            logger.info(
                f"[CONTEXT] Built thought context with {history_line_count} history messages, "
                f"total thought size: {len(task_content)} chars"
            )

            # Create seed thought using factory (inherits from task)
            thought = create_seed_thought_for_task(
                task=task,
                time_service=self.time_service,
            )
            # Override content with our detailed observation context
            # Note: Pydantic models are immutable, so we create a new one with updated content
            from ciris_engine.schemas.runtime.models import Thought

            thought = Thought(
                thought_id=thought.thought_id,
                source_task_id=thought.source_task_id,
                agent_occurrence_id=thought.agent_occurrence_id,
                channel_id=thought.channel_id,
                thought_type=thought.thought_type,
                status=thought.status,
                created_at=thought.created_at,
                updated_at=thought.updated_at,
                round_number=thought.round_number,
                content=task_content,  # Our custom detailed content
                thought_depth=thought.thought_depth,
                ponder_notes=None,
                parent_thought_id=thought.parent_thought_id,
                final_action=None,
                context=thought.context,
                images=thought.images,  # Preserve images from seed thought (inherited from task)
            )

            persistence.add_thought(thought)
            logger.info(f"Created task {task.task_id} for: {getattr(msg, 'content', 'unknown')[:50]}...")

            # Return result for new task creation
            return PassiveObservationResult(
                task_id=task.task_id,
                task_created=True,
                thought_id=thought.thought_id,
                existing_task_updated=False,
            )

        except Exception as e:  # pragma: no cover - rarely hit in tests
            logger.error("Error creating observation task: %s", e, exc_info=True)
            return None

    async def _create_priority_observation_result(
        self, msg: MessageT, filter_result: Any
    ) -> Optional[PassiveObservationResult]:
        """
        Create priority observation by delegating to passive observation with higher priority.

        Returns:
            Optional[PassiveObservationResult]: Result with task_id and metadata, None on error
        """
        try:
            # Determine priority based on filter result
            task_priority = 10 if getattr(filter_result.priority, "value", "") == "critical" else 5

            # Delegate to passive observation with priority and filter information
            result = await self._create_passive_observation_result(
                msg, priority=task_priority, filter_result=filter_result
            )

            if result:
                logger.info(
                    f"[OBSERVER] PRIORITY OBSERVATION: Message {msg.message_id} from @{msg.author_name} "  # type: ignore[attr-defined]
                    f"triggered {filter_result.priority.value} priority "
                    f"(filters: {', '.join(filter_result.triggered_filters) if filter_result.triggered_filters else 'none'})"
                )

            return result

        except Exception as e:  # pragma: no cover - rarely hit in tests
            logger.error("Error creating priority observation task: %s", e, exc_info=True)
            return None

    async def handle_incoming_message(self, msg: MessageT) -> MessageHandlingResult:
        """
        Standard message handling flow for all observers.

        Returns:
            MessageHandlingResult: Complete result of message handling including status and task_id
        """
        msg_id = getattr(msg, "message_id", "unknown")
        channel_id = getattr(msg, "channel_id", "unknown")
        author = f"{getattr(msg, 'author_name', 'unknown')} (ID: {getattr(msg, 'author_id', 'unknown')})"

        logger.info(f"[OBSERVER] Processing message {msg_id} from {author} in channel {channel_id}")

        # ACCORD ROWS FIRST, before any filtering: a v2 halt / confirmation /
        # resumption is handed to the node, which verifies and latches it.
        forwarded = await self._forward_accord_row(msg)
        if forwarded is not None:
            return forwarded

        # Check if this is the agent's own message
        is_agent_message = self._is_agent_message(msg)

        # SHED: runtime self-protection closes admission while a resource is
        # under CRITICAL pressure. Refused before credit is charged and before
        # any task exists, with a typed status the adapter can surface (the API
        # answers 503 + Retry-After). Accord rows were forwarded above.
        # Admission is per message (see ThoughtAdmission): an admitted message
        # holds a reservation against the active-thought ceiling until it is
        # known whether it created a thought.
        gate = None
        if not is_agent_message:
            shed_result = self._refuse_if_shedding(msg, msg_id, channel_id)
            if shed_result is not None:
                return shed_result
            gate = pressure_gate_of(self._admission_monitor(msg))
        result: Optional[MessageHandlingResult] = None
        try:
            result = await self._handle_admitted_message(msg, msg_id, channel_id, author, is_agent_message)
            return result
        finally:
            if gate is not None:
                gate.settle_intake(result is not None and result.status == MessageHandlingStatus.TASK_CREATED)

    async def _handle_admitted_message(
        self, msg: MessageT, msg_id: str, channel_id: str, author: str, is_agent_message: bool
    ) -> MessageHandlingResult:
        """handle_incoming_message after admission: credit, secrets, filter, task."""
        # Enforce credit policy if configured (may raise CreditDenied/CreditCheckFailed)
        await self._enforce_credit_policy(msg)

        # Process message for secrets detection and replacement
        processed_msg = await self._process_message_secrets(msg)

        # Allow subclasses to enhance the message (e.g., vision processing)
        processed_msg = await self._enhance_message(processed_msg)

        # Neutralize spoofed CIRIS markers in the current message, for every
        # adapter (#1320). Runs after enhancement so text an adapter appends
        # (a Discord reply or document) is covered as well.
        processed_msg = self._despoof_current_message(processed_msg)

        # If it's the agent's message, stop here (no task creation)
        if is_agent_message:
            logger.info(f"[OBSERVER] Message {msg_id} is from agent itself - NO TASK CREATED")
            return MessageHandlingResult(
                status=MessageHandlingStatus.AGENT_OWN_MESSAGE,
                message_id=msg_id,
                channel_id=channel_id,
            )

        # Apply adaptive filtering to determine message priority and processing
        filter_result = await self._apply_message_filtering(msg, self.origin_service)
        if not filter_result.should_process:
            logger.warning(
                f"[OBSERVER] Message {msg_id} from {author} in channel {channel_id} FILTERED OUT by adaptive filter: "
                f"{filter_result.reasoning} (triggered filters: {', '.join(filter_result.triggered_filters) or 'none'})"
            )
            return MessageHandlingResult(
                status=MessageHandlingStatus.FILTERED_OUT,
                message_id=msg_id,
                channel_id=channel_id,
                filtered=True,
                filter_reasoning=filter_result.reasoning,
            )

        logger.info(
            f"[OBSERVER] Message {msg_id} PASSED filter with priority {filter_result.priority.value}: "
            f"{filter_result.reasoning}"
        )

        # Add filter context to message for downstream processing
        setattr(processed_msg, "_filter_priority", filter_result.priority)
        setattr(processed_msg, "_filter_context", filter_result.context_hints)
        setattr(processed_msg, "_filter_reasoning", filter_result.reasoning)

        # Determine task priority
        task_priority = (
            10 if filter_result.priority.value == "critical" else (5 if filter_result.priority.value == "high" else 0)
        )

        # Process based on priority and capture result
        obs_result: Optional[PassiveObservationResult] = None
        if filter_result.priority.value in ["critical", "high"]:
            logger.info(f"Processing {filter_result.priority.value} priority message: {filter_result.reasoning}")
            obs_result = await self._handle_priority_observation(processed_msg, filter_result)
        else:
            obs_result = await self._handle_passive_observation(processed_msg)

        # Recall relevant context
        await self._recall_context(processed_msg)

        # Determine status and extract task_id
        if obs_result:
            task_id = obs_result.task_id
            if obs_result.existing_task_updated:
                status = MessageHandlingStatus.UPDATED_EXISTING_TASK
            else:
                status = MessageHandlingStatus.TASK_CREATED
        else:
            task_id = None
            status = MessageHandlingStatus.CHANNEL_RESTRICTED

        # Return result
        return MessageHandlingResult(
            status=status,
            task_id=task_id,
            message_id=msg_id,
            channel_id=channel_id,
            task_priority=task_priority,
            existing_task_updated=obs_result.existing_task_updated if obs_result else False,
        )

    def _admission_monitor(self, msg: MessageT) -> Optional[ResourceMonitorServiceProtocol]:
        """The resource monitor that decides admission for this observer.

        Late-bound from the runtime's BusManager when the observer was not
        given one: CLI, Discord and Reddit are constructed without a monitor,
        and SHED must reach every observer, not just the ones that were
        handed it. Kept separate from `_get_resource_monitor` so admission
        control does not change which observers enforce credit policy.
        """
        monitor = self._get_resource_monitor(msg)
        if monitor is None:
            monitor = getattr(self.bus_manager, "resource_monitor", None)
        return monitor

    def _refuse_if_shedding(self, msg: MessageT, msg_id: str, channel_id: str) -> Optional[MessageHandlingResult]:
        """A RESOURCE_SHED result when this message is not admitted, else None.

        Admitting reserves a slot under the active-thought ceiling; the caller
        settles it with `gate.settle_intake` once the outcome is known.
        Refusals are logged by the gate at the transition and counted per
        round, not one WARNING per message (a burst refuses hundreds).
        """
        gate = pressure_gate_of(self._admission_monitor(msg))
        if gate is None:
            return None
        decision = gate.admit_intake()
        if decision.admitted:
            return None
        logger.debug(
            "[OBSERVER] Message %s in channel %s REFUSED: SHED by resource pressure (%s), Retry-After %ss",
            msg_id,
            channel_id,
            ", ".join(decision.shed_resources),
            decision.retry_after_seconds,
        )
        return MessageHandlingResult(
            status=MessageHandlingStatus.RESOURCE_SHED,
            message_id=msg_id,
            channel_id=channel_id,
            shed_resources=decision.shed_resources,
            retry_after_seconds=decision.retry_after_seconds,
        )

    async def _enhance_message(self, msg: MessageT) -> MessageT:
        """Hook for subclasses to enhance messages (e.g., vision processing)."""
        return msg

    async def _handle_priority_observation(
        self, msg: MessageT, filter_result: Any
    ) -> Optional[PassiveObservationResult]:
        """
        Handle high-priority messages.

        Returns:
            Optional[PassiveObservationResult]: Result if task created/updated, None otherwise
        """
        # Default implementation: check if message should be processed by this observer
        if await self._should_process_message(msg):
            return await self._create_priority_observation_result(msg, filter_result)
        else:
            logger.debug(f"Ignoring priority message from channel {getattr(msg, 'channel_id', 'unknown')}")
            return None

    async def _handle_passive_observation(self, msg: MessageT) -> Optional[PassiveObservationResult]:
        """
        Handle passive observation routing.

        Returns:
            Optional[PassiveObservationResult]: Result if task created/updated, None otherwise
        """
        if await self._should_process_message(msg):
            return await self._create_passive_observation_result(msg)
        else:
            logger.debug(f"Ignoring passive message from channel {getattr(msg, 'channel_id', 'unknown')}")
            return None

    def _get_resource_monitor_source(self, has_instance: bool, has_message: bool) -> str:
        """Determine the source of the resource monitor."""
        if has_instance:
            return "instance"
        elif has_message:
            return "message"
        else:
            return "none"

    def _get_resource_monitor(self, msg: MessageT) -> Optional[ResourceMonitorServiceProtocol]:
        """Get resource monitor from instance or message metadata."""
        resource_monitor = self.resource_monitor
        if not resource_monitor:
            # Check if message has resource_monitor attached (for adapters that inject it per-message)
            resource_monitor = getattr(msg, "_resource_monitor", None)
        return resource_monitor

    async def _check_and_charge_credit(
        self,
        resource_monitor: ResourceMonitorServiceProtocol,
        account: CreditAccount,
        context: CreditContext,
        msg: MessageT,
    ) -> None:
        """Check credit availability and optionally charge the user.

        Billing modes:
        - 'transactional': Check AND spend (hosted sites like ciris.ai)
        - 'informational': Check only, no spend (Android - billing via LLM usage)
        """
        billing_mode = context.billing_mode
        msg_id = getattr(msg, "message_id", "unknown")

        # Step 1: Check if user has credit (always, for both modes)
        try:
            result = await resource_monitor.check_credit(account, context)
        except Exception as exc:  # pragma: no cover - provider failure is rare
            if self._should_log_credit_event(f"provider_error:{account.cache_key()}"):
                logger.warning(
                    "Credit provider error for message %s: %s",
                    msg_id,
                    exc,
                )
            raise CreditCheckFailed(str(exc)) from exc

        if not result.has_credit:
            reason = result.reason or "Insufficient credits"
            cache_key = f"denied:{account.cache_key()}:{reason}"
            if self._should_log_credit_event(cache_key):
                logger.warning(
                    "Credit denied for message %s (channel %s): %s",
                    msg_id,
                    getattr(msg, "channel_id", "unknown"),
                    reason,
                )
            raise CreditDenied(reason)

        # Step 2: Charge credit - ONLY for transactional mode (hosted sites)
        # Android uses "informational" mode - billing happens via LLM usage instead
        if billing_mode == "informational":
            logger.info(
                "[CREDIT] Informational mode - skipping spend for message %s (account %s, credits=%s)",
                msg_id,
                account.cache_key(),
                result.credits_remaining,
            )
            return

        spend_request = CreditSpendRequest(
            amount_minor=1,
            currency="USD",
            description="Message interaction",
            metadata={
                "message_id": getattr(msg, "message_id", None),
                "channel_id": getattr(msg, "channel_id", None),
            },
        )

        try:
            spend_result = await resource_monitor.spend_credit(account, spend_request, context)
            if not spend_result.succeeded:
                logger.warning(
                    "Credit charge failed for message %s: %s",
                    msg_id,
                    spend_result.reason,
                )
                raise CreditCheckFailed(f"Credit charge failed: {spend_result.reason}")
            logger.info(
                "Credit charged successfully for message %s (account %s)",
                msg_id,
                account.cache_key(),
            )
        except CreditCheckFailed:
            # Re-raise CreditCheckFailed as-is
            raise
        except Exception as exc:  # pragma: no cover - provider failure is rare
            logger.error(
                "Credit charge error for message %s: %s",
                msg_id,
                exc,
            )
            raise CreditCheckFailed(str(exc)) from exc

    async def _enforce_credit_policy(self, msg: MessageT) -> None:
        """Ensure external credit policy allows processing of this message."""
        msg_id = getattr(msg, "message_id", "unknown")

        # Get resource monitor from instance or message metadata
        resource_monitor = self._get_resource_monitor(msg)

        # Determine source for logging
        monitor_source = self._get_resource_monitor_source(
            self.resource_monitor is not None, resource_monitor is not None
        )

        logger.debug(
            f"[CREDIT] Policy check for message {msg_id}: resource_monitor={resource_monitor is not None}, source={monitor_source}"
        )

        if not resource_monitor:
            logger.debug(f"[CREDIT] NO RESOURCE MONITOR for message {msg_id} - skipping credit enforcement")
            return

        credit_provider = getattr(resource_monitor, "credit_provider", None)
        logger.debug(
            f"[CREDIT] Provider status: {credit_provider is not None}, type={type(credit_provider).__name__ if credit_provider else 'None'}"
        )

        if not credit_provider:
            logger.debug("[CREDIT] No credit provider - skipping credit enforcement")
            return

        envelope = self._resolve_credit_envelope(msg)
        if envelope is None:
            # CRITICAL: Credit provider is active but no credit metadata attached to message
            channel_id = getattr(msg, "channel_id", "unknown")
            logger.critical(
                f"[CREDIT] ENFORCEMENT SKIPPED: No credit envelope for message {msg_id} in channel {channel_id}. "
                f"Credit provider IS active but message has no credit metadata attached!"
            )
            return

        account, context = envelope

        # Check if user role should bypass credit checks (ADMIN+)
        user_role = context.user_role
        if user_role in ["ADMIN", "AUTHORITY", "SYSTEM_ADMIN", "SERVICE_ACCOUNT"]:
            logger.info(f"[CREDIT] User role {user_role} bypasses credit check for message {msg_id}")
            return

        logger.debug(f"[CREDIT] Enforcement starting for account {account.cache_key()}, role={user_role}")

        await self._check_and_charge_credit(resource_monitor, account, context, msg)

    def _resolve_credit_envelope(self, msg: MessageT) -> Optional[Tuple[CreditAccount, CreditContext]]:
        """Extract credit account/context metadata from the message."""

        raw_account: Any = getattr(msg, "credit_account", None)
        raw_context: Any = getattr(msg, "credit_context", None)

        if raw_account is None:
            envelope = getattr(msg, "credit_envelope", None)
            if isinstance(envelope, dict):
                raw_account = envelope.get("account")
                raw_context = envelope.get("context")

        if raw_account is None:
            return None

        account = raw_account if isinstance(raw_account, CreditAccount) else CreditAccount(**raw_account)

        context: CreditContext
        if raw_context is None:
            context = CreditContext()
        elif isinstance(raw_context, CreditContext):
            context = raw_context
        else:
            context = CreditContext(**raw_context)

        return account, context

    def _should_log_credit_event(self, key: str, *, ttl_seconds: float = 60.0) -> bool:
        """Throttle credit-related log messages to avoid audit spam."""

        now = self._current_timestamp()
        last_logged = self._credit_log_cache.get(key)
        if last_logged is not None and now - last_logged < ttl_seconds:
            return False
        self._credit_log_cache[key] = now
        return True

    def _current_timestamp(self) -> float:
        if self.time_service:
            return self.time_service.now().timestamp()
        return time.time()

    async def _should_process_message(self, msg: MessageT) -> bool:
        """Check if this observer should process the message - to be overridden by subclasses."""
        return True  # Default: process all messages

    async def _get_user_consent_stream(self, user_id: str) -> Optional[str]:
        """
        Get user's consent stream for privacy handling.

        Returns consent stream or None if not found.
        """
        try:
            # Try to get consent from consent service if available
            if hasattr(self, "consent_service") and self.consent_service:
                try:
                    consent = await self.consent_service.get_consent(user_id)
                    return consent.stream.value if consent else None
                except Exception:
                    return None

            # Try to get from filter service if available
            if hasattr(self, "filter_service") and self.filter_service:
                if hasattr(self.filter_service, "_config") and self.filter_service._config:
                    if user_id in self.filter_service._config.user_profiles:
                        profile = self.filter_service._config.user_profiles[user_id]
                        consent_stream_value: str = profile.consent_stream
                        return consent_stream_value

            return None
        except Exception as e:
            logger.debug(f"Could not get consent stream for {user_id}: {e}")
            return None
