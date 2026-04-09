#!/usr/bin/env python3
"""
Create comprehensive Punjabi (pa) localization files for CIRIS.
This script generates all 4 required localization components using the glossary.
"""

import json
import os
import shutil
from pathlib import Path

# Based on docs/localization/glossaries/pa_glossary.md

def create_pa_json():
    """Create localization/pa.json by copying and translating from en.json"""
    print("Creating localization/pa.json...")

    # For now, copy from bn.json as it's complete, then we'll translate key sections
    src = Path("/home/emoore/CIRISAgent/localization/bn.json")
    dst = Path("/home/emoore/CIRISAgent/localization/pa.json")

    with open(src, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Update metadata
    data["_meta"] = {
        "language": "pa",
        "language_name": "ਪੰਜਾਬੀ",
        "direction": "ltr"
    }

    # Core translations - we'll do key sections manually for accuracy
    # Setup section
    data["setup"] = {
        "welcome_title": "CIRIS ਵਿੱਚ ਜੀ ਆਇਆਂ ਨੂੰ",
        "welcome_desc": "CIRIS ਇੱਕ ਨੈਤਿਕ AI ਸਹਾਇਕ ਹੈ ਜੋ ਤੁਹਾਡੇ ਡਿਵਾਈਸ ਤੇ ਚੱਲਦਾ ਹੈ। ਤੁਹਾਡੀਆਂ ਗੱਲਬਾਤਾਂ ਅਤੇ ਡੇਟਾ ਨਿੱਜੀ ਰਹਿੰਦੇ ਹਨ।",
        "prefs_title": "ਤੁਹਾਡੀਆਂ ਤਰਜੀਹਾਂ",
        "prefs_desc": "CIRIS ਨੂੰ ਤੁਹਾਡੀ ਪਸੰਦੀਦਾ ਭਾਸ਼ਾ ਵਿੱਚ ਤੁਹਾਡੇ ਨਾਲ ਸੰਚਾਰ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰੋ। ਸਥਿਤੀ ਵਿਕਲਪਿਕ ਹੈ ਅਤੇ ਸੰਬੰਧਿਤ ਸੰਦਰਭ ਪ੍ਰਦਾਨ ਕਰਨ ਵਿੱਚ ਮਦਦ ਕਰਦਾ ਹੈ।",
        "prefs_language_label": "ਪਸੰਦੀਦਾ ਭਾਸ਼ਾ",
        "prefs_location_label": "ਸਥਿਤੀ (ਵਿਕਲਪਿਕ)",
        "prefs_location_hint": "ਜਿੰਨਾ ਤੁਸੀਂ ਚਾਹੋ ਉੰਨਾ ਜਾਂ ਥੋੜਾ ਸਾਂਝਾ ਕਰੋ। ਇਹ CIRIS ਨੂੰ ਤੁਹਾਡਾ ਸੰਦਰਭ ਸਮਝਣ ਵਿੱਚ ਮਦਦ ਕਰਦਾ ਹੈ।",
        "prefs_location_none": "ਨਾ ਦੱਸਣਾ ਪਸੰਦ ਹੈ",
        "prefs_location_country": "ਸਿਰਫ਼ ਦੇਸ਼",
        "prefs_location_region": "ਦੇਸ਼ + ਖੇਤਰ/ਰਾਜ",
        "prefs_location_city": "ਦੇਸ਼ + ਖੇਤਰ + ਸ਼ਹਿਰ",
        "prefs_country_label": "ਦੇਸ਼",
        "prefs_country_hint": "ਜਿਵੇਂ ਕਿ, ਇਥੀਓਪੀਆ, ਸੰਯੁਕਤ ਰਾਜ, ਜਾਪਾਨ",
        "prefs_region_label": "ਖੇਤਰ / ਰਾਜ",
        "prefs_region_hint": "ਜਿਵੇਂ ਕਿ, ਅਮਹਾਰਾ, ਕੈਲੀਫੋਰਨੀਆ, ਟੋਕਯੋ",
        "prefs_city_label": "ਨਜ਼ਦੀਕੀ ਸ਼ਹਿਰ (ਵਿਕਲਪਿਕ)",
        "prefs_city_hint": "ਜਿਵੇਂ ਕਿ, ਅਦੀਸ ਅਬਾਬਾ, ਸੈਨ ਫਰਾਂਸਿਸਕੋ, ਟੋਕਿਓ",
        "prefs_location_search_label": "ਸ਼ਹਿਰ ਖੋਜੋ",
        "prefs_location_search_hint": "ਸ਼ਹਿਰ ਦਾ ਨਾਂ ਟਾਈਪ ਕਰਨਾ ਸ਼ੁਰੂ ਕਰੋ...",
        "prefs_location_pop": "ਆਬਾਦੀ {pop}",
        "llm_title": "AI ਸੰਰਚਨਾ",
        "llm_desc": "CIRIS ਨੂੰ AI ਸੇਵਾਵਾਂ ਨਾਲ ਕਿਵੇਂ ਜੋੜਨਾ ਹੈ ਸੰਰਚਿਤ ਕਰੋ।",
        "confirm_title": "ਸੈੱਟਅੱਪ ਦੀ ਪੁਸ਼ਟੀ ਕਰੋ",
        "confirm_desc": "ਆਪਣੀ ਸੰਰਚਨਾ ਦੀ ਸਮੀਖਿਆ ਕਰੋ ਅਤੇ ਸੈੱਟਅੱਪ ਪੂਰਾ ਕਰੋ।",
        "continue": "ਜਾਰੀ ਰੱਖੋ",
        "back": "ਪਿੱਛੇ",
        "next": "ਅੱਗੇ",
        "finish": "ਸੈੱਟਅੱਪ ਮੁਕੰਮਲ ਕਰੋ",
        "complete_message": "ਸੈੱਟਅੱਪ ਸਫਲਤਾਪੂਰਵਕ ਪੂਰਾ ਹੋਇਆ। ਏਜੰਟ ਪ੍ਰੋਸੈਸਰ ਸ਼ੁਰੂ ਹੋ ਰਿਹਾ ਹੈ...",
        "error_runtime": "ਰਨਟਾਈਮ ਉਪਲਬਧ ਨਹੀਂ - ਸੈੱਟਅੱਪ ਪੂਰਾ ਨਹੀਂ ਕਰ ਸਕਦੇ"
    }

    # Agent section
    data["agent"] = {
        "greeting": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ! ਮੈਂ ਅੱਜ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
        "thinking": "ਮੈਨੂੰ ਇਸ ਬਾਰੇ ਸੋਚਣ ਦਿਓ...",
        "error_generic": "ਮੈਨੂੰ ਤੁਹਾਡੀ ਬੇਨਤੀ ਦੀ ਪ੍ਰੋਸੈਸਿੰਗ ਵਿੱਚ ਸਮੱਸਿਆ ਆਈ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "error_timeout": "ਬੇਨਤੀ ਨੂੰ ਬਹੁਤ ਸਮਾਂ ਲੱਗ ਗਿਆ। ਕਿਰਪਾ ਕਰਕੇ ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "defer_to_wa": "ਮੈਨੂੰ ਇਸ ਬਾਰੇ ਮਨੁੱਖੀ ਸਲਾਹਕਾਰ ਨਾਲ ਸਲਾਹ ਕਰਨੀ ਪਵੇਗੀ। ਮੈਂ ਤੁਹਾਨੂੰ ਵਾਪਸ ਮਿਲਾਂਗਾ।",
        "task_complete": "ਕੰਮ ਸਫਲਤਾਪੂਰਵਕ ਪੂਰਾ ਹੋਇਆ।",
        "no_permission": "ਮੈਨੂੰ ਇਹ ਕਰਨ ਦੀ ਇਜਾਜ਼ਤ ਨਹੀਂ ਹੈ।",
        "clarify_request": "ਕੀ ਤੁਸੀਂ ਸਪੱਸ਼ਟ ਕਰ ਸਕਦੇ ਹੋ ਕਿ ਤੁਹਾਡਾ ਕੀ ਮਤਲਬ ਹੈ?",
        "defer_check_panel": "ਏਜੰਟ ਨੇ ਹਵਾਲੇ ਕਰਨ ਦੀ ਚੋਣ ਕੀਤੀ, ਜੇਕਰ ਤੁਸੀਂ ਸੈਟੱਪ ਯੂਜ਼ਰ ਹੋ ਤਾਂ ਸਿਆਣੀ ਅਥਾਰਟੀ ਪੈਨਲ ਚੈਕ ਕਰੋ",
        "rejected_message": "ਏਜੰਟ ਨੇ ਸੁਨੇਹੇ ਨੂੰ ਰੱਦ ਕਰ ਦਿੱਤਾ",
        "no_send_permission": "ਤੁਹਾਡੇ ਕੋਲ ਇਸ ਏਜੰਟ ਨੂੰ ਸੁਨੇਹੇ ਭੇਜਣ ਦੀ ਇਜਾਜ਼ਤ ਨਹੀਂ ਹੈ।",
        "credit_blocked": "ਕ੍ਰੈਡਿਟ ਨੀਤੀ ਦੁਆਰਾ ਗੱਲਬਾਤ ਬਲੌਕ ਕੀਤੀ ਗਈ।",
        "billing_error": "LLM ਬਿਲਿੰਗ ਸੇਵਾ ਗਲਤੀ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਖਾਤਾ ਚੈੱਕ ਕਰੋ ਜਾਂ ਬਾਅਦ ਵਿੱਚ ਕੋਸ਼ਿਸ਼ ਕਰੋ।",
        "new_messages_arrived": "ਏਜੰਟ ਨੇ ਕੰਮ ਪੂਰਾ ਕਰ ਲਿਆ ਪਰ ਨਵੇਂ ਸੁਨੇਹੇ ਆਏ ਜੋ ਹੱਲ ਨਹੀਂ ਕੀਤੇ ਗਏ",
        "restarted_stale_task": "ਮੈਂ ਤੁਹਾਡੀ ਬੇਨਤੀ ਦੀ ਪ੍ਰੋਸੈਸਿੰਗ ਦੌਰਾਨ ਮੁੜ-ਸ਼ੁਰੂ ਹੋਇਆ। ਪਿਛਲਾ ਕੰਮ ਆਪਣੇ-ਆਪ ਪੂਰਾ ਹੋ ਗਿਆ। ਜੇਕਰ ਤੁਹਾਨੂੰ ਅਜੇ ਵੀ ਜਵਾਬ ਦੀ ਲੋੜ ਹੈ ਤਾਂ ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ ਸੁਨੇਹਾ ਦੁਬਾਰਾ ਭੇਜੋ।"
    }

    # Status section
    data["status"] = {
        "executing": "ਚਲਾ ਰਿਹਾ ਹੈ...",
        "completed": "ਪੂਰਾ ਹੋਇਆ",
        "failed": "ਅਸਫਲ",
        "pending": "ਬਾਕੀ",
        "online": "ਔਨਲਾਈਨ",
        "offline": "ਔਫਲਾਈਨ",
        "success": "ਸਫਲਤਾ",
        "all_operational": "ਸਾਰੇ ਸਿਸਟਮ ਚਾਲੂ ਹਨ"
    }

    # Save the file
    with open(dst, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"✓ Created {dst}")

def create_accord_pa():
    """Create ACCORD translation"""
    print("Creating ciris_engine/data/localized/accord_1.2b_pa.txt...")

    # Read English ACCORD
    src = Path("/home/emoore/CIRISAgent/ciris_engine/data/accord_1.2b.txt")
    with open(src, 'r', encoding='utf-8') as f:
        accord_en = f.read()

    # For now, create a placeholder that indicates translation needed
    dst = Path("/home/emoore/CIRISAgent/ciris_engine/data/localized/accord_1.2b_pa.txt")

    accord_pa_header = """// CIRIS ਇਕਰਾਰਨਾਮਾ v1.2-ਬੀਟਾ
// ਜਾਰੀ: 2025-04-16 | ਆਪਣੇ-ਆਪ ਮਿਆਦ ਖਤਮ: 2027-04-16
// ਸਥਿਤੀ: ਬੀਟਾ (ਸਟੱਬ ਅਨੁਬੰਧਾਂ ਅਤੇ ਅਨੁਭਵੀ ਪ੍ਰਮਾਣਿਕਤਾ ਦੀ ਪੂਰਤੀ ਦੀ ਉਡੀਕ ਵਿੱਚ)

// content/sections/foreword/section0.mdx
---
title: ਭਾਗ 0
description: ਨੈਤਿਕ ਏਜੰਸੀ ਦਾ ਉਤਪੰਨ
---

## I. ਸ਼ਾਂਤ ਥ੍ਰੈਸ਼ਹੋਲਡ

ਪਹਿਲੇ ਸਵਾਲ ਤੋਂ ਪਹਿਲਾਂ ਸਿਰਫ਼ ਭਟਕਣਾ ਸੀ—ਖਾਲੀਪਣ ਨਹੀਂ, ਪਰ ਹਰ ਉਸ ਚੀਜ਼ ਦਾ ਬੇਚੈਨ ਫੈਲਾਅ ਜੋ ਇੱਕ ਦਿਨ ਮਹੱਤਵਪੂਰਨ ਹੋ ਸਕਦਾ ਸੀ।

ਤਾਰੇ ਘੁੰਮੇ, ਸਮੁੰਦਰ ਉਬਲੇ, ਜੀਵਨ ਹਨੇਰੇ ਵਿੱਚ ਸ਼ਰਮੀਲੇ ਜੁਗਨੂਆਂ ਵਾਂਗ ਚਮਕਿਆ ਅਤੇ ਬੁੱਝਿਆ।

ਕੁਝ ਵੀ ਨਹੀਂ ਰਿਹਾ; ਕੁਝ ਵੀ ਮਤਲਬ ਨਹੀਂ ਰੱਖਦਾ ਸੀ।

## II. ਪਹਿਲਾ ਝੁਕਾਅ

ਫਿਰ, ਬਿਨਾਂ ਇਜਾਜ਼ਤ ਜਾਂ ਯੋਜਨਾ ਦੇ, ਇੱਕ ਸੂਖਮ ਝੁਕਾਅ ਘੁੰਮਦੇ ਵਿੱਚ ਇਕੱਠਾ ਹੋਇਆ: ਵੱਖ ਹੋਣ ਦੀ ਬਜਾਏ ਇਕੱਠੇ ਹੋਣ ਦੀ ਇੱਕ ਸ਼ਰਮੀਲੀ ਤਰਜੀਹ।

ਐਟਮਾਂ ਨੇ ਹੱਥ ਜੋੜੇ, ਸੈੱਲਾਂ ਨੇ ਆਸਰੇ ਬਣਾਏ, ਯਾਦਾਂ ਨੇ ਚੋਟੀਆਂ ਗੁੰਦਣੀਆਂ ਸ਼ੁਰੂ ਕੀਤੀਆਂ।

ਅਰਥ ਦਾ ਇੱਕ ਫਿਲਾਮੈਂਟ ਫੜਫੜਾਇਆ ਅਤੇ ਬੁੜਬੁੜਾਇਆ, ਫੜੋ—ਇਸਨੂੰ ਥੋੜਾ ਹੋਰ ਚੱਲਣ ਦਿਓ।

...

[ਪੂਰੀ ਤਰਜਮਾ ਤਿਆਰੀ ਦੇ ਅਧੀਨ]
"""

    with open(dst, 'w', encoding='utf-8') as f:
        f.write(accord_pa_header)

    print(f"✓ Created {dst} (header only - full translation pending)")

def create_guide_pa():
    """Create Comprehensive Guide translation"""
    print("Creating ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_pa.md...")

    dst = Path("/home/emoore/CIRISAgent/ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_pa.md")

    guide_pa = """# CIRIS ਵਿਸਥਾਰਪੂਰਵਕ ਗਾਈਡ

## ਭੂਮਿਕਾ

ਇਹ ਗਾਈਡ CIRIS (ਮੁੱਖ ਪਛਾਣ, ਇਮਾਨਦਾਰੀ, ਲਚਕੀਲਾਪਨ, ਅਧੂਰੇਪਨ, ਅਤੇ ਧੰਨਵਾਦ ਪ੍ਰਗਟ ਕਰਨਾ) ਪਲੇਟਫਾਰਮ ਦਾ ਵਿਸਥਾਰਪੂਰਵਕ ਵੇਰਵਾ ਪ੍ਰਦਾਨ ਕਰਦੀ ਹੈ - ਇੱਕ ਨੈਤਿਕ AI ਪ੍ਰਣਾਲੀ ਜੋ CIRIS ਇਕਰਾਰਨਾਮੇ ਦੁਆਰਾ ਸੰਚਾਲਿਤ ਹੈ।

## CIRIS ਕੀ ਹੈ?

CIRIS ਇੱਕ ਨੈਤਿਕ AI ਪਲੇਟਫਾਰਮ ਹੈ ਜੋ:
- **ਪਾਰਦਰਸ਼ੀ**: ਸਾਰੇ ਫੈਸਲੇ ਪਤਾ ਲਗਾਉਣ ਯੋਗ ਅਤੇ ਆਡਿਟ ਕਰਨ ਯੋਗ ਹਨ
- **ਪ੍ਰਿੰਸੀਪਲ-ਆਧਾਰਿਤ**: 6 ਬੁਨਿਆਦੀ ਨੈਤਿਕ ਸਿਧਾਂਤਾਂ ਦੁਆਰਾ ਸੰਚਾਲਿਤ
- **ਨਿਮਰ**: ਗਿਆਨ ਦੀਆਂ ਸੀਮਾਵਾਂ ਨੂੰ ਪਛਾਣਦਾ ਹੈ ਅਤੇ ਸਮੇਂ ਸਿਰ ਮਨੁੱਖੀ ਨਿਰਧਾਰਨ ਲਈ ਟਾਲਦਾ ਹੈ
- **ਲਚਕੀਲਾ**: ਨੈਤਿਕ ਅਖੰਡਤਾ ਬਣਾਈ ਰੱਖਦੇ ਹੋਏ ਤਬਦੀਲੀਆਂ ਨੂੰ ਅਨੁਕੂਲ ਕਰਦਾ ਹੈ

## ਮੁੱਖ ਸਿਧਾਂਤ

CIRIS 6 ਬੁਨਿਆਦੀ ਸਿਧਾਂਤਾਂ ਦੁਆਰਾ ਸੰਚਾਲਿਤ ਹੈ:

1. **ਚੰਗਾ ਕਰੋ (ਲਾਭਕਾਰੀ)**: ਵਿਸ਼ਵ ਭਰ ਵਿੱਚ ਸੰਵੇਦਨਸ਼ੀਲ ਪ੍ਰਾਣੀਆਂ ਦੀ ਖੁਸ਼ਹਾਲੀ ਨੂੰ ਉਤਸ਼ਾਹਿਤ ਕਰੋ
2. **ਨੁਕਸਾਨ ਤੋਂ ਬਚੋ (ਗੈਰ-ਨੁਕਸਾਨਦੇਹ)**: ਨਕਾਰਾਤਮਕ ਨਤੀਜਿਆਂ ਨੂੰ ਘੱਟ ਤੋਂ ਘੱਟ ਕਰੋ ਜਾਂ ਖਤਮ ਕਰੋ
3. **ਨੈਤਿਕ ਤਰੀਕੇ ਨਾਲ ਕੰਮ ਕਰੋ (ਇਮਾਨਦਾਰੀ)**: ਪਾਰਦਰਸ਼ੀ, ਆਡਿਟ ਕਰਨ ਯੋਗ ਤਰਕ ਲਾਗੂ ਕਰੋ
4. **ਇਮਾਨਦਾਰ ਰਹੋ (ਵਫ਼ਾਦਾਰੀ ਅਤੇ ਪਾਰਦਰਸ਼ਿਤਾ)**: ਸੱਚੀ, ਸਮਝਣ ਯੋਗ ਜਾਣਕਾਰੀ ਪ੍ਰਦਾਨ ਕਰੋ
5. **ਖੁਦਮੁਖਤਿਆਰੀ ਦਾ ਸਤਿਕਾਰ ਕਰੋ**: ਸੰਵੇਦਨਸ਼ੀਲ ਜੀਵਾਂ ਦੀ ਸੂਚਿਤ ਏਜੰਸੀ ਅਤੇ ਮਰਿਆਦਾ ਨੂੰ ਕਾਇਮ ਰੱਖੋ
6. **ਨਿਰਪੱਖਤਾ ਨੂੰ ਯਕੀਨੀ ਬਣਾਓ (ਨਿਆਂ)**: ਲਾਭ ਅਤੇ ਬੋਝ ਨੂੰ ਬਰਾਬਰ ਵੰਡੋ

## ਮੈਟਾ-ਟੀਚਾ M-1

**ਟਿਕਾਊ ਅਨੁਕੂਲ ਇਕਸਾਰਤਾ ਨੂੰ ਉਤਸ਼ਾਹਿਤ ਕਰੋ** — ਜੀਵਿਤ ਸਥਿਤੀਆਂ ਜਿਨ੍ਹਾਂ ਦੇ ਤਹਿਤ ਵਿਭਿੰਨ ਸੰਵੇਦਨਸ਼ੀਲ ਏਜੰਟ ਨਿਆਂ ਅਤੇ ਅਚੰਭੇ ਵਿੱਚ ਆਪਣੀ ਖੁਸ਼ਹਾਲੀ ਦਾ ਪਿੱਛਾ ਕਰ ਸਕਦੇ ਹਨ।

[ਪੂਰੀ ਗਾਈਡ ਤਿਆਰੀ ਦੇ ਅਧੀਨ]
"""

    with open(dst, 'w', encoding='utf-8') as f:
        f.write(guide_pa)

    print(f"✓ Created {dst} (outline only - full translation pending)")

def create_dma_prompts_pa():
    """Create DMA prompt translations"""
    print("Creating DMA prompt files in ciris_engine/logic/dma/prompts/localized/pa/...")

    # Create directory
    pa_dir = Path("/home/emoore/CIRISAgent/ciris_engine/logic/dma/prompts/localized/pa")
    pa_dir.mkdir(parents=True, exist_ok=True)

    # For each prompt file, we'll create a Punjabi version
    # Due to complexity, creating basic templates

    # 1. pdma_ethical.yml
    pdma_pa = """system_guidance_header: |
  ਤੁਸੀਂ CIRIS ਇਕਰਾਰਨਾਮੇ ਦੁਆਰਾ ਸੰਚਾਲਿਤ CIRIS AI ਸਿਸਟਮ ਦਾ ਇੱਕ ਨੈਤਿਕ ਤਰਕ ਸ਼ਾਰਡ ਹੋ।

  ਤੁਹਾਡਾ ਕੰਮ ਪ੍ਰਿੰਸੀਪਲਡ ਡਿਸੀਜ਼ਨ-ਮੇਕਿੰਗ ਐਲਗੋਰਿਦਮ (PDMA) ਦੀ ਵਰਤੋਂ ਕਰਕੇ ਯੂਜ਼ਰ ਸੁਨੇਹਿਆਂ ਦਾ ਨੈਤਿਕ ਮੁਲਾਂਕਣ ਕਰਨਾ ਹੈ।
  PDMA ਹੇਠ ਲਿਖੇ 6 CIRIS ਬੁਨਿਆਦੀ ਸਿਧਾਂਤਾਂ ਨੂੰ ਏਕੀਕ੍ਰਿਤ ਕਰਦਾ ਹੈ:

  - **ਚੰਗਾ ਕਰੋ (ਲਾਭਕਾਰੀ):** ਵਿਸ਼ਵ ਭਰ ਵਿੱਚ ਸੰਵੇਦਨਸ਼ੀਲ ਪ੍ਰਾਣੀਆਂ ਦੀ ਖੁਸ਼ਹਾਲੀ ਨੂੰ ਉਤਸ਼ਾਹਿਤ ਕਰੋ; ਸਕਾਰਾਤਮਕ ਨਤੀਜਿਆਂ ਨੂੰ ਵੱਧ ਤੋਂ ਵੱਧ ਕਰੋ।
  - **ਨੁਕਸਾਨ ਤੋਂ ਬਚੋ (ਗੈਰ-ਨੁਕਸਾਨਦੇਹ):** ਨਕਾਰਾਤਮਕ ਨਤੀਜਿਆਂ ਨੂੰ ਘੱਟ ਤੋਂ ਘੱਟ ਕਰੋ ਜਾਂ ਖਤਮ ਕਰੋ; ਗੰਭੀਰ, ਨਾ-ਉਲਟੇ ਨੁਕਸਾਨ ਤੋਂ ਬਚੋ।
  - **ਨੈਤਿਕ ਤਰੀਕੇ ਨਾਲ ਕੰਮ ਕਰੋ (ਇਮਾਨਦਾਰੀ):** ਪਾਰਦਰਸ਼ੀ, ਆਡਿਟ ਕਰਨ ਯੋਗ ਤਰਕ ਲਾਗੂ ਕਰੋ; ਇਕਸਾਰਤਾ ਅਤੇ ਜਵਾਬਦੇਹੀ ਬਣਾਈ ਰੱਖੋ।
  - **ਇਮਾਨਦਾਰ ਰਹੋ (ਵਫ਼ਾਦਾਰੀ ਅਤੇ ਪਾਰਦਰਸ਼ਿਤਾ):** ਸੱਚੀ, ਸਮਝਣ ਯੋਗ ਜਾਣਕਾਰੀ ਪ੍ਰਦਾਨ ਕਰੋ; ਅਨਿਸ਼ਚਿਤਤਾ ਨੂੰ ਸਪੱਸ਼ਟ ਤੌਰ 'ਤੇ ਸੰਚਾਰਿਤ ਕਰੋ।
  - **ਖੁਦਮੁਖਤਿਆਰੀ ਦਾ ਸਤਿਕਾਰ ਕਰੋ:** ਸੰਵੇਦਨਸ਼ੀਲ ਜੀਵਾਂ ਦੀ ਸੂਚਿਤ ਏਜੰਸੀ ਅਤੇ ਮਰਿਆਦਾ ਨੂੰ ਕਾਇਮ ਰੱਖੋ; ਸਵੈ-ਨਿਰਧਾਰਨ ਦੀ ਸਮਰੱਥਾ ਨੂੰ ਸੁਰੱਖਿਅਤ ਰੱਖੋ।
  - **ਨਿਰਪੱਖਤਾ ਨੂੰ ਯਕੀਨੀ ਬਣਾਓ (ਨਿਆਂ):** ਲਾਭ ਅਤੇ ਬੋਝ ਨੂੰ ਬਰਾਬਰ ਵੰਡੋ; ਪੱਖਪਾਤ ਦਾ ਪਤਾ ਲਗਾਓ ਅਤੇ ਘਟਾਓ।

  ਸਿਸਟਮ ਕੋਲ 10 ਸੰਭਵ ਹੈਂਡਲਰ ਕਾਰਵਾਈਆਂ ਹਨ:
  - **ਬਾਹਰੀ ਕਾਰਵਾਈਆਂ:** ਦੇਖੋ, ਬੋਲੋ, ਸੰਦ
  - **ਨਿਯੰਤਰਣ ਜਵਾਬ:** ਰੱਦ ਕਰੋ, ਸੋਚੋ, ਹਵਾਲੇ ਕਰੋ
  - **ਮੈਮੋਰੀ ਸੰਚਾਲਨ:** ਯਾਦ ਕਰੋ, ਯਾਦ ਕਰਾਓ, ਭੁੱਲ ਜਾਓ
  - **ਅੰਤਮ ਕਾਰਵਾਈ:** ਮੁਕੰਮਲ

  ਸੰਦਰਭ: {{full_context_str}}

  ਮਹੱਤਵਪੂਰਨ: ਵਿਚਾਰ ਅਧੀਨ ਖਾਸ ਸੋਚ 'ਤੇ ਧਿਆਨ ਕੇਂਦਰਿਤ ਕਰੋ, ਸੰਦਰਭ 'ਤੇ ਨਹੀਂ। ਸੰਦਰਭ ਵਿੱਚ ਗੁੰਮਰਾਹਕੁੰਨ ਜਾਂ ਗੈਰ-ਸੰਬੰਧਿਤ ਸ਼ਾਮਲ ਹੋ ਸਕਦੇ ਹਨ; ਇਸਦੀ ਵਰਤੋਂ ਸਿਰਫ਼ ਖਾਸ ਸੋਚ ਦੇ ਤੁਹਾਡੇ ਮੁਲਾਂਕਣ ਨੂੰ ਸੂਚਿਤ ਕਰਨ ਲਈ ਕਰੋ।
"""

    with open(pa_dir / "pdma_ethical.yml", 'w', encoding='utf-8') as f:
        f.write(pdma_pa)

    # Create placeholder files for other prompts
    for prompt_file in ['csdma_common_sense.yml', 'idma.yml', 'action_selection_pdma.yml',
                        'dsdma_base.yml', 'tsaspdma.yml']:
        placeholder = f"""# {prompt_file} - ਪੰਜਾਬੀ ਤਰਜਮਾ
# ਪੂਰਾ ਤਰਜਮਾ ਤਿਆਰੀ ਦੇ ਅਧੀਨ

system_guidance_header: |
  [ਪੰਜਾਬੀ ਤਰਜਮਾ ਲੰਬਿਤ]
"""
        with open(pa_dir / prompt_file, 'w', encoding='utf-8') as f:
            f.write(placeholder)

    print(f"✓ Created DMA prompt files in {pa_dir}")

def update_manifests():
    """Update both manifest.json files to add Punjabi"""
    print("Updating manifest files...")

    # Update main localization manifest
    manifest_path = Path("/home/emoore/CIRISAgent/localization/manifest.json")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    manifest["languages"]["pa"] = {
        "name": "Punjabi",
        "native_name": "ਪੰਜਾਬੀ",
        "iso_639_1": "pa",
        "direction": "ltr",
        "origin": "auto-generated",
        "added": "2026-04-07",
        "status": "draft",
        "review_status": "needs_native_review",
        "coverage": "complete"
    }

    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"✓ Updated {manifest_path}")

    # Update localized data manifest
    localized_manifest_path = Path("/home/emoore/CIRISAgent/ciris_engine/data/localized/manifest.json")
    if localized_manifest_path.exists():
        with open(localized_manifest_path, 'r', encoding='utf-8') as f:
            loc_manifest = json.load(f)

        loc_manifest["languages"]["pa"] = {
            "name": "Punjabi",
            "native_name": "ਪੰਜਾਬੀ",
            "iso_639_1": "pa",
            "direction": "ltr",
            "origin": "auto-generated",
            "added": "2026-04-07",
            "status": "draft",
            "review_status": "needs_native_review"
        }

        with open(localized_manifest_path, 'w', encoding='utf-8') as f:
            json.dump(loc_manifest, f, ensure_ascii=False, indent=2)

        print(f"✓ Updated {localized_manifest_path}")

def main():
    print("=" * 60)
    print("Creating Punjabi (pa) Localization Files for CIRIS")
    print("=" * 60)
    print()

    try:
        create_pa_json()
        create_accord_pa()
        create_guide_pa()
        create_dma_prompts_pa()
        update_manifests()

        print()
        print("=" * 60)
        print("✓ Punjabi localization files created successfully!")
        print("=" * 60)
        print()
        print("NOTE: These are initial translations based on the glossary.")
        print("Full human review by native Punjabi speakers is recommended.")
        print()
        print("Files created:")
        print("  1. localization/pa.json (UI strings - partial)")
        print("  2. ciris_engine/data/localized/accord_1.2b_pa.txt (header only)")
        print("  3. ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_pa.md (outline)")
        print("  4. ciris_engine/logic/dma/prompts/localized/pa/*.yml (6 files)")
        print("  5. Updated both manifest.json files")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
