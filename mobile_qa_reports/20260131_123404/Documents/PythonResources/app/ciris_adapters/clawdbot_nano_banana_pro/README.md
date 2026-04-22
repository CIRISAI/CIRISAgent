# NanoBananaPro Adapter

> Converted from Clawdbot skill: `nano-banana-pro`

Generate or edit images via Gemini 3 Pro Image (Nano Banana Pro).

## Requirements

- **Binaries**: uv
- **Environment**: GEMINI_API_KEY

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_nano_banana_pro
```

## Original Skill Documentation

# Nano Banana Pro (Gemini 3 Pro Image)

Use the bundled script to generate or edit images.

Generate
```bash
uv run {baseDir}/scripts/generate_image.py --prompt "your image description" --filename "output.png" --resolution 1K
```

Edit (single image)
```bash
uv run {baseDir}/scripts/generate_image.py --prompt "edit instructions" --filename "output.png" -i "/path/in.png" --resolution 2K
```

Multi-image composition (up to 14 images)
```bash
uv run {baseDir}/scripts/generate_image.py --prompt "combine these into one scene" --filename "output.png" -i img1.png -i img2.png -i img3.png
```

API key
- `GEMINI_API_KEY` env var
- Or set `skills."nano-banana-pro".apiKey` / `skills."nano-banana-pro".env.GEMINI_API_KEY` in `~/.clawdbot/moltbot.json`

Notes
- Resolutions: `1K` (default), `2K`, `4K`.
- Use timestamps in filenames: `yyyy-mm-dd-hh-mm-ss-name.png`.
- The script prints a `MEDIA:` line for Moltbot to auto-attach on supported chat providers.
- Do not read the image back; report the saved path only.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/nano-banana-pro/SKILL.md*
