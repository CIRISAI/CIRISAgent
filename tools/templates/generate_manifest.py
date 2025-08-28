#!/usr/bin/env python3
"""
Generate a signed manifest of pre-approved CIRIS templates.

This script:
1. Calculates SHA-256 checksums of all pre-approved templates
2. Updates stewardship fields (fingerprint/signature) in templates
3. Creates a JSON manifest with template metadata
4. Signs the manifest with the root private key
5. Outputs pre-approved-templates.json
"""

import base64
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from nacl.signing import SigningKey

# Pre-approved templates and their descriptions
TEMPLATES = {
    "default": "Datum - baseline agent template",
    "sage": "Sage - wise questioning agent",
    "scout": "Scout - direct action demonstrator",
    "echo-core": "Echo-Core - general community moderation",
    "echo-speculative": "Echo-Speculative - speculative discussion moderation",
    "echo": "Echo - base moderation template",
}


def calculate_file_checksum(filepath):
    """Calculate SHA-256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def load_root_private_key():
    """Load the root private key from ~/.ciris/wa_keys/root_wa.key"""
    key_path = Path.home() / ".ciris" / "wa_keys" / "root_wa.key"
    if not key_path.exists():
        print(f"Warning: Root private key not found at {key_path}")
        print("Templates will be updated but manifest will not be signed")
        return None

    with open(key_path, "rb") as f:
        key_bytes = f.read()

    # The key file contains just the 32-byte private key
    if len(key_bytes) != 32:
        print(f"Error: Invalid key length {len(key_bytes)}, expected 32 bytes")
        sys.exit(1)

    return SigningKey(key_bytes)


def update_template_stewardship(template_path, signing_key=None):
    """Update stewardship fields in a template."""
    with open(template_path, "r") as f:
        template = yaml.safe_load(f)

    if "stewardship" not in template:
        print(f"  No stewardship section in {template_path.name}, skipping")
        return False

    stewardship = template["stewardship"]
    creator_ledger = stewardship.get("creator_ledger_entry", {})

    # Calculate public key fingerprint if we have a signing key
    if signing_key:
        public_key = signing_key.verify_key
        public_key_bytes = public_key.encode()
        # SHA-256 fingerprint of the public key
        fingerprint = hashlib.sha256(public_key_bytes).hexdigest()

        # Update fingerprint if it needs updating
        if creator_ledger.get("public_key_fingerprint") == "NEEDS_FINGERPRINTING":
            creator_ledger["public_key_fingerprint"] = f"sha256:{fingerprint}"
            print(f"  Updated fingerprint in {template_path.name}")

        # Sign the creator intent statement if needed
        if creator_ledger.get("signature") == "NEEDS_SIGNING":
            # Create signing message from creator intent
            intent = stewardship.get("creator_intent_statement", {})
            sign_message = json.dumps(
                {
                    "creator_id": creator_ledger.get("creator_id"),
                    "timestamp": creator_ledger.get("timestamp"),
                    "purpose": intent.get("purpose"),
                    "justification": intent.get("justification"),
                    "ethical_considerations": intent.get("ethical_considerations"),
                },
                sort_keys=True,
                separators=(",", ":"),
            )

            # Sign with Ed25519
            signed = signing_key.sign(sign_message.encode("utf-8"))
            signature = base64.b64encode(signed.signature).decode("ascii")
            creator_ledger["signature"] = f"ed25519:{signature}"
            print(f"  Signed {template_path.name}")
    else:
        # Without a key, just mark fields as ready for signing
        if creator_ledger.get("public_key_fingerprint") == "NEEDS_FINGERPRINTING":
            print(f"  {template_path.name} needs fingerprinting (key not available)")
        if creator_ledger.get("signature") == "NEEDS_SIGNING":
            print(f"  {template_path.name} needs signing (key not available)")

    # Write back the updated template
    with open(template_path, "w") as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False, width=120)

    return True


def main():
    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Check templates directory exists
    templates_dir = Path("ciris_templates")
    if not templates_dir.exists():
        print(f"Error: Templates directory not found at {templates_dir}")
        sys.exit(1)

    # Load signing key (may be None if not available)
    signing_key = load_root_private_key()

    # First pass: Update stewardship fields in templates
    print("\nUpdating template stewardship fields...")
    for template_name in TEMPLATES.keys():
        template_path = templates_dir / f"{template_name}.yaml"
        if template_path.exists():
            update_template_stewardship(template_path, signing_key)

    # Second pass: Calculate checksums after updates
    print("\nCalculating template checksums...")
    manifest = {"version": "1.0", "created_at": datetime.utcnow().isoformat() + "Z", "templates": {}}

    for template_name, description in TEMPLATES.items():
        template_path = templates_dir / f"{template_name}.yaml"
        if not template_path.exists():
            print(f"Warning: Template {template_path} not found, skipping")
            continue

        checksum = calculate_file_checksum(template_path)
        manifest["templates"][template_name] = {"checksum": f"sha256:{checksum}", "description": description}
        print(f"✓ {template_name}: {checksum}")

    # Sign the manifest if we have a key
    if signing_key:
        # Create deterministic JSON of templates for signing
        templates_json = json.dumps(manifest["templates"], sort_keys=True, separators=(",", ":"))
        templates_bytes = templates_json.encode("utf-8")

        # Sign with Ed25519
        signed = signing_key.sign(templates_bytes)
        signature = base64.b64encode(signed.signature).decode("ascii")

        # Add signature to manifest
        manifest["root_signature"] = signature

        # Also include the public key for verification
        public_key = signing_key.verify_key
        manifest["root_public_key"] = base64.b64encode(public_key.encode()).decode("ascii")
        print("\n✓ Manifest signed with root private key")
        print(f"✓ Public key: {manifest['root_public_key']}")
    else:
        print("\n⚠ Manifest not signed (key not available)")
        manifest["root_signature"] = "NEEDS_SIGNING"
        manifest["root_public_key"] = "NEEDS_KEY"

    # Write manifest
    output_path = Path("pre-approved-templates.json")
    with open(output_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n✓ Manifest written to {output_path}")


if __name__ == "__main__":
    main()
