"""WA CLI Wizard Service - Interactive onboarding and wizard flows."""

from pathlib import Path

from rich.console import Console
from rich.prompt import Confirm, IntPrompt, Prompt

from ciris_engine.logic.infrastructure.sub_services.wa_cli_bootstrap import WACLIBootstrapService
from ciris_engine.logic.infrastructure.sub_services.wa_cli_display import WACLIDisplayService
from ciris_engine.logic.infrastructure.sub_services.wa_cli_oauth import WACLIOAuthService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.schemas.infrastructure.wa_cli_wizard import (
    JoinRequestResult,
    OAuthConfigResult,
    RootCreationResult,
    WizardResult,
)
from ciris_engine.schemas.services.authority_core import WACertificate


class WACLIWizardService:
    """Handles interactive wizard flows for WA onboarding."""

    def __init__(
        self,
        auth_service: AuthenticationService,
        bootstrap_service: WACLIBootstrapService,
        oauth_service: WACLIOAuthService,
        display_service: WACLIDisplayService,
    ):
        """Initialize wizard service with required services."""
        self.auth_service = auth_service
        self.bootstrap_service = bootstrap_service
        self.oauth_service = oauth_service
        self.display_service = display_service
        self.console = Console()

    async def onboard_wizard(self) -> WizardResult:
        """Interactive onboarding wizard for new operators."""
        self.console.print("\n🎭 [bold cyan]Welcome to CIRIS WA Onboarding![/bold cyan]\n")

        # Check if any WAs exist
        existing_was = await self.auth_service.list_was(active_only=False)
        root_exists = any(wa.role == "root" for wa in existing_was)

        if root_exists:
            self.console.print("✅ A root WA already exists in this system.")
            self.console.print("You can:")
            self.console.print("  1. Join the existing WA tree (request approval)")
            self.console.print("  2. Stay as an observer (default)")
            self.console.print("  3. Configure OAuth login")

            choice = IntPrompt.ask("Choose an option", choices=["1", "2", "3"], default="2")

            if choice == "1":
                return self._join_wa_tree()
            elif choice == "3":
                return await self._configure_oauth()
            else:
                self.console.print("✅ You'll remain an observer. You can run this wizard again anytime.")
                return WizardResult(status="observer")
        else:
            self.console.print("🌟 No root WA exists yet!")
            self.console.print("You can:")
            self.console.print("  1. Create a new root WA (become the first authority)")
            self.console.print("  2. Import an existing root certificate")
            self.console.print("  3. Stay as an observer (default)")

            choice = IntPrompt.ask("Choose an option", choices=["1", "2", "3"], default="3")

            if choice == "1":
                return await self._create_root_wa()
            elif choice == "2":
                return await self._import_root_cert()
            else:
                self.console.print("✅ You'll remain an observer. You can run this wizard again anytime.")
                return WizardResult(status="observer")

    async def _create_root_wa(self) -> RootCreationResult:
        """Wizard flow for creating a new root WA."""
        self.console.print("\n🌱 [bold]Creating New Root WA[/bold]\n")

        # Get name
        name = Prompt.ask("Enter a name for your root WA", default="ciris_root")

        # Ask about password
        use_password = Confirm.ask("Do you want to add a password for extra security?", default=True)

        # Ask about Shamir secret sharing
        use_shamir = Confirm.ask("Enable Shamir secret sharing? (splits key into multiple parts)", default=False)
        shamir_shares = None
        if use_shamir:
            total = IntPrompt.ask("Total number of shares (2-10)", default=3)
            threshold = IntPrompt.ask(f"Threshold needed to reconstruct (must be <= {total})", default=2)
            shamir_shares = (threshold, total)

        # Create root WA
        result = await self.bootstrap_service.bootstrap_new_root(
            name=name, use_password=use_password, shamir_shares=shamir_shares
        )

        if result["status"] == "success":
            self.console.print("\n🎉 [bold green]Root WA created successfully![/bold green]")
            self.console.print("\n⚠️  [bold yellow]IMPORTANT: Back up your private key![/bold yellow]")
            self.console.print(f"Key location: {result['key_file']}")

            if shamir_shares:
                self.console.print("\n📋 Your Shamir shares have been generated.")
                self.console.print("Store each share with a different trusted person.")

        return RootCreationResult(**result)

    async def _import_root_cert(self) -> WizardResult:
        """Wizard flow for importing existing root certificate."""
        self.console.print("\n📥 [bold]Import Root Certificate[/bold]\n")

        cert_path = Prompt.ask("Path to root certificate JSON file")

        try:
            import json

            cert_data = json.loads(Path(cert_path).read_text())

            # Validate it's a root cert
            if cert_data.get("role") != "root":
                raise ValueError("Certificate is not a root WA")

            # Import the certificate
            wa_cert = WACertificate(**cert_data)
            await self.auth_service._store_wa_certificate(wa_cert)

            self.console.print("✅ Root certificate imported successfully!")
            self.console.print("⚠️  You'll need the corresponding private key to use root privileges.")

            return WizardResult(status="imported", wa_id=cert_data["wa_id"])

        except Exception as e:
            self.console.print(f"❌ Error importing certificate: {e}")
            return WizardResult(status="error", error=str(e))

    def _join_wa_tree(self) -> JoinRequestResult:
        """Wizard flow for joining existing WA tree."""
        self.console.print("\n🤝 [bold]Join Existing WA Tree[/bold]\n")

        name = Prompt.ask("Your desired WA name")
        role = Prompt.ask("Requested role", choices=["authority", "observer"], default="observer")

        # Generate join request
        result = self.bootstrap_service.generate_mint_request(name=name, requested_role=role)

        if result["status"] == "success":
            self.console.print("\n📋 Join request generated!")
            self.console.print("Share this code with an existing WA holder.")
            self.console.print("The code expires in 10 minutes.")

        return JoinRequestResult(**result)

    async def _configure_oauth(self) -> OAuthConfigResult:
        """Wizard flow for OAuth configuration."""
        self.console.print("\n🔐 [bold]Configure OAuth Provider[/bold]\n")

        providers = ["google", "discord", "github", "custom"]
        provider = Prompt.ask("Select OAuth provider", choices=providers)

        if provider == "custom":
            provider = Prompt.ask("Enter custom provider name")

        client_id = Prompt.ask(f"{provider.title()} Client ID")
        client_secret = Prompt.ask(f"{provider.title()} Client Secret", password=True)

        # Configure OAuth
        result = await self.oauth_service.oauth_setup(
            provider=provider, client_id=client_id, client_secret=client_secret
        )

        if result.status == "success":
            self.console.print("\n✅ OAuth configured successfully!")
            self.console.print("You can now login with:")
            self.console.print(f"[bold]ciris wa oauth-login {provider}[/bold]")

        return OAuthConfigResult(status=result.status, provider=result.provider or provider, error=result.error)
