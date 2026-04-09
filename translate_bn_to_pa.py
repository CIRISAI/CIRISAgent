#!/usr/bin/env python3
"""
Translate Bengali (bn) files to Punjabi (pa) for CIRIS localization.
This performs systematic translation using the Punjabi glossary.
"""

import json
import re
from pathlib import Path

# Core translation mappings from Bengali to Punjabi
# Based on pa_glossary.md and Indic language cognates
TRANSLATIONS = {
    # Metadata
    "বাংলা": "ਪੰਜਾਬੀ",
    "bn": "pa",

    # Greetings and common phrases
    "স্বাগতম": "ਜੀ ਆਇਆਂ ਨੂੰ",
    "হ্যালো": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ",
    "ধন্যবাদ": "ਧੰਨਵਾਦ",
    "দয়া করে": "ਕਿਰਪਾ ਕਰਕੇ",
    "আপনি": "ਤੁਸੀਂ",
    "আমি": "ਮੈਂ",
    "আপনার": "ਤੁਹਾਡੇ",
    "আমার": "ਮੇਰੇ",

    # Setup wizard
    "স্বাগতম CIRIS-এ": "CIRIS ਵਿੱਚ ਜੀ ਆਇਆਂ ਨੂੰ",
    "পছন্দ": "ਪਸੰਦ",
    "ভাষা": "ਭਾਸ਼ਾ",
    "অবস্থান": "ਸਥਿਤੀ",
    "ঐচ্ছিক": "ਵਿਕਲਪਿਕ",
    "দেশ": "ਦੇਸ਼",
    "অঞ্চল": "ਖੇਤਰ",
    "রাজ্য": "ਰਾਜ",
    "শহর": "ਸ਼ਹਿਰ",
    "কনফিগারেশন": "ਸੰਰਚਨਾ",
    "সেটআপ": "ਸੈੱਟਅੱਪ",
    "নিশ্চিত করুন": "ਪੁਸ਼ਟੀ ਕਰੋ",
    "পরবর্তী": "ਅੱਗੇ",
    "পূর্ববর্তী": "ਪਿੱਛੇ",
    "এগিয়ে যান": "ਜਾਰੀ ਰੱਖੋ",
    "সম্পন্ন": "ਮੁਕੰਮਲ",
    "সফল": "ਸਫਲਤਾ",

    # Agent messages
    "আমি কিভাবে সাহায্য করতে পারি": "ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ",
    "ভাবতে দিন": "ਸੋਚਣ ਦਿਓ",
    "সমস্যা": "ਸਮੱਸਿਆ",
    "অনুরোধ": "ਬੇਨਤੀ",
    "পুনরায় চেষ্টা করুন": "ਦੁਬਾਰਾ ਕੋਸ਼ਿਸ਼ ਕਰੋ",
    "পরামর্শদাতা": "ਸਲਾਹਕਾਰ",
    "মানব": "ਮਨੁੱਖੀ",
    "কাজ সম্পন্ন": "ਕੰਮ ਪੂਰਾ ਹੋਇਆ",
    "অনুমতি নেই": "ਇਜਾਜ਼ਤ ਨਹੀਂ",
    "স্পষ್ট করুন": "ਸਪੱਸ਼ਟ ਕਰੋ",
    "বার্তা": "ਸੁਨੇਹਾ",
    "প্রত্যাখ্যান": "ਰੱਦ",

    # Status
    "কার্যকর হচ্ছে": "ਚਲਾ ਰਿਹਾ ਹੈ",
    "সম্পূর্ণ": "ਪੂਰਾ ਹੋਇਆ",
    "ব্যর্থ": "ਅਸਫਲ",
    "অপেক্ষমাণ": "ਬਾਕੀ",
    "অনলাইন": "ਔਨਲਾਈਨ",
    "অফলাইন": "ਔਫਲਾਈਨ",
    "সাফল্য": "ਸਫਲਤਾ",
    "ত্রুটি": "ਗਲਤੀ",

    # Core action verbs (from glossary)
    "পর্যবেক্ষণ": "ਦੇਖੋ",
    "বলুন": "ਬੋਲੋ",
    "সরঞ্জাম": "ਸੰਦ",
    "প্রত্যাখ্যান করুন": "ਰੱਦ ਕਰੋ",
    "চিন্তা": "ਸੋਚੋ",
    "স্থগিত": "ਹਵਾਲੇ ਕਰੋ",
    "মুখস্থ": "ਯਾਦ ਕਰੋ",
    "স্মরণ": "ਯਾਦ ਕਰਾਓ",
    "ভুলে যান": "ਭੁੱਲ ਜਾਓ",

    # ACCORD concepts
    "চুক্তি": "ਇਕਰਾਰਨਾਮਾ",
    "জ্ঞানী কর্তৃপক্ষ": "ਸਿਆਣੀ ਅਥਾਰਟੀ",
    "বিবেক": "ਜ਼ਮੀਰ",
    "সততা": "ਇਮਾਨਦਾਰੀ",
    "স্থিতিস্থাপকতা": "ਲਚਕੀਲਾਪਨ",
    "সমৃদ্ধি": "ਖੁਸ਼ਹਾਲੀ",
    "সংগতি": "ਇਕਸਾਰਤਾ",
    "জ্ঞানের নম্রতা": "ਗਿਆਨ ਦੀ ਨਿਮਰਤਾ",

    # Technical terms
    "এজেন্ট": "ਏਜੰਟ",
    "টোকেন": "ਟੋਕਨ",
    "অ্যাডাপ্টার": "ਅਡੈਪਟਰ",
    "সেবা": "ਸੇਵਾ",
    "পাইপলাইন": "ਪਾਈਪਲਾਈਨ",
    "মেমরি": "ਮੈਮੋਰੀ",
    "গ্রাফ": "ਗ੍ਰਾਫ",

    # Mobile UI
    "পাঠান": "ਭੇਜੋ",
    "বাতিল": "ਰੱਦ ਕਰੋ",
    "সংরক্ষণ": "ਸੁਰੱਖਿਅਤ ਕਰੋ",
    "মুছুন": "ਮਿਟਾਓ",
    "সম্পাদনা": "ਸੋਧੋ",
    "সেটিংস": "ਸੈਟਿੰਗਾਂ",
    "প্রধান": "ਮੁੱਖ",
    "সাহায্য": "ਮਦਦ",
    "বন্ধ": "ਬੰਦ",

    # Common words
    "প্রয়োজনীয়": "ਲੋੜੀਂਦਾ",
    "বিবরণ": "ਵੇਰਵਾ",
    "তথ্য": "ਜਾਣਕਾਰੀ",
    "প্রক্রিয়া": "ਪ੍ਰੋਸੈਸ",
    "শুরু": "ਸ਼ੁਰੂ",
    "শেষ": "ਅੰਤ",
    "সময়": "ਸਮਾਂ",
    "তারিখ": "ਤਾਰੀਖ",
    "ব্যবহারকারী": "ਯੂਜ਼ਰ",
    "সিস্টেম": "ਸਿਸਟਮ",
    "নিরাপত্তা": "ਸੁਰੱਖਿਆ",
    "ব্যক্তিগত": "ਨਿੱਜੀ",
    "সর্বজনীন": "ਜਨਤਕ",
}

