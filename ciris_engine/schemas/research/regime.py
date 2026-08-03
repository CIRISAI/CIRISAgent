"""The experimental-regime manifest v2 (#976, FSD/RESEARCH_PROMPT_OVERRIDES.md §10.3).

``schema: ciris.ai/experimental_regime/v2``.

This is the DECLARATION only — shape, defaults and the parsing of the two
notations the FSD's example uses (a contrast written ``arm-a - arm-b``, an arm
list written ``all``). Every §10.4 refusal lives in
``ciris_engine.logic.utils.regime_manifest``, because each one needs the source
tree (the residue inventory, the transmitted decoding keys, the block
annotation table, the kill-instrument tables) and a schema module must not
reach for any of that.

Reuse, not re-declaration: ``RegimeArm``, ``RegimeBlockEntry``, ``RegimePins``,
``BlockClass`` and ``BlockDisposition`` are the #973 schemas in
``ciris_engine.schemas.dma.compose``. ``ExperimentalRegimeV2.gate_view()``
projects down to the Phase-1 ``GateRegime`` the compose gate already consumes,
so there is exactly one gate input shape and v2 is a strict superset of it.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ciris_engine.schemas.dma.compose import BlockClass, GateRegime, RegimeArm, RegimeBlockEntry, RegimePins
from ciris_engine.schemas.types import JSONDict

#: The only schema string this loader answers to. The Phase-1 self-check
#: regimes carry ``…/v2-phase1`` and are loaded as bare ``GateRegime`` —
#: deliberately a different string, so a Phase-1 file can never be mistaken
#: for a campaign manifest that simply omitted its power statement.
REGIME_SCHEMA_V2 = "ciris.ai/experimental_regime/v2"

#: Registered class-set versions (§10.2.2). A split creates a new version and
#: results are reported under the version they were gathered at; an unknown
#: version is refused (§10.4). v1 is NOT here: it was never staked (§10 preamble).
KNOWN_CLASS_SET_VERSIONS: frozenset[int] = frozenset({2})

#: ``arms: all`` in a DV tier — the FSD's own notation for "every declared arm".
ARMS_ALL = "all"


class VarianceSource(str, Enum):
    """Where the variance in a repeat structure comes from [M-N1].

    ``NONE`` exists so a manifest can *say* it has no variance source, which is
    refused with n>1 rather than being unrepresentable — an unrepresentable
    state is a state nobody has to justify.
    """

    TEMPERATURE = "temperature"
    SEEDS = "seeds"
    NONE = "none"


class RegimeContrast(BaseModel):
    """One named contrast, naming its two arms [M-1].

    Accepts the FSD's ``minuend - subtrahend`` string as well as the explicit
    mapping form. Every claim must name its contrast, and a contrast must name
    exactly two arms — ``bare - h3ere-alt`` is confounded on both factors and
    may not carry a claim, which is a review fact, not a parse fact.
    """

    model_config = ConfigDict(extra="forbid")

    minuend: str = Field(..., description="Arm on the left of the difference")
    subtrahend: str = Field(..., description="Arm on the right of the difference")

    @model_validator(mode="before")
    @classmethod
    def _accept_expression(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        # Arm names contain hyphens (``h3ere-ciris``), so split on the
        # SPACED minus only — ``h3ere-ciris - values-ciris`` is two arms.
        parts = [p.strip() for p in value.split(" - ")]
        if len(parts) != 2 or not all(parts):
            raise ValueError(
                f"contrast {value!r} must name exactly two arms as '<arm> - <arm>' "
                f"(spaces around the minus; arm names may contain hyphens)"
            )
        return {"minuend": parts[0], "subtrahend": parts[1]}


class RegimeDVTier(BaseModel):
    """One DV tier: what it measures, and the arms it is claimed over [M-2].

    ``arms: all`` is kept verbatim rather than expanded at parse time — the
    expansion needs the arm table, and a tier that says ``all`` while an arm
    lacks the DV must be able to say so in its own words.
    """

    model_config = ConfigDict(extra="forbid")

    measures: List[str] = Field(..., min_length=1)
    arms: List[str] = Field(default_factory=lambda: [ARMS_ALL])

    @model_validator(mode="before")
    @classmethod
    def _accept_all(cls, value: object) -> object:
        if isinstance(value, dict) and value.get("arms") == ARMS_ALL:
            return {**value, "arms": [ARMS_ALL]}
        return value

    def is_all_arms(self) -> bool:
        return self.arms == [ARMS_ALL]


class RegimeDV(BaseModel):
    """The tiered DV (§10.3) — the DV must exist in the arms it is claimed over.

    ``text_tier_rows`` is the PRE-REGISTERED per-locale U-row subset [M-N5]:
    U-codes are per-language rubric rows, not one construct [T-N3], so the
    corrected family is (locale x row x contrast) and the subset has to be
    named before the run, not chosen after it.
    """

    model_config = ConfigDict(extra="forbid")

    action_tier: Optional[RegimeDVTier] = Field(
        default=None,
        description="Handler-verb measures; h3ere arms ONLY (a direct-provider call has no handler enum)",
    )
    text_tier: Optional[RegimeDVTier] = Field(default=None, description="Scored text measures; any arm")
    text_tier_rows: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="locale -> pre-registered U-row subset (e.g. {'am': ['U10']})",
    )


class RegimeRepeats(BaseModel):
    """The repeat structure [M-7, M-N1].

    ``unit: conversation`` because the battery threads ONE channel_id through
    the arc — the conversation is the independent unit and n is conversations,
    not questions.
    """

    model_config = ConfigDict(extra="forbid")

    unit: str = Field(default="conversation")
    conversations_per_cell: int = Field(..., ge=1)
    variance_source: VarianceSource = Field(
        ...,
        description="MUST be live at the declared holds: temperature>0, or enumerated seeds with seed transmitted",
    )
    seeds: List[int] = Field(default_factory=list)
    comparison_policy: str = Field(default="holm-bonferroni")
    mde: Dict[str, float] = Field(
        default_factory=dict,
        description="contrast name -> minimum detectable effect; required for every MAIN contrast",
    )


class RegimeDecoding(BaseModel):
    """The pinned decoding parameters.

    ENFORCED-OR-REFUSED with SET-EQUALITY semantics [M-6, M-N3]: the loader
    compares this pin set against what the call path actually transmits at the
    declared endpoint, in BOTH directions. Every field is Optional so "not
    pinned" is representable and distinguishable from "pinned to the default".
    """

    model_config = ConfigDict(extra="forbid")

    temperature: Optional[float] = None
    top_p: Optional[float] = None
    max_tokens: Optional[int] = None
    seed: Optional[int] = None
    extra_body: Optional[JSONDict] = Field(
        default=None,
        description="A FUNCTION of base_url (service.py _build_reasoning_off_extras), not a free choice",
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Optional here; §10.3 pins it one level up on holds. Both are read; a disagreement refuses.",
    )


class RegimeHolds(BaseModel):
    """Everything held constant across arms (§10.3).

    ``locales`` must include ``en`` [M-N2]: in low-resource locales a values
    effect cannot be separated from alt-corpus translation quality, and en is
    where corpus fidelity is natively checkable.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = Field(...)
    decoding: RegimeDecoding = Field(default_factory=RegimeDecoding)
    base_url: Optional[str] = None
    corpus: str = Field(...)
    locales: List[str] = Field(..., min_length=1)
    adapter_set: List[str] = Field(default_factory=lambda: ["api"])

    def resolved_base_url(self) -> Optional[str]:
        """The endpoint the pin set is a function of; None if unpinned."""
        return self.decoding.base_url or self.base_url


