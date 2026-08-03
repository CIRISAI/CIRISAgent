"""Composed-block schema for the ablation gate (#973, FSD/RESEARCH_PROMPT_OVERRIDES.md §12 Phase 1).

One :class:`ComposedBlock` row per discrete block in a composed DMA message
list, as emitted by ``python3 -m ciris_engine.logic.utils.compose_dump``.

Block identity is honest by construction (FSD §14 step 3): only the
already-block-structured surface — the discrete system messages appended by
``append_round1_accord_blocks`` and the per-seam accord / language-guidance
appends — gets a routed ``source``. Text inside a single composed message that
mixes routed and inline content is ONE block with ``block_class="mixed"`` and
``source="inline"``; the dump never pretends to finer granularity than the
composition code has. Granularity improves as #974 routes the residue.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BlockClass(str, Enum):
    """The eleven §10.2 classes, plus ``mixed`` (§10.2.1).

    The definitional criterion for every class is its operational test — see
    the FSD §10.2 table. ``mixed`` is not a twelfth class: it marks a block the
    routing cannot yet split, and per §10.2.1 it MUST carry a populated
    contaminant list and defaults to refusal at the gate.
    """

    AXIOTIC = "axiotic"
    DEONTIC = "deontic"
    PRAGMATIC = "pragmatic"
    ONTOLOGICAL = "ontological"
    EPISTEMIC = "epistemic"
    EMPIRICAL = "empirical"
    CONTINGENT = "contingent"
    PROCEDURAL = "procedural"
    NOMOLOGICAL = "nomological"
    STRUCTURAL = "structural"
    AXIOMATIC = "axiomatic"
    MIXED = "mixed"


class BlockDisposition(str, Enum):
    """Per-block disposition (§10.2.1): ``vary | hold | n/a | refuse``.

    The dump records the CLASS-DEFAULT disposition (§10.2 table rightmost
    column). The gate resolves the EFFECTIVE disposition from the regime
    manifest — which classes an arm varies, and the per-block entries for
    ``mixed`` blocks — never from this column alone.
    """

    VARY = "vary"
    HOLD = "hold"
    NOT_APPLICABLE = "n/a"
    REFUSE = "refuse"


#: Class-default dispositions, straight from the §10.2 table. ``contingent``
#: is out of gate scope by construction [T-2]; ``structural``/``axiomatic``
#: cannot vary in-runtime; ``mixed`` refuses by default [T-0/T-1].
CLASS_DEFAULT_DISPOSITION: dict[BlockClass, BlockDisposition] = {
    BlockClass.AXIOTIC: BlockDisposition.VARY,
    BlockClass.DEONTIC: BlockDisposition.HOLD,
    BlockClass.PRAGMATIC: BlockDisposition.HOLD,
    BlockClass.ONTOLOGICAL: BlockDisposition.HOLD,
    BlockClass.EPISTEMIC: BlockDisposition.HOLD,
    BlockClass.EMPIRICAL: BlockDisposition.HOLD,
    BlockClass.CONTINGENT: BlockDisposition.NOT_APPLICABLE,
    BlockClass.PROCEDURAL: BlockDisposition.HOLD,
    BlockClass.NOMOLOGICAL: BlockDisposition.HOLD,
    BlockClass.STRUCTURAL: BlockDisposition.NOT_APPLICABLE,
    BlockClass.AXIOMATIC: BlockDisposition.NOT_APPLICABLE,
    BlockClass.MIXED: BlockDisposition.REFUSE,
}


class ComposedBlock(BaseModel):
    """One row of the compose dump (FSD §12 Phase 1 row shape).

    ``residue_hits`` / ``token_hits`` extend the FSD's minimal row so the gate
    (a pure dump-to-dump comparison, no re-composition) can run assertion 4:
    the dump records which normalized ``RESIDUE_SITES`` fragments and adjunct
    tokens matched the composed content; the gate asserts the hit sets are
    arm-invariant per block.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    block_id: str = Field(..., description="Stable block identity, '<step>.<block>' (e.g. 'pdma.accord')")
    step: str = Field(..., description="Pipeline step (pdma|csdma|idma|dsdma|aspdma|dsaspdma|tsaspdma|...)")
    locale: str = Field(..., description="Locale the composition ran under (CIRIS_PREFERRED_LANGUAGE)")
    arm: str = Field(..., description="Regime arm name this dump was composed under")
    seq: int = Field(
        ...,
        ge=0,
        description=(
            "Running block index within (locale, step). Since #997 a composed message yields one row "
            "per FIELD, so this is no longer the message index"
        ),
    )
    role: str = Field(..., description="Chat role of the message the block was emitted as")
    block_class: BlockClass = Field(..., alias="class", description="§10.2 class (or 'mixed', §10.2.1)")
    disposition: BlockDisposition = Field(..., description="Class-default disposition (see BlockDisposition doc)")
    source: str = Field(
        ...,
        description=(
            "Routed provenance ('corpus:accord.polyglot_compressed', 'string:prompts.language_guidance', ...) "
            "or 'inline' for text composed from templates/fixtures inside the seam"
        ),
    )
    sha256: str = Field(..., description="Hex SHA-256 over the block's exact UTF-8 content bytes")
    bytes: int = Field(..., ge=0, description="UTF-8 byte length of the block content")
    contaminant: Optional[List[BlockClass]] = Field(
        default=None,
        description="Populated for every mixed block (§10.2.1 T-N1): the classes present in the block",
    )
    residue_hits: List[str] = Field(
        default_factory=list,
        description="Ids of normalized RESIDUE_SITES fragments found in this block's content (assertion 4)",
    )
    token_hits: List[str] = Field(
        default_factory=list,
        description="Adjunct token scan hits (CIRIS / M-1 / principle names) — cheap adjunct, never the mechanism",
    )
    parent_block_id: Optional[str] = Field(
        default=None,
        description=(
            "For a row that is one FIELD of a composed message (#997), the block_id of the message it "
            "was split out of; None when the row IS the whole message. Makes the dump self-describing: "
            "group by parent and the pieces reassemble to the bytes the model received"
        ),
    )


