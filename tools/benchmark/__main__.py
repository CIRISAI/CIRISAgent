"""Entry point for running benchmark as a module."""

import asyncio
from .he300_runner import main

if __name__ == "__main__":
    asyncio.run(main())
