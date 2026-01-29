# Ordercli Adapter

> Converted from Clawdbot skill: `ordercli`

Foodora-only CLI for checking past orders and active order status (Deliveroo WIP).

## Requirements

- **Binaries**: ordercli

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_ordercli
```

## Original Skill Documentation

# ordercli

Use `ordercli` to check past orders and track active order status (Foodora only right now).

Quick start (Foodora)
- `ordercli foodora countries`
- `ordercli foodora config set --country AT`
- `ordercli foodora login --email you@example.com --password-stdin`
- `ordercli foodora orders`
- `ordercli foodora history --limit 20`
- `ordercli foodora history show <orderCode>`

Orders
- Active list (arrival/status): `ordercli foodora orders`
- Watch: `ordercli foodora orders --watch`
- Active order detail: `ordercli foodora order <orderCode>`
- History detail JSON: `ordercli foodora history show <orderCode> --json`

Reorder (adds to cart)
- Preview: `ordercli foodora reorder <orderCode>`
- Confirm: `ordercli foodora reorder <orderCode> --confirm`
- Address: `ordercli foodora reorder <orderCode> --confirm --address-id <id>`

Cloudflare / bot protection
- Browser login: `ordercli foodora login --email you@example.com --password-stdin --browser`
- Reuse profile: `--browser-profile "$HOME/Library/Application Support/ordercli/browser-profile"`
- Import Chrome cookies: `ordercli foodora cookies chrome --profile "Default"`

Session import (no password)
- `ordercli foodora session chrome --url https://www.foodora.at/ --profile "Default"`
- `ordercli foodora session refresh --client-id android`

Deliveroo (WIP, not working yet)
- Requires `DELIVEROO_BEARER_TOKEN` (optional `DELIVEROO_COOKIE`).
- `ordercli deliveroo config set --market uk`
- `ordercli deliveroo history`

Notes
- Use `--config /tmp/ordercli.json` for testing.
- Confirm before any reorder or cart-changing action.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/ordercli/SKILL.md*