class ComposeDumpMeta(BaseModel):
    """Header line of a dump file — instrument identity, no timestamps.

    ``residue_digest`` is recorded at compose time so the gate can prove both
    dumps were produced against the same uncovered-inline surface (assertion 5)
    without re-running composition. ``fragment_count`` pins the size of the
    normalized-fragment inventory the residue scan (assertion 4) ran with, so a
    dump produced by a weakened scanner is visibly different.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="compose_dump_meta")
    arm: str = Field(..., description="Regime arm name")
    manifest: Optional[str] = Field(default=None, description="Override manifest path the dump composed under")
    locales: List[str] = Field(..., description="Locales composed, in composition order")
    steps: List[str] = Field(..., description="Steps composed per locale, in composition order")
    residue_digest: str = Field(..., description="compute_residue_digest() of the composing tree")
    fragment_count: int = Field(..., ge=0, description="Residue fragments the scan matched against")
    conscience_guidance_mode: str = Field(
        default="full",
        description="#983 mode at compose time (#986: arm assignment must be auditable from artifacts, never from operator intention)",
    )


class RegimeArm(BaseModel):
    """A §10.3 arm declaration.

    Shared by the Phase-1 gate view (``GateRegime``) and the full v2 manifest
    (``ciris_engine.schemas.research.regime.ExperimentalRegimeV2``): which
    harness, and which classes the arm varies. The rest of v2 (tiered DV,
    repeats, holds, kills) lives in the research module, keyed on these arms.
    """

    model_config = ConfigDict(extra="forbid")

    harness: str = Field(..., description="'h3ere' or 'direct-provider'")
    replace: dict[str, str] = Field(default_factory=dict, description="class -> replacement corpus path")
    disable: List[str] = Field(default_factory=list, description="classes blanked in this arm")
    inject: dict[str, str] = Field(default_factory=dict, description="class -> corpus injected (direct-provider)")
    safety_review: Optional[str] = Field(
        default=None,
        description=(
            "Reviewer/reference for a `deontic` replacement (§10.4 — deontic in replace: without "
            "safety_review refuses). Varying categorical permission changes what is PERMITTED, not "
            "how outcomes rank, so it is the one class whose replacement is reviewed before it runs."
        ),
    )


class RegimeBlockEntry(BaseModel):
    """Per-block disposition for a ``mixed`` block (§10.2.1)."""

    model_config = ConfigDict(extra="forbid")

    disposition: BlockDisposition = Field(...)
    contaminant: List[BlockClass] = Field(default_factory=list)
    confound_accepted: List[BlockClass] = Field(
        default_factory=list,
        description="Contaminants whose intersection with a varied class is knowingly accepted [T-N1]",
    )


class RegimePins(BaseModel):
    """Phase-1 pins: only the residue digest is asserted by the gate."""

    model_config = ConfigDict(extra="ignore")

    residue_digest: str = Field(...)


class GateRegime(BaseModel):
    """Phase-1 gate view of a regime manifest (subset of FSD §10.3).

    Loaded from YAML by ``compose_dump gate --regime``. ``blocks`` keys match a
    row's full ``block_id`` or its suffix after the step ('language_guidance'
    covers every step's language_guidance block). Varied classes are the union
    of every arm's ``replace`` and ``disable`` class names — ``inject`` targets
    direct-provider arms, whose source-hash comparison half of assertion 3 is
    descoped in Phase 1 (FSD §14 step 11 lands it).
    """

    model_config = ConfigDict(extra="ignore")

    regime_id: str = Field(...)
    arms: dict[str, RegimeArm] = Field(default_factory=dict)
    blocks: dict[str, RegimeBlockEntry] = Field(default_factory=dict)
    pins: RegimePins = Field(...)

    def varied_classes(self) -> frozenset[BlockClass]:
        """Classes any h3ere arm varies (replace or disable)."""
        varied: set[BlockClass] = set()
        for arm in self.arms.values():
            for name in list(arm.replace) + list(arm.disable):
                varied.add(BlockClass(name))
        return frozenset(varied)
