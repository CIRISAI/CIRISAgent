#!/usr/bin/env python3
"""
Generate a signed manifest of pre-approved CIRIS templates.

This unified script:
1. Calculates SHA-256 checksums of all pre-approved templates
2. Updates stewardship fields (fingerprint/signature) in templates
3. Creates a JSON manifest with template metadata
4. Signs the manifest with the root private key
5. Outputs pre-approved-templates.json

Usage: python tools/generate_template_manifest.py
"""

import base64
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from nacl.signing import SigningKey

# Pre-approved templates and their descriptions
TEMPLATES = {
    "default": "Datum - baseline agent template",
    "sage": "Sage - wise questioning agent",
    "scout": "Scout - direct action demonstrator",
    "ally": "Ally - personal thriving assistant",
    "echo": "Echo - base moderation template",
    "echo-core": "Echo-Core - general community moderation",
    "echo-speculative": "Echo-Speculative - speculative discussion moderation",
}


def calculate_file_checksum(filepath: Path) -> str:
    """Calculate SHA-256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def load_root_private_key() -> SigningKey:
    """Load the root private key from ~/.ciris/wa_keys/root_wa.key"""
    key_path = Path.home() / ".ciris" / "wa_keys" / "root_wa.key"
    if not key_path.exists():
        print(f"Error: Root private key not found at {key_path}")
        print("Please ensure the key file exists for signing templates.")
        sys.exit(1)

    with open(key_path, "rb") as f:
        key_bytes = f.read()

    # The key file contains just the 32-byte private key
    if len(key_bytes) != 32:
        print(f"Error: Invalid key length {len(key_bytes)}, expected 32 bytes")
        sys.exit(1)

    return SigningKey(key_bytes)


def update_template_stewardship(template_path: Path, signing_key: SigningKey) -> bool:
    """Update stewardship fields in a template."""
    with open(template_path, "r", encoding="utf-8") as f:
        template = yaml.safe_load(f)

    if "stewardship" not in template:
        print(f"  No stewardship section in {template_path.name}, skipping")
        return False

    stewardship = template["stewardship"]
    creator_ledger = stewardship.get("creator_ledger_entry", {})

    # Calculate public key fingerprint
    public_key = signing_key.verify_key
    public_key_bytes = public_key.encode()
    fingerprint = hashlib.sha256(public_key_bytes).hexdigest()

    # Update fingerprint - always ensure it matches current key
    expected_fingerprint = f"sha256:{fingerprint}"
    if creator_ledger.get("public_key_fingerprint") != expected_fingerprint:
        creator_ledger["public_key_fingerprint"] = expected_fingerprint
        print(f"  Updated fingerprint in {template_path.name}")

    # Re-sign the creator intent statement
    intent = stewardship.get("creator_intent_statement", {})
    sign_message = json.dumps(
        {
            "creator_id": creator_ledger.get("creator_id"),
            "creation_timestamp": creator_ledger.get("creation_timestamp"),
            "covenant_version": creator_ledger.get("covenant_version"),
            "book_vi_compliance_check": creator_ledger.get("book_vi_compliance_check"),
            "stewardship_tier_calculation": creator_ledger.get("stewardship_tier_calculation"),
            "purpose_and_functionalities": intent.get("purpose_and_functionalities"),
            "limitations_and_design_choices": intent.get("limitations_and_design_choices"),
            "anticipated_benefits": intent.get("anticipated_benefits"),
            "anticipated_risks": intent.get("anticipated_risks"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )

    # Sign with Ed25519
    signed = signing_key.sign(sign_message.encode("utf-8"))
    signature = base64.b64encode(signed.signature).decode("ascii")
    creator_ledger["signature"] = f"ed25519:{signature}"
    print(f"  Re-signed {template_path.name}")

    # Write back the updated template
    with open(template_path, "w", encoding="utf-8") as f:
        yaml.dump(template, f, default_flow_style=False, sort_keys=False, width=120, allow_unicode=True)

    return True


def main():
    """Main function to generate and sign template manifest."""
    # Determine project root - handle being called from anywhere
    script_path = Path(__file__).resolve()
    if script_path.parent.name == "tools":
        project_root = script_path.parent.parent
    else:
        # Assume we're in project root or tools/
        project_root = Path.cwd()

    os.chdir(project_root)
    print(f"Working in project root: {project_root}")

    # Check templates directory exists (consolidated to engine folder)
    templates_dir = Path("ciris_engine/ciris_templates")
    if not templates_dir.exists():
        print(f"Error: Templates directory not found at {templates_dir}")
        print(f"Expected path: {project_root / templates_dir}")
        sys.exit(1)

    # Load signing key
    print("Loading root private key...")
    signing_key = load_root_private_key()

    # Get public key for verification
    public_key = signing_key.verify_key
    public_key_b64 = base64.b64encode(public_key.encode()).decode("utf-8")
    print(f"Root public key: {public_key_b64}")

    # First pass: Update stewardship fields in templates
    print("\nUpdating template stewardship fields...")
    for template_name in TEMPLATES.keys():
        template_path = templates_dir / f"{template_name}.yaml"
        if template_path.exists():
            update_template_stewardship(template_path, signing_key)
        else:
            print(f"  Warning: Template {template_path} not found")

    # Second pass: Calculate checksums after updates
    print("\nCalculating template checksums...")
    templates_data = {}

    for template_name, description in TEMPLATES.items():
        template_path = templates_dir / f"{template_name}.yaml"
        if not template_path.exists():
            print(f"Warning: Template {template_path} not found, skipping")
            continue

        checksum = calculate_file_checksum(template_path)
        templates_data[template_name] = {"checksum": f"sha256:{checksum}", "description": description}
        print(f"✓ {template_name}: {checksum}")

    # Create manifest structure
    manifest = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "root_public_key": public_key_b64,
        "templates": templates_data,
    }

    # Sign the templates object
    print("\nSigning manifest...")
    templates_json = json.dumps(templates_data, sort_keys=True, separators=(",", ":"))
    templates_bytes = templates_json.encode("utf-8")

    signed = signing_key.sign(templates_bytes)
    signature = base64.b64encode(signed.signature).decode("ascii")
    manifest["root_signature"] = signature

    # Write manifest
    output_path = Path("pre-approved-templates.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n✓ Manifest signed with root private key")
    print(f"✓ Manifest written to {output_path}")
    print(f"✓ Total templates: {len(templates_data)}")

    # Verify against expected key
    expected_public_key = "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk"
    public_key_url_safe = public_key_b64.replace("+", "-").replace("/", "_").rstrip("=")
    if public_key_url_safe == expected_public_key:
        print("✓ Public key matches expected root key")
    else:
        print("⚠ WARNING: Public key does not match expected root key")
        print(f"  Expected: {expected_public_key}")
        print(f"  Got: {public_key_url_safe}")


if __name__ == "__main__":
    main()
