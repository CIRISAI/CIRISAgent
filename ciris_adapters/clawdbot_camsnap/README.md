# Camsnap Adapter

> Converted from Clawdbot skill: `camsnap`

Capture frames or clips from RTSP/ONVIF cameras.

## Requirements

- **Binaries**: camsnap

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_camsnap
```

## Original Skill Documentation

# camsnap

Use `camsnap` to grab snapshots, clips, or motion events from configured cameras.

Setup
- Config file: `~/.config/camsnap/config.yaml`
- Add camera: `camsnap add --name kitchen --host 192.168.0.10 --user user --pass pass`

Common commands
- Discover: `camsnap discover --info`
- Snapshot: `camsnap snap kitchen --out shot.jpg`
- Clip: `camsnap clip kitchen --dur 5s --out clip.mp4`
- Motion watch: `camsnap watch kitchen --threshold 0.2 --action '...'`
- Doctor: `camsnap doctor --probe`

Notes
- Requires `ffmpeg` on PATH.
- Prefer a short test capture before longer clips.

---

*Converted by CIRIS Skill Converter*
*Source: ../clawdbot/skills/camsnap/SKILL.md*
