# SherpaOnnxTts Adapter

> Converted from Clawdbot skill: `sherpa-onnx-tts`

Local text-to-speech via sherpa-onnx (offline, no cloud)

## Requirements

- **Environment**: SHERPA_ONNX_RUNTIME_DIR, SHERPA_ONNX_MODEL_DIR
- **Platforms**: darwin, linux, win32

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_sherpa_onnx_tts
```

## Original Skill Documentation

# sherpa-onnx-tts

Local TTS using the sherpa-onnx offline CLI.

## Install

1) Download the runtime for your OS (extracts into `~/.clawdbot/tools/sherpa-onnx-tts/runtime`)
2) Download a voice model (extracts into `~/.clawdbot/tools/sherpa-onnx-tts/models`)

Update `~/.clawdbot/moltbot.json`:

```json5
{
  skills: {
    entries: {
      "sherpa-onnx-tts": {
        env: {
          SHERPA_ONNX_RUNTIME_DIR: "~/.clawdbot/tools/sherpa-onnx-tts/runtime",
          SHERPA_ONNX_MODEL_DIR: "~/.clawdbot/tools/sherpa-onnx-tts/models/vits-piper-en_US-lessac-high"
        }
      }
    }
  }
}
```

The wrapper lives in this skill folder. Run it directly, or add the wrapper to PATH:

```bash
export PATH="{baseDir}/bin:$PATH"
```

## Usage

```bash
{baseDir}/bin/sherpa-onnx-tts -o ./tts.wav "Hello from local TTS."
```

Notes:
- Pick a different model from the sherpa-onnx `tts-models` release if you want another voice.
- If the model dir has multiple `.onnx` files, set `SHERPA_ONNX_MODEL_FILE` or pass `--model-file`.
- You can also pass `--tokens-file` or `--data-dir` to override the defaults.
- Windows: run `node {baseDir}\\bin\\sherpa-onnx-tts -o tts.wav "Hello from local TTS."`

---

*Converted by CIRIS Skill Converter*
*Source: ../clawdbot/skills/sherpa-onnx-tts/SKILL.md*
