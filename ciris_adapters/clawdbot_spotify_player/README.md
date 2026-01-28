# SpotifyPlayer Adapter

> Converted from Clawdbot skill: `spotify-player`

Terminal Spotify playback/search via spogo (preferred) or spotify_player.

## Requirements

- **Any of**: spogo, spotify_player

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_spotify_player
```

## Original Skill Documentation

# spogo / spotify_player

Use `spogo` **(preferred)** for Spotify playback/search. Fall back to `spotify_player` if needed.

Requirements
- Spotify Premium account.
- Either `spogo` or `spotify_player` installed.

spogo setup
- Import cookies: `spogo auth import --browser chrome`

Common CLI commands
- Search: `spogo search track "query"`
- Playback: `spogo play|pause|next|prev`
- Devices: `spogo device list`, `spogo device set "<name|id>"`
- Status: `spogo status`

spotify_player commands (fallback)
- Search: `spotify_player search "query"`
- Playback: `spotify_player playback play|pause|next|previous`
- Connect device: `spotify_player connect`
- Like track: `spotify_player like`

Notes
- Config folder: `~/.config/spotify-player` (e.g., `app.toml`).
- For Spotify Connect integration, set a user `client_id` in config.
- TUI shortcuts are available via `?` in the app.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/spotify-player/SKILL.md*
