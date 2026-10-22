"""The prompts a DMA call actually sent, carried by the object that call returned.

Prompts used to live on the evaluator (``self.last_user_prompt`` /
``self.last_system_prompt``) and were read back from it after the call. One
evaluator instance serves every thought, and the read came after an ``await``
on the model, so a concurrent thought could overwrite them in between: RATCHET
run 39853438022 found a follow-up thought's DMA_RESULTS carrying the CSDMA,
DSDMA and PDMA prompts of a different task.

Here the record is derived from the exact ``messages`` list of one call and
attached to the object that call produced (``BaseDMA.call_llm_structured``), or
carried explicitly from that object to one built from it. It is a pydantic
private attribute, so it never enters the JSON schema a model is asked to fill,
and it survives ``model_copy``. Where nothing attached one, there is none: a
trace may lack a prompt, but it cannot carry another conversation's.
"""

from typing import Any, List, Optional, Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr


T = TypeVar("T")


class SentPrompts(BaseModel):
    """The system and user text of one LLM call, as sent."""

    system: Optional[str] = Field(None, description="Every system message of the call, joined")
    user: Optional[str] = Field(None, description="The text of the call's last user message")

    model_config = ConfigDict(extra="forbid", frozen=True)


class PromptCarrier(BaseModel):
    """Base for results that carry the prompts of the call that produced them."""

    _sent_prompts: Optional[SentPrompts] = PrivateAttr(default=None)


def _text_of(content: Any) -> str:
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts)
    return "" if content is None else str(content)


def sent_prompts_from_messages(messages: Sequence[Any]) -> SentPrompts:
    """The record of one call, from the messages list it sent."""
    system = [_text_of(m.get("content")) for m in messages if isinstance(m, dict) and m.get("role") == "system"]
    users = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    return SentPrompts(
        system="\n\n".join(system) if system else None,
        user=_text_of(users[-1].get("content")) if users else None,
    )


def attach_sent_prompts(result: T, prompts: Optional[SentPrompts]) -> T:
    """Attach ``prompts`` to ``result`` if it can carry them; returns ``result``."""
    if prompts is not None and isinstance(result, PromptCarrier):
        result._sent_prompts = prompts
    return result


def sent_prompts_of(obj: Any) -> Optional[SentPrompts]:
    """The prompts the call that produced ``obj`` sent, or None."""
    return obj._sent_prompts if isinstance(obj, PromptCarrier) else None


def carry_sent_prompts(source: Any, target: T) -> T:
    """Move the record from the object a call returned to one built from it."""
    return attach_sent_prompts(target, sent_prompts_of(source))
