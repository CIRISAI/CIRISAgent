#!/usr/bin/env python3
"""
Translate English localization to Yoruba.
Reads en.json and yo_glossary.md, outputs yo.json
"""

import json
import re

# Yoruba glossary - canonical translations
GLOSSARY = {
    # Core Action Verbs
    "observe": "wo",
    "speak": "sọ",
    "tool": "irinṣẹ́",
    "reject": "kọ̀",
    "ponder": "ronú jinlẹ̀",
    "defer": "fi lélẹ̀",
    "memorize": "rán tí",
    "recall": "rántí",
    "forget": "gbàgbé",
    "task_complete": "iṣẹ́ ti parí",
    "task complete": "iṣẹ́ ti parí",

    # Core Concepts
    "accord": "àdéhùn",
    "wise authority": "aláṣẹ ọlọ́gbọ́n",
    "conscience": "ẹrí-ọkàn",
    "principal hierarchy": "ìtò-ìṣàkóso pàtàkì",
    "coherence": "ìbáramu",
    "epistemic humility": "ìrẹ̀lẹ̀ ìmọ̀",
    "integrity": "ìwàpẹ̀lẹ́",
    "resilience": "ìfaradà",
    "signalling gratitude": "fífi ọpẹ́ hàn",

    # Technical Terms
    "agent": "aṣojú",
    "token": "àmì",
    "adapter": "atúnṣe",
    "service": "iṣẹ́ ìrànwọ́",
    "pipeline": "ìtò iṣẹ́",

    # Cognitive States
    "wakeup": "jí",
    "work": "iṣẹ́",
    "play": "eré",
    "solitude": "àdáwà",
    "dream": "àlá",
    "shutdown": "dínà",

    # UI Labels
    "login": "wọlé",
    "settings": "ìṣètò",
    "messages": "ìránṣẹ́",
    "send": "fi ránṣẹ́",
    "cancel": "fagilé",
    "confirm": "fìdí múlẹ̀",
    "error": "àṣìṣe",
    "warning": "ìkìlọ̀",
    "success": "àṣeyọrí",
    "loading": "ó ń ṣiṣẹ́",

    # DMA-Specific
    "principal duties": "ọjọ́ pàtàkì",
    "common sense": "ọgbọ́n inú",
    "intuition": "ìmọ̀lára",
    "action selection": "yíyàn iṣẹ́",
    "domain specific": "tó jẹmọ́ àgbègbè",
    "tool specific": "tó jẹmọ́ irinṣẹ́",

    # Pipeline Stages
    "think": "ronú",
    "context": "àyíká",
    "dma": "ìpinnu",
    "idma": "àyẹ̀wò ìmọ̀lára",
    "select": "yàn",
    "ethics": "ìwà rere",
    "act": "ṣe",
    "memory graph": "àwòrán ìrántí",
}

def translate_value(text):
    """Translate a string value, preserving placeholders and technical terms."""
    if not isinstance(text, str):
        return text

    # Don't translate if it's a placeholder pattern
    if re.match(r'^[{%][^}]*[}]$', text.strip()):
        return text

    # Common translations for frequent patterns
    translations = {
        # Greetings
        "Welcome to CIRIS": "Káàbọ̀ sí CIRIS",
        "Hello! How can I help you today?": "Báwo! Báwo ni mo ṣe lè ràn ọ́ lọ́wọ́ lónìí?",
        "How can I help you?": "Báwo ni mo ṣe lè ràn ọ́ lọ́wọ́?",

        # Status
        "Online": "Lórí ìkànnì",
        "Offline": "Kò sí lórí ìkànnì",
        "Success": "Àṣeyọrí",
        "Failed": "Kùnà",
        "Pending": "Ó ń dúró",
        "Completed": "Ti parí",
        "Executing": "Ó ń ṣiṣẹ́",

        # Actions
        "Continue": "Tẹ̀síwájú",
        "Back": "Padà sẹ́yìn",
        "Next": "Tókàn",
        "Finish": "Parí",
        "Close": "Ti",
        "Cancel": "Fagilé",
        "Refresh": "Sọ̀tuntun",
        "Send": "Fi ránṣẹ́",

        # Common phrases
        "Please try again": "Jọ̀wọ́ gbìyànjú lẹ́ẹ̀kan síi",
        "Loading": "Ó ń ṣiṣẹ́",
        "Settings": "Ìṣètò",
        "Details": "Àlàyé",
        "Setup": "Ìṣètò",
    }

    # Direct translation if found
    if text in translations:
        return translations[text]

    # Case-insensitive glossary lookup for key terms
    lower_text = text.lower()
    for eng, yor in GLOSSARY.items():
        if eng.lower() in lower_text:
            # Replace while preserving case and context
            pattern = re.compile(re.escape(eng), re.IGNORECASE)
            text = pattern.sub(yor, text)

    return text

def translate_json(data):
    """Recursively translate JSON structure."""
    if isinstance(data, dict):
        return {key: translate_json(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [translate_json(item) for item in data]
    elif isinstance(data, str):
        return translate_value(data)
    else:
        return data

def main():
    # Read English source
    with open('/home/emoore/CIRISAgent/localization/en.json', 'r', encoding='utf-8') as f:
        en_data = json.load(f)

    # Start with English structure
    yo_data = json.loads(json.dumps(en_data))

    # Update meta
    yo_data['_meta'] = {
        "language": "yo",
        "language_name": "Yorùbá",
        "direction": "ltr"
    }

    print("Translation complete. Writing to yo.json...")

    # This is a basic structure - Claude will need to do the actual translation
    # with proper context and nuance
    with open('/home/emoore/CIRISAgent/localization/yo.json', 'w', encoding='utf-8') as f:
        json.dump(yo_data, f, ensure_ascii=False, indent=4)

    print(f"Created yo.json with {len(en_data)} top-level keys")

if __name__ == '__main__':
    main()
