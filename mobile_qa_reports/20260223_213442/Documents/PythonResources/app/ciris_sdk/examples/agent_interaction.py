#!/usr/bin/env python3
"""
Example of using the CIRIS SDK for agent interaction.

This demonstrates the simplified agent endpoints:
- /v1/agent/interact - Send message and get response
- /v1/agent/history - Get conversation history
- /v1/agent/status - Get agent status
- /v1/agent/identity - Get agent identity
"""
import asyncio

from ciris_sdk import CIRISClient


async def main() -> None:
    # Create client
    async with CIRISClient() as client:
        print("=== CIRIS SDK Agent Interaction Example ===\n")

        # 1. Simple interaction
        print("1. Simple interaction:")
        response = await client.interact("Hello! Can you tell me about yourself?")
        print(f"Response: {response.response}")
        print(f"State: {response.state}")
        print(f"Processing time: {response.processing_time_ms}ms")
        print()

        # 2. Using the ask() convenience method
        print("2. Ask a question (convenience method):")
        answer = await client.ask("What is 2 + 2?")
        print(f"Answer: {answer}")
        print()

        # 3. Get agent status
        print("3. Agent status:")
        status = await client.status()
        print(f"Agent: {status.name} ({status.agent_id})")
        print(f"State: {status.cognitive_state}")
        print(f"Uptime: {status.uptime_seconds:.1f}s")
        print(f"Messages processed: {status.messages_processed}")
        print(f"Memory usage: {status.memory_usage_mb:.1f}MB")
        print()

        # 4. Get agent identity
        print("4. Agent identity:")
        identity = await client.identity()
        print(f"Name: {identity.name}")
        print(f"Purpose: {identity.purpose}")
        print(f"Tools: {', '.join(identity.tools[:5])}...")  # First 5 tools
        print(f"Handlers: {', '.join(identity.handlers[:5])}...")  # First 5 handlers
        print(f"Permissions: {', '.join(identity.permissions)}")
        print()

        # 5. Interaction with context
        print("5. Interaction with context:")
        response = await client.interact(
            "Can you help me with a calculation?", context={"task": "math", "difficulty": "simple"}
        )
        print(f"Response: {response.response}")
        print()

        # 6. Get conversation history
        print("6. Conversation history:")
        history = await client.history(limit=5)
        print(f"Total messages: {history.total_count}")
        for msg in history.messages[-3:]:  # Last 3 messages
            author = "Agent" if msg.is_agent else "User"
            print(f"  [{author}] {msg.content[:50]}...")
        print()


async def authenticated_example() -> None:
    """Example with authentication."""
    async with CIRISClient() as client:
        print("=== Authenticated Example ===\n")

        # Login first
        await client.login("root", "your-password-here")
        print("Logged in successfully")

        # Now we can access protected endpoints
        response = await client.interact("What permissions do I have?")
        print(f"Response: {response.response}")

        # Logout when done
        await client.logout()
        print("Logged out")


async def error_handling_example() -> None:
    """Example of error handling."""
    async with CIRISClient() as client:
        print("=== Error Handling Example ===\n")

        try:
            # This might timeout if the agent takes too long
            response = await client.interact("Can you solve this complex problem that might take a while?")
            print(f"Response: {response.response}")

        except Exception as e:
            print(f"Error: {type(e).__name__}: {e}")

            # The interact endpoint handles timeouts gracefully
            # You'll still get a response indicating the request is processing


if __name__ == "__main__":
    # Run the main example
    asyncio.run(main())

    # Uncomment to run authenticated example
    # asyncio.run(authenticated_example())

    # Uncomment to run error handling example
    # asyncio.run(error_handling_example())
