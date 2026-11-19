"""The manifest's locale record: the language a call was rendered for, the locale each segment's bytes were
rendered in and how that is known, and the segments that fell back to another language."""

import pytest

from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader
from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader
from ciris_engine.logic.prompt_assembly import AssemblyCall, PromptAssembler
from ciris_engine.logic.prompt_assembly.assembler import is_locale_fallback, segment_locale
from ciris_engine.logic.prompt_assembly.segmenting import split_template
from ciris_engine.schemas.context.prompt_provenance import (
    AssemblyMode,
    AuthnCarrier,
    LocaleBasis,
    PolicyFacts,
    PromptSegment,
    PromptStage,
    SegmentKind,
    SegmentSource,
)

QA = AssemblyMode.FAIL_CLOSED
SENDER = AuthnCarrier(subject_id="wa-user-42", role="OBSERVER", verifier="api_auth")


def seg(segment_id, kind, text="", **kw):
    kw.setdefault("source", SegmentSource.ENGINE)
    return PromptSegment(segment_id=segment_id, kind=kind, text=text, **kw)


def segments(instr_locale):
    return [
        seg("instr", SegmentKind.STAGE_INSTRUCTION, "ትዕዛዝ" if instr_locale == "am" else "You judge.", locale=instr_locale),
        seg("accord", SegmentKind.ACCORD, "ACCORD"),
        seg("ident", SegmentKind.IDENTITY_BASE, "I am Ally.", source=SegmentSource.AGENT_PROFILE),
        seg("draft", SegmentKind.DRAFT, "SPEAK: hello", source=SegmentSource.LLM_OUTPUT),
        seg("pos", SegmentKind.PIPELINE_POSITION, "You see the draft.", locale="en"),
    ]


def build(instr_locale, language):
    call = AssemblyCall(response_model="Verdict", task_id="t", thought_id="th", facts=PolicyFacts(), language=language)
    return PromptAssembler().build(PromptStage.COHERENCE, segments(instr_locale), QA, call=call)


def test_manifest_records_the_call_language_and_each_segments_locale():
    _, manifest = build("am", "am")
    assert manifest.language == "am"
    by_id = {r.segment_id: r for r in manifest.segments}
    assert (by_id["instr"].locale, by_id["instr"].locale_basis) == ("am", LocaleBasis.DECLARED)
    # Model output and agent-template text: no locale the engine can vouch for.
    assert (by_id["draft"].locale, by_id["draft"].locale_basis) == (None, LocaleBasis.UNSTATED)
    assert by_id["ident"].locale_basis == LocaleBasis.UNSTATED


def test_a_declared_locale_other_than_the_call_language_is_a_fallback():
    _, manifest = build("am", "am")
    assert manifest.locale_fallbacks == ["pos"]  # the English pipeline position in an Amharic call
    _, manifest = build("en", "am")
    assert manifest.locale_fallbacks == ["instr", "pos"]
    _, manifest = build("en", "en")
    assert manifest.locale_fallbacks == []


def test_polyglot_and_no_language_text_and_unset_language_are_never_fallbacks():
    assert not is_locale_fallback("mul", "am")
    assert not is_locale_fallback("zxx", "am")
    assert not is_locale_fallback("en", None)
    assert not is_locale_fallback(None, "am")
    assert not is_locale_fallback("pt-BR", "pt")
    assert is_locale_fallback("en", "am")


def test_stub_lines_and_the_senders_lines_are_assembler_rendered():
    stub_source = seg("req", SegmentKind.REQUEST, "user text", source=SegmentSource.USER_INPUT)
    assert segment_locale(stub_source, "am", withheld=True) == ("zxx", LocaleBasis.ASSEMBLER_RENDERED)
    sender = seg("sender", SegmentKind.SENDER_IDENTITY, source=SegmentSource.AUTH_CONTEXT, authn=SENDER)
    assert segment_locale(sender, "am", withheld=False) == ("am", LocaleBasis.ASSEMBLER_RENDERED)
    assert segment_locale(sender, None, withheld=False) == ("en", LocaleBasis.ASSEMBLER_RENDERED)


def test_split_template_records_the_served_locale_on_instruction_pieces_only():
    slot = seg("request", SegmentKind.REQUEST, "hi", source=SegmentSource.USER_INPUT)
    pieces, _ = split_template(lambda request: f"HEAD {request} TAIL", {"request": slot}, prefix="instr", locale="am")
    assert [(s.segment_id, s.locale) for s in pieces] == [("instr:0", "am"), ("request", None), ("instr:1", "am")]


@pytest.mark.parametrize("language,expected", [("en", "en"), ("am", "am")])
def test_dma_loader_reports_the_locale_it_served(language, expected):
    collection = DMAPromptLoader(language=language).load_prompt_template("csdma_common_sense")
    assert collection.served_language == expected


def test_dma_loader_reports_english_when_the_locale_has_no_file(tmp_path):
    loader = DMAPromptLoader(language="am")
    loader.localized_dir = tmp_path  # an empty locale directory: every template falls back
    assert loader.load_prompt_template("csdma_common_sense").served_language == "en"


def test_conscience_locales_mark_the_polyglot_veto_as_mul():
    loader = ConsciencePromptLoader(language="am")
    system, _, user = loader.prompt_locales("optimization_veto_conscience")
    assert system == "mul"
    assert user in ("am", "en")
    system, _, _ = loader.prompt_locales("coherence_conscience")
    assert system == loader.load_prompts("coherence_conscience").served_language


# ------------------------------------------------------------------------------------------------ review of #1368


