"""Ask a provider what models it serves — one implementation, every caller.

Two separate bugs made this worth extracting rather than fixing twice.

**The envelope.** The OpenAI SDK's ``models.list()`` assumes ``{"data": [...]}``.
Together answers with a BARE JSON ARRAY, so the SDK's own parse raises
``'list' object has no attribute '_set_private_attributes'`` — on a valid key
holding 279 models. The setup wizard read that as a failed listing and silently
showed a cached catalogue; the conformance harness read it as a dead credential.
Same provider quirk, two different wrong conclusions, because each had its own
copy of the call.

**The model.** Asking "does this key work?" through a *completion* forces the
caller to name a model, which quietly turns an authentication question into an
availability one. When Groq retired the model the harness probed with, a live
key reported 404 and its entire column was skipped. ``/models`` needs no model,
so a decommissioned model can no longer make a working credential look dead.

Both callers now share this, which is the point: a provider quirk should be
learned once.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = ["list_model_ids", "SDK_OPENAI", "SDK_ANTHROPIC", "SDK_GOOGLE"]

SDK_OPENAI = "openai"
SDK_ANTHROPIC = "anthropic"
SDK_GOOGLE = "google"


def _ids_from(entries: Any) -> List[str]:
    """Pull ids out of whatever shape the provider returned."""
    out: List[str] = []
    for entry in entries or []:
        model_id = getattr(entry, "id", None)
        if model_id is None and isinstance(entry, dict):
            model_id = entry.get("id") or entry.get("name")
        if model_id is None:
            model_id = getattr(entry, "name", None)
        if model_id:
            out.append(str(model_id))
    return out


async def _list_openai_compatible(api_key: str, base_url: Optional[str], timeout: float) -> List[str]:
    from openai import AsyncOpenAI

    kwargs: Dict[str, Any] = {"api_key": api_key or "local", "timeout": timeout, "max_retries": 0}
    if base_url:
        kwargs["base_url"] = base_url
    client = AsyncOpenAI(**kwargs)

    try:
        page = await client.models.list()
        return _ids_from(page.data)
    except AttributeError:
        # A non-standard envelope — a bare array rather than {"data": [...]}.
        # Read the raw body instead of concluding the endpoint is broken.
        logger.info("[MODEL_LISTING] %s returned a non-standard /models envelope; reading the raw body", base_url)
        raw = await client.get("/models", cast_to=object)
        payload = raw.get("data") if isinstance(raw, dict) else raw
        return _ids_from(payload if isinstance(payload, list) else [])


async def _list_anthropic(api_key: str, timeout: float) -> List[str]:
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=0)
    page = await client.models.list(limit=100)
    return _ids_from(page.data)


async def _list_google(api_key: str) -> List[str]:
    from google import genai

    client = genai.Client(api_key=api_key)
    # AsyncModels.list() returns a COROUTINE resolving to the pager; it is not
    # itself an async iterable. Awaiting it is the difference between a working
    # listing and "'async for' requires an object with __aiter__".
    pager = await client.aio.models.list(config={"query_base": True})
    out: List[str] = []
    async for model in pager:
        name = getattr(model, "name", None) or getattr(model, "id", None)
        if name:
            out.append(str(name))
    return out


async def list_model_ids(
    sdk: str,
    api_key: str,
    base_url: Optional[str] = None,
    timeout: float = 30.0,
) -> List[str]:
    """Model ids this credential can see. Raises on failure — callers decide what that means.

    Deliberately raises rather than returning ``[]``: "the provider said no" and
    "the provider serves nothing" are different facts, and collapsing them is
    how a failed listing came to be presented as a catalogue.
    """
    if sdk == SDK_ANTHROPIC:
        return await _list_anthropic(api_key, timeout)
    if sdk == SDK_GOOGLE:
        return await _list_google(api_key)
    return await _list_openai_compatible(api_key, base_url, timeout)
