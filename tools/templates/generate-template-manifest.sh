#!/bin/bash
# Generate signed manifest of pre-approved CIRIS templates

set -e

# Change to project root
cd "$(dirname "$0")/.."

echo "Generating pre-approved template manifest..."
echo

# Run the Python script
python scripts/generate-template-manifest.py

echo
echo "Manifest created successfully!"
echo
echo "The manifest contains:"
echo "  - SHA-256 checksums of all pre-approved templates"
echo "  - Ed25519 signature from the root private key"
echo "  - Root public key for verification"
echo
echo "Save this file for use in agent creation ceremonies."
