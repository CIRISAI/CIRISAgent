"""
Configuration schemas for the Mobile Local LLM adapter.

Runs a local OpenAI-compatible Gemma 4 inference server on mobile devices
(Android today, iOS when an adequate LiteRT-LM build is available) that
are determined to be capable enough per the Google AI Edge guidance.

All configuration is strongly typed via Pydantic - no Dict[str, Any].
Values are read from environment variables at runtime so they can be
injected from the mobile harness or the interactive configuration wizard.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Environment variable names (single source of truth)
# ---------------------------------------------------------------------------

ENV_ENABLED = "CIRIS_MOBILE_LOCAL_LLM_ENABLED"
ENV_MODEL_VARIANT = "CIRIS_MOBILE_LOCAL_LLM_MODEL"
ENV_MODEL_PATH = "CIRIS_MOBILE_LOCAL_LLM_MODEL_PATH"
ENV_SERVER_BINARY = "CIRIS_MOBILE_LOCAL_LLM_SERVER_BINARY"
ENV_SERVER_HOST = "CIRIS_MOBILE_LOCAL_LLM_HOST"
ENV_SERVER_PORT = "CIRIS_MOBILE_LOCAL_LLM_PORT"
ENV_READY_TIMEOUT = "CIRIS_MOBILE_LOCAL_LLM_READY_TIMEOUT"
ENV_REQUEST_TIMEOUT = "CIRIS_MOBILE_LOCAL_LLM_REQUEST_TIMEOUT"
ENV_HEALTH_INTERVAL = "CIRIS_MOBILE_LOCAL_LLM_HEALTH_INTERVAL"
ENV_MIN_RAM_GB = "CIRIS_MOBILE_LOCAL_LLM_MIN_RAM_GB"
ENV_MIN_FREE_DISK_GB = "CIRIS_MOBILE_LOCAL_LLM_MIN_FREE_DISK_GB"
ENV_FORCE_CAPABILITY = "CIRIS_MOBILE_LOCAL_LLM_FORCE_CAPABILITY"
ENV_ALLOW_DESKTOP = "CIRIS_MOBILE_LOCAL_LLM_ALLOW_DESKTOP"
ENV_IOS_STUB_MODEL_PATH = "CIRIS_MOBILE_LOCAL_LLM_IOS_MODEL_PATH"


class ModelVariant(str, Enum):
    """Gemma 4 mobile variants supported by this adapter.

    Values match the variant names used by the Google AI Edge / LiteRT-LM
    documentation. The tier also governs the minimum device capability
    required before the adapter will start the inference server.
    """

    GEMMA_4_E2B = "gemma-4-e2b"  # ~1.5 GB, works on capable mid/high-tier phones
    GEMMA_4_E4B = "gemma-4-e4b"  # heavier variant, high-end phones only


class DeviceTier(str, Enum):
    """Outcome of the capability probe for a device.

    ``IOS_STUB`` is a distinct value because on iOS we can detect a capable
    device (enough RAM, arm64, recent OS) but Google AI Edge / LiteRT-LM
    does not yet ship an adequate on-device model in every configuration.
    The wizard surfaces iOS-stub devices differently so the user knows the
    path exists but is not yet active.

    ``DESKTOP_CAPABLE`` indicates a desktop system with enough RAM/disk to
    run llama.cpp with Gemma4. Unlike mobile, desktop doesn't auto-start
    the server - the user must opt in via the wizard.
    """

    CAPABLE_E4B = "capable_e4b"  # can run the heavier E4B model
    CAPABLE_E2B = "capable_e2b"  # can run E2B reliably
    DESKTOP_CAPABLE = "desktop_capable"  # desktop with enough RAM/disk for llama.cpp
    IOS_STUB = "ios_stub"  # iOS device that would be capable, model not yet available
    INCAPABLE = "incapable"  # local inference is not safe on this device


class Platform(str, Enum):
    """Mobile-aware platform identifier used by the capability probe."""

    ANDROID = "android"
    IOS = "ios"
    DESKTOP = "desktop"
    UNKNOWN = "unknown"


class MobileLocalLLMConfig(BaseModel):
    """Typed configuration for the mobile local LLM adapter."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    # --- Feature gate -------------------------------------------------------
    enabled: bool = Field(
        default=True,
        description="Master switch. When False the adapter loads but never starts the server.",
    )

    # --- Model selection ----------------------------------------------------
    model_variant: ModelVariant = Field(
        default=ModelVariant.GEMMA_4_E2B,
        description="Gemma 4 variant to load. Start with E2B on mobile per Google AI Edge guidance.",
    )
    model_path: Optional[Path] = Field(
        default=None,
        description=(
            "Path to the LiteRT-LM model bundle on disk. If None the adapter "
            "looks in the default on-device model directory."
        ),
    )

    # --- Inference server binary -------------------------------------------
    server_binary: Optional[Path] = Field(
        default=None,
        description=(
            "Absolute path to the local inference server binary (e.g. LiteRT-LM "
            "or llama.cpp 'server'). Required when the adapter must spawn the "
            "server itself. If None and the server is already running at host:port "
            "the adapter will attach instead of spawning."
        ),
    )
    server_extra_args: List[str] = Field(
        default_factory=list,
        description="Extra CLI arguments passed to the inference server binary.",
    )

    # --- Network transport --------------------------------------------------
    host: str = Field(
        default="127.0.0.1",
        description="Host the local inference server binds to. Must stay on loopback by default.",
    )
    port: int = Field(
        default=8091,
        ge=1024,
        le=65535,
        description="Port the local inference server listens on for OpenAI-compatible requests.",
    )

    # --- Timeouts and probing ----------------------------------------------
    ready_timeout_seconds: float = Field(
        default=30.0,
        gt=0.0,
        description="How long to wait for the server to become healthy after start().",
    )
    request_timeout_seconds: float = Field(
        default=60.0,
        gt=0.0,
        description="Per-request timeout for inference calls.",
    )
    health_interval_seconds: float = Field(
        default=15.0,
        gt=0.0,
        description="Interval between background health probes while the adapter is running.",
    )

    # --- Device capability gates -------------------------------------------
    min_total_ram_gb_e2b: float = Field(
        default=6.0,
        gt=0.0,
        description="Minimum total RAM (GB) required to run the E2B variant safely.",
    )
    min_total_ram_gb_e4b: float = Field(
        default=8.0,
        gt=0.0,
        description="Minimum total RAM (GB) required to run the E4B variant safely.",
    )
    min_free_disk_gb: float = Field(
        default=3.0,
        gt=0.0,
        description="Minimum free disk space (GB) required before model download/load.",
    )

    # --- iOS-specific -------------------------------------------------------
    ios_model_path: Optional[Path] = Field(
        default=None,
        description=(
            "Expected path to the iOS Gemma 4 model bundle. When unset or the "
            "path does not exist the adapter reports the device as IOS_STUB "
            "so the wizard can show 'coming soon' rather than offering a "
            "broken local option."
        ),
    )

    # --- Escape hatches (for testing / power users) ------------------------
    force_capability: Optional[DeviceTier] = Field(
        default=None,
        description="Override the capability probe. Only use for testing or known-good devices.",
    )
    allow_desktop: bool = Field(
        default=False,
        description="Allow the adapter to run on desktop platforms (development / QA only).",
    )

    @field_validator("host")
    @classmethod
    def _validate_host(cls, value: str) -> str:
        """Safety rail: block accidental empty bind host."""
        if not value:
            raise ValueError("host must not be empty")
        return value

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def base_url(self) -> str:
        """OpenAI-compatible base URL for the local server."""
        return f"http://{self.host}:{self.port}/v1"

    def health_url(self) -> str:
        """HTTP URL the adapter probes to confirm the server is up."""
        return f"http://{self.host}:{self.port}/health"

    def required_ram_gb(self) -> float:
        """Minimum RAM required for the configured model variant."""
        if self.model_variant == ModelVariant.GEMMA_4_E4B:
            return self.min_total_ram_gb_e4b
        return self.min_total_ram_gb_e2b


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def _env_tier(name: str) -> Optional[DeviceTier]:
    raw = os.environ.get(name)
    if not raw:
        return None
    try:
        return DeviceTier(raw.strip().lower())
    except ValueError:
        return None


