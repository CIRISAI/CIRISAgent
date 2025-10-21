"""
Message ID correlation debugging test.

This module tests whether the message_id returned from POST /v1/agent/message
matches the message_id found in GET /v1/agent/history.

Issue: User reports that message_id from /message endpoint differs from
the message_id in /history endpoint results.
"""

import asyncio
import time
import traceback
from typing import Dict, List

from rich.console import Console

from ciris_sdk.client import CIRISClient


class MessageIDDebugTests:
    """Test module for debugging message_id correlation."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize message ID debug tests."""
        self.client = client
        self.console = console
        self.results = []
        self.sent_message_id = None
        self.history_message_id = None

    async def run(self) -> List[Dict]:
        """Run all message ID correlation tests."""
        self.console.print("\n[cyan]🔍 Testing Message ID Correlation[/cyan]")

        tests = [
            ("Send message via /agent/message", self.test_send_message),
            ("Wait for processing", self.test_wait_for_processing),
            ("Fetch history and compare IDs", self.test_fetch_and_compare_ids),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                self.console.print(f"  ❌ {name}: {str(e)}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")

        self._print_summary()
        return self.results

    async def test_send_message(self):
        """Send a message via /agent/message and capture the returned message_id."""
        import aiohttp

        # Use raw HTTP to access the /agent/message endpoint
        message_content = f"DEBUG: Message ID correlation test at {time.time()}"

        # Get the API key from the client's transport
        api_key = self.client._transport.api_key if hasattr(self.client, "_transport") else self.client.api_key

        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {api_key}"}
            url = f"{self.client.base_url}/v1/agent/message"

            async with session.post(
                url, json={"message": message_content}, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    raise ValueError(f"Message submission failed with status {response.status}")

                data = await response.json()
                if "data" in data and "message_id" in data["data"]:
                    self.sent_message_id = data["data"]["message_id"]
                    self.console.print(f"     [dim]Sent message_id: {self.sent_message_id}[/dim]")
                else:
                    raise ValueError(f"No message_id in response: {data}")

    async def test_wait_for_processing(self):
        """Brief wait to ensure message appears in history."""
        await asyncio.sleep(2)  # Give the system time to process

    async def test_fetch_and_compare_ids(self):
        """Fetch history and compare the message_id."""
        import aiohttp

        if not self.sent_message_id:
            raise ValueError("No sent_message_id to compare (previous test failed)")

        # Get the API key from the client's transport
        api_key = self.client._transport.api_key if hasattr(self.client, "_transport") else self.client.api_key

        # Fetch history via /agent/history
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {api_key}"}
            url = f"{self.client.base_url}/v1/agent/history?limit=10"

            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    raise ValueError(f"History fetch failed with status {response.status}")

                data = await response.json()
                if "data" not in data or "messages" not in data["data"]:
                    raise ValueError(f"Invalid history response: {data}")

                messages = data["data"]["messages"]

                # Find our message
                found = False
                for msg in messages:
                    msg_id = msg.get("id")
                    if msg_id == self.sent_message_id:
                        found = True
                        self.history_message_id = msg_id
                        self.console.print(f"     [dim]✅ Found matching message_id in history[/dim]")
                        break

                if not found:
                    # Print all message IDs for debugging
                    all_ids = [msg.get("id") for msg in messages]
                    self.console.print(f"     [red]❌ Message ID mismatch!")
                    self.console.print(f"     [red]Sent message_id:     {self.sent_message_id}")
                    self.console.print(f"     [red]History message_ids: {all_ids}")
                    raise ValueError(
                        f"Message ID not found in history! " f"Sent: {self.sent_message_id}, History IDs: {all_ids}"
                    )

    def _print_summary(self):
        """Print test summary."""
        passed = sum(1 for r in self.results if "✅" in r["status"])
        total = len(self.results)

        self.console.print(f"\n[bold]Message ID Debug Summary: {passed}/{total} passed[/bold]")

        if self.sent_message_id and self.history_message_id:
            if self.sent_message_id == self.history_message_id:
                self.console.print(f"  [green]✅ Message IDs match correctly[/green]")
                self.console.print(f"     ID: {self.sent_message_id}")
            else:
                self.console.print(f"  [red]❌ Message ID MISMATCH DETECTED![/red]")
                self.console.print(f"     Sent:    {self.sent_message_id}")
                self.console.print(f"     History: {self.history_message_id}")
