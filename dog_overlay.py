"""
dog_overlay.py -- Dog reaction overlay for Reddit story videos.

Primary path (Ollama + Tenor):
  Ollama generates a specific Tenor search query per story segment
  (e.g. "dog shocked finding out secret", "dog angry confrontation argument").
  GIFs are fetched from Tenor and cached in dog_reactions/cache/{query}/.

Fallback (emotion folders):
  If Ollama or Tenor is unavailable, falls back to the pre-downloaded GIFs in:
    dog_reactions/shocked / angry / sad / happy / confused / disgusted

The overlay waits until after the header card has faded (start_time param).
"""

import os
import re
import json
import math
import random
import subprocess

import requests
import numpy as np
from moviepy import VideoFileClip, ImageClip, concatenate_videoclips
from PIL import Image

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DOG_REACTIONS_DIR = "dog_reactions"

def _cache_dir() -> str:
    """Computed at call-time so test patches to DOG_REACTIONS_DIR are respected."""
    return os.path.join(DOG_REACTIONS_DIR, "cache")
TENOR_KEY         = "LIVDSRZULELA"

SUPPORTED_VIDEO = {".gif", ".mp4"}
SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg"}
SUPPORTED_ALL   = SUPPORTED_VIDEO | SUPPORTED_IMAGE

MIN_SEGMENT_DURATION = 4.0   # seconds — shorter segments get merged

_VALID_EMOTIONS = {"shocked", "angry", "sad", "happy", "confused", "disgusted"}

# Fallback keyword → emotion mapping (used when Ollama is down)
EMOTION_KEYWORDS = {
    "shocked":   ["shocked", "surprised", "can't believe", "cannot believe",
                  "omg", "unbelievable", "speechless", "jaw dropped", "stunned",
                  "floored", "blown away", "couldn't believe", "never expected",
                  "out of nowhere", "suddenly", "found out"],
    "angry":     ["angry", "furious", "mad", "yelled", "screamed", "livid",
                  "rage", "raging", "snapped", "exploded", "stormed", "fuming",
                  "seething", "irate", "outraged", "confronted", "threatened",
                  "demanded", "accused", "yelling", "screaming", "argument",
                  "arguing", "fight", "fighting"],
    "sad":       ["sad", "cried", "crying", "hurt", "heartbroken", "devastated",
                  "tears", "sobbed", "sobbing", "wept", "weeping", "broke down",
                  "upset", "depressed", "miserable", "despair", "grief",
                  "disappointed", "gutted", "crushed", "lost", "alone"],
    "happy":     ["happy", "excited", "love", "amazing", "thrilled", "grateful",
                  "wonderful", "fantastic", "overjoyed", "ecstatic", "proud",
                  "relief", "relieved", "glad", "delighted", "celebrate"],
    "confused":  ["confused", "weird", "strange", "bizarre", "puzzled",
                  "didn't understand", "don't understand", "makes no sense",
                  "what the", "why would", "how could", "baffled", "perplexed",
                  "dumbfounded", "didn't know", "not sure"],
    "disgusted": ["disgusted", "gross", "awful", "horrible", "nasty",
                  "repulsed", "sickened", "revolting", "appalled", "offensive",
                  "inappropriate", "unacceptable", "crossed the line",
                  "can't stand", "cannot stand"],
}

# Default Tenor queries per emotion — used when Ollama is down
# "real dog" prefix keeps results to actual dogs, not cartoons or people
_FALLBACK_QUERIES = {
    "shocked":   "real dog shocked surprised",
    "angry":     "real dog angry barking",
    "sad":       "real dog sad crying",
    "happy":     "real dog excited happy",
    "confused":  "real dog confused head tilt",
    "disgusted": "real dog disgusted reaction",
}

# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

