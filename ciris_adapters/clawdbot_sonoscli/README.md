# Sonoscli Adapter

> Converted from Clawdbot skill: `sonoscli`

Control Sonos speakers (discover/status/play/volume/group).

## Requirements

- **Binaries**: sonos

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_sonoscli
```

## Original Skill Documentation

# Sonos CLI

Use `sonos` to control Sonos speakers on the local network.

Quick start
- `sonos discover`
- `sonos status --name "Kitchen"`
- `sonos play|pause|stop --name "Kitchen"`
- `sonos volume set 15 --name "Kitchen"`

Common tasks
- Grouping: `sonos group status|join|unjoin|party|solo`
- Favorites: `sonos favorites list|open`
- Queue: `sonos queue list|play|clear`
- Spotify search (via SMAPI): `sonos smapi search --service "Spotify" --category tracks "query"`

Notes
- If SSDP fails, specify `--ip <speaker-ip>`.
- Spotify Web API search is optional and requires `SPOTIFY_CLIENT_ID/SECRET`.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/sonoscli/SKILL.md*
