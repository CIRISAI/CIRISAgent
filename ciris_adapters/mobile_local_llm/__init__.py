"""
Mobile Local LLM Adapter.

Runs a local OpenAI-compatible Gemma 4 inference server (LiteRT-LM,
llama.cpp, etc.) as part of the CIRIS runtime on mobile devices — Android
today, iOS as soon as Google AI Edge ships an adequate LiteRT-LM model
for iPhone/iPad — that are determined to be capable enough per the Google
AI Edge guidance.

Key modules:
- :mod:`config`           - Pydantic config + env var bindings
- :mod:`capability`       - Device tier detection (RAM, arch, platform)
- :mod:`inference_server` - Subprocess lifecycle for the local server
- :mod:`service`          - LLMServiceProtocol implementation
- :mod:`adapter`          - BaseAdapterProtocol wrapper that registers with the LLM bus
"""

from .adapter import Adapter, MobileLocalLLMAdapter
from .capability import DeviceCapabilityReport, probe_device_capability
from .config import DeviceTier, MobileLocalLLMConfig, ModelVariant, Platform, load_config_from_env
from .inference_server import InferenceServerError, InferenceServerManager
from .service import MobileLocalLLMService

__all__ = [
    "Adapter",
    "DeviceCapabilityReport",
    "DeviceTier",
    "InferenceServerError",
    "InferenceServerManager",
    "MobileLocalLLMAdapter",
    "MobileLocalLLMConfig",
    "MobileLocalLLMService",
    "ModelVariant",
    "Platform",
    "load_config_from_env",
    "probe_device_capability",
]
