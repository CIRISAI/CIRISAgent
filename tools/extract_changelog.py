#!/usr/bin/env python3
"""
Extract changelog content for CI/CD deployment messages.

This tool extracts release notes from CHANGELOG.md in Keep a Changelog format
and formats them for CIRISManager deployment notifications.
"""

import re
import sys
from pathlib import Path
from typing import Optional


def extract_version_changelog(changelog_path: str, version: str) -> Optional[str]:
    """Extract changelog for a specific version from CHANGELOG.md."""
    if not Path(changelog_path).exists():
        return None
    
    content = Path(changelog_path).read_text()
    
    # Pattern to match version section in Keep a Changelog format
    # Matches: ## [1.1.1] - 2025-09-09 until next ## section or end
    version_pattern = rf"## \[{re.escape(version)}\].*?(?=\n## |\Z)"
    match = re.search(version_pattern, content, re.DOTALL)
    
    if not match:
        return None
    
    version_section = match.group(0)
    return format_for_deployment(version_section, version)


def format_for_deployment(version_section: str, version: str) -> str:
    """Format changelog section for deployment message."""
    lines = []
    current_section = None
    
    for line in version_section.split('\n'):
        line = line.strip()
        
        # Skip version header and date
        if line.startswith(f"## [{version}]"):
            continue
            
        # Track current section (Added, Fixed, etc.)
        if line.startswith('### '):
            current_section = line[4:].strip().lower()
            continue
            
        # Extract bullet points
        if line.startswith('- ') and current_section:
            item = line[2:].strip()
            # Remove markdown bold formatting for cleaner deployment message
            item = re.sub(r'\*\*(.*?)\*\*', r'\1', item)
            # Take first sentence for brevity
            item = item.split(' - ')[0] if ' - ' in item else item.split('.')[0]
            
            # Prioritize certain types of changes
            priority_sections = ['security', 'fixed']
            if current_section in priority_sections:
                lines.insert(0, f"{current_section.title()}: {item}")
            else:
                lines.append(f"{current_section.title()}: {item}")
    
    # Return top 3 most important items for deployment message
    return ' | '.join(lines[:3]) if lines else f"Release {version} updates"


def assess_risk_level(changelog_content: str) -> str:
    """Assess deployment risk based on changelog content."""
    content_lower = changelog_content.lower()
    
    # High risk indicators
    high_risk_terms = [
        'breaking', 'major', 'critical', 'security', 'vulnerability', 
        'emergency', 'urgent', 'authentication', 'authorization'
    ]
    
    # Low risk indicators  
    low_risk_terms = [
        'fix', 'patch', 'minor', 'cleanup', 'documentation', 'typo',
        'test', 'coverage', 'refactor'
    ]
    
    if any(term in content_lower for term in high_risk_terms):
        return "high"
    elif any(term in content_lower for term in low_risk_terms):
        return "low"
    else:
        return "medium"


def main():
    """Main CLI interface."""
    if len(sys.argv) < 3:
        print("Usage: extract_changelog.py <changelog_file> <version>")
        print("Example: extract_changelog.py CHANGELOG.md 1.1.1")
        sys.exit(1)
    
    changelog_file = sys.argv[1]
    version = sys.argv[2]
    
    try:
        changelog = extract_version_changelog(changelog_file, version)
        if changelog:
            print(changelog)
        else:
            # Fallback message
            print(f"Release {version} updates available")
            
    except Exception as e:
        print(f"Error extracting changelog: {e}", file=sys.stderr)
        # Don't fail CI - provide fallback
        print(f"Release {version} updates")


if __name__ == "__main__":
    main()