import importlib
import logging

from ciris_engine.protocols.runtime.base import BaseAdapterProtocol

__all__ = ["load_adapter", "BaseAdapterProtocol"]

logger = logging.getLogger(__name__)


def _validate_adapter_class(adapter_class: type, mode: str) -> None:
    """Validate that adapter class implements required methods."""
    required_methods = ["get_services_to_register", "start", "run_lifecycle", "stop", "__init__"]
    for method_name in required_methods:
        if not hasattr(adapter_class, method_name):
            logger.error(f"Adapter class for mode '{mode}' is missing required method '{method_name}'.")
            raise AttributeError(
                f"Adapter class for mode '{mode}' does not fully implement BaseAdapterProtocol (missing {method_name})."
            )


def _refuse_unadmitted_unit(module_path: str, mode: str) -> None:
    """Code admission before the import (rc21 CC 2.7.11).

    ``ciris_adapters.<mode>`` normally resolves inside the installed package (the
    attested build) and this is a no-op. If it resolves anywhere else, the unit
    is beyond the build and loads only under a live admission:unit row.
    """
    import importlib.util
    from pathlib import Path

    try:
        spec = importlib.util.find_spec(module_path)
    except (ImportError, ValueError):
        return
    if spec is None or not spec.origin:
        return
    from ciris_engine.logic.infrastructure.authorization.unit_admission import check_unit_load_sync

    unit_dir = Path(spec.origin).parent
    decision = check_unit_load_sync(unit_dir, mode)
    if decision is not None and not decision.admitted:
        raise ValueError(f"Adapter '{mode}' is not admitted on this host: {decision.message()}")


def load_adapter(mode: str) -> type[BaseAdapterProtocol]:
    """Dynamically imports and returns the adapter class for the given mode.

    Searches in both core adapters (ciris_engine.logic.adapters) and
    modular adapters (ciris_adapters) directories.
    """
    logger.debug(f"Attempting to load adapter for mode: {mode}")

    # Search locations in order of priority
    search_paths = [
        (f".{mode}", __name__),  # Core: ciris_engine.logic.adapters.{mode}
        (f"ciris_adapters.{mode}", None),  # Modular: ciris_adapters.{mode}
    ]

    last_import_error = None
    for module_path, package in search_paths:
        try:
            if not package:
                _refuse_unadmitted_unit(module_path, mode)
            if package:
                adapter_module = importlib.import_module(module_path, package=package)
            else:
                adapter_module = importlib.import_module(module_path)

            adapter_class = getattr(adapter_module, "Adapter")
            _validate_adapter_class(adapter_class, mode)

            location = "core" if package else "modular"
            logger.info(f"Successfully loaded adapter for mode '{mode}' from {location} adapters")
            return adapter_class  # type: ignore[no-any-return]

        except ImportError as e:
            last_import_error = e
            logger.debug(f"Adapter '{mode}' not found at {module_path}: {e}")
            continue
        except AttributeError as e:
            logger.error(
                f"Could not load 'Adapter' class or method from mode '{mode}'. Attribute error: {e}", exc_info=True
            )
            raise ValueError(
                f"Could not load 'Adapter' class from mode '{mode}' or it's missing BaseAdapterProtocol methods. "
                "Ensure it's defined and implements BaseAdapterProtocol."
            ) from e

    # If we get here, adapter wasn't found in any location
    logger.error(f"Could not import adapter module for mode '{mode}'. Import error: {last_import_error}", exc_info=True)
    raise ValueError(
        f"Could not import adapter module for mode '{mode}'. "
        f"Searched in ciris_engine.logic.adapters.{mode} and ciris_adapters.{mode}. "
        "Ensure the adapter exists and is correctly structured."
    ) from last_import_error
