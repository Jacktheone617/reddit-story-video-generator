# Fix Pillow compatibility issue with MoviePy
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

from moviepy import CompositeVideoClip, ColorClip
from header import create_reddit_header

# Create a dark background matching the video dimensions (720x1280)
VIDEO_WIDTH = 720
VIDEO_HEIGHT = 1280

bg = ColorClip(size=(VIDEO_WIDTH, VIDEO_HEIGHT), color=(30, 30, 30)).with_duration(1)

# Generate the header with a sample title
header_clips = create_reddit_header(
    title="AITA for telling my sister she can't bring her kids to my wedding after she demanded I change the venue?",
    author="u/BrokenStories",
    subreddit="r/AmItheAsshole",
    duration=1,
    logo_path="logo/Redit logo.png",
    video_width=VIDEO_WIDTH,
    video_height=VIDEO_HEIGHT
)

# Composite header onto background
all_clips = [bg] + header_clips
composite = CompositeVideoClip(all_clips)

# Save frame as image
composite.save_frame("header_preview.png", t=0)
composite.close()
bg.close()
for clip in header_clips:
    clip.close()

print("Saved header_preview.png")
