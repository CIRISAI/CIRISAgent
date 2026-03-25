"""
Wallet Adapter for CIRIS.

Provides generic money tools (send_money, request_money, get_statement)
that work across crypto (x402/USDC) and fiat (Chapa/ETB) providers.

This adapter follows the CIRIS adapter pattern:
- Tool service registered with ToolBus
- Provider-agnostic interface
- DMA-gated financial operations
"""

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.adapters import AdapterServiceRegistration
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType

from .config import ChapaProviderConfig, WalletAdapterConfig, X402ProviderConfig
from .providers.chapa_provider import ChapaProvider
from .providers.x402_provider import X402Provider
from .tool_service import WalletToolService

logger = logging.getLogger(__name__)


class WalletAdapter(Service):
    """
    Wallet adapter platform for CIRIS.

    Provides generic money tools that abstract crypto and fiat payments:
    - send_money: Send to any recipient (USDC address, phone number, etc.)
    - request_money: Create payment requests/invoices
    - get_statement: Check balance and transaction history

    The implementation routes to the appropriate provider based on currency
    or explicit provider_params.
    """

    def __init__(
        self,
        runtime: Any,
        context: Optional[Any] = None,
        config: Optional[WalletAdapterConfig] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Wallet adapter."""
        super().__init__(config=kwargs.get("adapter_config"))
        self.runtime = runtime
        self.context = context

        # Load configuration
        self.adapter_config = config or self._load_config_from_env()

        # Initialize providers
        self._providers: Dict[str, Any] = {}
        self._init_providers()

        # Create tool service
        self.tool_service = WalletToolService(
            config=self.adapter_config,
            providers=self._providers,
        )

        # Track adapter state
        self._running = False

        logger.info(
            f"Wallet adapter initialized with providers: {list(self._providers.keys())}"
        )

    def _load_config_from_env(self) -> WalletAdapterConfig:
        """Load configuration from environment variables."""
        x402_config = X402ProviderConfig(
            enabled=os.getenv("WALLET_X402_ENABLED", "true").lower() == "true",
            network=os.getenv("WALLET_X402_NETWORK", "base-sepolia"),
            treasury_address=os.getenv("WALLET_X402_TREASURY_ADDRESS"),
            facilitator_url=os.getenv(
                "WALLET_X402_FACILITATOR_URL", "https://x402.org/facilitator"
            ),
        )

        chapa_secret = os.getenv("WALLET_CHAPA_SECRET_KEY")
        chapa_config = ChapaProviderConfig(
            enabled=os.getenv("WALLET_CHAPA_ENABLED", "true").lower() == "true",
            secret_key=chapa_secret if chapa_secret else None,
            callback_base_url=os.getenv("WALLET_CHAPA_CALLBACK_URL"),
            merchant_name=os.getenv("WALLET_CHAPA_MERCHANT_NAME", "CIRIS"),
        )

        return WalletAdapterConfig(
            x402=x402_config,
            chapa=chapa_config,
            default_provider=os.getenv("WALLET_DEFAULT_PROVIDER", "x402"),
        )

    def _init_providers(self) -> None:
        """Initialize enabled wallet providers."""
        # Initialize x402 provider if enabled
        if self.adapter_config.x402.enabled:
            # In production, Ed25519 seed comes from CIRISVerify secure element
            # For now, use a test seed or derive from environment
            ed25519_seed = self._get_ed25519_seed()
            x402_provider = X402Provider(
                config=self.adapter_config.x402,
                ed25519_seed=ed25519_seed,
            )
            self._providers["x402"] = x402_provider
            logger.info("x402 provider configured")

        # Initialize Chapa provider if enabled
        if self.adapter_config.chapa.enabled:
            chapa_provider = ChapaProvider(config=self.adapter_config.chapa)
            self._providers["chapa"] = chapa_provider
            logger.info("Chapa provider configured")

    def _get_ed25519_seed(self) -> Optional[bytes]:
        """
        Get Ed25519 seed for wallet derivation.

        In production, this comes from CIRISVerify secure element.
        For testing, can use environment variable or generate deterministically.
        """
        # Check for test seed in environment
        seed_hex = os.getenv("WALLET_ED25519_SEED")
        if seed_hex:
            try:
                return bytes.fromhex(seed_hex)
            except ValueError:
                logger.warning("Invalid WALLET_ED25519_SEED format")

        # TODO: Get from CIRISVerify in production
        # For now, return None which will use placeholder
        return None

    def get_services_to_register(self) -> List[AdapterServiceRegistration]:
        """
        Get services provided by this adapter.

        Returns TOOL service registration for wallet operations.
        """
        registrations = []

        # Register TOOL service for wallet operations
        registrations.append(
            AdapterServiceRegistration(
                service_type=ServiceType.TOOL,
                provider=self.tool_service,
                priority=Priority.NORMAL,
                capabilities=[
                    "execute_tool",
                    "get_available_tools",
                    "send_money",
                    "request_money",
                    "get_statement",
                    "provider:wallet",
                ],
            )
        )

        return registrations

    async def start(self) -> None:
        """Start the Wallet adapter."""
        logger.info("Starting Wallet adapter")

        # Start tool service (which initializes providers)
        await self.tool_service.start()
        logger.info("WalletToolService started")

        self._running = True
        logger.info("Wallet adapter started")

    async def stop(self) -> None:
        """Stop the Wallet adapter."""
        logger.info("Stopping Wallet adapter")
        self._running = False

        # Stop tool service (which cleans up providers)
        await self.tool_service.stop()

        logger.info("Wallet adapter stopped")

    async def run_lifecycle(self, agent_task: Any) -> None:
        """
        Run the adapter lifecycle.

        For Wallet, we just wait for the agent task to complete.
        Payment operations are request-driven, not continuous.
        """
        logger.info("Wallet adapter lifecycle started")
        try:
            await agent_task
        except asyncio.CancelledError:
            logger.info("Wallet adapter lifecycle cancelled")
        finally:
            await self.stop()

    def get_config(self) -> AdapterConfig:
        """Get adapter configuration."""
        return AdapterConfig(
            adapter_type="wallet",
            enabled=self._running,
            settings={
                "providers": list(self._providers.keys()),
                "x402_network": self.adapter_config.x402.network,
                "chapa_enabled": self.adapter_config.chapa.enabled,
            },
        )

    def get_status(self) -> RuntimeAdapterStatus:
        """Get adapter status."""
        return RuntimeAdapterStatus(
            adapter_id="wallet",
            adapter_type="wallet",
            is_running=self._running,
            loaded_at=None,
            error=None,
        )

    async def get_active_channels(self) -> List[Dict[str, Any]]:
        """Get active channels (not applicable for wallet adapter)."""
        return []


# Export as Adapter for load_adapter() compatibility
Adapter = WalletAdapter