def translate_text(text: str) -> str:
    """Translate text from Bengali to Punjabi using word substitutions"""
    result = text
    for bn, pa in TRANSLATIONS.items():
        result = result.replace(bn, pa)
    return result

def translate_json_file():
    """Translate pa.json file"""
    print("Translating localization/pa.json...")

    path = Path("/home/emoore/CIRISAgent/localization/pa.json")
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    def translate_dict(obj):
        """Recursively translate dictionary values"""
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key == "_meta":
                    # Update metadata specifically
                    result[key] = {
                        "language": "pa",
                        "language_name": "ਪੰਜਾਬੀ",
                        "direction": "ltr"
                    }
                else:
                    result[key] = translate_dict(value)
            return result
        elif isinstance(obj, str):
            return translate_text(obj)
        elif isinstance(obj, list):
            return [translate_dict(item) for item in obj]
        else:
            return obj

    translated = translate_dict(data)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(translated, f, ensure_ascii=False, indent=4)

    print(f"✓ Translated {path}")

def translate_accord_file():
    """Translate ACCORD file"""
    print("Translating accord_1.2b_pa.txt...")

    path = Path("/home/emoore/CIRISAgent/ciris_engine/data/localized/accord_1.2b_pa.txt")
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Translate content
    translated = translate_text(content)

    # Update header to Punjabi
    translated = re.sub(
        r'// CIRIS.*?\n',
        '// CIRIS ਇਕਰਾਰਨਾਮਾ v1.2-ਬੀਟਾ\n',
        translated,
        count=1
    )

    with open(path, 'w', encoding='utf-8') as f:
        f.write(translated)

    print(f"✓ Translated {path}")

def translate_guide_file():
    """Translate Comprehensive Guide"""
    print("Translating CIRIS_COMPREHENSIVE_GUIDE_pa.md...")

    path = Path("/home/emoore/CIRISAgent/ciris_engine/data/localized/CIRIS_COMPREHENSIVE_GUIDE_pa.md")
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Translate content
    translated = translate_text(content)

    # Update title
    translated = re.sub(
        r'# CIRIS.*?\n',
        '# CIRIS ਵਿਸਥਾਰਪੂਰਵਕ ਗਾਈਡ\n',
        translated,
        count=1
    )

    with open(path, 'w', encoding='utf-8') as f:
        f.write(translated)

    print(f"✓ Translated {path}")

def translate_dma_prompts():
    """Translate DMA prompt files"""
    print("Translating DMA prompts...")

    pa_dir = Path("/home/emoore/CIRISAgent/ciris_engine/logic/dma/prompts/localized/pa")

    for yml_file in pa_dir.glob("*.yml"):
        with open(yml_file, 'r', encoding='utf-8') as f:
            content = f.read()

        translated = translate_text(content)

        with open(yml_file, 'w', encoding='utf-8') as f:
            f.write(translated)

        print(f"  ✓ Translated {yml_file.name}")

def main():
    print("=" * 60)
    print("Translating Bengali files to Punjabi")
    print("=" * 60)
    print()

    try:
        translate_json_file()
        translate_accord_file()
        translate_guide_file()
        translate_dma_prompts()

        print()
        print("=" * 60)
        print("✓ Translation completed successfully!")
        print("=" * 60)
        print()
        print("NOTE: This is automated translation using word substitutions.")
        print("Native Punjabi speaker review is strongly recommended.")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0

if __name__ == "__main__":
    exit(main())
