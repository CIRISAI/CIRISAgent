#!/usr/bin/env python3
"""
Validate all CIRIS agent templates against the AgentTemplate schema.

This ensures Book VI compliance and proper template structure.
"""

import os
import sys
from pathlib import Path
from typing import List, Tuple

# Ensure we can import from project root
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
os.chdir(project_root)

import yaml

from ciris_engine.schemas.config.agent import AgentTemplate


def find_all_templates() -> List[Path]:
    """Find all YAML templates in ciris_templates directory."""
    templates_dir = Path("ciris_templates")
    if not templates_dir.exists():
        print(f"ERROR: Templates directory not found at {templates_dir}")
        return []
    
    templates = list(templates_dir.glob("*.yaml"))
    templates.extend(templates_dir.glob("*.yml"))
    return sorted(templates)


def validate_template(path: Path) -> Tuple[bool, str]:
    """
    Validate a single template against the AgentTemplate schema.
    
    Returns:
        (success, message) tuple
    """
    try:
        with open(path, "r") as f:
            data = yaml.safe_load(f)
            
        # Validate against schema
        AgentTemplate.model_validate(data)
        
        # Check Book VI compliance
        if "stewardship" not in data:
            return False, "Missing stewardship section (Book VI required)"
        
        stewardship = data["stewardship"]
        
        # Check top-level required fields
        if "creator_intent_statement" not in stewardship:
            return False, "Missing creator_intent_statement in stewardship"
        if "creator_ledger_entry" not in stewardship:
            return False, "Missing creator_ledger_entry in stewardship"
        
        # Check if calculation is in ledger entry (where it actually is in templates)
        ledger = stewardship.get("creator_ledger_entry", {})
        if "stewardship_tier_calculation" not in ledger:
            return False, "Missing stewardship_tier_calculation in creator_ledger_entry"
        
        # Check if needs signing
        ledger = stewardship.get("creator_ledger_entry", {})
        if ledger.get("signature") == "NEEDS_SIGNING":
            return True, "Valid but NEEDS SIGNING"
        if ledger.get("public_key_fingerprint") == "NEEDS_FINGERPRINTING":
            return True, "Valid but NEEDS FINGERPRINTING"
            
        return True, "Valid and signed"
        
    except yaml.YAMLError as e:
        return False, f"YAML error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"


def main():
    """Validate all templates and report results."""
    print("CIRIS Template Validator")
    print("=" * 50)
    
    templates = find_all_templates()
    if not templates:
        print("No templates found to validate")
        return 1
    
    print(f"Found {len(templates)} templates to validate\n")
    
    all_valid = True
    results = []
    
    for template_path in templates:
        print(f"Validating {template_path.name}...")
        success, message = validate_template(template_path)
        results.append((template_path.name, success, message))
        
        if success:
            if "NEEDS" in message:
                print(f"  ⚠️  {message}")
            else:
                print(f"  ✅ {message}")
        else:
            print(f"  ❌ {message}")
            all_valid = False
    
    # Summary
    print("\n" + "=" * 50)
    print("VALIDATION SUMMARY")
    print("=" * 50)
    
    valid_count = sum(1 for _, success, _ in results if success)
    print(f"Templates validated: {len(results)}")
    print(f"Valid templates: {valid_count}")
    print(f"Invalid templates: {len(results) - valid_count}")
    
    # List any that need action
    needs_signing = [name for name, success, msg in results if success and "NEEDS" in msg]
    if needs_signing:
        print(f"\nTemplates needing signatures: {', '.join(needs_signing)}")
        print("Run: python tools/templates/generate_manifest.py")
    
    invalid = [name for name, success, _ in results if not success]
    if invalid:
        print(f"\nInvalid templates: {', '.join(invalid)}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())