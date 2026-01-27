# Blucli Adapter

> Converted from Clawdbot skill: `blucli`

BluOS CLI (blu) for discovery, playback, grouping, and volume.

## Requirements

- **Binaries**: blu

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_blucli
```

## Original Skill Documentation

# blucli (blu)

Use `blu` to control Bluesound/NAD players.

Quick start
- `blu devices` (pick target)
- `blu --device <id> status`
- `blu play|pause|stop`
- `blu volume set 15`

Target selection (in priority order)
- `--device <id|name|alias>`
- `BLU_DEVICE`
- config default (if set)

Common tasks
- Grouping: `blu group status|add|remove`
- TuneIn search/play: `blu tunein search "query"`, `blu tunein play "query"`

Prefer `--json` for scripts. Confirm the target device before changing playback.

---

*Converted by CIRIS Skill Converter*
*Source: ../clawdbot/skills/blucli/SKILL.md*
