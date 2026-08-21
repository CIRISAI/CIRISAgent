"""Matrix dimensions as DATA.

Nothing in this file executes a probe. It declares what the axes are; the
executor in ``matrix.py`` expands the product of these declarations into
``MatrixCell`` objects. Adding a provider, a failure injection, or a new
option quirk to hunt is an edit here and nowhere else.

Provenance of the constants
---------------------------
Model ids, endpoints and per-provider gotchas come from ``CLAUDE.md``'s live
model matrix, which is the repo's source of truth for exact case-sensitive
identifiers. Where this file names a model expected to fail, the comment says
why it is expected to fail — a cell whose expectation stops matching reality
is itself a finding (the provider changed), not a bug in the harness.

The catalogue axis is NOT hardcoded: models tagged ``ModelSelector.CATALOGUE``
are read at runtime from ``ciris_engine/config/MODEL_CAPABILITIES.json`` via
``get_model_capabilities()``, so the sweep always covers exactly what the
wizard offers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .schemas import CredentialMode, ExpectedCause, ModelSelector, ProbeKind

# ─────────────────────────────────────────────────────────────────────────────
# Provider declarations
# ─────────────────────────────────────────────────────────────────────────────


class ProviderSpec(BaseModel):
    """Everything the matrix needs to know about one provider.

    ``base_url`` deliberately mirrors what the PRODUCT resolves, not what the
    provider documents — the whole point is to exercise the code path a user
    hits. Where the product hardcodes a URL inside a provider-specific
    validator (Google), that hardcoded value is what appears here, and the
    documented/advertised one appears in ``advertised_base_url`` so the two can
    be probed against each other.
    """

    provider_id: str = Field(..., description="Provider id as the wizard names it")
    display_name: str = Field(..., description="Human-readable name")
    key_file: str = Field(..., description="Path holding the raw token — never read into the report")
    sdk: str = Field(..., description="'openai' (OpenAI-compatible) or 'anthropic' (native SDK)")
    base_url: Optional[str] = Field(None, description="Base URL the product probes; None = SDK default")
    advertised_base_url: Optional[str] = Field(
        None, description="Base URL the wizard advertises to the client, when it differs from the probed one"
    )

    cheap_model: str = Field(..., description="Smallest/cheapest model — used where the test is model-independent")
    nonexistent_model: str = Field(..., description="A model id that cannot exist at this provider")
    wrong_case_model: Optional[str] = Field(
        None, description="A real model id with its case mangled — Together's canonical footgun"
    )
    gated_model: Optional[str] = Field(
        None, description="Exists in the provider's catalogue; this account is not entitled to it"
    )
    policy_blocked_model: Optional[str] = Field(
        None, description="Reachable only via endpoints that fail a data-policy guardrail"
    )
    # Dict[str, Any] is correct here and not a shortcut: this is a passthrough
    # of a FOREIGN api's request-body extension (OpenRouter's `provider` block),
    # whose shape OpenRouter owns and changes. Modelling it would be modelling
    # someone else's schema.
    policy_blocked_extra_body: Optional[Dict[str, Any]] = Field(
        None, description="Request-body knob that forces the routing/data-policy filter (OpenRouter)"
    )

    max_tokens_cap: Optional[int] = Field(None, description="Documented hard cap on max_tokens; None = no known cap")
    invalid_key: str = Field(..., description="Well-formed-looking but never-issued key, for the INVALID injection")
    supports_models_list: bool = Field(default=True, description="Whether a live /models listing exists")
    notes: str = Field(default="", description="Free-form provenance / gotcha note")

    model_config = ConfigDict(extra="forbid")


# The six providers in MODEL_CAPABILITIES.json. `deepinfra`, `local`, `other`
# and `mobile_local` are offered by the wizard's provider list but carry no
# catalogue entry — see analysis.static_table_audit(), which reports that
# divergence rather than silently sweeping them.
PROVIDERS: Dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        provider_id="openai",
        display_name="OpenAI",
        key_file="~/.openai_key",
        sdk="openai",
        base_url=None,  # product leaves the SDK default (api.openai.com/v1)
        cheap_model="gpt-4o-mini",
        # Deliberately absurd; no namespace collision with a real id.
        nonexistent_model="gpt-4o-mini-ciris-qa-does-not-exist",
        wrong_case_model="GPT-4O-MINI",
        # OBSERVED 2026-08-21: o1-pro answers 404 "This model is only
        # supported in v1/responses and not in v1/chat/completions" — not an
        # entitlement wall but an endpoint-family wall, which for a user is the
        # same experience: the model is real, they cannot have it here, and the
        # 404 is indistinguishable from a typo'd name.
        gated_model="o1-pro",
        invalid_key="sk-proj-cirisqa0000000000000000000000000000000000000000",
        notes="Reasoning models reject max_tokens and demand max_completion_tokens; the wizard retries on that.",
    ),
    "anthropic": ProviderSpec(
        provider_id="anthropic",
        display_name="Anthropic",
        key_file="~/.anthropic_key",
        sdk="anthropic",
        base_url="https://api.anthropic.com/v1",
        cheap_model="claude-haiku-4-5-20251001",
        nonexistent_model="claude-haiku-4-5-ciris-qa-does-not-exist",
        wrong_case_model="Claude-Haiku-4-5-20251001",
        gated_model=None,  # no reliably-gated public model; catalogue sweep covers the rest
        invalid_key="sk-ant-api03-cirisqa000000000000000000000000000000000000000000000000000000000000000000000000AA",
        notes="Native SDK. Its 404 body says type=not_found_error, which is the ONLY phrasing the "
        "product's model-not-found branch matches — hence the branch works here and nowhere else.",
    ),
    "openrouter": ProviderSpec(
        provider_id="openrouter",
        display_name="OpenRouter",
        key_file="~/.openrouter_key",
        sdk="openai",
        base_url="https://openrouter.ai/api/v1",
        cheap_model="meta-llama/llama-3.3-70b-instruct",
        nonexistent_model="meta-llama/llama-3.3-70b-instruct-ciris-qa-does-not-exist",
        wrong_case_model="Meta-Llama/Llama-3.3-70B-Instruct",
        # No GATED cell: OpenRouter aggregates, so account-level model
        # entitlement walls are rare (o1-pro, the obvious candidate, answered
        # 200 here on 2026-08-21). The equivalent failure at this provider is
        # the routing-restriction 404 below, which is also the one that hurt a
        # real user.
        gated_model=None,
        # The incident, reproduced deterministically. A routing restriction no
        # endpoint can satisfy returns 404 "No allowed providers are available
        # for the selected model…". That is the same 404 family as the report
        # that motivated this module ("No endpoints available matching your
        # guardrail restrictions and data policy" — the Zero-Data-Retention
        # member of the family), and unlike the ZDR variant it does not depend
        # on the account's privacy settings being in a particular state.
        policy_blocked_model="meta-llama/llama-3.3-70b-instruct",
        policy_blocked_extra_body={"provider": {"only": ["Azure"]}},
        invalid_key="sk-or-v1-cirisqa0000000000000000000000000000000000000000000000000000000000",
        notes="404 with 'No endpoints available matching your guardrail restrictions and data policy' is a "
        "PRIVACY-SETTINGS error, not a network error. This is the incident that motivated the matrix.",
    ),
    "together": ProviderSpec(
        provider_id="together",
        display_name="Together AI",
        key_file="~/.together_key",
        sdk="openai",
        base_url="https://api.together.xyz/v1",
        cheap_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
        nonexistent_model="meta-llama/Llama-3.3-70B-Instruct-Turbo-ciris-qa-does-not-exist",
        # CLAUDE.md: capital B / lowercase it matters; Together lists both
        # 'google/gemma-4-31B-it' and lookalikes under other namespaces.
        wrong_case_model="meta-llama/llama-3.3-70b-instruct-turbo",
        # CLAUDE.md: every Llama-4 variant on Together needs a paid dedicated
        # endpoint — it is in the catalogue and still unusable serverless.
        gated_model="meta-llama/Llama-4-Scout-17B-16E-Instruct",
        invalid_key="cirisqa0000000000000000000000000000000000000000000000000000000000",
        notes="Cloudflare-fronted: requests with no User-Agent get 403 'error code: 1010', "
        "indistinguishable from a real permission denial. See modules/mobile/llm_preflight.py.",
    ),
    "groq": ProviderSpec(
        provider_id="groq",
        display_name="Groq",
        key_file="~/.groq_key",
        sdk="openai",
        base_url="https://api.groq.com/openai/v1",
        cheap_model="llama-3.3-70b-versatile",
        nonexistent_model="llama-3.3-70b-versatile-ciris-qa-does-not-exist",
        wrong_case_model="Llama-3.3-70B-Versatile",
        gated_model=None,
        # CLAUDE.md: 8192 max_tokens ceiling; exceeding it was the 2.7.4 incident.
        max_tokens_cap=8192,
        invalid_key="gsk_cirisqa000000000000000000000000000000000000000000000",
        notes="Hard 8192 max_tokens cap. Key rotation has 401'd this provider before — a 401 here is as "
        "likely to be a stale ~/.groq_key as a product defect.",
    ),
    "google": ProviderSpec(
        provider_id="google",
        display_name="Google AI",
        key_file="~/.google_key",
        sdk="openai",
        # What _validate_google_connection HARDCODES:
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        # What _get_llm_providers ADVERTISES as default_base_url. The two are
        # not the same endpoint; CHAT_ALT_BASE_URL probes the advertised one.
        advertised_base_url="https://generativelanguage.googleapis.com/v1beta",
        # NOT gemini-2.0-flash: decommissioned. Asking for it returns 404
        # "This model models/gemini-2.0-flash is no longer available" — which
        # is what the wizard's own fabricated default still sends.
        cheap_model="gemini-3.6-flash",
        nonexistent_model="gemini-3.6-flash-ciris-qa-does-not-exist",
        wrong_case_model="Gemini-3.6-Flash",
        gated_model=None,
        invalid_key="AIzaSyCirisQa0000000000000000000000000000",
        notes="Validated through the OpenAI-compatibility shim; listed through the google-genai SDK. "
        "Two different endpoints for one provider id.",
    ),
}

DEFAULT_PROVIDERS: List[str] = list(PROVIDERS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Injection declarations
# ─────────────────────────────────────────────────────────────────────────────


class InjectionSpec(BaseModel):
    """One failure injection: a (credential, model) pair plus its ground truth."""

    credential: CredentialMode
    model_selector: ModelSelector
    expected_cause: ExpectedCause
    rationale: str = Field(..., description="The quirk this injection hunts")
    requires: Optional[str] = Field(
        None,
        description="ProviderSpec field that must be non-None for this injection to apply "
        "(e.g. 'gated_model'); None means it applies to every provider",
    )

    model_config = ConfigDict(extra="forbid")


# The core sweep. Every provider gets every applicable injection.
CORE_INJECTIONS: List[InjectionSpec] = [
    InjectionSpec(
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.CHEAP,
        expected_cause=ExpectedCause.SUCCESS,
        rationale="Baseline: the happy path must work, or nothing else in this provider's column means anything.",
    ),
    InjectionSpec(
        credential=CredentialMode.INVALID,
        model_selector=ModelSelector.CHEAP,
        expected_cause=ExpectedCause.AUTH,
        rationale="Does the provider return 401 (classifiable) or 403/404 (which our classifier misreads)?",
    ),
    InjectionSpec(
        credential=CredentialMode.ABSENT,
        model_selector=ModelSelector.CHEAP,
        expected_cause=ExpectedCause.AUTH,
        rationale="Blank key field. The product should refuse before the network, not after.",
    ),
    InjectionSpec(
        credential=CredentialMode.MALFORMED,
        model_selector=ModelSelector.CHEAP,
        # Exploratory: any of three outcomes is defensible (the SDK strips the
        # newline and succeeds; the provider 401s; or the HTTP layer refuses to
        # build the header at all). So this cell is not graded for a cause gap
        # — it is here for the credential-leak and unclassified-error checks,
        # because a local header-construction error renders the WHOLE Bearer
        # value into str(exception), which the product then logs.
        expected_cause=ExpectedCause.UNKNOWN,
        rationale="Real key pasted with a trailing newline — the single most common credential paste bug. "
        "Hunts a key-in-exception-text leak, since the product logs str(e) verbatim.",
    ),
    InjectionSpec(
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.NONEXISTENT,
        expected_cause=ExpectedCause.MODEL_NOT_FOUND,
        rationale="The single most common user error — a typo'd model name. Is the message about the MODEL?",
    ),
    InjectionSpec(
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.WRONG_CASE,
        expected_cause=ExpectedCause.MODEL_NOT_FOUND,
        rationale="Case-sensitivity footgun. Same expectation as NONEXISTENT, but the user believes the "
        "name is right, so a message about the network is doubly misleading.",
    ),
    InjectionSpec(
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.OMITTED,
        expected_cause=ExpectedCause.MODEL_NOT_FOUND,
        rationale="No model chosen. The wizard fabricates 'gpt-3.5-turbo' and sends it to whatever provider "
        "is selected — this is precisely how Francesco hit OpenRouter with an OpenAI model name.",
    ),
    InjectionSpec(
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.GATED,
        expected_cause=ExpectedCause.MODEL_ACCESS_DENIED,
        rationale="Model exists, account is not entitled. Does the user learn that, or 'check your URL'?",
        requires="gated_model",
    ),
    InjectionSpec(
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.POLICY_BLOCKED,
        expected_cause=ExpectedCause.POLICY_BLOCKED,
        rationale="The Francesco cell. A data-policy guardrail rejects every endpoint for the model. The "
        "remedy is a privacy setting; the product currently says 'check your configuration'.",
        requires="policy_blocked_model",
    ),
]


# Option probes. Off by default — they burn generation tokens and their value
# is comparative (the finding is that provider A rejects what B accepts).
OPTION_PROBES: List[ProbeKind] = [
    ProbeKind.CHAT_MAX_TOKENS_OVER_CAP,
    ProbeKind.CHAT_ALT_BASE_URL,
]

# The minimal prompt every chat probe sends. Kept to a couple of tokens.
PROBE_PROMPT = "Hi"
PROBE_MAX_TOKENS = 1

# Over-cap probe. 16384 is above Groq's documented 8192 ceiling and below the
# limits of the other providers, so a rejection here isolates the cap. The
# prompt asks for a one-word answer so an ACCEPTING provider still generates
# ~2 tokens rather than 16k of text.
OVER_CAP_PROMPT = "Reply with the single word OK."
OVER_CAP_MAX_TOKENS = 16384

# Cost guard. A run is refused before making any call if the expansion exceeds
# this; raise it explicitly with --max-live-calls when sweeping the catalogue.
DEFAULT_MAX_LIVE_CALLS = 150


__all__ = [
    "CORE_INJECTIONS",
    "DEFAULT_MAX_LIVE_CALLS",
    "DEFAULT_PROVIDERS",
    "InjectionSpec",
    "OPTION_PROBES",
    "OVER_CAP_MAX_TOKENS",
    "OVER_CAP_PROMPT",
    "PROBE_MAX_TOKENS",
    "PROBE_PROMPT",
    "PROVIDERS",
    "ProviderSpec",
]
