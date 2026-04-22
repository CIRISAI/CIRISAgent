"""
VideoFrames Adapter - Converted from Clawdbot skill: video-frames

Extract frames or short clips from videos using ffmpeg.

Original source: /home/emoore/clawdbot_lessons/clawdbot/skills/video-frames/SKILL.md
"""

from .adapter import VideoFramesAdapter
from .service import VideoFramesToolService

# Export as Adapter for load_adapter() compatibility
Adapter = VideoFramesAdapter

__all__ = [
    "Adapter",
    "VideoFramesAdapter",
    "VideoFramesToolService",
]