def _env_variant(name: str, default: ModelVariant) -> ModelVariant:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return ModelVariant(raw.strip().lower())
    except ValueError:
        return default


def load_config_from_env() -> MobileLocalLLMConfig:
    """Build a config instance from environment variables.

    This mirrors the pattern used by the wallet and mock_llm adapters: the
    interactive configurable adapter writes env vars, and the service reads
    them here. Anything unset falls back to the defaults on the model.
    """
    defaults = MobileLocalLLMConfig()
    return MobileLocalLLMConfig(
        enabled=_env_bool(ENV_ENABLED, defaults.enabled),
        model_variant=_env_variant(ENV_MODEL_VARIANT, defaults.model_variant),
        model_path=_env_path(ENV_MODEL_PATH),
        server_binary=_env_path(ENV_SERVER_BINARY),
        host=os.environ.get(ENV_SERVER_HOST, defaults.host),
        port=_env_int(ENV_SERVER_PORT, defaults.port),
        ready_timeout_seconds=_env_float(ENV_READY_TIMEOUT, defaults.ready_timeout_seconds),
        request_timeout_seconds=_env_float(ENV_REQUEST_TIMEOUT, defaults.request_timeout_seconds),
        health_interval_seconds=_env_float(ENV_HEALTH_INTERVAL, defaults.health_interval_seconds),
        min_total_ram_gb_e2b=_env_float(ENV_MIN_RAM_GB, defaults.min_total_ram_gb_e2b),
        min_free_disk_gb=_env_float(ENV_MIN_FREE_DISK_GB, defaults.min_free_disk_gb),
        ios_model_path=_env_path(ENV_IOS_STUB_MODEL_PATH),
        force_capability=_env_tier(ENV_FORCE_CAPABILITY),
        allow_desktop=_env_bool(ENV_ALLOW_DESKTOP, defaults.allow_desktop),
    )


__all__ = [
    "MobileLocalLLMConfig",
    "DeviceTier",
    "ModelVariant",
    "Platform",
    "load_config_from_env",
    # Env var names
    "ENV_ENABLED",
    "ENV_MODEL_VARIANT",
    "ENV_MODEL_PATH",
    "ENV_SERVER_BINARY",
    "ENV_SERVER_HOST",
    "ENV_SERVER_PORT",
    "ENV_READY_TIMEOUT",
    "ENV_REQUEST_TIMEOUT",
    "ENV_HEALTH_INTERVAL",
    "ENV_MIN_RAM_GB",
    "ENV_MIN_FREE_DISK_GB",
    "ENV_FORCE_CAPABILITY",
    "ENV_ALLOW_DESKTOP",
    "ENV_IOS_STUB_MODEL_PATH",
]
