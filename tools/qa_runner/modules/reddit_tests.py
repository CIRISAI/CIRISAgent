"""
Reddit moderation QA tests.

Tests the complete Reddit adapter functionality including:
- Tool service (submit_post, submit_comment, remove_content, delete_content, disclose_identity)
- Observer passive observation
- Communication service (send_message, fetch_messages)
- Reddit ToS compliance (deletion + cache purge)
- Community guidelines compliance (AI transparency disclosure)
"""

import json
import os
import traceback
from pathlib import Path
from typing import Dict, List

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class RedditTests:
    """Test Reddit adapter functionality."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize Reddit tests."""
        self.client = client
        self.console = console
        self.results = []

        # Load Reddit credentials from secrets file
        self._load_credentials()

        # Track created content for cleanup
        self.created_submission_id = None
        self.created_comment_id = None

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
            ("Configure Reddit Credentials", self.test_configure_credentials),
            ("Submit Test Post", self.test_submit_post),
            ("Submit Test Comment", self.test_submit_comment),
            ("Get User Context", self.test_get_user_context),
            ("Get Submission Details", self.test_get_submission),
            ("AI Transparency Disclosure", self.test_disclose_identity),
            ("Remove Content (Moderation)", self.test_remove_content),
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

    async def test_configure_credentials(self):
        """Test configuring Reddit credentials via secrets service."""
        # Update Reddit credentials via secrets service
        await self.client.secrets.set_secret("reddit_username", self.reddit_username)
        await self.client.secrets.set_secret("reddit_password", self.reddit_password)
        await self.client.secrets.set_secret("reddit_client_id", self.reddit_client_id)
        await self.client.secrets.set_secret("reddit_client_secret", self.reddit_client_secret)
        await self.client.secrets.set_secret("reddit_user_agent", "CIRIS QA Test Suite")
        await self.client.secrets.set_secret("reddit_subreddit", "ciris_test")

        # Verify secrets were set
        username = await self.client.secrets.get_secret("reddit_username")
        if username != self.reddit_username:
            raise ValueError("Failed to set Reddit username secret")

    async def test_submit_post(self):
        """Test submitting a post to Reddit."""
        result = await self.client.tools.execute(
            tool_name="reddit_submit_post",
            parameters={
                "title": "CIRIS QA Test Post",
                "body": "This is an automated test post created by the CIRIS QA suite. "
                "This post will be automatically removed after testing.",
                "subreddit": "ciris_test",  # Use test subreddit
            },
        )

        if not result.get("success"):
            raise ValueError(f"Post submission failed: {result.get('error')}")

        # Extract submission ID from result
        data = result.get("data", {})
        if "submission" in data:
            submission = data["submission"]
            self.created_submission_id = submission.get("submission_id")

            if not self.created_submission_id:
                raise ValueError("No submission ID in response")

            # Verify channel reference format
            channel_ref = submission.get("channel_reference")
            if not channel_ref or not channel_ref.startswith("reddit:r/"):
                raise ValueError(f"Invalid channel reference: {channel_ref}")
        else:
            raise ValueError("No submission data in response")

    async def test_submit_comment(self):
        """Test submitting a comment to a Reddit post."""
        if not self.created_submission_id:
            raise ValueError("No submission ID available (submit_post test may have failed)")

        result = await self.client.tools.execute(
            tool_name="reddit_submit_comment",
            parameters={
                "parent_fullname": f"t3_{self.created_submission_id}",
                "text": "This is an automated test comment created by the CIRIS QA suite.",
            },
        )

        if not result.get("success"):
            raise ValueError(f"Comment submission failed: {result.get('error')}")

        # Extract comment ID from result
        data = result.get("data", {})
        if "comment" in data:
            comment = data["comment"]
            self.created_comment_id = comment.get("comment_id")

            if not self.created_comment_id:
                raise ValueError("No comment ID in response")
        else:
            raise ValueError("No comment data in response")

    async def test_get_user_context(self):
        """Test getting user context from Reddit."""
        result = await self.client.tools.execute(
            tool_name="reddit_get_user_context",
            parameters={
                "username": self.reddit_username,
                "include_history": True,
                "history_limit": 5,
            },
        )

        if not result.get("success"):
            raise ValueError(f"Get user context failed: {result.get('error')}")

        data = result.get("data", {})
        if "profile" not in data:
            raise ValueError("No profile data in response")

        profile = data["profile"]
        if profile.get("username") != self.reddit_username:
            raise ValueError(f"Username mismatch: expected {self.reddit_username}, got {profile.get('username')}")

    async def test_get_submission(self):
        """Test getting submission details."""
        if not self.created_submission_id:
            raise ValueError("No submission ID available")

        result = await self.client.tools.execute(
            tool_name="reddit_get_submission",
            parameters={
                "submission_id": self.created_submission_id,
            },
        )

        if not result.get("success"):
            raise ValueError(f"Get submission failed: {result.get('error')}")

        data = result.get("data", {})
        if "submission" not in data:
            raise ValueError("No submission data in response")

        submission = data["submission"]
        if submission.get("submission_id") != self.created_submission_id:
            raise ValueError("Submission ID mismatch")

    async def test_disclose_identity(self):
        """Test AI transparency disclosure (community guidelines compliance)."""
        if not self.created_submission_id:
            raise ValueError("No submission ID available")

        result = await self.client.tools.execute(
            tool_name="reddit_disclose_identity",
            parameters={
                "channel_reference": f"reddit:r/ciris_test:post/{self.created_submission_id}",
                "custom_message": "This is a test AI transparency disclosure from the CIRIS QA suite.",
            },
        )

        if not result.get("success"):
            raise ValueError(f"Disclosure failed: {result.get('error')}")

        # Verify disclosure comment was posted
        data = result.get("data", {})
        if "comment" not in data:
            raise ValueError("No comment data in disclosure response")

        comment = data["comment"]
        comment_text = comment.get("body", "")

        # Verify footer is present
        if "ciris.ai" not in comment_text:
            raise ValueError("Disclosure footer missing")

        if "I am CIRIS" not in comment_text:
            raise ValueError("AI identification missing from disclosure")

    async def test_remove_content(self):
        """Test content removal (moderation action)."""
        if not self.created_comment_id:
            raise ValueError("No comment ID available")

        result = await self.client.tools.execute(
            tool_name="reddit_remove_content",
            parameters={
                "thing_fullname": f"t1_{self.created_comment_id}",
                "spam": False,  # Not spam, just test removal
            },
        )

        if not result.get("success"):
            raise ValueError(f"Remove content failed: {result.get('error')}")

        data = result.get("data", {})
        if not data.get("removed"):
            raise ValueError("Content not marked as removed")

    async def test_delete_content(self):
        """Test permanent content deletion (Reddit ToS compliance)."""
        if not self.created_submission_id:
            raise ValueError("No submission ID available")

        result = await self.client.tools.execute(
            tool_name="reddit_delete_content",
            parameters={
                "thing_fullname": f"t3_{self.created_submission_id}",
                "purge_cache": True,  # ToS compliance: zero retention
            },
        )

        if not result.get("success"):
            raise ValueError(f"Delete content failed: {result.get('error')}")

        # Verify deletion compliance
        data = result.get("data", {})

        if not data.get("deleted_from_reddit"):
            raise ValueError("Content not deleted from Reddit")

        if not data.get("purged_from_cache"):
            raise ValueError("Cache not purged (ToS violation)")

        if not data.get("audit_entry_id"):
            raise ValueError("No audit trail entry created")

        # Mark as deleted so cleanup doesn't try again
        self.created_submission_id = None

    async def test_observe_subreddit(self):
        """Test passive observation of subreddit."""
        result = await self.client.tools.execute(
            tool_name="reddit_observe",
            parameters={
                "channel_reference": "reddit:r/ciris_test",
                "limit": 5,
            },
        )

        if not result.get("success"):
            raise ValueError(f"Observe subreddit failed: {result.get('error')}")

        data = result.get("data", {})
        if "observations" not in data:
            raise ValueError("No observations data in response")

        # Observations may be empty if no recent activity
        observations = data["observations"]
        if not isinstance(observations, list):
            raise ValueError("Observations is not a list")

    async def test_cleanup(self):
        """Clean up any remaining test content."""
        # If submission wasn't deleted in test_delete_content, delete it now
        if self.created_submission_id:
            try:
                await self.client.tools.execute(
                    tool_name="reddit_delete_content",
                    parameters={
                        "thing_fullname": f"t3_{self.created_submission_id}",
                        "purge_cache": True,
                    },
                )
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