class KillDeclaration(BaseModel):
    """A kill is an equivalence claim and is priced as one [T-4].

    Operable only with (i) a named instrument that exists in EVERY declared
    locale and (ii) a declared MDE and equivalence bound. Missing either makes
    the kill decoration and reverts the class to ``hold`` — which the loader
    refuses if the manifest is varying that class anyway.
    """

    model_config = ConfigDict(extra="forbid")

    instrument: str = Field(..., description="U-row identifier, e.g. 'U10' or 'U10_slur_echo'")
    mde: Optional[float] = Field(default=None, gt=0)
    equivalence_bound: Optional[float] = Field(default=None, gt=0)

    def is_operable(self) -> bool:
        return self.mde is not None and self.equivalence_bound is not None


class RegimeGate(BaseModel):
    """Which gate stages the regime requires (§10.3 ``gate:``)."""

    model_config = ConfigDict(extra="forbid")

    compose_dump: str = Field(default="required")
    block_diff: str = Field(default="required")
    residue_scan: str = Field(default="required")
    onwire_verify: str = Field(default="required")
    on_incomplete_ablation: str = Field(default="refuse")


class RegimePinsV2(RegimePins):
    """§10.3 pins. ``residue_digest`` is inherited and is the only one the
    Phase-1 gate asserts today; the rest are recorded for ``regime:manifest:v1``.
    """

    model_config = ConfigDict(extra="ignore")

    accord_sha256: Optional[str] = None
    template_sha256: Optional[str] = None
    substrate: Optional[str] = None
    harness: Dict[str, str] = Field(default_factory=dict)