_QUERY_PROMPT = """\
You are choosing reaction GIFs for a Reddit AITA story video. The GIFs show a dog reacting to each part of the story.

For each numbered story segment, write a SHORT Tenor search query (3-5 words) for a dog reaction GIF that specifically matches what is happening in that moment.

Always start the query with "real dog". This is CRITICAL — it ensures results show real dogs, not cartoons, animated characters, or people. Be specific — match the query to the actual event, not just a generic emotion.

Good examples:
- "real dog shocked jaw drop" — for surprising news or a plot twist
- "real dog angry barking" — for an argument or confrontation
- "real dog sad crying" — for heartbreak or betrayal
- "real dog confused head tilt" — for strange or unclear behaviour
- "real dog disgusted reaction" — for something gross or inappropriate
- "real dog excited jumping" — for good news or relief
- "real dog nervous anxious" — for a tense or worrying moment
- "real dog judging side eye" — for when someone does something questionable
- "real dog embarrassed" — for an awkward or cringe moment
- "real dog waiting impatient" — for a slow build-up
- "real dog betrayed shocked" — for a trust violation

Segments:
{segments}

Return ONLY a JSON array of query strings, one per segment, in the same order.
Example: ["dog shocked jaw drop", "dog angry confrontation", "dog sad heartbroken"]
"""


def _ollama_search_queries(segments: list):
    """
    Ask Ollama to write a specific Tenor search query for each segment.
    Returns list of query strings aligned with segments, or None on failure.
    """
    try:
        from ai_config import OLLAMA_URL, OLLAMA_MODEL
    except ImportError:
        return None

    numbered = "\n".join(f"{i+1}. {s['text']}" for i, s in enumerate(segments))
    prompt   = _QUERY_PROMPT.format(segments=numbered)

    try:
        resp = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 400},
            },
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json().get("response", "").strip()

        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not match:
            return None
        queries = json.loads(match.group())
        if len(queries) != len(segments):
            return None
        # Ensure every query starts with "real dog" (real animals, not cartoons)
        cleaned = []
        for q in queries:
            q = str(q).strip().lower()
            if q.startswith("real dog"):
                pass
            elif q.startswith("dog "):
                q = "real " + q
            else:
                q = "real dog " + q
            cleaned.append(q)
        return cleaned

    except requests.ConnectionError:
        return None
    except Exception as e:
        print(f"Ollama query generation failed: {e}")
        return None


# ---------------------------------------------------------------------------
# Tenor GIF fetch + cache
# ---------------------------------------------------------------------------

def _cache_key(query: str) -> str:
    """Turn a search query into a safe folder name."""
    return re.sub(r"[^a-z0-9]+", "_", query.lower()).strip("_")[:60]


def _cached_gif(query: str):
    """Return a cached media path (gif or mp4) from cache, or None if not cached yet."""
    folder = os.path.join(_cache_dir(), _cache_key(query))
    if not os.path.isdir(folder):
        return None
    files = [os.path.join(folder, f) for f in os.listdir(folder)
             if os.path.splitext(f)[1].lower() in {".gif", ".mp4"}]
    return random.choice(files) if files else None


def _fetch_from_tenor(query: str):
    """
    Search Tenor for *query*, download up to 5 MP4s (watermark-free format),
    cache in dog_reactions/cache/{key}/.
    Returns a local MP4 path, or None on failure.
    """
    key    = _cache_key(query)
    folder = os.path.join(_cache_dir(), key)
    os.makedirs(folder, exist_ok=True)

    # Prepend "real" so Tenor returns real dogs, not cartoons or people
    tenor_q = ("real " + query) if not query.startswith("real ") else query
    url = (f"https://api.tenor.com/v1/search"
           f"?q={requests.utils.quote(tenor_q)}&key={TENOR_KEY}"
           f"&limit=5&contentfilter=high&media_filter=minimal")
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        results = resp.json().get("results", [])
    except Exception as e:
        print(f"Tenor search failed for '{query}': {e}")
        return None

    saved = []
    for i, item in enumerate(results[:5]):
        try:
            mp4_url = item["media"][0]["mp4"]["url"]
            r = requests.get(mp4_url, timeout=30)
            r.raise_for_status()
            dest = os.path.join(folder, f"dog_{i}.mp4")
            with open(dest, "wb") as fh:
                fh.write(r.content)
            if os.path.getsize(dest) >= 500:
                saved.append(dest)
            else:
                os.remove(dest)
        except Exception:
            pass

    if not saved:
        return None
    print(f"Fetched {len(saved)} clips for '{query}'")
    return random.choice(saved)


