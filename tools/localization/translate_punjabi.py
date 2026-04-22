#!/usr/bin/env python3
"""
Translate CIRIS localization files to Punjabi using the glossary.
This script creates all required localization files for Punjabi (pa).
"""

import json
import os
from pathlib import Path

# Punjabi translations based on glossary
GLOSSARY = {
    # Core action verbs
    "observe": "ਦੇਖੋ",
    "speak": "ਬੋਲੋ",
    "tool": "ਸੰਦ",
    "reject": "ਰੱਦ ਕਰੋ",
    "ponder": "ਸੋਚੋ",
    "defer": "ਹਵਾਲੇ ਕਰੋ",
    "memorize": "ਯਾਦ ਕਰੋ",
    "recall": "ਯਾਦ ਕਰਾਓ",
    "forget": "ਭੁੱਲ ਜਾਓ",
    "task_complete": "ਮੁਕੰਮਲ",
    # Core concepts
    "ACCORD": "ਇਕਰਾਰਨਾਮਾ",
    "Wise Authority": "ਸਿਆਣੀ ਅਥਾਰਟੀ",
    "Conscience": "ਜ਼ਮੀਰ",
    "Principal Hierarchy": "ਮੁੱਖ ਲੜੀ",
    "Coherence": "ਇਕਸਾਰਤਾ",
    "Epistemic Humility": "ਗਿਆਨ ਦੀ ਨਿਮਰਤਾ",
    "Integrity": "ਇਮਾਨਦਾਰੀ",
    "Resilience": "ਲਚਕੀਲਾਪਨ",
    "Signalling Gratitude": "ਧੰਨਵਾਦ ਪ੍ਰਗਟ ਕਰਨਾ",
    "Flourishing": "ਖੁਸ਼ਹਾਲੀ",
    # Technical terms (keep in English mostly)
    "Agent": "ਏਜੰਟ",
    "Token": "ਟੋਕਨ",
    "Adapter": "ਅਡੈਪਟਰ",
    "Service": "ਸੇਵਾ",
    "Pipeline": "ਪਾਈਪਲਾਈਨ",
    "Memory": "ਮੈਮੋਰੀ",
    "Graph": "ਗ੍ਰਾਫ",
    # Cognitive states
    "WAKEUP": "ਜਾਗੋ",
    "WORK": "ਕੰਮ",
    "PLAY": "ਖੇਡੋ",
    "SOLITUDE": "ਇਕੱਲਤਾ",
    "DREAM": "ਸੁਪਨਾ",
    "SHUTDOWN": "ਬੰਦ",
    # UI labels
    "Login": "ਲੌਗਇਨ",
    "Logout": "ਲੌਗਆਊਟ",
    "Settings": "ਸੈਟਿੰਗਾਂ",
    "Messages": "ਸੁਨੇਹੇ",
    "Send": "ਭੇਜੋ",
    "Cancel": "ਰੱਦ ਕਰੋ",
    "Confirm": "ਪੁਸ਼ਟੀ ਕਰੋ",
    "Error": "ਗਲਤੀ",
    "Warning": "ਚੇਤਾਵਨੀ",
    "Success": "ਸਫਲਤਾ",
    "Loading": "ਲੋਡ ਹੋ ਰਿਹਾ ਹੈ",
    "Save": "ਸੁਰੱਖਿਅਤ ਕਰੋ",
    "Delete": "ਮਿਟਾਓ",
    "Edit": "ਸੋਧੋ",
}

# Common phrases
PHRASES = {
    "How can I help you?": "ਮੈਂ ਤੁਹਾਡੀ ਕੀ ਮਦਦ ਕਰ ਸਕਦਾ ਹਾਂ?",
    "I need to think about this": "ਮੈਨੂੰ ਇਸ ਬਾਰੇ ਸੋਚਣਾ ਪਵੇਗਾ",
    "Let me check with my Wise Authority": "ਮੈਨੂੰ ਆਪਣੀ ਸਿਆਣੀ ਅਥਾਰਟੀ ਨਾਲ ਸਲਾਹ ਕਰਨ ਦਿਓ",
    "Task completed successfully": "ਕੰਮ ਸਫਲਤਾਪੂਰਵਕ ਪੂਰਾ ਹੋਇਆ",
    "I cannot perform this action": "ਮੈਂ ਇਹ ਕਾਰਵਾਈ ਨਹੀਂ ਕਰ ਸਕਦਾ",
    "Please wait while I process this": "ਕਿਰਪਾ ਕਰਕੇ ਉਡੀਕ ਕਰੋ ਜਦੋਂ ਮੈਂ ਇਸ ਨੂੰ ਪ੍ਰੋਸੈਸ ਕਰਦਾ ਹਾਂ",
    "I understand your request": "ਮੈਂ ਤੁਹਾਡੀ ਬੇਨਤੀ ਸਮਝਦਾ ਹਾਂ",
}


def main():
    print("This is a placeholder script for Punjabi translation.")
    print("The actual translation will be done manually using the glossary.")
    print(f"Glossary has {len(GLOSSARY)} core terms")
    print(f"Phrases has {len(PHRASES)} common phrases")


if __name__ == "__main__":
    main()
