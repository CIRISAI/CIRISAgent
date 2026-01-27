#!/usr/bin/env python3
"""
CLI entry point for CIRIS Mobile SDK Generator.

Usage:
    python -m tools.generate_sdk generate    # Full generation (fetch, generate, fix, verify)
    python -m tools.generate_sdk fetch       # Just fetch OpenAPI spec from running server
    python -m tools.generate_sdk fix         # Just apply fixes to existing generated code
    python -m tools.generate_sdk clean       # Clean generated files
    python -m tools.generate_sdk verify      # Verify build compiles
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from tools.generate_sdk.generator import SDKGenerator


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCommands:")
        print("  generate  - Full SDK generation pipeline")
        print("  fetch     - Fetch OpenAPI spec from running CIRIS server")
        print("  fix       - Apply fixes to existing generated code")
        print("  clean     - Remove generated files")
        print("  verify    - Verify generated code compiles")
        sys.exit(1)

    command = sys.argv[1].lower()
    generator = SDKGenerator(project_root)

    if command == "generate":
        # Check for --no-fetch flag
        fetch_spec = "--no-fetch" not in sys.argv
        verify = "--no-verify" not in sys.argv
        success = generator.generate(fetch_spec=fetch_spec, verify=verify)
        sys.exit(0 if success else 1)

    elif command == "fetch":
        # Optional: specify server URL
        server_url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:8765"
        if server_url.startswith("--"):
            # Auto-start server
            success = generator.start_server_and_fetch()
        else:
            success = generator.fetch_openapi_spec(server_url)
        sys.exit(0 if success else 1)

    elif command == "fix":
        generator.fix_generated_code()
        sys.exit(0)

    elif command == "clean":
        generator.clean()
        sys.exit(0)

    elif command == "verify":
        success = generator.verify_build()
        sys.exit(0 if success else 1)

    elif command == "config":
        generator.create_generator_config()
        sys.exit(0)

    elif command == "build-gradle":
        generator.create_build_gradle()
        sys.exit(0)

    else:
        print(f"Unknown command: {command}")
        print("Run without arguments for help.")
        sys.exit(1)


if __name__ == "__main__":
    main()
