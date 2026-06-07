<div align="center">

[![License](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/Status-STABLE-green.svg)](CHANGELOG.md)
[![DeepWiki](https://img.shields.io/badge/DeepWiki-CIRIS_Codebase-blue?logo=readthedocs)](https://deepwiki.com/CIRISAI/CIRISAgent)
[![CIRIS Architecture](https://img.shields.io/badge/Paper-CIRIS_Architecture-orange?logo=arxiv)](https://doi.org/10.5281/zenodo.18137161)
[![Coherence Ratchet](https://img.shields.io/badge/Paper-Coherence_Ratchet-orange?logo=arxiv)](https://doi.org/10.5281/zenodo.18142668)
[![Accord](https://img.shields.io/badge/Ethical_Framework-The_Accord-purple)](https://ciris.ai/ciris_accord.pdf)

# CIRIS

### A safer, more ethical AI assistant — one you can actually check.

[![Download on the App Store](https://img.shields.io/badge/Download-App%20Store-0D96F6?style=for-the-badge&logo=apple&logoColor=white)](https://apps.apple.com/us/app/cirisagent/id6758524415)
&nbsp;&nbsp;
[![Get it on Google Play](https://img.shields.io/badge/Get%20it%20on-Google%20Play-48B563?style=for-the-badge&logo=googleplay&logoColor=white)](https://play.google.com/store/apps/details?id=ai.ciris.mobile)

</div>

CIRIS replaces apps like ChatGPT and Grok everywhere you need AI. It's the
same chat you already expect — but it shows its reasoning, escalates to a
human when it's unsure, keeps your data private, works in 29 languages, and
runs on your own device. Open source, free, no ads, no growth-at-all-costs
pressure.

**Desktop & self-host:** `pip install ciris-agent` — see [Run it yourself](#run-it-yourself).
Sign in with Google for the free hosted CIRIS model, or bring your own key
(OpenAI, Anthropic, Groq, Together.ai, or a local model).

## Why CIRIS

- **It shows its work.** Every answer passes ethical, common-sense, domain,
  and reasoning-fragility checks — and you can see *why* it said yes or no,
  not just the answer.
- **It defers to you.** When a decision is uncertain, CIRIS escalates to a
  designated human ("Wise Authority") instead of guessing.
- **Private by design.** Runs on your device. The hosted CIRIS proxy stores
  nothing — your prompts are not logged and never train a model.
- **Speaks your language.** The *entire* ethical-reasoning system — not just
  the buttons — operates in 29 languages.
- **Auditable and open.** AGPL-3.0, cryptographically signed decisions, a
  tamper-evident audit trail, and a public ethical framework anyone can
  review: [the Accord](https://ciris.ai/ciris_accord.pdf).

*Not a replacement for humans — a tool that knows its limits.*

## How it works

CIRIS wraps every AI response in a reasoning pipeline: multiple evaluation
passes for ethics, common sense, domain knowledge, and reasoning fragility
(it flags answers that lean on a single weak source). Uncertain calls defer
to designated humans. Every decision is written to a hash-chained audit
trail. Today CIRIS powers Discord community moderation in production at
[agents.ciris.ai](https://agents.ciris.ai); the architecture is built to
scale to settings like education and healthcare.

The design is described in two papers — [CIRIS
Architecture](https://doi.org/10.5281/zenodo.18137161) and the [Coherence
Ratchet](https://doi.org/10.5281/zenodo.18142668).

## Run it yourself

```bash
pip install ciris-agent
ciris-agent                       # desktop app + local API server
ciris-agent --adapter discord     # or run it as a Discord bot
```

Server install (agent + web UI) — download, optionally inspect, then run:

```bash
curl -fsSLO https://ciris.ai/install.sh
# (optional) read install.sh to see what it does, then:
bash install.sh
```

> Security note: piping `curl ... | bash` runs unreviewed code straight from
> the network. Downloading first lets you inspect the script before executing it.

## For developers

Under the consumer app, CIRIS is a type-safe, auditable AI agent framework —
22 core services on a 6-bus message architecture, 200+ API endpoints, 4 GB
RAM target, 10,000+ tests. Extend it with adapters, run it headless, or
embed it.

- **[Documentation Hub](docs/README.md)** — everything, organized
- **[Architecture](docs/ARCHITECTURE.md)** · **[API Reference](docs/API_SPEC.md)** · **[Quick Start](docs/QUICKSTART.md)**
- **[Contributing](CONTRIBUTING.md)** · **[Security](SECURITY.md)** · **[For AI assistants](llms.txt)**

## Honest read

CIRIS is real and running in production, but young — version 2.x, under
active development. It proves an AI is *accountable*, not that it is
*correct*: the reasoning is made visible so you can judge it yourself. It
does not give medical advice or substitute for professional care. It is not
magic — it is an ordinary chat assistant, plus the accountability machinery
that closed apps don't give you.

---

**CIRIS** — Core Identity, Integrity, Resilience, Incompleteness, and Signalling Gratitude
Copyright © 2025 Eric Moore and CIRIS L3C · AGPL-3.0 · [Release Notes](CHANGELOG.md) · [Issues](https://github.com/CIRISAI/CIRISAgent/issues)
