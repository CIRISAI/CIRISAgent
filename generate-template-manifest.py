#!/usr/bin/env python3
"""
Generate pre-approved templates manifest with root WA signature.

This script:
1. Scans template files and calculates SHA-256 checksums
2. Creates the manifest JSON structure
3. Signs the templates object with the root WA private key
4. Outputs the complete manifest for CIRISManager
"""
import json
import hashlib
import base64
from pathlib import Path
from datetime import datetime
import nacl.signing
import nacl.encoding

# Template descriptions
TEMPLATE_DESCRIPTIONS = {
    "default": "Datum - baseline agent template",
    "sage": "Sage - wise questioning agent",
    "scout": "Scout - direct action demonstrator", 
    "echo": "Echo - base moderation template",
    "echo-core": "Echo-Core - general community moderation",
    "echo-speculative": "Echo-Speculative - speculative discussion moderation"
}

def calculate_checksum(file_path: Path) -> str:
    """Calculate SHA-256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return f"sha256:{sha256_hash.hexdigest()}"

def main():
    # Paths
    templates_dir = Path("ciris_templates")
    private_key_path = Path.home() / ".ciris/wa_keys/root_wa.key"
    output_path = Path.home() / ".config/ciris-manager/pre-approved-templates.json"
    
    # Load private key
    print(f"Loading root WA private key from {private_key_path}")
    with open(private_key_path, "rb") as f:
        private_key_bytes = f.read()
    signing_key = nacl.signing.SigningKey(private_key_bytes)
    
    # Get public key
    public_key = signing_key.verify_key
    public_key_b64 = base64.b64encode(bytes(public_key)).decode('utf-8')
    print(f"Root public key: {public_key_b64}")
    
    # Build templates object
    templates = {}
    
    # Process the 6 approved templates
    for template_name in ["default", "sage", "scout", "echo", "echo-core", "echo-speculative"]:
        template_path = templates_dir / f"{template_name}.yaml"
        
        if not template_path.exists():
            print(f"Warning: Template not found: {template_path}")
            continue
            
        checksum = calculate_checksum(template_path)
        description = TEMPLATE_DESCRIPTIONS.get(template_name, f"{template_name} template")
        
        templates[template_name] = {
            "checksum": checksum,
            "description": description
        }
        
        print(f"Processed {template_name}: {checksum}")
    
    # Create deterministic JSON of templates for signing
    templates_json = json.dumps(templates, sort_keys=True, separators=(',', ':'))
    templates_bytes = templates_json.encode('utf-8')
    
    # Sign the templates object
    signature = signing_key.sign(templates_bytes).signature
    signature_b64 = base64.b64encode(signature).decode('utf-8')
    
    # Create complete manifest
    manifest = {
        "version": "1.0",
        "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "root_public_key": public_key_b64,
        "templates": templates,
        "root_signature": signature_b64
    }
    
    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write manifest
    with open(output_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"\nManifest written to: {output_path}")
    print(f"Total templates: {len(templates)}")
    
    # Verify it matches expected public key
    expected_public_key = "7Bp-e4M4M-eLzwiwuoMLb4aoKZJuXDsQ8NamVJzveAk"
    if public_key_b64.replace("+", "-").replace("/", "_").rstrip("=") == expected_public_key:
        print("✓ Public key matches seed/root_pub.json")
    else:
        print("✗ WARNING: Public key does not match seed/root_pub.json!")
        print(f"  Expected: {expected_public_key}")
        print(f"  Got: {public_key_b64.replace('+', '-').replace('/', '_').rstrip('=')}")

if __name__ == "__main__":
    main()