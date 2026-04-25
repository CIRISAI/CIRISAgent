"""
Tests for ConfigBootstrap tolerance of legacy/renamed config fields.

Production agents have a persistent datum_config Docker volume that outlives
the current image schema. When a field is renamed or removed, the old YAML
must NOT crash-loop the agent — bootstrap strips unknown keys with a warning
and retries, while still failing fast on genuine misconfiguration.
"""

import logging
from typing import Any, Dict

import pytest

from ciris_engine.logic.config.bootstrap import ConfigBootstrap
from ciris_engine.schemas.config.essential import EssentialConfig


def test_unknown_top_level_key_is_stripped_and_warned(caplog):
    """Legacy top-level fields from an older schema are dropped, not fatal."""
    legacy_data = {
        "database": {},
        "obsolete_top_level": {"foo": "bar"},  # doesn't exist in current schema
    }
    caplog.set_level(logging.WARNING)

    stripped, dropped = ConfigBootstrap._strip_unknown_keys(EssentialConfig, legacy_data)

    assert dropped == ["obsolete_top_level"]
    assert "obsolete_top_level" not in stripped
    assert "database" in stripped


def test_unknown_nested_key_is_stripped_with_dotted_path():
    """The datum bug: security.audit_key_path was renamed to secrets_key_path."""
    legacy_data: Dict[str, Any] = {
        "security": {
            "audit_key_path": "audit_keys",  # renamed → secrets_key_path
        },
    }
    stripped, dropped = ConfigBootstrap._strip_unknown_keys(EssentialConfig, legacy_data)

    assert dropped == ["security.audit_key_path"]
    # security dict is preserved but without the stale key
    assert stripped["security"] == {}


def test_known_nested_fields_are_preserved():
    """Real config keys must survive the strip pass untouched."""
    data = {
        "security": {"audit_retention_days": 42},
        "database": {},
    }
    stripped, dropped = ConfigBootstrap._strip_unknown_keys(EssentialConfig, data)

    assert dropped == []
    assert stripped["security"]["audit_retention_days"] == 42


def test_extra_forbidden_detector_requires_all_errors_to_be_extras():
    """If any ValidationError is a genuine type mismatch, we must NOT swallow."""
    from pydantic import ValidationError

    # Build a ValidationError with a mix of extra_forbidden and a real error
    try:
        EssentialConfig(
            unknown_top=1,  # extra_forbidden
            log_level=123,  # wrong type (int not str) — real error
        )
    except ValidationError as e:
        # Mixed errors → strip-and-warn path must refuse
        assert not ConfigBootstrap._has_only_extra_forbidden_errors(e)

    # Pure extra_forbidden case → strip-and-warn path proceeds
    try:
        EssentialConfig(unknown_top=1, another_unknown=2)
    except ValidationError as e:
        assert ConfigBootstrap._has_only_extra_forbidden_errors(e)


@pytest.mark.asyncio
async def test_load_essential_config_recovers_from_stale_nested_key(tmp_path, caplog):
    """End-to-end: YAML with a legacy security field boots successfully."""
    config_path = tmp_path / "essential.yaml"
    config_path.write_text(
        "security:\n"
        "  audit_key_path: audit_keys  # renamed, no longer valid\n"
        "log_level: INFO\n"
    )
    caplog.set_level(logging.WARNING)

    config = await ConfigBootstrap.load_essential_config(config_path=config_path)

    assert isinstance(config, EssentialConfig)
    assert config.log_level == "INFO"
    # The warning must clearly identify the dropped key.
    warnings = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("security.audit_key_path" in str(m) for m in warnings), warnings


@pytest.mark.asyncio
async def test_load_essential_config_still_rejects_genuine_type_errors(tmp_path):
    """Strip-and-warn must not mask real misconfiguration — wrong-type
    values should still fail fast so ops see the problem immediately."""
    config_path = tmp_path / "essential.yaml"
    config_path.write_text(
        "limits:\n"
        "  max_active_tasks: not-a-number\n"  # wrong type — genuine error
    )

    with pytest.raises(ValueError, match="Invalid configuration"):
        await ConfigBootstrap.load_essential_config(config_path=config_path)


def test_extra_forbidden_detector_empty_error_list_returns_false():
    """A ValidationError with no entries should NOT match — bail out path."""
    # Can't directly construct ValidationError with empty errors in pydantic v2,
    # but we can simulate it with a minimal fake.
    from pydantic import ValidationError

    class _FakeErr:
        def errors(self):
            return []

    # _has_only_extra_forbidden_errors handles any .errors()-returning object
    fake = _FakeErr()
    assert ConfigBootstrap._has_only_extra_forbidden_errors(fake) is False  # type: ignore[arg-type]


def test_strip_unknown_keys_passes_through_non_dict_values():
    """Plain-value fields (strings, numbers) are preserved untouched."""
    data = {"log_level": "WARNING", "debug_mode": True}
    stripped, dropped = ConfigBootstrap._strip_unknown_keys(EssentialConfig, data)
    assert dropped == []
    assert stripped == data


def test_strip_unknown_keys_non_basemodel_annotation_returns_subdata():
    """Fields whose annotation is not a BaseModel subclass are not recursed."""
    # log_level is str — passing a dict shouldn't crash _clean, it just
    # returns the value as-is (pydantic will then reject it downstream).
    data = {"log_level": {"nested": "oops"}}
    stripped, dropped = ConfigBootstrap._strip_unknown_keys(EssentialConfig, data)
    assert dropped == []
    assert stripped["log_level"] == {"nested": "oops"}


def test_strip_unknown_keys_non_basemodel_class_short_circuits():
    """If the target class isn't a BaseModel subclass, return the data as-is."""

    class NotAModel:
        pass

    stripped, dropped = ConfigBootstrap._strip_unknown_keys(NotAModel, {"x": 1})
    assert dropped == []
    assert stripped == {"x": 1}
