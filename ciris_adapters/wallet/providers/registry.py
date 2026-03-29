"""
Lazy Provider Registry.

Loads wallet providers on-demand to minimize memory footprint.
Only the providers actually used get imported and instantiated.
"""

import importlib
import logging
from typing import Any, Callable, Dict, Optional, Type

logger = logging.getLogger(__name__)


# Provider module paths - providers are imported lazily from these paths
PROVIDER_MODULES: Dict[str, str] = {
    "x402": "ciris_adapters.wallet.providers.x402_provider",
    "chapa": "ciris_adapters.wallet.providers.chapa_provider",
    "mpesa": "ciris_adapters.wallet.providers.mpesa_provider",
    "razorpay": "ciris_adapters.wallet.providers.razorpay_provider",
    "pix": "ciris_adapters.wallet.providers.pix_provider",
    "wise": "ciris_adapters.wallet.providers.wise_provider",
    "stripe": "ciris_adapters.wallet.providers.stripe_provider",
}

# Provider class names within each module
PROVIDER_CLASSES: Dict[str, str] = {
    "x402": "X402Provider",
    "chapa": "ChapaProvider",
    "mpesa": "MPesaProvider",
    "razorpay": "RazorpayProvider",
    "pix": "PIXProvider",
    "wise": "WiseProvider",
    "stripe": "StripeProvider",
}

# Config class names for each provider
CONFIG_CLASSES: Dict[str, str] = {
    "x402": "X402ProviderConfig",
    "chapa": "ChapaProviderConfig",
    "mpesa": "MPesaProviderConfig",
    "razorpay": "RazorpayProviderConfig",
    "pix": "PIXProviderConfig",
    "wise": "WiseProviderConfig",
    "stripe": "StripeProviderConfig",
}

# Cached loaded modules to avoid re-importing
_loaded_modules: Dict[str, Any] = {}
_loaded_classes: Dict[str, Type[Any]] = {}


class ProviderLoadError(Exception):
    """Raised when a provider fails to load."""
    pass


def get_available_providers() -> list[str]:
    """Get list of all registered provider names."""
    return list(PROVIDER_MODULES.keys())


def is_provider_available(provider_name: str) -> bool:
    """Check if a provider is registered (doesn't load it)."""
    return provider_name in PROVIDER_MODULES


def get_provider_class(provider_name: str) -> Type[Any]:
    """
    Lazily load and return a provider class.

    Args:
        provider_name: Name of the provider (e.g., "x402", "mpesa")

    Returns:
        The provider class (not an instance)

    Raises:
        ProviderLoadError: If provider not found or fails to load
    """
    if provider_name not in PROVIDER_MODULES:
        raise ProviderLoadError(
            f"Unknown provider: {provider_name}. "
            f"Available: {list(PROVIDER_MODULES.keys())}"
        )

    # Return cached class if already loaded
    if provider_name in _loaded_classes:
        return _loaded_classes[provider_name]

    module_path = PROVIDER_MODULES[provider_name]
    class_name = PROVIDER_CLASSES[provider_name]

    try:
        logger.debug(f"Lazy loading provider: {provider_name} from {module_path}")

        # Import the module
        if module_path not in _loaded_modules:
            _loaded_modules[module_path] = importlib.import_module(module_path)

        module = _loaded_modules[module_path]

        # Get the provider class
        if not hasattr(module, class_name):
            raise ProviderLoadError(
                f"Module {module_path} does not have class {class_name}"
            )

        provider_class: Type[Any] = getattr(module, class_name)
        _loaded_classes[provider_name] = provider_class

        logger.info(f"Loaded provider: {provider_name}")
        return provider_class

    except ImportError as e:
        raise ProviderLoadError(
            f"Failed to import {provider_name} provider from {module_path}: {e}"
        ) from e
    except Exception as e:
        raise ProviderLoadError(
            f"Failed to load {provider_name} provider: {e}"
        ) from e


def create_provider(
    provider_name: str,
    config: Any,
    **kwargs: Any,
) -> Any:
    """
    Lazily create a provider instance.

    Args:
        provider_name: Name of the provider
        config: Provider-specific configuration object
        **kwargs: Additional arguments passed to provider constructor

    Returns:
        Initialized provider instance
    """
    provider_class = get_provider_class(provider_name)
    return provider_class(config=config, **kwargs)


def get_loaded_providers() -> list[str]:
    """Get list of currently loaded provider names."""
    return list(_loaded_classes.keys())


def unload_provider(provider_name: str) -> bool:
    """
    Unload a provider from cache (for testing/memory management).

    Note: This doesn't unload the module from sys.modules,
    just removes from our cache so it will be re-imported if needed.

    Returns:
        True if provider was unloaded, False if it wasn't loaded
    """
    if provider_name in _loaded_classes:
        del _loaded_classes[provider_name]
        logger.debug(f"Unloaded provider class: {provider_name}")
        return True
    return False


def clear_cache() -> None:
    """Clear all cached modules and classes (for testing)."""
    _loaded_modules.clear()
    _loaded_classes.clear()
    logger.debug("Provider registry cache cleared")
