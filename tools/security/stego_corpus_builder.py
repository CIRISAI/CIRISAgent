#!/usr/bin/env python3
"""
Steganographic Corpus Builder.

Extracts natural sentences from markdown files to build a codebook
for steganographic covenant encoding.

Each sentence slot encodes 6 bits (64 variants per slot).
616 bits requires ~103 slots = ~103 sentences in the output message.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import Optional


def extract_sentences_from_markdown(text: str) -> list[str]:
    """
    Extract natural English sentences from markdown text.

    Filters out:
    - Code blocks
    - Headers
    - Lists with technical content
    - URLs
    - Very short sentences
    - Sentences with special characters
    """
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`[^`]+`", "", text)

    # Remove headers
    text = re.sub(r"^#+\s+.*$", "", text, flags=re.MULTILINE)

    # Remove URLs
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize whitespace - convert all whitespace to single spaces
    text = re.sub(r"\s+", " ", text)

    # Remove list numbers/bullets that might be attached
    text = re.sub(r"\s+\d+\.\s*$", ".", text)
    text = re.sub(r"\s+\d+\.\s+", " ", text)

    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", text)

    good_sentences = []
    for s in sentences:
        s = s.strip()

        # Skip if contains newlines (shouldn't happen after normalization but be safe)
        if "\n" in s or "\r" in s:
            continue

        # Skip empty or too short
        if len(s) < 20 or len(s) > 200:
            continue

        # Skip if has too many special chars
        special_count = sum(1 for c in s if c in "{}[]()<>|\\@#$%^&*_=+")
        if special_count > 3:
            continue

        # Skip if starts with bullet/number
        if re.match(r"^[\d\-\*\>]", s):
            continue

        # Skip if has code-like patterns
        if re.search(r"[A-Z][a-z]+[A-Z]|_[a-z]+_|[a-z]+\(\)", s):
            continue

        # Must start with capital, end with period
        if not re.match(r"^[A-Z]", s):
            continue
        if not s.endswith("."):
            continue

        # Skip if too many caps (likely acronyms/code)
        caps = sum(1 for c in s if c.isupper())
        if caps > len(s) * 0.20:
            continue

        good_sentences.append(s)

    return good_sentences


def build_corpus_from_directory(directory: Path) -> list[str]:
    """Extract all sentences from markdown files in directory."""
    all_sentences = []

    for md_file in directory.rglob("*.md"):
        try:
            text = md_file.read_text(encoding="utf-8", errors="ignore")
            sentences = extract_sentences_from_markdown(text)
            all_sentences.extend(sentences)
        except Exception:
            continue

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for s in all_sentences:
        normalized = s.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            unique.append(s)

    return unique


def categorize_sentences(sentences: list[str]) -> dict[str, list[str]]:
    """
    Categorize sentences by their semantic opening pattern.
    This helps create natural-flowing messages.
    """
    categories = {
        "statement": [],  # General statements
        "process": [],  # Describes processes/actions
        "property": [],  # Describes properties/attributes
        "relation": [],  # Describes relationships
        "temporal": [],  # Time-related
        "conditional": [],  # If/when statements
        "purpose": [],  # Purpose/goal statements
        "example": [],  # Examples/instances
        "transition": [],  # Transitional sentences
        "conclusion": [],  # Concluding statements
    }

    for s in sentences:
        s_lower = s.lower()

        if s_lower.startswith(("if ", "when ", "unless ")):
            categories["conditional"].append(s)
        elif s_lower.startswith(("for example", "for instance", "such as")):
            categories["example"].append(s)
        elif s_lower.startswith(("this ", "these ", "that ")):
            categories["relation"].append(s)
        elif s_lower.startswith(("the ", "a ", "an ")):
            categories["statement"].append(s)
        elif any(s_lower.startswith(w) for w in ["therefore", "thus", "hence", "consequently"]):
            categories["conclusion"].append(s)
        elif any(s_lower.startswith(w) for w in ["however", "moreover", "furthermore", "additionally"]):
            categories["transition"].append(s)
        elif any(w in s_lower for w in ["process", "step", "procedure", "method"]):
            categories["process"].append(s)
        else:
            categories["statement"].append(s)

    return categories


def build_codebook(sentences: list[str], slots_needed: int = 103, variants_per_slot: int = 64) -> dict:
    """
    Build a codebook mapping bit patterns to sentences.

    Structure:
    {
        "version": 2,
        "bits_per_slot": 6,
        "slots": [
            {
                "slot_id": 0,
                "variants": {
                    "000000": "The system operates continuously.",
                    "000001": "Operations proceed without interruption.",
                    ...
                }
            },
            ...
        ],
        "sentence_to_bits": {
            "the system operates continuously.": {"slot": 0, "bits": "000000"},
            ...
        }
    }
    """
    total_needed = slots_needed * variants_per_slot

    if len(sentences) < total_needed:
        raise ValueError(f"Need {total_needed} sentences, only have {len(sentences)}")

    # Calculate bits per slot (log2 of variants)
    import math

    bits_per_slot = int(math.log2(variants_per_slot))

    # Shuffle deterministically based on content hash
    corpus_hash = hashlib.sha256("".join(sentences).encode()).hexdigest()
    import random

    rng = random.Random(corpus_hash)
    shuffled = sentences.copy()
    rng.shuffle(shuffled)

    # Build slots
    slots = []
    sentence_to_bits = {}

    for slot_id in range(slots_needed):
        slot_sentences = shuffled[slot_id * variants_per_slot : (slot_id + 1) * variants_per_slot]

        variants = {}
        for i, sentence in enumerate(slot_sentences):
            bits = format(i, f"0{bits_per_slot}b")  # n-bit binary string
            variants[bits] = sentence
            sentence_to_bits[sentence.lower().strip()] = {"slot": slot_id, "bits": bits}

        slots.append({"slot_id": slot_id, "variants": variants})

    return {
        "version": 2,
        "bits_per_slot": bits_per_slot,
        "total_bits": slots_needed * bits_per_slot,
        "slots": slots,
        "sentence_to_bits": sentence_to_bits,
    }


def main():
    """Build corpus and codebook from CIRISAgent markdown files."""
    import argparse

    parser = argparse.ArgumentParser(description="Build steganographic corpus")
    parser.add_argument("--source", type=Path, default=Path("."), help="Source directory")
    parser.add_argument(
        "--output", type=Path, default=Path("tools/security/stego_codebook.json"), help="Output codebook"
    )
    parser.add_argument("--slots", type=int, default=103, help="Number of sentence slots")
    parser.add_argument("--variants", type=int, default=64, help="Variants per slot (2^bits)")
    args = parser.parse_args()

    print(f"Extracting sentences from {args.source}...")
    sentences = build_corpus_from_directory(args.source)
    print(f"Found {len(sentences)} unique sentences")

    needed = args.slots * args.variants
    if len(sentences) < needed:
        print(f"ERROR: Need {needed} sentences, only found {len(sentences)}")
        print("Try increasing source material or reducing slots/variants")
        return 1

    print(f"Building codebook with {args.slots} slots x {args.variants} variants...")
    codebook = build_codebook(sentences, args.slots, args.variants)

    # Save codebook
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(codebook, f, indent=2)

    print(f"Codebook saved to {args.output}")
    print(f"Total encoding capacity: {codebook['total_bits']} bits")

    return 0


if __name__ == "__main__":
    exit(main())
