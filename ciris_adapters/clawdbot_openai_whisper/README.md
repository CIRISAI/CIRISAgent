# OpenaiWhisper Adapter

> Converted from Clawdbot skill: `openai-whisper`

Local speech-to-text with the Whisper CLI (no API key).

## Requirements

- **Binaries**: whisper

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_openai_whisper
```

## Original Skill Documentation

# Whisper (CLI)

Use `whisper` to transcribe audio locally.

Quick start
- `whisper /path/audio.mp3 --model medium --output_format txt --output_dir .`
- `whisper /path/audio.m4a --task translate --output_format srt`

Notes
- Models download to `~/.cache/whisper` on first run.
- `--model` defaults to `turbo` on this install.
- Use smaller models for speed, larger for accuracy.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/openai-whisper/SKILL.md*
