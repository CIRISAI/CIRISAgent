"""
LLM time budgets: how long each stage of one interaction may take, and how
many tries it gets (CIRISAgent#1186).

Written in the Envoy/Istio notation: a stage has a per-try timeout and an
attempt count, and the enclosing deadline must cover them —

    thought_budget_s   >= what the stages inside it may spend
    conscience_per_try >= llm_http_timeout   (inner never outlives outer)
    dma_per_try        >= llm_http_timeout

Two profiles, because the right answer differs by what serves the model:

* REMOTE (elastic capacity). Retries are independent draws, so more attempts
  buy reliability: 4 conscience attempts take the stage ceiling from 95.5% to
  99.95% on the measured 10.7% per-call timeout rate.
* LOCAL (one slot). Cancelling a request does not free the slot on common
  local servers (llama.cpp, llama-swap, Ollama < 0.33), so a retry queues
  behind the call it abandoned. One long try beats several short ones.

The values come from tools/analysis/interact_budget (7 five-platform runs,
633 LLM calls); change them there first and carry the result here.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProviderClass(str, Enum):
    """Where the model runs, as far as time budgets are concerned."""

    LOCAL = "local"
    REMOTE = "remote"


class LLMBudgetProfile(BaseModel):
    """Per-stage timeouts and attempt counts for one provider class."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_class: ProviderClass
    llm_http_timeout_s: float = Field(..., gt=0, description="One HTTP request to the model")
    dma_per_try_s: float = Field(..., gt=0, description="One attempt of one DMA")
    dma_attempts: int = Field(..., ge=1, le=5, description="DMA attempts every thought gets")
    dma_attempt_cap: int = Field(
        ...,
        ge=1,
        le=5,
        description="Most DMA attempts a thought may spend while its deadline still affords one (>= dma_attempts)",
    )
    conscience_per_try_s: float = Field(..., gt=0, description="One attempt of one conscience shard")
    conscience_attempts: int = Field(..., ge=1, le=5)
    thought_budget_s: float = Field(
        ..., gt=0, description="Everything one thought may spend, DMAs through conscience; stages get the remainder"
    )
    interact_deadline_s: float = Field(..., gt=0, description="How long /v1/agent/interact waits for the reply")

    @model_validator(mode="after")
    def _nesting_holds(self) -> "LLMBudgetProfile":
        if self.llm_http_timeout_s > self.conscience_per_try_s:
            raise ValueError(
                f"llm_http_timeout_s ({self.llm_http_timeout_s}) exceeds conscience_per_try_s "
                f"({self.conscience_per_try_s}): the HTTP client could never report its own timeout"
            )
        if self.llm_http_timeout_s > self.dma_per_try_s:
            raise ValueError(
                f"llm_http_timeout_s ({self.llm_http_timeout_s}) exceeds dma_per_try_s ({self.dma_per_try_s})"
            )
        if self.dma_attempt_cap < self.dma_attempts:
            raise ValueError(f"dma_attempt_cap ({self.dma_attempt_cap}) is below dma_attempts ({self.dma_attempts})")
        if self.thought_budget_s > self.interact_deadline_s:
            raise ValueError(
                f"thought_budget_s ({self.thought_budget_s}) exceeds interact_deadline_s "
                f"({self.interact_deadline_s}): the reply would arrive after the caller stopped waiting"
            )
        return self


#: Measured: at 45s x 4 conscience attempts, 99% of interacts reply inside
#: ~193s (p50 85s, p90 135s). Today's 45s x 2 inside 110s replies to 72%.
REMOTE_PROFILE = LLMBudgetProfile(
    provider_class=ProviderClass.REMOTE,
    llm_http_timeout_s=45.0,
    dma_per_try_s=90.0,
    dma_attempts=2,
    dma_attempt_cap=3,
    conscience_per_try_s=45.0,
    conscience_attempts=4,
    thought_budget_s=190.0,
    interact_deadline_s=195.0,
)

#: Modelled, not yet measured on hardware (#1186 part 6): the shape — one
#: long try — holds at every speed tested; the seconds assume a slow edge box.
LOCAL_PROFILE = LLMBudgetProfile(
    provider_class=ProviderClass.LOCAL,
    llm_http_timeout_s=240.0,
    dma_per_try_s=300.0,
    dma_attempts=1,
    dma_attempt_cap=1,  # one slot: a retry queues behind the call it abandoned
    conscience_per_try_s=240.0,
    conscience_attempts=1,
    thought_budget_s=890.0,
    interact_deadline_s=900.0,
)

#: A hosted API that is reachable but slow to answer: DeepInfra's
#: Qwen3.6-35B-A3B measured 16-68s per structured call (2026-10-15), so the
#: REMOTE 45s HTTP timeout cut off honest answers, and three parallel DMA
#: timeouts on one slow thought tripped the breaker. Same shape as REMOTE
#: (elastic capacity, retries are independent draws), longer tries. Applied
#: by host (`SLOW_HOST_MARKERS` in logic/config/llm_budget.py), never by class.
SLOW_REMOTE_PROFILE = LLMBudgetProfile(
    provider_class=ProviderClass.REMOTE,
    llm_http_timeout_s=90.0,
    dma_per_try_s=120.0,
    dma_attempts=2,
    dma_attempt_cap=3,
    conscience_per_try_s=90.0,
    conscience_attempts=2,
    thought_budget_s=290.0,
    interact_deadline_s=295.0,
)

PROFILES = {ProviderClass.REMOTE: REMOTE_PROFILE, ProviderClass.LOCAL: LOCAL_PROFILE}
