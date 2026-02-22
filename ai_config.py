"""
AI Background Generation Configuration.

All tunable parameters for scene extraction, image generation,
and animation in one place. No API keys needed - everything runs locally.
"""

# === OLLAMA SCENE EXTRACTION ===
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:latest"
OLLAMA_TIMEOUT = 120  # seconds
TARGET_SCENES = 7
MIN_SCENE_DURATION = 3.0  # seconds - shorter feels jarring
MAX_SCENE_DURATION = 25.0  # seconds - longer gets boring

# === IMAGE GENERATION (SDXL TURBO) ===
SDXL_MODEL_ID = "stabilityai/sdxl-turbo"
SDXL_CACHE_DIR = "models/sdxl_turbo"
SDXL_NUM_STEPS = 4  # SDXL Turbo sweet spot
SDXL_GUIDANCE_SCALE = 0.0  # Turbo requires 0.0
SDXL_WIDTH = 936  # 1.3x of 720 for Ken Burns headroom
SDXL_HEIGHT = 1664  # 1.3x of 1280 for Ken Burns headroom
SDXL_NEGATIVE_PROMPT = (
    "blurry, low quality, text, watermark, logo, "
    "human face close-up, portrait, selfie, deformed, ugly, "
    "duplicate, morbid, mutilated, extra fingers"
)

# === KEN BURNS ANIMATION ===
CROSSFADE_DURATION = 0.5  # seconds between scenes

# === OUTPUT ===
GENERATED_SCENES_DIR = "generated_scenes"
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280
FPS = 24

# === FALLBACK BEHAVIOR ===
USE_GAMEPLAY_FALLBACK = True  # Fall back to gameplay if AI fails
GAMEPLAY_FOLDER = "gameplay_videos"
