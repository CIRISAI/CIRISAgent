"""WA CLI Bootstrap Service - Handles WA creation and minting operations."""

import json
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console
from rich.prompt import Prompt

from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.authority_core import WACertificate, WARole
from ciris_engine.schemas.types import JSONDict


class WACLIBootstrapService:
    """Handles WA bootstrap and minting operations."""

    def __init__(self, auth_service: AuthenticationService, time_service: TimeService):
        """Initialize bootstrap service with authentication service."""
        self.auth_service = auth_service
        self.time_service = time_service
        self.console = Console()

    async def bootstrap_new_root(
        self, name: str, use_password: bool = False, shamir_shares: Optional[Tuple[int, int]] = None
    ) -> JSONDict:
        """Bootstrap a new root WA."""
        try:
            self.console.print(f"🌱 Creating new root WA: [bold]{name}[/bold]")

            # Generate Ed25519 keypair
            private_key, public_key = self.auth_service.generate_keypair()

            # Generate WA ID and JWT kid
            timestamp = self.time_service.now()
            wa_id = self.auth_service._generate_wa_id(timestamp)
            jwt_kid = f"wa-jwt-{wa_id[-6:].lower()}"

            # Create WA certificate
            root_wa = WACertificate(
                wa_id=wa_id,
                name=name,
                role=WARole.ROOT,
                pubkey=self.auth_service._encode_public_key(public_key),
                jwt_kid=jwt_kid,
                scopes_json='["*"]',
                created_at=timestamp,
            )

            # Add password if requested
            if use_password:
                password = Prompt.ask("Enter password for root WA", password=True)
                confirm_password = Prompt.ask("Confirm password", password=True)

                if password != confirm_password:
                    raise ValueError("Passwords do not match")

                root_wa.password_hash = self.auth_service.hash_password(password)

            # Save private key
            key_file = self.auth_service.key_dir / f"{wa_id}.key"
            key_file.write_bytes(private_key)
            key_file.chmod(0o600)

            # Store WA certificate
            await self.auth_service._store_wa_certificate(root_wa)

            self.console.print("✅ Root WA created successfully!")
            self.console.print(f"📋 WA ID: [bold]{wa_id}[/bold]")
            self.console.print(f"🔑 Private key saved to: [bold]{key_file}[/bold]")

            return {"wa_id": wa_id, "name": name, "role": "root", "key_file": str(key_file), "status": "success"}

        except Exception as e:
            self.console.print(f"❌ Error creating root WA: {e}")
            return {"status": "error", "error": str(e)}

    async def mint_wa(
        self,
        parent_wa_id: str,
        parent_key_file: str,
        name: str,
        role: str = "authority",
        scopes: Optional[List[str]] = None,
        use_password: bool = False,
    ) -> JSONDict:
        """Mint a new WA as a child of an existing WA."""
        try:
            self.console.print(f"🪙 Minting new WA: [bold]{name}[/bold]")
            self.console.print(f"👤 Parent: [bold]{parent_wa_id}[/bold]")

            # Verify parent exists and load key
            parent_wa = await self.auth_service.get_wa(parent_wa_id)
            if not parent_wa:
                raise ValueError(f"Parent WA {parent_wa_id} not found")

            # Load parent's private key
            parent_key_path = Path(parent_key_file)
            if not parent_key_path.exists():
                raise ValueError(f"Parent key file not found: {parent_key_file}")

            parent_private_key = parent_key_path.read_bytes()

            # Generate new keypair
            private_key, public_key = self.auth_service.generate_keypair()

            # Generate IDs
            timestamp = self.time_service.now()
            wa_id = self.auth_service._generate_wa_id(timestamp)
            jwt_kid = f"wa-jwt-{wa_id[-6:].lower()}"

            # Determine scopes
            if scopes is None:
                if role == "observer":
                    scopes = ["read:any", "write:message"]
                else:
                    scopes = ["wa:mint", "wa:approve", "write:task", "read:any", "write:message"]

            # Create child WA
            child_wa = WACertificate(
                wa_id=wa_id,
                name=name,
                role=WARole(role),
                pubkey=self.auth_service._encode_public_key(public_key),
                jwt_kid=jwt_kid,
                parent_wa_id=parent_wa_id,
                scopes_json=json.dumps(scopes),
                created_at=timestamp,
            )

            # Sign with parent's key
            signature_data = f"{wa_id}:{child_wa.pubkey}:{parent_wa_id}"
            parent_signature = self.auth_service.sign_data(signature_data.encode(), parent_private_key)
            child_wa.parent_signature = parent_signature

            # Add password if requested
            if use_password:
                password = Prompt.ask("Enter password for new WA", password=True)
                confirm_password = Prompt.ask("Confirm password", password=True)

                if password != confirm_password:
                    raise ValueError("Passwords do not match")

                child_wa.password_hash = self.auth_service.hash_password(password)

            # Save private key
            key_file = self.auth_service.key_dir / f"{wa_id}.key"
            key_file.write_bytes(private_key)
            key_file.chmod(0o600)

            # Store WA certificate
            await self.auth_service._store_wa_certificate(child_wa)

            self.console.print("✅ WA minted successfully!")
            self.console.print(f"📋 WA ID: [bold]{wa_id}[/bold]")
            self.console.print(f"🔑 Private key saved to: [bold]{key_file}[/bold]")
            self.console.print(f"👥 Role: [bold]{role}[/bold]")
            self.console.print(f"🔓 Scopes: {', '.join(scopes)}")

            return {
                "wa_id": wa_id,
                "name": name,
                "role": role,
                "parent_wa_id": parent_wa_id,
                "key_file": str(key_file),
                "scopes": scopes,
                "status": "success",
            }

        except Exception as e:
            self.console.print(f"❌ Error minting WA: {e}")
            return {"status": "error", "error": str(e)}

    def generate_mint_request(
        self, name: str, requested_role: str = "authority", requested_scopes: Optional[List[str]] = None
    ) -> JSONDict:
        """Generate a mint request code for approval by existing WA."""
        try:
            # Generate temporary keypair
            private_key, public_key = self.auth_service.generate_keypair()

            # Create one-time code
            code = secrets.token_urlsafe(16)

            # Store request temporarily (would normally go to DB)
            request_data = {
                "code": code,
                "name": name,
                "role": requested_role,
                "scopes": requested_scopes or ["read:any", "write:message"],
                "pubkey": self.auth_service._encode_public_key(public_key),
                "created": self.time_service.now().isoformat(),
                "expires": (self.time_service.now() + timedelta(minutes=10)).isoformat(),
            }

            # Save private key temporarily
            temp_key_file = self.auth_service.key_dir / f"pending_{code}.key"
            temp_key_file.write_bytes(private_key)
            temp_key_file.chmod(0o600)

            self.console.print("📋 Mint request generated!")
            self.console.print(f"🔑 One-time code: [bold yellow]{code}[/bold yellow]")
            self.console.print("⏰ Expires in 10 minutes")
            self.console.print("\nShare this code with an existing WA holder.")
            self.console.print("They should run: [bold]ciris wa approve-code[/bold]")

            return {"status": "success", "code": code, "request": request_data}

        except Exception as e:
            self.console.print(f"❌ Error generating mint request: {e}")
            return {"status": "error", "error": str(e)}

    def approve_mint_request(self, code: str, approver_wa_id: str, _approver_key_file: str) -> JSONDict:
        """Approve a mint request and create new WA."""
        try:
            # In production, would fetch from DB
            # For now, mock the approval
            self.console.print("✅ Mint request approved!")
            self.console.print(f"📋 Code: [bold]{code}[/bold]")
            self.console.print(f"👤 Approver: [bold]{approver_wa_id}[/bold]")

            return {"status": "success", "message": "Mint request approved (mock implementation)"}

        except Exception as e:
            self.console.print(f"❌ Error approving mint request: {e}")
            return {"status": "error", "error": str(e)}
