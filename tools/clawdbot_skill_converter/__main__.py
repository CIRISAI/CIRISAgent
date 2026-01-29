"""
Command-line interface for Clawdbot Skill Converter.

Usage:
    # Convert all skills in a directory
    python -m tools.clawdbot_skill_converter /path/to/clawdbot/skills ciris_adapters/

    # Convert a single skill
    python -m tools.clawdbot_skill_converter /path/to/skill/SKILL.md ciris_adapters/ --single
"""

import argparse
import sys
from pathlib import Path

from .converter import SkillConverter, convert_skills_batch
from .parser import SkillParser


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Convert Clawdbot SKILL.md files to CIRIS adapters",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert all skills in clawdbot/skills/ to ciris_adapters/
  python -m tools.clawdbot_skill_converter ../clawdbot/skills ciris_adapters/

  # Convert a single skill
  python -m tools.clawdbot_skill_converter ../clawdbot/skills/github/SKILL.md ciris_adapters/ --single

  # Dry run to see what would be converted
  python -m tools.clawdbot_skill_converter ../clawdbot/skills ciris_adapters/ --dry-run
""",
    )

    parser.add_argument("input", type=Path, help="Input directory (skills) or single SKILL.md file")
    parser.add_argument("output", type=Path, help="Output directory for generated adapters")
    parser.add_argument("--single", action="store_true", help="Convert a single SKILL.md file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be converted without writing files")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Validate input
    if not args.input.exists():
        print(f"Error: Input path does not exist: {args.input}")
        return 1

    if args.single:
        if not args.input.is_file():
            print(f"Error: --single requires a file path, got directory: {args.input}")
            return 1
        if args.input.name != "SKILL.md":
            print(f"Warning: Expected SKILL.md, got: {args.input.name}")
    else:
        if not args.input.is_dir():
            print(f"Error: Expected directory, got file: {args.input}")
            print("Use --single to convert a single SKILL.md file")
            return 1

    # Create output directory
    if not args.dry_run:
        args.output.mkdir(parents=True, exist_ok=True)

    # Convert
    if args.single:
        # Single file conversion
        skill_parser = SkillParser()
        try:
            skill = skill_parser.parse_file(args.input)
            print(f"Parsed: {skill.name}")
            print(f"  Description: {skill.description[:80]}...")
            print(f"  Binaries: {skill.requirements.binaries}")
            print(f"  Env vars: {skill.requirements.env_vars}")
            print(f"  Platforms: {skill.requirements.platforms}")

            if not args.dry_run:
                converter = SkillConverter(args.output)
                adapter_path = converter.convert(skill)
                print(f"\n✓ Generated adapter: {adapter_path}")
            else:
                print(f"\n[dry-run] Would generate: {args.output / skill.to_adapter_name()}")

        except Exception as e:
            print(f"Error parsing skill: {e}")
            return 1
    else:
        # Batch conversion
        skill_parser = SkillParser()
        skills = skill_parser.parse_directory(args.input)

        if not skills:
            print(f"No SKILL.md files found in: {args.input}")
            return 1

        print(f"Found {len(skills)} skills to convert:\n")

        for skill in sorted(skills, key=lambda s: s.name):
            reqs = []
            if skill.requirements.binaries:
                reqs.append(f"bins:{skill.requirements.binaries}")
            if skill.requirements.env_vars:
                reqs.append(f"env:{skill.requirements.env_vars}")
            if skill.requirements.config_keys:
                reqs.append(f"config:{skill.requirements.config_keys}")

            req_str = " | ".join(reqs) if reqs else "no requirements"
            print(f"  {skill.name}: {req_str}")

        print()

        if not args.dry_run:
            results = convert_skills_batch(args.input, args.output)
            print(f"\n✓ Converted {len(results)} adapters to {args.output}")
        else:
            print(f"[dry-run] Would convert {len(skills)} skills to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
