# VideoFrames Adapter

> Converted from Clawdbot skill: `video-frames`

Extract frames or short clips from videos using ffmpeg.

## Requirements

- **Binaries**: ffmpeg

## Installation

This adapter was automatically generated from a Clawdbot SKILL.md file.

```bash
# Load the adapter
python main.py --adapter api --adapter clawdbot_video_frames
```

## Original Skill Documentation

# Video Frames (ffmpeg)

Extract a single frame from a video, or create quick thumbnails for inspection.

## Quick start

First frame:

```bash
{baseDir}/scripts/frame.sh /path/to/video.mp4 --out /tmp/frame.jpg
```

At a timestamp:

```bash
{baseDir}/scripts/frame.sh /path/to/video.mp4 --time 00:00:10 --out /tmp/frame-10s.jpg
```

## Notes

- Prefer `--time` for “what is happening around here?”.
- Use a `.jpg` for quick share; use `.png` for crisp UI frames.

---

*Converted by CIRIS Skill Converter*
*Source: /home/emoore/clawdbot_lessons/clawdbot/skills/video-frames/SKILL.md*
