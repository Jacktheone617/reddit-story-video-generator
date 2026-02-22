"""
Scene Extraction Module - Uses local Ollama to decompose story text into visual scenes.

Each scene gets:
  - A time range (mapped to Edge TTS word_timings)
  - A descriptive SDXL-optimized image prompt
  - A transition type
"""

import json
import re
import requests
from typing import List, Dict, Optional

from ai_config import (
    OLLAMA_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT,
    TARGET_SCENES, MIN_SCENE_DURATION, MAX_SCENE_DURATION,
)


def build_scene_prompt(story_text: str, num_scenes: int = TARGET_SCENES) -> str:
    """Build the Ollama prompt that instructs the LLM to decompose the story into visual scenes."""
    return f"""You are a visual scene director for narrative videos. Given a story, break it into {num_scenes} visual scenes.

For each scene, provide:
1. "summary" - One sentence summarizing what happens in this scene
2. "image_prompt" - A detailed Stable Diffusion prompt for the background image. Focus on ENVIRONMENTS, LIGHTING, and MOOD. Never describe specific people or faces. Use cinematic photography terms.
3. "start_word" - Approximate word number where this scene begins (0-indexed from the start of the story)
4. "mood" - One of: calm, tense, angry, sad, happy, dramatic, mysterious, chaotic

Rules:
- Scenes should cover the entire story from start to finish
- Scenes should be roughly equal in word count, but natural story beats take priority
- Image prompts must be 20-40 words
- Focus on settings: rooms, outdoor scenes, weather, time of day, lighting
- Never include text, logos, or UI elements in prompts
- Always append quality tags: "cinematic lighting, photorealistic, 4k, detailed"
- For emotional moments, describe the environment reflecting the mood

Story:
{story_text}

Return ONLY a valid JSON array, no markdown, no explanation. Example format:
[
  {{
    "summary": "The narrator arrives home to find the door unlocked",
    "image_prompt": "dark suburban house exterior at dusk, unlocked front door slightly ajar, warm light spilling out, ominous atmosphere, cinematic lighting, photorealistic, 4k",
    "start_word": 0,
    "mood": "mysterious"
  }}
]"""


def _parse_json_response(response_text: str) -> List[Dict]:
    """Extract and parse JSON array from LLM response, handling common formatting issues."""
    text = response_text.strip()

    # Try direct parse first
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try extracting JSON array from markdown code block
    match = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first [ to last ]
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {text[:200]}...")


def extract_scenes(
    story_text: str,
    word_timings: List[Dict],
    audio_duration: float,
    model: str = OLLAMA_MODEL,
    ollama_url: str = OLLAMA_URL,
    num_scenes: int = TARGET_SCENES,
    timeout: int = OLLAMA_TIMEOUT,
) -> List[Dict]:
    """
    Analyze story text and produce scene descriptions with timing info.

    Args:
        story_text: Cleaned story text
        word_timings: Edge TTS WordBoundary events [{word, start, duration}, ...]
        audio_duration: Total audio length in seconds
        model: Ollama model name
        ollama_url: Ollama API endpoint
        num_scenes: Target scene count
        timeout: HTTP request timeout

    Returns:
        List of scene dicts with keys:
            scene_index, description, image_prompt, start_time, end_time,
            start_word_index, end_word_index, transition, mood
    """
    prompt = build_scene_prompt(story_text, num_scenes)

    # Call Ollama
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 2048,
        }
    }

    try:
        resp = requests.post(ollama_url, json=payload, timeout=timeout)
        resp.raise_for_status()
    except requests.ConnectionError:
        print("Ollama is not running - using fallback scene generation")
        return generate_fallback_scenes(story_text, word_timings, audio_duration, num_scenes)
    except requests.Timeout:
        print("Ollama timed out - using fallback scene generation")
        return generate_fallback_scenes(story_text, word_timings, audio_duration, num_scenes)

    response_text = resp.json().get("response", "")

    try:
        scenes_raw = _parse_json_response(response_text)
    except ValueError as e:
        print(f"Failed to parse Ollama response: {e}")
        return generate_fallback_scenes(story_text, word_timings, audio_duration, num_scenes)

    # Validate and clean scenes
    valid_scenes = []
    for scene in scenes_raw:
        if "image_prompt" in scene and "start_word" in scene:
            valid_scenes.append(scene)

    if len(valid_scenes) < 2:
        print(f"Only {len(valid_scenes)} valid scenes from Ollama - using fallback")
        return generate_fallback_scenes(story_text, word_timings, audio_duration, num_scenes)

    # Sort by start_word to ensure proper ordering
    valid_scenes.sort(key=lambda s: s.get("start_word", 0))

    return map_scenes_to_timings(valid_scenes, word_timings, audio_duration)


