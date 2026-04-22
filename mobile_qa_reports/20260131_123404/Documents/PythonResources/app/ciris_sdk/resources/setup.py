"""
Setup resource for CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.

Provides first-run setup wizard endpoints for GUI-based configuration.
"""

from typing import Any, Dict, List, Optional, cast

from ..transport import Transport


class LLMProvider:
    """LLM provider configuration."""

    def __init__(self, data: Dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.description: str = data["description"]
        self.requires_api_key: bool = data["requires_api_key"]
        self.requires_base_url: bool = data["requires_base_url"]
        self.requires_model: bool = data["requires_model"]
        self.default_base_url: Optional[str] = data.get("default_base_url")
        self.default_model: Optional[str] = data.get("default_model")
        self.examples: List[str] = data.get("examples", [])


class AgentTemplate:
    """Agent identity template."""

    def __init__(self, data: Dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.description: str = data["description"]
        self.identity: str = data["identity"]
        self.example_use_cases: List[str] = data.get("example_use_cases", [])
        self.supported_sops: List[str] = data.get("supported_sops", [])
        self.stewardship_tier: int = data["stewardship_tier"]
        self.creator_id: str = data["creator_id"]
        self.signature: str = data["signature"]


class AdapterConfig:
    """Adapter configuration."""

    def __init__(self, data: Dict[str, Any]):
        self.id: str = data["id"]
        self.name: str = data["name"]
        self.description: str = data["description"]
        self.enabled_by_default: bool = data["enabled_by_default"]
        self.required_env_vars: List[str] = data.get("required_env_vars", [])
        self.optional_env_vars: List[str] = data.get("optional_env_vars", [])


class SetupStatus:
    """Setup status information."""

    def __init__(self, data: Dict[str, Any]):
        self.is_first_run: bool = data["is_first_run"]
        self.config_exists: bool = data["config_exists"]
        self.config_path: Optional[str] = data.get("config_path")
        self.setup_required: bool = data["setup_required"]


class LLMValidationResult:
    """LLM validation result."""

    def __init__(self, data: Dict[str, Any]):
        self.valid: bool = data["valid"]
        self.message: str = data["message"]
        self.error: Optional[str] = data.get("error")


class SetupResource:
    """
    Setup wizard resource for first-run configuration.

    Provides endpoints for:
    - Checking setup status
    - Listing LLM providers, templates, adapters
    - Validating LLM configuration
    - Completing initial setup
    - Getting/updating configuration

    Note: Setup endpoints are unauthenticated during first-run,
    but require authentication after setup is complete.
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def get_status(self) -> SetupStatus:
        """
        Get setup status.

        Returns information about whether this is first-run,
        config exists, and if setup is required.

        Returns:
            SetupStatus with first-run information
        """
        response = await self._transport.request("GET", "/v1/setup/status")
        assert response is not None
        return SetupStatus(response)

    async def list_providers(self) -> List[LLMProvider]:
        """
        List available LLM providers.

        Returns all supported LLM providers with their configuration
        requirements and defaults.

        Returns:
            List of LLMProvider objects
        """
        response = await self._transport.request("GET", "/v1/setup/providers")
        assert response is not None
        return [LLMProvider(p) for p in cast(List[Dict[str, Any]], response)]

    async def list_templates(self) -> List[AgentTemplate]:
        """
        List available agent templates.

        Returns all agent templates from ciris_templates directory
        with full metadata including Book VI Stewardship information.

        Returns:
            List of AgentTemplate objects
        """
        response = await self._transport.request("GET", "/v1/setup/templates")
        assert response is not None
        return [AgentTemplate(t) for t in cast(List[Dict[str, Any]], response)]

    async def list_adapters(self) -> List[AdapterConfig]:
        """
        List available adapters.

        Returns all communication adapters (API, CLI, Discord, Reddit)
        with their configuration requirements.

        Returns:
            List of AdapterConfig objects
        """
        response = await self._transport.request("GET", "/v1/setup/adapters")
        assert response is not None
        return [AdapterConfig(a) for a in cast(List[Dict[str, Any]], response)]

    async def validate_llm(
        self, provider: str, api_key: str, base_url: Optional[str] = None, model: Optional[str] = None
    ) -> LLMValidationResult:
        """
        Validate LLM configuration.

        Tests the LLM connection by attempting to list models.
        Useful for providing real-time feedback during setup.

        Args:
            provider: Provider ID (openai, local, other)
            api_key: API key for authentication
            base_url: Base URL for OpenAI-compatible endpoints
            model: Model name

        Returns:
            LLMValidationResult with validation status
        """
        request_data = {"provider": provider, "api_key": api_key, "base_url": base_url, "model": model}

        response = await self._transport.request("POST", "/v1/setup/validate-llm", json=request_data)
        assert response is not None
        return LLMValidationResult(response)

    async def complete_setup(
        self,
        llm_provider: str,
        llm_api_key: str,
        admin_username: str,
        admin_password: str,
        llm_base_url: Optional[str] = None,
        llm_model: Optional[str] = None,
        backup_llm_api_key: Optional[str] = None,
        backup_llm_base_url: Optional[str] = None,
        backup_llm_model: Optional[str] = None,
        template_id: str = "default",
        enabled_adapters: Optional[List[str]] = None,
        adapter_config: Optional[Dict[str, Any]] = None,
        system_admin_password: Optional[str] = None,
        agent_port: int = 8080,
    ) -> Dict[str, Any]:
        """
        Complete initial setup.

        Creates .env file with configuration and sets up pending user creation.

        Args:
            llm_provider: LLM provider ID
            llm_api_key: LLM API key
            admin_username: New admin user's username
            admin_password: New admin user's password (min 8 characters)
            llm_base_url: LLM base URL (optional)
            llm_model: LLM model name (optional)
            backup_llm_api_key: Backup LLM API key (CIRIS_OPENAI_API_KEY_2, optional)
            backup_llm_base_url: Backup LLM base URL (CIRIS_OPENAI_API_BASE_2, optional)
            backup_llm_model: Backup LLM model (CIRIS_OPENAI_MODEL_NAME_2, optional)
            template_id: Agent template ID (default: "default")
            enabled_adapters: List of enabled adapters (default: ["api"])
            adapter_config: Adapter-specific configuration (optional)
            system_admin_password: Password to update default admin (optional)
            agent_port: Agent API port (default: 8080)

        Returns:
            Success response with setup completion status
        """
        request_data = {
            "llm_provider": llm_provider,
            "llm_api_key": llm_api_key,
            "llm_base_url": llm_base_url,
            "llm_model": llm_model,
            "backup_llm_api_key": backup_llm_api_key,
            "backup_llm_base_url": backup_llm_base_url,
            "backup_llm_model": backup_llm_model,
            "template_id": template_id,
            "enabled_adapters": enabled_adapters or ["api"],
            "adapter_config": adapter_config or {},
            "admin_username": admin_username,
            "admin_password": admin_password,
            "system_admin_password": system_admin_password,
            "agent_port": agent_port,
        }

        response = await self._transport.request("POST", "/v1/setup/complete", json=request_data)
        assert response is not None
        return response

    async def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration.

        Reads current .env configuration and returns it.
        Requires authentication after setup is complete.

        Returns:
            Dictionary with current configuration
        """
        response = await self._transport.request("GET", "/v1/setup/config")
        assert response is not None
        return response

    async def update_config(self, **config_updates: Any) -> Dict[str, Any]:
        """
        Update configuration.

        Updates .env file with new configuration values.
        Requires ADMIN role or higher.

        Args:
            **config_updates: Configuration fields to update

        Returns:
            Success response
        """
        response = await self._transport.request("PUT", "/v1/setup/config", json=config_updates)
        assert response is not None
        return response
