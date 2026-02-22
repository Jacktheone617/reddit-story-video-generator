"""
Scene Animation Module - Ken Burns effect + crossfade transitions.

Converts static AI-generated images into animated video clips.
No GPU required - uses PIL transforms and MoviePy compositing.
"""

import random
import numpy as np
from PIL import Image
from typing import List, Dict, Tuple, Optional

from moviepy import ImageClip, VideoClip, CompositeVideoClip, concatenate_videoclips, vfx

from ai_config import VIDEO_WIDTH, VIDEO_HEIGHT, FPS, CROSSFADE_DURATION


# Ken Burns presets: (start_rect, end_rect) as (x_frac, y_frac, w_frac, h_frac)
# These define crop regions as fractions of the source image dimensions.
# The animation interpolates from start_rect to end_rect over the clip duration.
KB_PRESETS = [
    # Slow zoom into center
    ((0.0, 0.0, 1.0, 1.0), (0.08, 0.08, 0.84, 0.84)),
    # Slow zoom out from center
    ((0.08, 0.08, 0.84, 0.84), (0.0, 0.0, 1.0, 1.0)),
    # Pan left to right
    ((0.0, 0.04, 0.85, 0.92), (0.15, 0.04, 0.85, 0.92)),
    # Pan right to left
    ((0.15, 0.04, 0.85, 0.92), (0.0, 0.04, 0.85, 0.92)),
    # Slow zoom in from top
    ((0.0, 0.0, 1.0, 1.0), (0.06, 0.0, 0.88, 0.88)),
    # Slow zoom in from bottom
    ((0.0, 0.12, 1.0, 1.0), (0.06, 0.12, 0.88, 0.88)),
]


def _interpolate_rect(start_rect: Tuple, end_rect: Tuple, progress: float) -> Tuple:
    """Linear interpolation between two crop rectangles (0.0-1.0 progress)."""
    return tuple(
        s + (e - s) * progress
        for s, e in zip(start_rect, end_rect)
    )


def apply_ken_burns(
    image_path: str,
    duration: float,
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    fps: int = FPS,
    preset: Optional[Tuple] = None,
) -> VideoClip:
    """
    Apply Ken Burns (zoom/pan) effect to a static image.

    Args:
        image_path: Path to the source image (generated at 936x1664)
        duration: How long this scene lasts (seconds)
        video_width: Output width (720)
        video_height: Output height (1280)
        fps: Output framerate
        preset: (start_rect, end_rect) tuple; random if None

    Returns:
        A MoviePy VideoClip with the Ken Burns animation applied
    """
    if preset is None:
        preset = random.choice(KB_PRESETS)

    start_rect, end_rect = preset

    # Load image as numpy array
    img = Image.open(image_path).convert("RGB")
    img_w, img_h = img.size
    img_array = np.array(img)

    def make_frame(t):
        # Calculate progress (0.0 to 1.0)
        progress = t / duration if duration > 0 else 0.0
        progress = min(1.0, max(0.0, progress))

        # Smooth easing (ease-in-out)
        progress = 0.5 - 0.5 * np.cos(progress * np.pi)

        # Interpolate crop region
        x_frac, y_frac, w_frac, h_frac = _interpolate_rect(start_rect, end_rect, progress)

        # Convert fractions to pixel coordinates
        x = int(x_frac * img_w)
        y = int(y_frac * img_h)
        w = int(w_frac * img_w)
        h = int(h_frac * img_h)

        # Clamp to image bounds
        x = max(0, min(x, img_w - 1))
        y = max(0, min(y, img_h - 1))
        w = max(1, min(w, img_w - x))
        h = max(1, min(h, img_h - y))

        # Crop
        cropped = img_array[y:y + h, x:x + w]

        # Resize to output dimensions using PIL for quality
        cropped_pil = Image.fromarray(cropped)
        resized = cropped_pil.resize((video_width, video_height), Image.LANCZOS)

        return np.array(resized)

    clip = VideoClip(make_frame, duration=duration)
    clip = clip.with_fps(fps)
    return clip


def create_scene_clips(
    scenes: List[Dict],
    video_width: int = VIDEO_WIDTH,
    video_height: int = VIDEO_HEIGHT,
    fps: int = FPS,
    crossfade_duration: float = CROSSFADE_DURATION,
) -> VideoClip:
    """
    Create a single continuous background clip from all scene images
    with Ken Burns effects and crossfade transitions.

    Args:
        scenes: List of scene dicts (must have 'image_path', 'start_time', 'end_time')
        video_width: Output width
        video_height: Output height
        fps: Output framerate
        crossfade_duration: Seconds for crossfade between scenes

    Returns:
        A single composited clip covering the full audio duration
    """
    if not scenes:
        raise ValueError("No scenes provided")

    clips = []
    used_presets = []

    for i, scene in enumerate(scenes):
        image_path = scene.get("image_path")
        if not image_path or not isinstance(image_path, str):
            continue

        duration = scene["end_time"] - scene["start_time"]
        if duration <= 0:
            continue

        # Pick a Ken Burns preset, avoiding consecutive duplicates
        available = [p for j, p in enumerate(KB_PRESETS) if j not in used_presets[-2:]]
        if not available:
            available = KB_PRESETS
        preset_idx = KB_PRESETS.index(random.choice(available))
        used_presets.append(preset_idx)

        clip = apply_ken_burns(
            image_path=image_path,
            duration=duration,
            video_width=video_width,
            video_height=video_height,
            fps=fps,
            preset=KB_PRESETS[preset_idx],
        )

        # Position clip at its start time
        clip = clip.with_start(scene["start_time"])

        clips.append(clip)

    if not clips:
        raise ValueError("No valid scene clips could be created")

    # If only one clip, return it directly
    if len(clips) == 1:
        return clips[0]

    # Composite all clips with crossfade transitions
    # Each clip is positioned at its start_time, and overlapping clips
    # create a natural crossfade effect via CompositeVideoClip
    total_duration = scenes[-1]["end_time"]

    # Add crossfade by adjusting start times to overlap slightly
    for i in range(1, len(clips)):
        original_start = scenes[i]["start_time"]
        # Start slightly earlier for crossfade overlap
        adjusted_start = max(0, original_start - crossfade_duration / 2)
        clips[i] = clips[i].with_start(adjusted_start)

        # Apply crossfade-in effect on the overlapping clip (MoviePy 2.x)
        clips[i] = clips[i].with_effects([vfx.FadeIn(crossfade_duration)])

    final = CompositeVideoClip(clips, size=(video_width, video_height))
    final = final.with_duration(total_duration)

    return final
