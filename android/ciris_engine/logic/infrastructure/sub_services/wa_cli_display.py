"""WA CLI Display Service - Handles WA listing and visualization."""

import logging
from datetime import datetime
from typing import Any, List

from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.schemas.services.authority_core import WACertificate

logger = logging.getLogger(__name__)


class WACLIDisplayService:
    """Handles WA listing and visualization operations."""

    def __init__(self, auth_service: AuthenticationService):
        """Initialize display service with authentication service."""
        self.auth_service = auth_service
        self.console = Console()

    async def list_was(self, tree_view: bool = False) -> None:
        """List all WAs in table or tree format."""
        try:
            # Get all WAs
            all_was = await self.auth_service.list_was(active_only=False)

            if not all_was:
                self.console.print("No WAs found. Run 'ciris wa onboard' to get started.")
                return

            if tree_view:
                await self._display_tree(all_was)
            else:
                await self._display_table(all_was)

        except Exception as e:
            self.console.print(f"❌ Error listing WAs: {e}")

    async def _display_table(self, was: List[WACertificate]) -> None:
        """Display WAs in a table format."""
        table = Table(title="Wise Authorities")

        table.add_column("WA ID", style="cyan", no_wrap=True)
        table.add_column("Name", style="magenta")
        table.add_column("Role", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Status", style="blue")
        table.add_column("Created", style="dim")

        for wa in was:
            status = "✅ Active"  # Assume active if in database
            created = wa.created_at.strftime("%Y-%m-%d") if isinstance(wa.created_at, datetime) else str(wa.created_at)

            table.add_row(wa.wa_id, wa.name, wa.role.value, "certificate", status, created)  # Default token type

        self.console.print(table)

    async def _display_tree(self, was: List[WACertificate]) -> None:
        """Display WAs in a tree format showing hierarchy."""
        # Find root WAs
        roots = [wa for wa in was if not wa.parent_wa_id]

        if not roots:
            self.console.print("No root WAs found.")
            return

        # Build tree for each root
        for root in roots:
            tree = Tree(f"[bold cyan]{root.name}[/bold cyan] ({root.wa_id})")
            tree.add(f"Role: [green]{root.role.value}[/green]")
            tree.add("Type: [yellow]certificate[/yellow]")
            tree.add("Status: ✅ Active")

            # Add children recursively
            await self._add_wa_children(tree, was, root.wa_id)

            self.console.print(tree)
            self.console.print()  # Space between trees

    async def _add_wa_children(self, parent_node: Any, all_was: List[WACertificate], parent_id: str) -> None:
        """Recursively add children to tree node."""
        children = [wa for wa in all_was if wa.parent_wa_id == parent_id]

        for child in children:
            child_node = parent_node.add(f"[cyan]{child.name}[/cyan] ({child.wa_id})")
            child_node.add(f"Role: [green]{child.role.value}[/green]")
            child_node.add("Type: [yellow]certificate[/yellow]")

            if child.oauth_provider:
                child_node.add(f"OAuth: [blue]{child.oauth_provider}[/blue]")

            # Discord ID removed - not part of WACertificate schema

            child_node.add("Status: ✅ Active")

            # Recursively add this WA's children
            await self._add_wa_children(child_node, all_was, child.wa_id)

    async def show_wa_details(self, wa_id: str) -> None:
        """Display detailed information about a specific WA."""
        try:
            wa = await self.auth_service.get_wa(wa_id)
            if not wa:
                self.console.print(f"❌ WA not found: {wa_id}")
                return

            # Create details table
            table = Table(title=f"WA Details: {wa.name}", show_header=False)
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")

            # Add all fields
            table.add_row("WA ID", wa.wa_id)
            table.add_row("Name", wa.name)
            table.add_row("Role", wa.role.value)
            table.add_row("Token Type", "certificate")
            table.add_row("Public Key", wa.pubkey[:32] + "..." if len(wa.pubkey) > 32 else wa.pubkey)
            table.add_row("JWT Kid", wa.jwt_kid)

            if wa.parent_wa_id:
                table.add_row("Parent WA", wa.parent_wa_id)

            if wa.oauth_provider:
                table.add_row("OAuth Provider", wa.oauth_provider)
                table.add_row("OAuth ID", wa.oauth_external_id or "N/A")

            # Discord ID removed - not part of WACertificate schema

            if wa.adapter_id:
                table.add_row("Adapter ID", wa.adapter_id)

            # Parse and display scopes
            import json

            try:
                scopes = json.loads(wa.scopes_json)
                table.add_row("Scopes", ", ".join(scopes))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse WA scopes JSON: {e}. Displaying raw JSON string.")
                table.add_row("Scopes", wa.scopes_json)

            table.add_row("Status", "✅ Active")  # Assume active if in database
            table.add_row("Auto-minted", "Yes" if wa.auto_minted else "No")

            created = (
                wa.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                if isinstance(wa.created_at, datetime)
                else str(wa.created_at)
            )
            table.add_row("Created", created)

            if wa.last_auth:
                last_login = (
                    wa.last_auth.strftime("%Y-%m-%d %H:%M:%S UTC")
                    if isinstance(wa.last_auth, datetime)
                    else str(wa.last_auth)
                )
                table.add_row("Last Login", last_login)

            self.console.print(table)

            # Show children if any
            all_was = await self.auth_service.list_was(active_only=False)
            children = [w for w in all_was if w.parent_wa_id == wa_id]

            if children:
                self.console.print("\n[bold]Children:[/bold]")
                for child in children:
                    self.console.print(f"  • {child.name} ({child.wa_id}) - {child.role.value}")

        except Exception as e:
            self.console.print(f"❌ Error showing WA details: {e}")