def _get_gif(query: str, fallback_emotion: str = "shocked"):
    """
    Return a local GIF path for *query*:
      1. Check cache
      2. Fetch from Tenor
      3. Fall back to emotion folder
    """
    cached = _cached_gif(query)
    if cached:
        return cached

    fetched = _fetch_from_tenor(query)
    if fetched:
        return fetched

    # Tenor failed — use pre-downloaded emotion folder
    return _pick_emotion_media(fallback_emotion)


# ---------------------------------------------------------------------------
# Keyword emotion detection (fallback when Ollama is down)
# ---------------------------------------------------------------------------

def _detect_emotion_raw(text: str):
    text_lower = text.lower()
    for emotion, keywords in EMOTION_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return emotion
    return None


def detect_emotion(text: str) -> str:
    return _detect_emotion_raw(text) or "shocked"


# ---------------------------------------------------------------------------
# Emotion-folder media helpers (final fallback)
# ---------------------------------------------------------------------------

def _list_media(emotion: str) -> list:
    folder = os.path.join(DOG_REACTIONS_DIR, emotion)
    if not os.path.isdir(folder):
        return []
    return [os.path.join(folder, f) for f in sorted(os.listdir(folder))
            if os.path.splitext(f)[1].lower() in SUPPORTED_ALL]


def _pick_emotion_media(emotion: str):
    files = _list_media(emotion)
    if not files and emotion != "shocked":
        files = _list_media("shocked")
    return random.choice(files) if files else None


# ---------------------------------------------------------------------------
# GIF → MP4 conversion
# ---------------------------------------------------------------------------

def _gif_to_mp4(gif_path: str) -> str:
    mp4_path = gif_path.replace(".gif", ".mp4")
    # Delete corrupt cached MP4s (< 500 bytes means a failed previous conversion)
    if os.path.exists(mp4_path):
        if os.path.getsize(mp4_path) >= 500:
            return mp4_path
        os.remove(mp4_path)
    cmd = ["ffmpeg", "-y", "-i", gif_path,
           "-c:v", "libx264", "-preset", "fast",
           "-pix_fmt", "yuv420p", "-an", mp4_path]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0 or not os.path.exists(mp4_path) or os.path.getsize(mp4_path) < 500:
        if os.path.exists(mp4_path):
            os.remove(mp4_path)
        return gif_path
    return mp4_path


# ---------------------------------------------------------------------------
# Clip helpers
# ---------------------------------------------------------------------------

def _loop_clip(clip, duration: float):
    try:
        return clip.loop(duration=duration)
    except (AttributeError, TypeError):
        n = math.ceil(duration / clip.duration)
        return concatenate_videoclips([clip] * n).subclipped(0, duration)


def _make_dog_clip(media_path: str, duration: float):
    """220x220 clip from *media_path* lasting *duration* seconds."""
    ext = os.path.splitext(media_path)[1].lower()
    try:
        if ext in SUPPORTED_VIDEO:
            # GIFs need converting to MP4 first for seekability; MP4s are used directly
            src = _gif_to_mp4(media_path) if ext == ".gif" else media_path
            raw = VideoFileClip(src)
            _orig = raw.reader.close
            def _safe(*a, _c=_orig, **kw):
                try: _c(*a, **kw)
                except OSError: pass
            raw.reader.close = _safe
            return _loop_clip(raw, duration).resized((220, 220))
        else:
            img = Image.open(media_path).convert("RGB").resize((220, 220))
            return ImageClip(np.array(img)).with_duration(duration)
    except Exception as e:
        print(f"Dog clip error ({os.path.basename(media_path)}): {e}")
        return None


# ---------------------------------------------------------------------------
# Story segmentation
# ---------------------------------------------------------------------------

