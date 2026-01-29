# Gemini Adapter

> Converted from Clawdbot skill: `gemini`

Gemini CLI for one-shot Q&A, summaries, and generation.

## Requirements

- **Binaries**: gemini

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_gemini
```

## Original Skill Documentation

# Gemini CLI

Use Gemini in one-shot mode with a positional prompt (avoid interactive mode).

Quick start
- `gemini "Answer this question..."`
- `gemini --model <name> "Prompt..."`
- `gemini --output-format json "Return JSON"`

Extensions
- List: `gemini --list-extensions`
- Manage: `gemini extensions <command>`

Notes
- If auth is required, run `gemini` once interactively and follow the login flow.
- Avoid `--yolo` for safety.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/gemini/SKILL.md*