def map_scenes_to_timings(
    scenes_raw: List[Dict],
    word_timings: List[Dict],
    audio_duration: float,
) -> List[Dict]:
    """
    Map LLM-produced scene boundaries (word indices) to precise timestamps
    using the Edge TTS word_timings data.
    """
    total_words = len(word_timings) if word_timings else 0
    scenes = []

    for i, scene in enumerate(scenes_raw):
        start_word_idx = max(0, int(scene.get("start_word", 0)))

        # Clamp to valid range
        if total_words > 0:
            start_word_idx = min(start_word_idx, total_words - 1)

        # Determine end word index (start of next scene, or end of story)
        if i + 1 < len(scenes_raw):
            end_word_idx = max(0, int(scenes_raw[i + 1].get("start_word", total_words)) - 1)
        else:
            end_word_idx = total_words - 1 if total_words > 0 else 0

        end_word_idx = min(end_word_idx, total_words - 1) if total_words > 0 else 0

        # Get timestamps from word_timings
        if word_timings and total_words > 0:
            start_time = word_timings[start_word_idx]["start"]
            last_word = word_timings[end_word_idx]
            end_time = last_word["start"] + last_word["duration"]
        else:
            # Fallback: distribute evenly
            scene_duration = audio_duration / len(scenes_raw)
            start_time = i * scene_duration
            end_time = (i + 1) * scene_duration

        # Clamp end_time
        if i == len(scenes_raw) - 1:
            end_time = audio_duration

        scenes.append({
            "scene_index": i,
            "summary": scene.get("summary", ""),
            "image_prompt": scene["image_prompt"],
            "start_time": start_time,
            "end_time": end_time,
            "start_word_index": start_word_idx,
            "end_word_index": end_word_idx,
            "transition": "crossfade" if i > 0 else "cut",
            "mood": scene.get("mood", "neutral"),
        })

    # Enforce minimum/maximum scene duration by merging or splitting
    scenes = _enforce_duration_limits(scenes, audio_duration)

    return scenes


def _enforce_duration_limits(scenes: List[Dict], audio_duration: float) -> List[Dict]:
    """Merge scenes that are too short, split scenes that are too long."""
    if not scenes:
        return scenes

    # Merge scenes shorter than MIN_SCENE_DURATION into their neighbor
    merged = []
    for scene in scenes:
        duration = scene["end_time"] - scene["start_time"]
        if duration < MIN_SCENE_DURATION and merged:
            # Extend previous scene to absorb this one
            merged[-1]["end_time"] = scene["end_time"]
            merged[-1]["end_word_index"] = scene["end_word_index"]
        else:
            merged.append(scene)

    # Re-index
    for i, scene in enumerate(merged):
        scene["scene_index"] = i
        scene["transition"] = "crossfade" if i > 0 else "cut"

    return merged


# ═══════════════════════════════════════════════════════════════════════════
# FALLBACK: No-LLM scene generation using keyword extraction
# ═══════════════════════════════════════════════════════════════════════════

# Keyword → visual prompt mappings
_MOOD_KEYWORDS = {
    "angry": ["angry", "furious", "rage", "yelled", "screamed", "fight", "hit", "punch"],
    "sad": ["sad", "cried", "tears", "depressed", "lonely", "heartbroken", "grief", "loss"],
    "happy": ["happy", "laughed", "smiled", "joy", "excited", "celebrated", "love", "wedding"],
    "scared": ["scared", "terrified", "horror", "dark", "creepy", "nightmare", "panic", "afraid"],
    "tense": ["nervous", "anxiety", "confronted", "argument", "divorce", "caught", "secret", "lie"],
    "calm": ["peaceful", "quiet", "morning", "coffee", "relaxed", "sunday", "garden", "walk"],
}

