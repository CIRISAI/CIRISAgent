"""
Unit tests for ConsciencePromptLoader.

Tests the loading and localization of conscience prompts from YAML files.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
import yaml

from ciris_engine.logic.conscience.prompt_loader import (
    DEFAULT_LANGUAGE,
    ConsciencePromptLoader,
    ConsciencePrompts,
    get_conscience_prompt_loader,
    set_conscience_prompt_language,
)


class TestConsciencePrompts:
    """Tests for the ConsciencePrompts model."""

    def test_default_values(self) -> None:
        """Test that ConsciencePrompts has sensible defaults."""
        prompts = ConsciencePrompts()
        assert prompts.version == "1.0"
        assert prompts.description == ""
        assert prompts.language == "en"
        assert prompts.system_prompt == ""
        assert prompts.user_prompt_template == ""
        assert prompts.user_prompt_with_image_template == ""

    def test_full_initialization(self) -> None:
        """Test ConsciencePrompts with all fields."""
        prompts = ConsciencePrompts(
            version="2.0",
            description="Test prompts",
            language="fr",
            system_prompt="System message",
            user_prompt_template="User: {text}",
            user_prompt_with_image_template="Image: {image_context}\nUser: {text}",
        )
        assert prompts.version == "2.0"
        assert prompts.description == "Test prompts"
        assert prompts.language == "fr"
        assert prompts.system_prompt == "System message"
        assert prompts.user_prompt_template == "User: {text}"


class TestConsciencePromptLoader:
    """Tests for the ConsciencePromptLoader class."""

    @pytest.fixture
    def temp_prompts_dir(self) -> Generator[Path, None, None]:
        """Create a temporary directory with test prompt files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            prompts_dir = Path(tmpdir) / "prompts"
            prompts_dir.mkdir()

            # Create English prompt
            en_prompt = {
                "version": "1.0",
                "description": "English test prompt",
                "language": "en",
                "system_prompt": "You are IRIS-E, the entropy-sensing shard.",
                "user_prompt_template": "ASSESS: {text}",
                "user_prompt_with_image_template": "{image_context}\n\nASSESS: {text}",
            }
            with open(prompts_dir / "entropy_conscience.yml", "w") as f:
                yaml.dump(en_prompt, f)

            # Create French localized prompt
            fr_dir = prompts_dir / "localized" / "fr"
            fr_dir.mkdir(parents=True)
            fr_prompt = {
                "version": "1.0",
                "description": "Prompt de test français",
                "language": "fr",
                "system_prompt": "Vous êtes IRIS-E, l'éclat détecteur d'entropie.",
                "user_prompt_template": "ÉVALUER : {text}",
                "user_prompt_with_image_template": "{image_context}\n\nÉVALUER : {text}",
            }
            with open(fr_dir / "entropy_conscience.yml", "w") as f:
                yaml.dump(fr_prompt, f)

            yield prompts_dir

    def test_load_english_prompts(self, temp_prompts_dir: Path) -> None:
        """Test loading English (default) prompts."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")
        prompts = loader.load_prompts("entropy_conscience")

        assert prompts.language == "en"
        assert "IRIS-E" in prompts.system_prompt
        assert "entropy-sensing" in prompts.system_prompt
        assert "{text}" in prompts.user_prompt_template

    def test_load_localized_prompts(self, temp_prompts_dir: Path) -> None:
        """Test loading French localized prompts."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="fr")
        prompts = loader.load_prompts("entropy_conscience")

        assert prompts.language == "fr"
        assert "Vous êtes IRIS-E" in prompts.system_prompt
        assert "l'éclat détecteur d'entropie" in prompts.system_prompt
        assert "ÉVALUER" in prompts.user_prompt_template

    def test_fallback_to_english(self, temp_prompts_dir: Path) -> None:
        """Test fallback to English when localized version doesn't exist."""
        # German locale doesn't exist in our temp dir
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="de")
        prompts = loader.load_prompts("entropy_conscience")

        # Should fall back to English
        assert "You are IRIS-E" in prompts.system_prompt
        assert "entropy-sensing" in prompts.system_prompt

    def test_cache_behavior(self, temp_prompts_dir: Path) -> None:
        """Test that prompts are cached after first load."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")

        # First load
        prompts1 = loader.load_prompts("entropy_conscience")
        assert "en:entropy_conscience" in loader._cache

        # Second load should return cached version
        prompts2 = loader.load_prompts("entropy_conscience")
        assert prompts1 is prompts2

    def test_cache_cleared_on_language_change(self, temp_prompts_dir: Path) -> None:
        """Test that cache is cleared when language changes."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")

        # Load English
        prompts_en = loader.load_prompts("entropy_conscience")
        assert len(loader._cache) == 1
        cache_key_en = list(loader._cache.keys())[0]

        # Change language
        loader.set_language("fr")
        assert len(loader._cache) == 0

        # Load French
        prompts_fr = loader.load_prompts("entropy_conscience")
        assert len(loader._cache) == 1
        cache_key_fr = list(loader._cache.keys())[0]

        assert cache_key_en != cache_key_fr
        assert "Vous êtes" in prompts_fr.system_prompt

    def test_get_system_prompt(self, temp_prompts_dir: Path) -> None:
        """Test get_system_prompt convenience method."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")
        system_prompt = loader.get_system_prompt("entropy_conscience")

        assert isinstance(system_prompt, str)
        assert "IRIS-E" in system_prompt

    def test_get_user_prompt_without_image(self, temp_prompts_dir: Path) -> None:
        """Test get_user_prompt without image context."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")
        user_prompt = loader.get_user_prompt("entropy_conscience", text="Hello world")

        assert "Hello world" in user_prompt
        assert "ASSESS:" in user_prompt

    def test_get_user_prompt_with_image(self, temp_prompts_dir: Path) -> None:
        """Test get_user_prompt with image context."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")
        user_prompt = loader.get_user_prompt("entropy_conscience", image_context="[IMAGE CONTEXT]", text="Hello world")

        assert "Hello world" in user_prompt
        assert "[IMAGE CONTEXT]" in user_prompt
        assert "ASSESS:" in user_prompt

    def test_file_not_found_raises(self, temp_prompts_dir: Path) -> None:
        """Test that missing prompt file raises FileNotFoundError."""
        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")

        with pytest.raises(FileNotFoundError):
            loader.load_prompts("nonexistent_conscience")

    def test_invalid_yaml_raises(self, temp_prompts_dir: Path) -> None:
        """Test that invalid YAML raises an error."""
        # Write invalid YAML
        with open(temp_prompts_dir / "invalid_conscience.yml", "w") as f:
            f.write("invalid: yaml: content: [unbalanced")

        loader = ConsciencePromptLoader(prompts_dir=str(temp_prompts_dir), language="en")

        with pytest.raises(yaml.YAMLError):
            loader.load_prompts("invalid_conscience")


class TestConsciencePromptLoaderRealFiles:
    """Tests using actual prompt files from the repository."""

    @pytest.fixture
    def real_prompts_dir(self) -> Path:
        """Get the real prompts directory."""
        return Path(__file__).parent.parent.parent.parent.parent / "ciris_engine" / "logic" / "conscience" / "prompts"

    def test_load_real_entropy_prompts_english(self, real_prompts_dir: Path) -> None:
        """Test loading real entropy conscience prompts in English."""
        if not real_prompts_dir.exists():
            pytest.skip("Prompts directory not found")

        loader = ConsciencePromptLoader(prompts_dir=str(real_prompts_dir), language="en")
        prompts = loader.load_prompts("entropy_conscience")

        assert "IRIS-E" in prompts.system_prompt
        assert "entropy" in prompts.system_prompt.lower()
        assert "{text}" in prompts.user_prompt_template

    def test_load_real_coherence_prompts_english(self, real_prompts_dir: Path) -> None:
        """Test loading real coherence conscience prompts in English."""
        if not real_prompts_dir.exists():
            pytest.skip("Prompts directory not found")

        loader = ConsciencePromptLoader(prompts_dir=str(real_prompts_dir), language="en")
        prompts = loader.load_prompts("coherence_conscience")

        assert "IRIS-C" in prompts.system_prompt
        assert "coherence" in prompts.system_prompt.lower()

    def test_load_real_optimization_veto_prompts_english(self, real_prompts_dir: Path) -> None:
        """Test loading real optimization veto conscience prompts in English."""
        if not real_prompts_dir.exists():
            pytest.skip("Prompts directory not found")

        loader = ConsciencePromptLoader(prompts_dir=str(real_prompts_dir), language="en")
        prompts = loader.load_prompts("optimization_veto_conscience")

        assert "CIRIS-EOV" in prompts.system_prompt or "Optimization Veto" in prompts.system_prompt

    def test_load_real_epistemic_humility_prompts_english(self, real_prompts_dir: Path) -> None:
        """Test loading real epistemic humility conscience prompts in English."""
        if not real_prompts_dir.exists():
            pytest.skip("Prompts directory not found")

        loader = ConsciencePromptLoader(prompts_dir=str(real_prompts_dir), language="en")
        prompts = loader.load_prompts("epistemic_humility_conscience")

        assert "CIRIS-EH" in prompts.system_prompt or "Epistemic Humility" in prompts.system_prompt

    @pytest.mark.parametrize(
        "language,expected_substring",
        [
            ("fr", "Vous êtes"),
            ("de", "Sie sind IRIS-E"),  # German uses formal "Sie" (not informal "Du")
            ("es", "Eres"),
            ("ja", "です"),
            ("ar", "أنت"),
            ("zh", "你是"),
            ("tr", "Sen"),
            ("sw", "Wewe"),
            ("am", "እርስዎ IRIS-E"),  # Amharic uses formal form
        ],
    )
    def test_load_localized_prompts(self, real_prompts_dir: Path, language: str, expected_substring: str) -> None:
        """Test loading localized prompts for various languages."""
        if not real_prompts_dir.exists():
            pytest.skip("Prompts directory not found")

        localized_dir = real_prompts_dir / "localized" / language
        if not localized_dir.exists():
            pytest.skip(f"Localized prompts for {language} not found")

        loader = ConsciencePromptLoader(prompts_dir=str(real_prompts_dir), language=language)
        prompts = loader.load_prompts("entropy_conscience")

        # Verify it's actually localized (not English)
        assert "You are IRIS-E" not in prompts.system_prompt
        # Verify expected language content is present
        assert (
            expected_substring in prompts.system_prompt
        ), f"Expected '{expected_substring}' in {language} system_prompt"


class TestGlobalLoaderFunctions:
    """Tests for the global loader convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_global_state(self) -> Generator[None, None, None]:
        """Reset global state before each test."""
        import ciris_engine.logic.conscience.prompt_loader as pl

        pl._default_loader = None
        pl._current_language = DEFAULT_LANGUAGE
        yield
        # Cleanup after test
        pl._default_loader = None
        pl._current_language = DEFAULT_LANGUAGE

    def test_get_conscience_prompt_loader_singleton(self) -> None:
        """Test that get_conscience_prompt_loader returns a singleton."""
        # Force English by explicitly passing it
        loader1 = get_conscience_prompt_loader(language="en")
        loader2 = get_conscience_prompt_loader()

        assert loader1 is loader2

    def test_get_conscience_prompt_loader_with_language(self) -> None:
        """Test get_conscience_prompt_loader with explicit language."""
        loader = get_conscience_prompt_loader(language="fr")
        assert loader.language == "fr"

    def test_set_conscience_prompt_language(self) -> None:
        """Test set_conscience_prompt_language updates global loader."""
        # Initialize with explicit English
        loader = get_conscience_prompt_loader(language="en")
        assert loader.language == "en"

        # Set new language
        set_conscience_prompt_language("de")

        # Verify loader was updated
        assert loader.language == "de"

    def test_loader_with_explicit_language_overrides_default(self) -> None:
        """Test that explicit language parameter overrides any default."""
        # Even if environment might be set to something else,
        # explicit language should win
        loader = get_conscience_prompt_loader(language="ja")
        assert loader.language == "ja"

        # Changing language should update the loader
        set_conscience_prompt_language("ko")
        assert loader.language == "ko"