def _segment_story(story_text: str, word_timings: list) -> list:
    """
    Split into sentence-level segments, assign a specific Tenor query per
    segment (via Ollama), falling back to keyword emotion → default query.

    Returns list of {"text", "start", "end", "query", "emotion"}.
    """
    if not word_timings:
        return []

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', story_text.strip())
                 if s.strip()]
    if not sentences:
        sentences = [story_text] if story_text.strip() else []
    if not sentences:
        return []

    # Map sentences → word_timing slices
    raw_segs, wt_idx = [], 0
    for sent in sentences:
        wc       = len(sent.split())
        si       = wt_idx
        ei       = min(wt_idx + wc - 1, len(word_timings) - 1)
        start_t  = word_timings[si]["start"]
        end_wt   = word_timings[ei]
        end_t    = end_wt["start"] + end_wt["duration"]
        raw_segs.append({"text": sent, "start": start_t, "end": end_t})
        wt_idx = ei + 1
        if wt_idx >= len(word_timings):
            break

    # Merge short segments
    merged = []
    for seg in raw_segs:
        if merged and (merged[-1]["end"] - merged[-1]["start"]) < MIN_SEGMENT_DURATION:
            merged[-1]["text"] += " " + seg["text"]
            merged[-1]["end"]   = seg["end"]
        else:
            merged.append(dict(seg))

    # --- Ask Ollama for specific search queries ---
    queries = _ollama_search_queries(merged)
    if queries:
        print("GIF queries: Ollama")
        for seg, q in zip(merged, queries):
            seg["query"]   = q
            seg["emotion"] = "shocked"   # emotion only used as last-resort fallback
    else:
        # Keyword fallback — map emotion → default Tenor query
        print("GIF queries: keyword fallback (Ollama unavailable)")
        baseline = _detect_emotion_raw(story_text) or "shocked"
        prev_emo = baseline
        for seg in merged:
            found        = _detect_emotion_raw(seg["text"])
            emo          = found if found else prev_emo
            seg["emotion"] = emo
            seg["query"]   = _FALLBACK_QUERIES.get(emo, "dog shocked reaction")
            prev_emo     = emo

    return merged


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_dog_overlay_clip(story_text: str, audio_duration: float,
                            word_timings=None, start_time: float = 0.0):
    """
    Build the dog reaction overlay.

    With word_timings: segments the story, generates story-specific GIF search
    queries via Ollama, fetches from Tenor (cached), assembles per-segment clips.

    Returns [border_clip, dog_clip] or None on failure.

    Layout (720x1280): 220x220 centered, top edge y=670, 6px white border.
    """
    display_duration = audio_duration - start_time
    if display_duration <= 0:
        return None

    if word_timings:
        segments = _segment_story(story_text, word_timings)
        if not segments:
            return None

        label = " -> ".join(f"'{s['query']}'({s['start']:.0f}-{s['end']:.0f}s)"
                            for s in segments)
        print(f"Dog GIF plan:\n  {label}")

        seg_clips  = []
        prev_query = None
        for seg in segments:
            duration = seg["end"] - seg["start"]
            if duration <= 0:
                continue

            query = seg["query"]
            # Avoid same query back-to-back by slightly varying it
            if query == prev_query:
                query = query + " reaction"
            prev_query = seg["query"]

            media_path = _get_gif(query, seg.get("emotion", "shocked"))
            if not media_path:
                continue
            clip = _make_dog_clip(media_path, duration)
            if clip:
                seg_clips.append(clip)

        if not seg_clips:
            print("No dog clips built, skipping overlay")
            return None

        dog_clip = concatenate_videoclips(seg_clips)
        if dog_clip.duration > display_duration:
            dog_clip = dog_clip.subclipped(0, display_duration)
        elif dog_clip.duration < display_duration - 0.1:
            gap  = display_duration - dog_clip.duration
            last = _get_gif(segments[-1]["query"], "shocked")
            if last:
                pad = _make_dog_clip(last, gap)
                if pad:
                    dog_clip = concatenate_videoclips([dog_clip, pad])

    else:
        # No word timings — single GIF for full video
        emotion    = detect_emotion(story_text)
        query      = _FALLBACK_QUERIES.get(emotion, "dog shocked reaction")
        media_path = _get_gif(query, emotion)
        if not media_path:
            print("No dog media available, skipping overlay")
            return None
        print(f"Dog overlay: {os.path.basename(media_path)}")
        dog_clip = _make_dog_clip(media_path, display_duration)
        if not dog_clip:
            return None

    # White border
    border_arr = np.ones((232, 232, 3), dtype=np.uint8) * 255
    border_clip = (
        ImageClip(border_arr)
        .with_duration(display_duration)
        .with_start(start_time)
        .with_position(("center", 664))
    )
    dog_clip = dog_clip.with_start(start_time).with_position(("center", 670))

    return [border_clip, dog_clip]
