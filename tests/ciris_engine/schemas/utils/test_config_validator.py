"""Tests for config validator schemas to achieve full coverage."""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.utils.config_validator import (
    ConfigData,
    DatabaseValidationConfig,
    LLMConfig,
    MaskedConfigResult,
    NestedValueUpdate,
)


class TestConfigData:
    """Test ConfigData schema."""

    def test_config_data_defaults(self):
        """Test ConfigData with default values."""
        config = ConfigData()

        assert config.llm_services == {}
        assert config.database == {}
        assert config.secrets == {}
        assert config.additional_config == {}

    def test_config_data_with_values(self):
        """Test ConfigData with provided values."""
        config = ConfigData(
            llm_services={"openai": {"api_key": "test"}},
            database={"db_filename": "test.db"},
            secrets={"secret_key": "value"},
            additional_config={"extra": "data"},
        )

        assert config.llm_services == {"openai": {"api_key": "test"}}
        assert config.database == {"db_filename": "test.db"}
        assert config.secrets == {"secret_key": "value"}
        assert config.additional_config == {"extra": "data"}

    def test_config_data_model_dump(self):
        """Test ConfigData serialization."""
        config = ConfigData(llm_services={"openai": {"api_key": "test"}}, database={"db_filename": "test.db"})

        dumped = config.model_dump()

        assert dumped["llm_services"] == {"openai": {"api_key": "test"}}
        assert dumped["database"] == {"db_filename": "test.db"}
        assert dumped["secrets"] == {}
        assert dumped["additional_config"] == {}


class TestLLMConfig:
    """Test LLMConfig schema."""

    def test_llm_config_defaults(self):
        """Test LLMConfig with default values."""
        config = LLMConfig()

        assert config.openai == {}
        assert config.additional_providers == {}

    def test_llm_config_with_values(self):
        """Test LLMConfig with provided values."""
        config = LLMConfig(
            openai={"api_key": "test_key", "model": "gpt-4"},
            additional_providers={"anthropic": {"api_key": "claude_key"}},
        )

        assert config.openai == {"api_key": "test_key", "model": "gpt-4"}
        assert config.additional_providers == {"anthropic": {"api_key": "claude_key"}}

    def test_llm_config_model_dump(self):
        """Test LLMConfig serialization."""
        config = LLMConfig(openai={"api_key": "test"}, additional_providers={"anthropic": {"key": "value"}})

        dumped = config.model_dump()

        assert dumped["openai"] == {"api_key": "test"}
        assert dumped["additional_providers"] == {"anthropic": {"key": "value"}}


class TestDatabaseValidationConfig:
    """Test DatabaseValidationConfig schema."""

    def test_database_validation_config_defaults(self):
        """Test DatabaseValidationConfig with default values."""
        config = DatabaseValidationConfig()

        assert config.db_filename is None
        assert config.additional_settings == {}

    def test_database_validation_config_with_filename(self):
        """Test DatabaseValidationConfig with filename."""
        config = DatabaseValidationConfig(db_filename="test.db")

        assert config.db_filename == "test.db"
        assert config.additional_settings == {}

    def test_database_validation_config_with_settings(self):
        """Test DatabaseValidationConfig with additional settings."""
        config = DatabaseValidationConfig(db_filename="prod.db", additional_settings={"timeout": 30, "pool_size": 10})

        assert config.db_filename == "prod.db"
        assert config.additional_settings == {"timeout": 30, "pool_size": 10}

    def test_database_validation_config_model_dump(self):
        """Test DatabaseValidationConfig serialization."""
        config = DatabaseValidationConfig(db_filename="test.db", additional_settings={"key": "value"})

        dumped = config.model_dump()

        assert dumped["db_filename"] == "test.db"
        assert dumped["additional_settings"] == {"key": "value"}


