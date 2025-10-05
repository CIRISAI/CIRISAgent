"""
Configuration resource for CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..exceptions import CIRISAPIError
from ..models import ConfigItem, ConfigOperationResponse, ConfigValue
from ..transport import Transport


class ConfigResource:
    """Client for interacting with CIRIS configuration endpoints.

    This client handles the simplified /v1/config endpoints with
    transparent role-based filtering for sensitive configuration.
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def list_configs(self, include_sensitive: bool = False) -> List[ConfigItem]:
        """List all configuration items.

        Args:
            include_sensitive: Whether to include sensitive configs (requires appropriate role)

        Returns:
            List of configuration items with their current values

        Note:
            Sensitive configurations will be automatically redacted based on
            the authenticated user's role. Use include_sensitive=True to attempt
            to retrieve sensitive values (requires ADMIN role or higher).
        """
        params = {}
        if include_sensitive:
            params["include_sensitive"] = "true"

        data = await self._transport.request("GET", "/v1/config", params=params)

        # Handle both dict and list responses
        if isinstance(data, dict):
            # Convert dict to list of ConfigItems
            configs = []
            for key, value in data.items():
                configs.append(ConfigItem(key=key, value=value, description=None, sensitive=False, redacted=False))
            return configs
        else:
            # Assume it's already a list
            assert data is not None, "Response data should not be None"
            configs = []
            for item in data:
                configs.append(ConfigItem(**item))
            return configs

    async def get_config(self, key: str) -> ConfigValue:
        """Get a specific configuration value by key.

        Args:
            key: The configuration key to retrieve

        Returns:
            The configuration value

        Raises:
            CIRISAPIError: If the configuration key does not exist

        Note:
            Sensitive values will be automatically redacted based on
            the authenticated user's role.
        """
        data = await self._transport.request("GET", f"/v1/config/{key}")
        # Handle SuccessResponse wrapper
        assert data is not None, "Response data should not be None"
        if "data" in data:
            data = data["data"]
        # Return ConfigValue with the right fields
        assert data is not None, "Response data['data'] should not be None"
        return ConfigValue(
            key=data.get("key", key),
            value=data.get("value"),
            description=data.get("description"),
            sensitive=data.get("is_sensitive", False),
            last_modified=data.get("updated_at"),
            modified_by=data.get("updated_by"),
        )

    async def set_config(
        self, key: str, value: Any, description: Optional[str] = None, sensitive: bool = False
    ) -> ConfigOperationResponse:
        """Set or update a configuration value using PATCH.

        Uses PATCH for partial updates, allowing you to update just the value
        without affecting other properties like description or sensitivity.

        Args:
            key: The configuration key to set
            value: The value to set (can be any JSON-serializable type)
            description: Optional description of the configuration
            sensitive: Whether this configuration contains sensitive data

        Returns:
            Response indicating success/failure of the operation

        Note:
            Setting configuration requires appropriate permissions.
            Sensitive configurations require ADMIN role or higher.

        Example:
            # Update just the value
            await client.config.set_config("api.timeout", 30)

            # Set with description
            await client.config.set_config(
                "api.key",
                "secret123",
                description="API key for external service",
                sensitive=True
            )
        """
        payload = {"value": value, "sensitive": sensitive}
        if description:
            payload["description"] = description

        # Use PUT for updates (API doesn't support PATCH yet)
        data = await self._transport.request("PUT", f"/v1/config/{key}", json=payload)

        # Convert ConfigItemResponse to ConfigOperationResponse
        assert data is not None, "Response data should not be None"
        if "key" in data and "value" in data:
            # This is a ConfigItemResponse, convert it
            return ConfigOperationResponse(
                success=True,
                operation="set",
                timestamp=data.get("updated_at", datetime.now().isoformat()),
                key=data.get("key"),
                new_value=data.get("value"),
                message=f"Config '{key}' updated successfully",
            )
        else:
            # Already in the expected format
            return ConfigOperationResponse(**data)

    async def delete_config(self, key: str) -> ConfigOperationResponse:
        """Delete a configuration key.

        Args:
            key: The configuration key to delete

        Returns:
            Response indicating success/failure of the operation

        Note:
            Deleting configuration requires ADMIN role or higher.
            Some system configurations may be protected from deletion.
        """
        data = await self._transport.request("DELETE", f"/v1/config/{key}")
        assert data is not None, "Response data should not be None"
        return ConfigOperationResponse(**data)

    async def update_config(self, key: str, value: Any, description: Optional[str] = None) -> ConfigOperationResponse:
        """Update an existing configuration value.

        This is an alias for set_config() for convenience.

        Args:
            key: The configuration key to update
            value: The new value
            description: Optional updated description

        Returns:
            Response indicating success/failure of the operation
        """
        return await self.set_config(key, value, description)

    async def patch_config(
        self, key: str, patches: List[Dict[str, Any]], patch_format: str = "merge"
    ) -> ConfigOperationResponse:
        """Apply JSON patch operations to a configuration.

        Supports two patch formats:
        - "merge": JSON Merge Patch (RFC 7396) - simple partial updates
        - "json-patch": JSON Patch (RFC 6902) - complex operations

        Args:
            key: The configuration key to patch
            patches: List of patch operations (format depends on patch_format)
            patch_format: Either "merge" or "json-patch"

        Returns:
            Response indicating success/failure of the operation

        Examples:
            # Merge patch (simple partial update)
            await client.config.patch_config(
                "database",
                [{"pool_size": 50, "timeout": 30}],
                patch_format="merge"
            )

            # JSON Patch (complex operations)
            await client.config.patch_config(
                "features",
                [
                    {"op": "add", "path": "/new_feature", "value": True},
                    {"op": "remove", "path": "/old_feature"},
                    {"op": "replace", "path": "/beta_feature", "value": False}
                ],
                patch_format="json-patch"
            )
        """
        headers = {}
        payload: Any
        if patch_format == "json-patch":
            headers["Content-Type"] = "application/json-patch+json"
            payload = patches
        else:
            headers["Content-Type"] = "application/merge-patch+json"
            payload = patches[0] if len(patches) == 1 else {"patches": patches}

        data = await self._transport.request("PATCH", f"/v1/config/{key}", json=payload, headers=headers)
        assert data is not None, "Response data should not be None"
        return ConfigOperationResponse(**data)

    async def bulk_set(self, configs: Dict[str, Any]) -> Dict[str, ConfigOperationResponse]:
        """Set multiple configuration values at once.

        Args:
            configs: Dictionary mapping configuration keys to values

        Returns:
            Dictionary mapping keys to their operation responses

        Note:
            This performs individual set operations for each config.
            Partial success is possible - check individual responses.
        """
        results = {}
        for key, value in configs.items():
            try:
                results[key] = await self.set_config(key, value)
            except CIRISAPIError as e:
                # Create error response for failed operations
                results[key] = ConfigOperationResponse(
                    success=False,
                    operation="set",
                    timestamp=datetime.now().isoformat(),
                    message=str(e),
                    key=key,
                )
        return results

    async def search_configs(self, pattern: str) -> List[ConfigItem]:
        """Search for configuration keys matching a pattern.

        Args:
            pattern: Search pattern (supports wildcards)

        Returns:
            List of matching configuration items

        Note:
            This is a client-side search that first fetches all configs
            then filters them. For large config sets, consider pagination.
        """
        all_configs = await self.list_configs()

        # Simple pattern matching (could be enhanced)
        import fnmatch

        matching = []
        for config in all_configs:
            if fnmatch.fnmatch(config.key.lower(), pattern.lower()):
                matching.append(config)

        return matching

    # Aliases for backward compatibility with tests
    async def get_all(self) -> Dict[str, Any]:
        """Get all configuration as a dictionary. Alias for list_configs."""
        configs = await self.list_configs()
        return {config.key: config.value for config in configs}

    async def get(self, key: str) -> Any:
        """Get configuration value by key. Alias for get_config."""
        config = await self.get_config(key)
        # Extract the actual value from nested structure
        if isinstance(config.value, dict):
            # Check if this is a full node object
            if "value" in config.value and isinstance(config.value["value"], dict):
                # This is a ConfigNode with nested ConfigValue
                config_value = config.value["value"]
                # Extract the actual value from ConfigValue
                for field_name, field_value in config_value.items():
                    if field_value is not None:
                        return field_value
            else:
                # Direct ConfigValue dict
                for field_name, field_value in config.value.items():
                    if field_value is not None:
                        return field_value
        return config.value

    async def set(self, key: str, value: Any) -> Any:
        """Set configuration value. Alias for set_config."""
        result = await self.set_config(key, value)
        # Return just the value for backward compatibility
        if hasattr(result, "new_value"):
            return result.new_value
        return value