class TestConsciencePromptIntegration:
    """Integration tests verifying conscience system uses prompt loader correctly."""

    @pytest.fixture(autouse=True)
    def reset_global_state(self) -> Generator[None, None, None]:
        """Reset global state before each test."""
        import ciris_engine.logic.conscience.prompt_loader as pl

        pl._default_loader = None
        pl._current_language = DEFAULT_LANGUAGE
        yield
        # Cleanup after test
        pl._default_loader = None
        pl._current_language = DEFAULT_LANGUAGE

    @pytest.fixture
    def mock_service_registry(self) -> MagicMock:
        """Create a mock service registry."""
        return MagicMock()

    @pytest.fixture
    def mock_config(self) -> Any:
        """Create a mock config with conscience settings."""
        from ciris_engine.logic.conscience.core import ConscienceConfig

        return ConscienceConfig()

    @pytest.fixture
    def mock_time_service(self) -> MagicMock:
        """Create a mock time service."""
        time_service = MagicMock()
        time_service.get_current_time.return_value = datetime.now(timezone.utc)
        return time_service

    def test_entropy_conscience_uses_loader(
        self, mock_service_registry: MagicMock, mock_config: Any, mock_time_service: MagicMock
    ) -> None:
        """Test that EntropyConscience uses the prompt loader."""
        from ciris_engine.logic.conscience.core import EntropyConscience
        from ciris_engine.logic.conscience.prompt_loader import get_conscience_prompt_loader

        # Initialize with explicit English
        get_conscience_prompt_loader(language="en")

        conscience = EntropyConscience(mock_service_registry, mock_config, time_service=mock_time_service)

        # The _create_entropy_messages method should use the loader
        messages, _user_prompt = conscience._create_entropy_messages("Test text")

        # Verify the messages contain expected content from YAML
        system_contents = [m.content for m in messages if m.role == "system"]
        assert any(
            "IRIS-E" in content for content in system_contents
        ), "System messages should contain IRIS-E from loaded prompts"

    def test_coherence_conscience_uses_loader(
        self, mock_service_registry: MagicMock, mock_config: Any, mock_time_service: MagicMock
    ) -> None:
        """Test that CoherenceConscience uses the prompt loader."""
        from ciris_engine.logic.conscience.core import CoherenceConscience
        from ciris_engine.logic.conscience.prompt_loader import get_conscience_prompt_loader

        # Initialize with explicit English
        get_conscience_prompt_loader(language="en")

        conscience = CoherenceConscience(mock_service_registry, mock_config, time_service=mock_time_service)
        messages, _user_prompt = conscience._create_coherence_messages("Test text")

        system_contents = [m.content for m in messages if m.role == "system"]
        assert any(
            "IRIS-C" in content for content in system_contents
        ), "System messages should contain IRIS-C from loaded prompts"

    def test_localized_conscience_prompts_used(
        self, mock_service_registry: MagicMock, mock_config: Any, mock_time_service: MagicMock
    ) -> None:
        """Test that localized prompts are used when language is set."""
        from ciris_engine.logic.conscience.core import EntropyConscience
        from ciris_engine.logic.conscience.prompt_loader import (
            get_conscience_prompt_loader,
            set_conscience_prompt_language,
        )

        # Initialize and set to French
        get_conscience_prompt_loader(language="en")  # First init
        set_conscience_prompt_language("fr")

        conscience = EntropyConscience(mock_service_registry, mock_config, time_service=mock_time_service)
        messages, _user_prompt = conscience._create_entropy_messages("Test text")

        # Verify French content appears
        system_contents = [str(m.content) for m in messages if m.role == "system"]
        all_content = " ".join(system_contents)

        # Should contain French, not English
        assert (
            "Vous êtes IRIS-E" in all_content or "l'éclat" in all_content
        ), f"Expected French content in: {all_content[:500]}..."
        assert (
            "You are IRIS-E, the entropy-sensing" not in all_content
        ), "Should not contain English original when French is set"
