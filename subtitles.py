"""
Subtitle/Caption Generation Module
Handles word-by-word text display with precise timing.

Supports two modes:
  1. Ground-truth timing via Edge TTS WordBoundary events (preferred)
  2. Heuristic estimation as fallback (Google TTS or missing metadata)
"""

import random
from typing import List, Dict, Optional

# MoviePy imports
try:
    from moviepy import TextClip
    MOVIEPY_VERSION = 2
except ImportError:
    from moviepy.editor import TextClip
    MOVIEPY_VERSION = 1


def word_timings_to_segments(word_timings: List[Dict]) -> List[Dict]:
    """
    Convert Edge TTS WordBoundary events directly to subtitle segments.

    Args:
        word_timings: List of dicts with keys: word, start (seconds), duration (seconds)

    Returns:
        List of segment dicts with keys: word, start, end, word_index
    """
    segments = []
    for i, wt in enumerate(word_timings):
        segments.append({
            'word': wt['word'],
            'start': wt['start'],
            'end': wt['start'] + wt['duration'],
            'word_index': i
        })
    return segments


def estimate_word_timings(text: str, duration: float) -> List[Dict]:
    """Estimate precise timing for each word based on Edge TTS characteristics"""
    words = text.split()
    total_words = len(words)
    
    if total_words == 0:
        return []
    
    # Edge TTS (Jenny Neural) typically speaks at ~2.0-2.5 words per second
    # But we need to account for natural speech patterns
    base_rate = 2.2  # words per second for Edge TTS
    
    word_timings = []
    current_time = 0
    
    for i, word in enumerate(words):
        # Adjust timing based on word characteristics
        word_length_factor = max(0.4, len(word) / 6.0)  # Longer words take more time
        
        # Add pauses for punctuation
        punctuation_pause = 0
        if word.endswith(('.', '!', '?')):
            punctuation_pause = 0.3  # Longer pause for sentence endings
        elif word.endswith((',', ';', ':')):
            punctuation_pause = 0.15  # Medium pause for commas
        
        # Calculate word duration (minimum 0.3 seconds per word)
        base_duration = max(0.3, word_length_factor / base_rate)
        word_duration = base_duration + punctuation_pause
        
        # Add slight randomness for natural speech (±10%)
        variation = random.uniform(0.9, 1.1)
        word_duration *= variation
        
        word_timings.append({
            'word': word,
            'start': current_time,
            'end': current_time + word_duration,
            'index': i
        })
        
        current_time += word_duration
    
    # Scale all timings to match actual audio duration
    if current_time > 0:
        scale_factor = duration / current_time
        for timing in word_timings:
            timing['start'] *= scale_factor
            timing['end'] *= scale_factor
    
    # Print first few timings
    print(f"Audio duration: {duration:.1f}s, Estimated total: {current_time:.1f}s")
    print(f"Scale factor: {scale_factor:.2f}")
    for i in range(min(5, len(word_timings))):
        t = word_timings[i]
        print(f"  '{t['word']}': {t['start']:.1f}-{t['end']:.1f}s")
    
    return word_timings


def create_word_segments(text: str, duration: float,
                         word_timings: Optional[List[Dict]] = None) -> List[Dict]:
    """
    Create segments for individual word display.

    Args:
        text: The full text (used for estimation fallback)
        duration: Total audio duration in seconds
        word_timings: Optional ground-truth timings from Edge TTS WordBoundary events.
                      If provided, uses exact timestamps instead of estimation.
    """
    if word_timings:
        print("Using ground-truth Edge TTS WordBoundary timings")
        segments = word_timings_to_segments(word_timings)
        if segments:
            first = segments[0]
            last = segments[-1]
            print(f"  First word '{first['word']}': {first['start']:.3f}s")
            print(f"  Last word '{last['word']}': {last['start']:.3f}-{last['end']:.3f}s")
        return segments

    # Fallback to estimation
    estimated = estimate_word_timings(text, duration)
    words = text.split()

    if not estimated:
        return []

    segments = []
    for word_idx, timing in enumerate(estimated):
        if word_idx < len(words):
            segments.append({
                'word': words[word_idx],
                'start': timing['start'],
                'end': timing['end'],
                'word_index': word_idx
            })

    return segments


def create_dynamic_text_clips(text: str, duration: float, video_width: int,
                              video_height: int, fps: int,
                              word_timings: Optional[List[Dict]] = None) -> List[TextClip]:
    """
    Create one-word-at-a-time text clips with NO clipping or overlap - FRAME-SAFE

    Args:
        text: The text to display word-by-word
        duration: Total audio duration
        video_width: Width of the video
        video_height: Height of the video
        fps: Frames per second for the video
        word_timings: Optional ground-truth timings from Edge TTS WordBoundary events

    Returns:
        List of TextClip objects
    """
    print("Creating one-word-at-a-time text display (FRAME-SAFE)...")

    segments = create_word_segments(text, duration, word_timings=word_timings)
    text_clips = []

    # 🔥 CRITICAL FIX: Force frame-safe gap to prevent overlap
    frame_gap = 1 / fps  # one full frame gap (prevents MoviePy frame collision)
    print(f"Frame gap: {frame_gap:.4f}s ({fps}fps)")

    for i, segment in enumerate(segments):
        # End word BEFORE next word starts by at least 1 frame (NO OVERLAP POSSIBLE)
        if i < len(segments) - 1:
            extended_duration = segments[i + 1]['start'] - segment['start'] - frame_gap
        else:
            extended_duration = segment['end'] - segment['start']

        # Safety minimum (at least 1 frame)
        extended_duration = max(extended_duration, frame_gap)

        # Create text clip with extra padding in size to prevent stroke cutoff
        word_clip = (
            TextClip(
                text=segment['word'],
                font="fonts/Montserrat-Black.ttf",
                font_size=64,
                color="white",
                stroke_color="black",
                stroke_width=6,
                size=(video_width - 80, 150),  # Extra height prevents stroke clipping
                method="caption"                     # IMPORTANT
            )
            .with_position(('center', video_height - 380))  # Moved up a bit more
            .with_start(segment['start'])
            .with_duration(extended_duration)
        )

        text_clips.append(word_clip)

        if i < 5:
            print(
                f"  Word '{segment['word']}': "
                f"{segment['start']:.2f} → {segment['start'] + extended_duration:.2f}s "
                f"(dur: {extended_duration:.3f}s)"
            )

    print(f"✓ Created {len(text_clips)} frame-safe word clips (NO OVERLAP)")
    return text_clips