class TestMaskedConfigResult:
    """Test MaskedConfigResult schema."""

    def test_masked_config_result_minimal(self):
        """Test MaskedConfigResult with minimal data."""
        result = MaskedConfigResult(masked_config={})

        assert result.masked_config == {}
        assert result.masked_count == 0
        assert result.masked_paths == []

    def test_masked_config_result_with_data(self):
        """Test MaskedConfigResult with full data."""
        result = MaskedConfigResult(
            masked_config={"api_key": "***", "secret": "***"},
            masked_count=2,
            masked_paths=["config.api_key", "config.secret"],
        )

        assert result.masked_config == {"api_key": "***", "secret": "***"}
        assert result.masked_count == 2
        assert result.masked_paths == ["config.api_key", "config.secret"]

    def test_masked_config_result_validation(self):
        """Test MaskedConfigResult requires masked_config."""
        with pytest.raises(ValidationError):
            MaskedConfigResult()  # Missing required masked_config

    def test_masked_config_result_model_dump(self):
        """Test MaskedConfigResult serialization."""
        result = MaskedConfigResult(masked_config={"key": "value"}, masked_count=1, masked_paths=["root.key"])

        dumped = result.model_dump()

        assert dumped["masked_config"] == {"key": "value"}
        assert dumped["masked_count"] == 1
        assert dumped["masked_paths"] == ["root.key"]


class TestNestedValueUpdate:
    """Test NestedValueUpdate schema."""

    def test_nested_value_update_minimal(self):
        """Test NestedValueUpdate with minimal data."""
        update = NestedValueUpdate(target_object={}, path="config.value", value="new_value")

        assert update.target_object == {}
        assert update.path == "config.value"
        assert update.value == "new_value"
        assert update.original_value is None

    def test_nested_value_update_with_original(self):
        """Test NestedValueUpdate with original value."""
        update = NestedValueUpdate(
            target_object={"config": {"value": "old"}}, path="config.value", value="new", original_value="old"
        )

        assert update.target_object == {"config": {"value": "old"}}
        assert update.path == "config.value"
        assert update.value == "new"
        assert update.original_value == "old"

    def test_nested_value_update_validation(self):
        """Test NestedValueUpdate requires all fields."""
        with pytest.raises(ValidationError):
            NestedValueUpdate()  # Missing required fields

        with pytest.raises(ValidationError):
            NestedValueUpdate(target_object={})  # Missing path and value

        with pytest.raises(ValidationError):
            NestedValueUpdate(target_object={}, path="test")  # Missing value

    def test_nested_value_update_various_value_types(self):
        """Test NestedValueUpdate with various value types."""
        # String value
        update1 = NestedValueUpdate(target_object={}, path="key", value="string_value")
        assert update1.value == "string_value"

        # Integer value
        update2 = NestedValueUpdate(target_object={}, path="key", value=42)
        assert update2.value == 42

        # Float value
        update3 = NestedValueUpdate(target_object={}, path="key", value=3.14)
        assert update3.value == 3.14

        # Boolean value
        update4 = NestedValueUpdate(target_object={}, path="key", value=True)
        assert update4.value is True

        # Dict value
        update5 = NestedValueUpdate(target_object={}, path="key", value={"nested": "dict"})
        assert update5.value == {"nested": "dict"}

        # List value
        update6 = NestedValueUpdate(target_object={}, path="key", value=[1, 2, 3])
        assert update6.value == [1, 2, 3]

    def test_nested_value_update_model_dump(self):
        """Test NestedValueUpdate serialization."""
        update = NestedValueUpdate(
            target_object={"a": "b"}, path="nested.path", value="value", original_value="old_value"
        )

        dumped = update.model_dump()

        assert dumped["target_object"] == {"a": "b"}
        assert dumped["path"] == "nested.path"
        assert dumped["value"] == "value"
        assert dumped["original_value"] == "old_value"


class TestConfigValidatorSchemasIntegration:
    """Integration tests for config validator schemas."""

    def test_config_data_to_masked_result(self):
        """Test converting ConfigData to MaskedConfigResult."""
        config = ConfigData(llm_services={"openai": {"api_key": "secret123"}}, secrets={"db_password": "pass456"})

        # Simulate masking
        masked = MaskedConfigResult(
            masked_config={"llm_services": {"openai": {"api_key": "***"}}, "secrets": {"db_password": "***"}},
            masked_count=2,
            masked_paths=["llm_services.openai.api_key", "secrets.db_password"],
        )

        assert masked.masked_count == 2
        assert len(masked.masked_paths) == 2

    def test_nested_value_update_on_config(self):
        """Test NestedValueUpdate with ConfigData."""
        config_dict = {"llm_services": {"openai": {"model": "gpt-3.5"}}, "database": {"db_filename": "old.db"}}

        update = NestedValueUpdate(
            target_object=config_dict, path="database.db_filename", value="new.db", original_value="old.db"
        )

        assert update.target_object["database"]["db_filename"] == "old.db"
        assert update.value == "new.db"
        assert update.original_value == "old.db"