def test_research_overrides_clear_the_served_locale(monkeypatch):
    from types import SimpleNamespace

    from ciris_engine.logic.utils import research_overrides

    fake = SimpleNamespace(overrides=SimpleNamespace(dma_prompt={"csdma_common_sense.closing_reminder": "X"}))
    monkeypatch.setattr(research_overrides, "get_active_overrides", lambda: fake)
    collection = DMAPromptLoader(language="en").load_prompt_template("csdma_common_sense")
    assert collection.closing_reminder == "X"
    assert collection.served_language is None


def test_a_locale_copy_without_the_pipeline_position_serves_it_in_english(tmp_path):
    import yaml

    loader = DMAPromptLoader(language="am")
    source = loader.localized_dir / "csdma_common_sense.yml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    data.pop("pipeline_position", None)
    (tmp_path / "csdma_common_sense.yml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    loader.localized_dir = tmp_path
    text, locale = loader.pipeline_position_served("csdma_common_sense")
    assert text and locale == "en"
    assert DMAPromptLoader(language="am").pipeline_position_served("csdma_common_sense")[1] == "am"
    # Recorded as declared English in an Amharic call: listed as a fallback.
    _, manifest = PromptAssembler().build(
        PromptStage.COHERENCE,
        [
            seg("instr", SegmentKind.STAGE_INSTRUCTION, "ትዕዛዝ", locale="am"),
            seg("accord", SegmentKind.ACCORD, "ACCORD"),
            seg("ident", SegmentKind.IDENTITY_BASE, "I am Ally.", source=SegmentSource.AGENT_PROFILE),
            seg("draft", SegmentKind.DRAFT, "SPEAK: hi", source=SegmentSource.LLM_OUTPUT),
            seg("pos", SegmentKind.PIPELINE_POSITION, text, locale=locale),
        ],
        QA,
        call=AssemblyCall(response_model="Verdict", task_id="t", thought_id="th", facts=PolicyFacts(), language="am"),
    )
    assert manifest.locale_fallbacks == ["pos"]


def test_aspdma_stage_contract_missing_from_a_locale_is_served_in_english_and_marks_its_piece(tmp_path, monkeypatch):
    """Independent of the shipped corpus: a ta copy WITHOUT stage_contract, in a temporary locale directory."""
    import yaml

    from ciris_engine.logic.dma.action_selection_pdma import _merged_locale, _stage_contract_served
    from ciris_engine.logic.dma.prompt_loader import get_prompt_loader
    from ciris_engine.logic.utils.localization import thought_language_scope

    loader = get_prompt_loader(language="ta")
    source = loader.localized_dir / "action_selection_pdma.yml"
    if not source.exists():
        source = loader.prompts_dir / "action_selection_pdma.yml"
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    data.pop("stage_contract", None)
    (tmp_path / "action_selection_pdma.yml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(loader, "localized_dir", tmp_path)

    with thought_language_scope("ta"):
        text, locale = _stage_contract_served()
    assert text and locale == "en"
    # after_position joins stage_contract (en) with decision_format and closing_reminder (ta): the piece is a fallback.
    assert _merged_locale(["en", "ta", "ta"], "ta") == "en"
    assert _merged_locale(["ta", "ta"], "ta") == "ta"
    assert _merged_locale(["ta", None], "ta") is None


# ------------------------------------------------------------------------------------------------ Codex P2s on #1368


def test_conscience_research_overrides_clear_the_locale_and_the_polyglot_mark(monkeypatch):
    from types import SimpleNamespace

    from ciris_engine.logic.utils import research_overrides

    fake = SimpleNamespace(
        overrides=SimpleNamespace(conscience_prompt={"optimization_veto_conscience.system_prompt": "X"})
    )
    monkeypatch.setattr(research_overrides, "get_active_overrides", lambda: fake)
    loader = ConsciencePromptLoader(language="en")
    prompts = loader.load_prompts("optimization_veto_conscience")
    assert prompts.system_prompt == "X"
    assert prompts.served_language is None and prompts.polyglot_system_prompt is False
    system, _, user = loader.prompt_locales("optimization_veto_conscience")
    assert system is None and user is None  # unknown, never "mul" or the requested language


def test_language_guidance_reports_the_locale_it_served(monkeypatch):
    from ciris_engine.logic.utils import localization

    assert localization.language_guidance_locale("am") == "am"
    assert localization.language_guidance_locale("en") == "en"
    # A locale with no guidance of its own is served the English block, and says so.
    monkeypatch.setattr(localization, "language_guidance_parts", lambda code: [] if code == "am" else ["x"])
    monkeypatch.setattr(localization, "get_string", lambda code, key, default="": "")
    assert localization.language_guidance_locale("am") == "en"


def test_aspdma_per_key_locale_falls_back_to_english_for_a_key_the_locale_lacks(tmp_path, monkeypatch):
    import yaml
    from unittest.mock import Mock

    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator, _merged_locale
    from ciris_engine.logic.dma.prompt_loader import get_prompt_loader
    from ciris_engine.logic.utils.localization import thought_language_scope

    loader = get_prompt_loader(language="am")
    data = yaml.safe_load((loader.localized_dir / "action_selection_pdma.yml").read_text(encoding="utf-8"))
    data.pop("closing_reminder", None)
    (tmp_path / "action_selection_pdma.yml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    monkeypatch.setattr(loader, "localized_dir", tmp_path)

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    with thought_language_scope("am"):
        closing, decision = dma._prompt_locale("closing_reminder"), dma._prompt_locale("decision_format")
    assert (closing, decision) == ("en", "am")
    # after_position = stage_contract + decision_format + closing_reminder: listed as a fallback.
    assert _merged_locale(["am", decision, closing], "am") == "en"
