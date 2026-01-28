# Imsg Adapter

> Converted from Clawdbot skill: `imsg`

iMessage/SMS CLI for listing chats, history, watch, and sending.

## Requirements

- **Binaries**: imsg
- **Platforms**: darwin

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_imsg
```

## Original Skill Documentation

# imsg

Use `imsg` to read and send Messages.app iMessage/SMS on macOS.

Requirements
- Messages.app signed in
- Full Disk Access for your terminal
- Automation permission to control Messages.app (for sending)

Common commands
- List chats: `imsg chats --limit 10 --json`
- History: `imsg history --chat-id 1 --limit 20 --attachments --json`
- Watch: `imsg watch --chat-id 1 --attachments`
- Send: `imsg send --to "+14155551212" --text "hi" --file /path/pic.jpg`

Notes
- `--service imessage|sms|auto` controls delivery.
- Confirm recipient + message before sending.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/imsg/SKILL.md*