_LOCATION_KEYWORDS = {
    "house": ["house", "home", "apartment", "room", "bedroom", "kitchen", "living room", "bathroom"],
    "car": ["car", "driving", "road", "highway", "parked", "traffic", "truck"],
    "office": ["office", "work", "desk", "meeting", "boss", "coworker", "cubicle"],
    "school": ["school", "class", "teacher", "student", "college", "university", "campus"],
    "hospital": ["hospital", "doctor", "nurse", "emergency", "surgery", "diagnosed"],
    "restaurant": ["restaurant", "dinner", "lunch", "cafe", "bar", "food", "eating"],
    "outdoor": ["park", "beach", "forest", "mountain", "lake", "street", "outside", "yard"],
}

_LOCATION_PROMPTS = {
    "house": "cozy suburban house interior, warm ambient lighting, lived-in feel",
    "car": "inside a car at night, dashboard lights, rain on windshield",
    "office": "modern office space, fluorescent lighting, cubicles and desks",
    "school": "school hallway with lockers, natural daylight through windows",
    "hospital": "hospital corridor, sterile white walls, soft overhead lighting",
    "restaurant": "restaurant interior, dim ambient lighting, candlelit tables",
    "outdoor": "quiet suburban street at golden hour, trees lining the sidewalk",
}

_MOOD_MODIFIERS = {
    "angry": "dramatic red-tinted lighting, stormy atmosphere",
    "sad": "melancholic blue tones, overcast sky, rain",
    "happy": "warm golden sunlight, bright and vibrant colors",
    "scared": "dark shadows, eerie fog, dim moonlight",
    "tense": "harsh contrast lighting, claustrophobic framing",
    "calm": "soft natural light, peaceful atmosphere, warm tones",
}


def generate_fallback_scenes(
    story_text: str,
    word_timings: Optional[List[Dict]],
    audio_duration: float,
    num_scenes: int = TARGET_SCENES,
) -> List[Dict]:
    """
    Fallback scene generation when Ollama is unavailable.
    Splits text evenly and uses keyword extraction for basic scene prompts.
    """
    words = story_text.split()
    total_words = len(words)
    words_per_scene = max(1, total_words // num_scenes)

    scenes = []
    for i in range(num_scenes):
        start_idx = i * words_per_scene
        end_idx = min((i + 1) * words_per_scene, total_words) if i < num_scenes - 1 else total_words

        if start_idx >= total_words:
            break

        segment_words = words[start_idx:end_idx]
        segment_text = " ".join(segment_words).lower()

        # Detect mood
        detected_mood = "calm"
        for mood, keywords in _MOOD_KEYWORDS.items():
            if any(kw in segment_text for kw in keywords):
                detected_mood = mood
                break

        # Detect location
        detected_location = "house"  # default
        for location, keywords in _LOCATION_KEYWORDS.items():
            if any(kw in segment_text for kw in keywords):
                detected_location = location
                break

        # Build image prompt
        base_prompt = _LOCATION_PROMPTS.get(detected_location, _LOCATION_PROMPTS["house"])
        mood_mod = _MOOD_MODIFIERS.get(detected_mood, "")
        image_prompt = f"{base_prompt}, {mood_mod}, cinematic lighting, photorealistic, 4k, detailed"

        # Get timestamps
        if word_timings and len(word_timings) > 0:
            clamped_start = min(start_idx, len(word_timings) - 1)
            clamped_end = min(end_idx - 1, len(word_timings) - 1)
            start_time = word_timings[clamped_start]["start"]
            last = word_timings[clamped_end]
            end_time = last["start"] + last["duration"]
        else:
            scene_dur = audio_duration / num_scenes
            start_time = i * scene_dur
            end_time = (i + 1) * scene_dur

        if i == num_scenes - 1 or end_idx >= total_words:
            end_time = audio_duration

        scenes.append({
            "scene_index": i,
            "summary": f"Scene {i + 1} of the story",
            "image_prompt": image_prompt,
            "start_time": start_time,
            "end_time": end_time,
            "start_word_index": start_idx,
            "end_word_index": end_idx - 1,
            "transition": "crossfade" if i > 0 else "cut",
            "mood": detected_mood,
        })

    return scenes
