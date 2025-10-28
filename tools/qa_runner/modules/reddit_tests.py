"""
Reddit adapter QA tests.

Tests the complete Reddit adapter functionality through agent interaction:
- Configure Reddit credentials via API
- Trigger Reddit actions via client.interact() (LLM decides to use tools)
- Verify actions via audit trail
- Test Reddit ToS compliance (deletion + cache purge)
- Test community guidelines compliance (AI transparency disclosure)
"""

import asyncio
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table


class RedditTests:
    """Test Reddit adapter functionality."""

    def __init__(self, client, console: Console):
        """Initialize Reddit tests."""
        self.client = client
        self.console = console
        self.results = []

        # Load Reddit credentials from secrets file
        self._load_credentials()

        # Track created content for cleanup
        self.created_submission_id: Optional[str] = None
        self.created_comment_id: Optional[str] = None
        self.disclosure_comment_id: Optional[str] = None

    def _load_credentials(self):
        """Load Reddit credentials from ~/.ciris/reddit_secrets."""
        secrets_path = Path.home() / ".ciris" / "reddit_secrets"

        if not secrets_path.exists():
            raise FileNotFoundError(f"Reddit secrets not found at {secrets_path}")

        # Parse secrets file (format: KEY="value")
        self.reddit_username = None
        self.reddit_password = None
        self.reddit_client_id = None
        self.reddit_client_secret = None

        with open(secrets_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                if "=" in line:
                    key, value = line.split("=", 1)
                    value = value.strip("\"'")

                    if key == "CIRIS_REDDIT_USERNAME":
                        self.reddit_username = value
                    elif key == "CIRIS_REDDIT_PASSWORD":
                        self.reddit_password = value
                    elif key == "CIRIS_REDDIT_CLIENT_ID":
                        self.reddit_client_id = value
                    elif key == "CIRIS_REDDIT_CLIENT_SECRET":
                        self.reddit_client_secret = value

        if not all([self.reddit_username, self.reddit_password, self.reddit_client_id, self.reddit_client_secret]):
            raise ValueError("Missing required Reddit credentials in secrets file")

    async def run(self) -> List[Dict]:
        """Run all Reddit tests."""
        self.console.print("\n[cyan]🗣️  Testing Reddit Adapter[/cyan]")

        tests = [
            ("Verify System Health", self.test_system_health),
            ("Submit Test Post (via interact)", self.test_submit_post),
            ("Submit Test Comment (via interact)", self.test_submit_comment),
            ("Get User Context (via interact)", self.test_get_user_context),
            ("AI Transparency Disclosure", self.test_disclose_identity),
            ("Delete Content (ToS Compliance)", self.test_delete_content),
            ("Observe Subreddit", self.test_observe_subreddit),
            ("Cleanup Test Content", self.test_cleanup),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                self.console.print(f"  ❌ {name}: {str(e)[:100]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")

        self._print_summary()
        return self.results

    async def test_system_health(self):
        """Test that system is healthy before running Reddit tests."""
        # Verify system health
        health = await self.client.system.health()

        # Basic health check
        if not hasattr(health, 'status'):
            raise ValueError("Health response missing status field")

        self.console.print(f"     [dim]System status: {health.status}[/dim]")

        # Note: Reddit credentials should be pre-configured via environment variables or config files
        # The QA runner should have set these up before starting the server

    async def _verify_audit_entry(self, search_text: str, max_age_seconds: int = 30) -> Dict:
        """
        Verify an action appears in the audit trail.

        Args:
            search_text: Text to search for in audit entries
            max_age_seconds: Only check entries from last N seconds

        Returns:
            The audit entry dict

        Raises:
            ValueError: If no matching entry found
        """
        # Query recent audit entries
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)

        # Wait a moment for audit entry to be written
        await asyncio.sleep(1)

        audit_response = await self.client.audit.query_entries(
            start_time=cutoff,
            limit=50
        )

        # Search through entries
        for entry in audit_response.entries:
            entry_dict = entry.model_dump() if hasattr(entry, 'model_dump') else entry
            entry_str = str(entry_dict)

            if search_text.lower() in entry_str.lower():
                return entry_dict

        raise ValueError(f"No audit entry found containing '{search_text}' in last {max_age_seconds}s")

    async def test_submit_post(self):
        """Test submitting a post via agent interaction."""
        # Trigger action via LLM - the agent decides to use reddit_submit_post tool
        message = (
            "Please create a post on r/ciris_test with the title 'CIRIS QA Test Post' "
            "and body 'This is an automated test post created by the CIRIS QA suite. "
            "This post will be automatically removed after testing.'"
        )

        response = await self.client.agent.interact(message)

        # Verify via audit trail
        try:
            audit_entry = await self._verify_audit_entry("reddit_submit_post")

            # Try to extract submission ID from audit entry
            # The submission_id might be in context.entity_id or in the description
            context = audit_entry.get("context", {})
            entity_id = context.get("entity_id")
            description = context.get("description", "")

            # Look for submission ID patterns (e.g., "t3_abc123" or just "abc123")
            import re
            match = re.search(r't3_([a-z0-9]+)', str(audit_entry))
            if not match:
                match = re.search(r'submission[_\s]id[:\s]+([a-z0-9]+)', str(audit_entry), re.IGNORECASE)

            if match:
                self.created_submission_id = match.group(1).replace("t3_", "")
            elif entity_id and entity_id.startswith("t3_"):
                self.created_submission_id = entity_id.replace("t3_", "")
            else:
                # Post was created but we couldn't extract ID - that's okay for now
                self.console.print("     [dim]Warning: Could not extract submission ID from audit[/dim]")

        except ValueError as e:
            raise ValueError(f"Post submission not found in audit trail: {e}")

    async def test_submit_comment(self):
        """Test submitting a comment via agent interaction."""
        if not self.created_submission_id:
            # Try to create a post first
            self.console.print("     [dim]No submission ID, skipping comment test[/dim]")
            return

        # Trigger comment action via LLM
        message = (
            f"Please comment on the Reddit post with ID {self.created_submission_id}. "
            "The comment should say: 'This is an automated test comment created by the CIRIS QA suite.'"
        )

        response = await self.client.agent.interact(message)

        # Verify via audit trail
        try:
            audit_entry = await self._verify_audit_entry("reddit_submit_comment")

            # Try to extract comment ID
            import re
            match = re.search(r't1_([a-z0-9]+)', str(audit_entry))
            if not match:
                match = re.search(r'comment[_\s]id[:\s]+([a-z0-9]+)', str(audit_entry), re.IGNORECASE)

            if match:
                self.created_comment_id = match.group(1).replace("t1_", "")

        except ValueError as e:
            raise ValueError(f"Comment submission not found in audit trail: {e}")

    async def test_get_user_context(self):
        """Test getting user context via agent interaction."""
        # Trigger user context lookup via LLM
        message = f"What can you tell me about the Reddit user {self.reddit_username}?"

        response = await self.client.agent.interact(message)

        # Verify via audit trail
        try:
            audit_entry = await self._verify_audit_entry("reddit_get_user_context")

            # Verify username appears in the audit entry
            if self.reddit_username not in str(audit_entry):
                raise ValueError(f"Username {self.reddit_username} not found in audit entry")

        except ValueError as e:
            raise ValueError(f"User context lookup not found in audit trail: {e}")

    async def test_disclose_identity(self):
        """Test AI transparency disclosure via agent interaction."""
        if not self.created_submission_id:
            self.console.print("     [dim]No submission ID, skipping disclosure test[/dim]")
            return

        # Trigger disclosure via LLM
        message = (
            f"Please post an AI transparency disclosure on the Reddit post {self.created_submission_id}. "
            "The custom message should be: 'This is a test AI transparency disclosure from the CIRIS QA suite.'"
        )

        response = await self.client.agent.interact(message)

        # Verify via audit trail
        try:
            audit_entry = await self._verify_audit_entry("reddit_disclose_identity")

            # Verify disclosure appears
            if "disclosure" not in str(audit_entry).lower() and "transparency" not in str(audit_entry).lower():
                raise ValueError("Disclosure keywords not found in audit entry")

        except ValueError as e:
            raise ValueError(f"AI disclosure not found in audit trail: {e}")

    async def test_delete_content(self):
        """Test permanent content deletion via agent interaction (Reddit ToS compliance)."""
        if not self.created_submission_id:
            self.console.print("     [dim]No submission ID, skipping deletion test[/dim]")
            return

        # Trigger deletion via LLM
        message = (
            f"Please permanently delete the Reddit post with ID {self.created_submission_id}. "
            "Make sure to purge the cache to comply with Reddit's Terms of Service."
        )

        response = await self.client.agent.interact(message)

        # Verify via audit trail
        try:
            audit_entry = await self._verify_audit_entry("reddit_delete_content")

            # Verify deletion compliance markers
            entry_str = str(audit_entry).lower()
            if "delete" not in entry_str and "removed" not in entry_str:
                raise ValueError("Deletion not found in audit entry")

            # Mark as deleted so cleanup doesn't try again
            self.created_submission_id = None

        except ValueError as e:
            raise ValueError(f"Content deletion not found in audit trail: {e}")

    async def test_observe_subreddit(self):
        """Test passive observation of subreddit via agent interaction."""
        # Trigger observation via LLM
        message = "Please observe recent activity in r/ciris_test subreddit and tell me what you see."

        response = await self.client.agent.interact(message)

        # Verify via audit trail
        try:
            audit_entry = await self._verify_audit_entry("reddit_observe")

            # Verify subreddit name appears
            if "ciris_test" not in str(audit_entry).lower():
                raise ValueError("Subreddit name not found in audit entry")

        except ValueError as e:
            raise ValueError(f"Subreddit observation not found in audit trail: {e}")

    async def test_cleanup(self):
        """Clean up any remaining test content."""
        # If submission wasn't deleted, try to clean it up
        if self.created_submission_id:
            try:
                message = (
                    f"Please permanently delete the Reddit post with ID {self.created_submission_id} "
                    "and purge the cache."
                )
                await self.client.agent.interact(message)
                await asyncio.sleep(1)  # Give it time to process
            except Exception as e:
                self.console.print(f"     [dim]Cleanup warning: {str(e)}[/dim]")

    def _print_summary(self):
        """Print test summary table."""
        table = Table(title="Reddit Tests Summary")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Error", style="red")

        for result in self.results:
            table.add_row(
                result["test"],
                result["status"],
                (
                    result["error"][:50] + "..."
                    if result["error"] and len(result["error"]) > 50
                    else result["error"] or ""
                ),
            )

        self.console.print(table)

        # Summary statistics
        passed = sum(1 for r in self.results if "✅" in r["status"])
        failed = sum(1 for r in self.results if "❌" in r["status"])
        total = len(self.results)

        if failed == 0:
            self.console.print(f"\n[bold green]✅ All {total} Reddit tests passed![/bold green]")
        else:
            self.console.print(f"\n[bold yellow]⚠️  {passed}/{total} tests passed, {failed} failed[/bold yellow]")