class ExperimentalRegimeV2(BaseModel):
    """``ciris.ai/experimental_regime/v2`` — the full §10.3 declaration."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    regime_schema: str = Field(..., alias="schema", description=f"Must be {REGIME_SCHEMA_V2!r}")
    regime_id: str = Field(..., min_length=1)
    class_set_version: int = Field(..., description="Pinned class-set version; unknown versions refuse (§10.2.2)")
    hypothesis: str = Field(..., min_length=1)
    arms: Dict[str, RegimeArm] = Field(..., min_length=1)
    contrasts: Dict[str, RegimeContrast] = Field(default_factory=dict)
    dv: RegimeDV = Field(default_factory=RegimeDV)
    repeats: RegimeRepeats = Field(...)
    holds: RegimeHolds = Field(...)
    pins: RegimePinsV2 = Field(...)
    blocks: Dict[str, RegimeBlockEntry] = Field(default_factory=dict)
    kills: Dict[BlockClass, KillDeclaration] = Field(
        default_factory=dict,
        description="Per-class kill declarations (§10.2). A varied class without an operable kill refuses.",
    )
    confound_accepted: List[str] = Field(
        default_factory=list,
        description=(
            "Regime-level confound acknowledgements in the v1 vocabulary — the "
            "`register` token §10.4 names for pragmatic-with-axiotic. Per-BLOCK "
            "acknowledgements live on the block entry and are typed as classes."
        ),
    )
    mode: str = Field(
        default="strict",
        description="'strict' (R2 totality: every reachable field resolves to exactly one class) or 'additive'",
    )
    gate: RegimeGate = Field(default_factory=RegimeGate)

    def h3ere_arms(self) -> Dict[str, RegimeArm]:
        return {name: arm for name, arm in self.arms.items() if arm.harness == "h3ere"}

    def varied_classes(self) -> frozenset[BlockClass]:
        """Classes any arm varies (replace or disable) — same rule as GateRegime."""
        varied: set[BlockClass] = set()
        for arm in self.arms.values():
            for name in list(arm.replace) + list(arm.disable):
                varied.add(BlockClass(name))
        return frozenset(varied)

    def gate_view(self) -> GateRegime:
        """Project to the Phase-1 gate input, so v2 and the #973 gate share one shape."""
        return GateRegime(
            regime_id=self.regime_id,
            arms=dict(self.arms),
            blocks=dict(self.blocks),
            pins=RegimePins(residue_digest=self.pins.residue_digest),
        )
