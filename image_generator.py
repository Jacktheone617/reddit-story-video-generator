"""
AI Image Generation Module - SDXL Turbo for 6GB VRAM GPUs.

Generates scene background images from text prompts.
Uses SDXL Turbo with 4-step inference for fast generation (~2-3s per image).

VRAM Budget (RTX 4050 Laptop, 6GB):
  - SDXL Turbo FP16: ~3.3GB
  - 936x1664 generation (4 steps): ~1.5GB
  - VAE tiling decode: ~0.5GB
  - Total peak: ~5.3GB (fits in 6GB)
"""

import os
import gc
import json
import torch
from typing import List, Dict, Optional
from PIL import Image

from ai_config import (
    SDXL_MODEL_ID, SDXL_CACHE_DIR, SDXL_NUM_STEPS,
    SDXL_GUIDANCE_SCALE, SDXL_WIDTH, SDXL_HEIGHT,
    SDXL_NEGATIVE_PROMPT, GENERATED_SCENES_DIR,
)


class SceneImageGenerator:
    """
    Generates scene background images using SDXL Turbo.
    Manages GPU memory carefully for 6GB VRAM constraint.
    """

    def __init__(self, model_id: str = SDXL_MODEL_ID,
                 cache_dir: str = SDXL_CACHE_DIR,
                 output_dir: str = GENERATED_SCENES_DIR):
        self.model_id = model_id
        self.cache_dir = cache_dir
        self.output_dir = output_dir
        self.pipe = None
        self._using_cpu_offload = False

    def load_model(self) -> None:
        """Load SDXL Turbo pipeline into GPU memory with 6GB optimizations."""
        from diffusers import AutoPipelineForText2Image

        # Disable xet (HuggingFace's new transfer protocol) — causes very slow/failed downloads
        os.environ["HF_HUB_DISABLE_XET"] = "1"

        print(f"Loading SDXL Turbo from {self.model_id}...")

        # Clear any existing GPU memory first
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.pipe = AutoPipelineForText2Image.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16,
            variant="fp16",
            cache_dir=self.cache_dir,
        )

        # 6GB VRAM: use model CPU offload — swaps components to GPU one at a time
        # This avoids the 6.6GB peak that occurs when loading everything to GPU at once
        self.pipe.enable_model_cpu_offload()
        self.pipe.enable_attention_slicing(1)
        self.pipe.vae.enable_tiling()
        self._using_cpu_offload = True

        print(f"SDXL Turbo loaded with CPU offload. VRAM: {self._get_vram_usage()}")

    def _enable_cpu_offload(self) -> None:
        """Enable sequential CPU offload as OOM recovery. Slower but guaranteed to fit."""
        if self._using_cpu_offload:
            return
        print("Enabling sequential CPU offload (slower but saves VRAM)...")
        # Need to reload from scratch since .to("cuda") and cpu_offload conflict
        self.unload_model()
        from diffusers import AutoPipelineForText2Image

        self.pipe = AutoPipelineForText2Image.from_pretrained(
            self.model_id,
            torch_dtype=torch.float16,
            variant="fp16",
            cache_dir=self.cache_dir,
        )
        self.pipe.enable_sequential_cpu_offload()
        self.pipe.enable_attention_slicing(1)
        self.pipe.enable_vae_tiling()
        self._using_cpu_offload = True
        print("CPU offload enabled.")

    def unload_model(self) -> None:
        """Free GPU memory after generation is complete."""
        if self.pipe is not None:
            del self.pipe
            self.pipe = None
        self._using_cpu_offload = False
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        print("SDXL Turbo unloaded, VRAM freed.")

    def generate_scene_image(self, prompt: str, scene_index: int,
                              negative_prompt: str = SDXL_NEGATIVE_PROMPT,
                              seed: Optional[int] = None) -> str:
        """
        Generate a single scene image.

        Returns:
            Path to the saved image file.
        """
        if self.pipe is None:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        generator = None
        if seed is not None:
            generator = torch.Generator("cpu").manual_seed(seed)

        try:
            result = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=SDXL_NUM_STEPS,
                guidance_scale=SDXL_GUIDANCE_SCALE,
                width=SDXL_WIDTH,
                height=SDXL_HEIGHT,
                generator=generator,
            )
        except torch.cuda.OutOfMemoryError:
            print(f"OOM on scene {scene_index}, switching to CPU offload...")
            self._enable_cpu_offload()
            result = self.pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                num_inference_steps=SDXL_NUM_STEPS,
                guidance_scale=SDXL_GUIDANCE_SCALE,
                width=SDXL_WIDTH,
                height=SDXL_HEIGHT,
                generator=generator,
            )

        image = result.images[0]

        # Save image
        image_path = os.path.join(self.output_dir, f"scene_{scene_index:03d}.png")
        image.save(image_path, "PNG")
        print(f"  Generated scene {scene_index}: {image_path}")

        return image_path

    def generate_all_scenes(self, scenes: List[Dict], story_id: str) -> List[Dict]:
        """
        Generate images for all scenes in a story.
        Loads model, generates all images, unloads model.
        Adds 'image_path' key to each scene dict.

        Args:
            scenes: List of scene dicts from scene_extractor
            story_id: Reddit post ID for folder naming

        Returns:
            The same scenes list with 'image_path' added to each
        """
        # Set up output directory for this story
        story_dir = os.path.join(self.output_dir, story_id)
        os.makedirs(story_dir, exist_ok=True)
        self.output_dir = story_dir

        # Check for cached scenes
        cache_file = os.path.join(story_dir, "scenes.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached = json.load(f)
                # Verify all images still exist
                all_exist = all(
                    os.path.exists(s.get("image_path", ""))
                    for s in cached
                )
                if all_exist and len(cached) == len(scenes):
                    print(f"Using cached scene images for {story_id}")
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass  # Cache corrupted, regenerate

        print(f"Generating {len(scenes)} scene images for {story_id}...")

        try:
            self.load_model()

            for scene in scenes:
                try:
                    image_path = self.generate_scene_image(
                        prompt=scene["image_prompt"],
                        scene_index=scene["scene_index"],
                    )
                    scene["image_path"] = image_path
                except Exception as e:
                    print(f"  Failed to generate scene {scene['scene_index']}: {e}")
                    scene["image_path"] = None

        finally:
            self.unload_model()

        # Remove scenes with failed image generation
        successful_scenes = [s for s in scenes if s.get("image_path")]

        if not successful_scenes:
            print("All scene image generations failed!")
            return []

        # If some failed, redistribute timing to fill gaps
        if len(successful_scenes) < len(scenes):
            successful_scenes = _redistribute_timing(successful_scenes, scenes[-1]["end_time"])

        # Cache for re-renders
        with open(cache_file, "w") as f:
            json.dump(successful_scenes, f, indent=2)

        return successful_scenes

    @staticmethod
    def _get_vram_usage() -> str:
        """Report current VRAM usage."""
        if not torch.cuda.is_available():
            return "No CUDA GPU"
        allocated = torch.cuda.memory_allocated() / 1024**3
        reserved = torch.cuda.memory_reserved() / 1024**3
        return f"{allocated:.1f}GB allocated, {reserved:.1f}GB reserved"


def _redistribute_timing(scenes: List[Dict], total_duration: float) -> List[Dict]:
    """Adjust scene timing to fill gaps when some scenes failed to generate."""
    if not scenes:
        return scenes

    # Ensure first scene starts at 0
    scenes[0]["start_time"] = 0.0

    # Ensure last scene ends at total_duration
    scenes[-1]["end_time"] = total_duration

    # Fill gaps between scenes
    for i in range(len(scenes) - 1):
        next_start = scenes[i + 1]["start_time"]
        current_end = scenes[i]["end_time"]
        if next_start > current_end:
            # Extend current scene to fill the gap
            scenes[i]["end_time"] = next_start

    # Re-index
    for i, scene in enumerate(scenes):
        scene["scene_index"] = i

    return scenes
